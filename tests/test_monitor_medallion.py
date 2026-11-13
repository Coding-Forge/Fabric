"""Synthetic medallion traces and publication guards; no live Fabric data."""

import base64
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from notebooks import monitor_medallion as md
from notebooks import monitor_medallion_runtime as runtime
from notebooks.build_monitor_notebooks import generated_notebooks
from notebooks.explore_gold_events import (
    gold_event_queries,
    open_gold_query_views,
    run_gold_event_queries,
)

TENANT = "10000000-0000-0000-0000-000000000001"
WORKSPACE = "20000000-0000-0000-0000-000000000001"
OTHER_WORKSPACE = "20000000-0000-0000-0000-000000000002"
ITEM = "30000000-0000-0000-0000-000000000001"
OTHER_ITEM = "30000000-0000-0000-0000-000000000002"
RUN = "40000000-0000-0000-0000-000000000001"
CHILD = "40000000-0000-0000-0000-000000000002"
ACTIVITY = "50000000-0000-0000-0000-000000000001"
TRACE = "60000000-0000-0000-0000-000000000001"


def observation(**values):
    return {
        "workspace_id": WORKSPACE,
        "item_id": ITEM,
        "observed_at_utc": "2026-01-01T10:01:00Z",
        "source_path": "synthetic/source.json",
        "source_sha256": "synthetic",
        "observation_id": "synthetic-observation",
        "coverage_status": "success",
        "module": "synthetic",
        "mode": "Scoped",
        "run_id": "collector-run",
        **values,
    }


def event(**values):
    return {
        "Id": "fixture-event",
        "WorkspaceId": WORKSPACE,
        "ItemId": ITEM,
        "CreationTime": "2026-01-01T10:00:00Z",
        "Operation": "RunPipeline",
        "ActivityId": TRACE,
        "RequestId": TRACE,
        "IsSuccess": None,
        "UserId": "fixture-user",
        "ClientIP": "192.0.2.10",
        **values,
    }


def silver(sources=None, events=None, *, tenant_id=TENANT, **settings):
    raw = [event()] if events is None else events
    return md.build_silver(
        sources or {},
        [
            {
                "path": "activity/2026/01/01/20260101_00001.json",
                "sha256": hashlib.sha256(json.dumps(raw).encode()).hexdigest(),
                "records": raw,
            }
        ],
        tenant_id=tenant_id,
        source_signature="synthetic",
        **settings,
    )


def source_fixture():
    return {
        "inventory": [
            observation(item_name="Later pipeline label", item_type="DataPipeline")
        ],
        "job_observations": [
            observation(job_id=RUN, root_activity_id=TRACE, status="Succeeded")
        ],
        "pipeline_activity_observations": [
            observation(
                pipeline_run_id=RUN,
                activity_run_id=ACTIVITY,
                activity_type="Copy",
                activity_name="Synthetic copy",
                status="Succeeded",
                rows_copied=42000,
                data_written=10485760,
            )
        ],
    }


class MedallionTests(unittest.TestCase):
    def test_tenant_discovery_uses_fabric_identity_and_preserves_scoped_keys(self):
        payload = (
            base64.urlsafe_b64encode(json.dumps({"tid": TENANT.upper()}).encode())
            .decode()
            .rstrip("=")
        )
        credentials = MagicMock()
        credentials.getToken.return_value = f"fixture.{payload}.fixture"
        with patch.dict(
            sys.modules, {"notebookutils": SimpleNamespace(credentials=credentials)}
        ):
            tenant = runtime.md_resolve_tenant()
        credentials.getToken.assert_called_once_with("pbi")
        self.assertEqual(tenant, TENANT)
        automatic = silver(source_fixture(), tenant_id=tenant)
        manual = silver(source_fixture())
        for dataset in ("audit_event", "event_execution_link", "pipeline_activity"):
            self.assertEqual(automatic[dataset], manual[dataset])

    def test_manual_tenant_override_and_opt_out_do_not_acquire_tokens(self):
        credentials = MagicMock()
        with patch.dict(
            sys.modules, {"notebookutils": SimpleNamespace(credentials=credentials)}
        ):
            self.assertEqual(runtime.md_resolve_tenant(TENANT), TENANT)
            self.assertEqual(
                runtime.md_resolve_tenant(TENANT, auto_discover=False), TENANT
            )
            with self.assertRaisesRegex(ValueError, "Set TENANT_ID"):
                runtime.md_resolve_tenant(auto_discover=False)
            with self.assertRaisesRegex(ValueError, "Manual TENANT_ID"):
                runtime.md_resolve_tenant("not-a-uuid")
            with self.assertRaisesRegex(ValueError, "must be boolean"):
                runtime.md_resolve_tenant(auto_discover="False")
        credentials.getToken.assert_not_called()

    def test_tenant_discovery_failure_is_safe_and_precedes_evidence_access(self):
        credentials = MagicMock()
        with patch.dict(
            sys.modules, {"notebookutils": SimpleNamespace(credentials=credentials)}
        ):
            for token in ("opaque-token", "fixture.invalid!.fixture"):
                credentials.getToken.return_value = token
                with self.assertRaisesRegex(
                    ValueError, "discovery unavailable"
                ) as error:
                    runtime.md_resolve_tenant()
                self.assertNotIn(token, str(error.exception))
            for claims in ({}, {"tid": "not-a-uuid"}, []):
                payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()
                credentials.getToken.return_value = f"fixture.{payload}.fixture"
                with self.assertRaisesRegex(ValueError, "discovery unavailable"):
                    runtime.md_resolve_tenant()
            credentials.getToken.side_effect = RuntimeError("private-token-detail")
            spark = MagicMock()
            with (
                patch.object(runtime, "MedallionReader") as reader,
                self.assertRaisesRegex(
                    ValueError, "AUTO_DISCOVER_TENANT=False"
                ) as error,
            ):
                runtime.run_silver(
                    spark, MagicMock(), lakehouse="lh_monitor", raw_root=""
                )
            self.assertNotIn("private-token-detail", str(error.exception))
            self.assertTrue(error.exception.__suppress_context__)
            reader.assert_not_called()
            spark.sql.assert_not_called()
        with (
            patch.dict(sys.modules, {"notebookutils": None}),
            self.assertRaisesRegex(ValueError, "discovery unavailable"),
        ):
            runtime.md_resolve_tenant()

    def test_exact_trace_is_scoped_deduplicated_and_does_not_invent_destinations(self):
        raw = event()
        tables = silver(source_fixture(), [raw, dict(reversed(list(raw.items())))])
        self.assertEqual(len(tables["audit_event"]), 1)
        self.assertEqual(len(tables["event_source"]), 1)
        self.assertEqual(len(tables["event_execution_link"]), 1)
        self.assertEqual(
            json.loads(tables["event_execution_link"][0]["matched_fields_json"]),
            ["activity_id", "request_id"],
        )
        self.assertIsNone(tables["actor_identity"][0]["reported_identity"])
        self.assertIsNone(tables["client_ip"][0]["reported_ip"])
        gold = md.build_gold(tables, source_signature="synthetic")
        case = gold["event_case"][0]
        self.assertEqual(case["linked_execution_count"], 1)
        self.assertEqual(case["traced_execution_count"], 1)
        self.assertIsNone(case["reported_event_success"])
        self.assertEqual(
            json.loads(case["artifact_labels_json"])[0]["label_timing"],
            "LATER_OBSERVED_HINT",
        )
        activity = gold["pipeline_activity_fact"][0]
        self.assertEqual(activity["rows_copied"], 42000)
        self.assertIsNone(activity["rows_read"])
        self.assertIsNone(activity["physical_destination"])
        self.assertTrue(
            any(
                row["relation_type"] == "EVIDENCE_GAP" and row["target_key"] is None
                for row in gold["event_trace_edge"]
            )
        )

    def test_conflicting_event_survives_as_quarantined_gold_case(self):
        tables = silver(source_fixture(), [event(), event(UserId="other-fixture-user")])
        self.assertEqual(tables["audit_event"][0]["validity"], "CONFLICT")
        self.assertEqual(tables["event_execution_link"], [])
        self.assertIsNone(tables["audit_event"][0]["actor_key"])
        self.assertEqual(
            tables["quarantine"][0]["reason"], "CONFLICTING_PROVIDER_EVENT"
        )
        self.assertEqual(
            md.build_gold(tables, source_signature="synthetic")["event_case"][0][
                "correlation_state"
            ],
            "CONFLICT",
        )

    def test_scope_mismatch_missing_scope_and_ambiguous_runs_are_not_promoted(self):
        for workspace, expected in (
            (OTHER_WORKSPACE, "SCOPE_MISMATCH"),
            (None, "UNRESOLVED_SCOPE"),
        ):
            with self.subTest(workspace=workspace):
                tables = silver(source_fixture(), [event(WorkspaceId=workspace)])
                self.assertEqual(tables["event_execution_link"], [])
                self.assertEqual(
                    tables["correlation_candidate"][0]["match_state"], expected
                )
                self.assertEqual(
                    len(
                        md.build_gold(tables, source_signature="synthetic")[
                            "event_case"
                        ]
                    ),
                    1,
                )
        sources = source_fixture()
        sources["job_observations"].append(
            observation(job_id=CHILD, root_activity_id=TRACE)
        )
        tables = silver(sources)
        self.assertEqual(tables["event_execution_link"], [])
        self.assertEqual(
            {row["match_state"] for row in tables["correlation_candidate"]},
            {"AMBIGUOUS"},
        )

    def test_latest_activity_metrics_do_not_sum_polls_and_failed_coverage_is_visible(
        self,
    ):
        sources = source_fixture()
        first = sources["pipeline_activity_observations"][0]
        sources["pipeline_activity_observations"].append(
            {
                **first,
                "observation_id": "later",
                "observed_at_utc": "2026-01-01T10:02:00Z",
                "rows_copied": 50000,
            }
        )
        sources["pipeline_activity_resources"] = [
            observation(
                pipeline_run_id=RUN,
                observed_at_utc="2026-01-01T10:03:00Z",
                coverage_status="failed",
                record_count=None,
            )
        ]
        tables = silver(sources)
        activity = tables["pipeline_activity"][0]
        self.assertEqual(activity["rows_copied"], 50000)
        self.assertEqual(activity["observation_count"], 2)
        self.assertEqual(activity["poll_state"], "LATEST_POLL_FAILED")

    def test_conflicting_latest_job_does_not_silently_choose_a_status(self):
        sources = source_fixture()
        sources["job_observations"].append(
            observation(
                job_id=RUN,
                root_activity_id=TRACE,
                status="Failed",
                source_path="synthetic/conflict.json",
            )
        )
        tables = silver(sources)
        self.assertEqual(tables["event_execution_link"], [])
        self.assertTrue(
            any(
                row["reason"] == "CONFLICTING_LATEST_EXECUTION"
                for row in tables["quarantine"]
            )
        )
        self.assertEqual(tables["execution_latest"][0]["status"], None)

    def test_multiple_references_and_events_do_not_multiply_run_activity_facts(self):
        tables = silver(
            source_fixture(),
            [
                event(DatasetId=OTHER_ITEM),
                event(Id="fixture-event-2", DatasetId=OTHER_ITEM),
            ],
        )
        gold = md.build_gold(tables, source_signature="synthetic")
        self.assertEqual(len(gold["event_case"]), 2)
        self.assertEqual(len(gold["execution_fact"]), 1)
        self.assertEqual(len(gold["pipeline_activity_fact"]), 1)
        self.assertEqual(gold["event_case"][0]["referenced_artifact_count"], 2)
        self.assertEqual(gold["pipeline_activity_fact"][0]["data_written"], 10485760)

    def test_child_run_uses_observed_scope_and_cycle_or_depth_limit_is_safe(self):
        sources = source_fixture()
        sources["job_observations"].append(
            observation(
                workspace_id=OTHER_WORKSPACE,
                item_id=OTHER_ITEM,
                job_id=CHILD,
                root_activity_id=None,
            )
        )
        sources["pipeline_activity_observations"][0]["child_pipeline_run_id"] = CHILD
        sources["pipeline_activity_observations"].append(
            observation(
                workspace_id=OTHER_WORKSPACE,
                item_id=OTHER_ITEM,
                pipeline_run_id=CHILD,
                activity_run_id="50000000-0000-0000-0000-000000000002",
                activity_type="InvokePipeline",
                child_pipeline_run_id=RUN,
            )
        )
        tables = silver(sources)
        child = next(
            row for row in tables["execution_latest"] if row["execution_id"] == CHILD
        )
        self.assertEqual(child["workspace_id"], OTHER_WORKSPACE)
        gold = md.build_gold(tables, source_signature="synthetic", max_trace_depth=1)
        self.assertEqual(gold["event_case"][0]["traced_execution_count"], 2)
        self.assertLess(len(gold["event_trace_edge"]), 20)
        third_run = "40000000-0000-0000-0000-000000000003"
        sources["job_observations"].append(observation(job_id=third_run))
        sources["pipeline_activity_observations"][1]["child_pipeline_run_id"] = (
            third_run
        )
        capped = md.build_gold(
            silver(sources), source_signature="synthetic", max_trace_depth=1
        )
        self.assertTrue(capped["event_case"][0]["trace_capped"])

    def test_sensitive_values_require_opt_in_and_location_tokens_are_removed(self):
        tables = silver(
            events=[
                event(
                    ObjectId="https://fixture-user:secret@example.invalid/Files/out?sig=secret#fragment"
                )
            ],
            include_sensitive=True,
        )
        self.assertEqual(
            tables["actor_identity"][0]["reported_identity"], "fixture-user"
        )
        self.assertEqual(
            tables["reported_location"][0]["reported_location"],
            "https://example.invalid/Files/out",
        )
        gold = md.build_gold(tables, source_signature="synthetic")
        self.assertNotIn("fixture-user", md.md_json(gold))
        self.assertNotIn("192.0.2.10", md.md_json(gold))

    def test_missing_sources_and_mixed_or_unready_builds_are_not_success(self):
        tables = silver({"job_observations": []})
        coverage = {row["dataset"]: row for row in tables["evidence_coverage"]}
        self.assertEqual(coverage["job_observations"]["availability"], "PRESENT")
        self.assertEqual(coverage["job_resources"]["availability"], "MISSING")
        broken = copy.deepcopy(tables)
        broken["audit_event"][0]["build_id"] = "another-build"
        with self.assertRaisesRegex(ValueError, "Mixed build"):
            md.build_gold(broken, source_signature="synthetic")
        tables["build"][0]["state"] = "building"
        with self.assertRaisesRegex(ValueError, "ready"):
            md.build_gold(tables, source_signature="synthetic")

    def test_unknown_observation_order_does_not_promote_historical_success(self):
        sources = source_fixture()
        sources["job_observations"].append(
            observation(
                job_id=RUN,
                root_activity_id=TRACE,
                status="Failed",
                observed_at_utc=None,
            )
        )
        tables = silver(sources)
        self.assertEqual(tables["event_execution_link"], [])
        self.assertTrue(
            any(
                row["reason"] == "CONFLICTING_LATEST_EXECUTION"
                for row in tables["quarantine"]
            )
        )
        self.assertEqual(
            md.md_poll_state([observation(observed_at_utc=None)], WORKSPACE, ITEM),
            "UNKNOWN_POLL_ORDER",
        )

    def test_trace_preserves_reference_roles_and_unknown_event_time(self):
        gold = md.build_gold(
            silver(source_fixture(), [event(CreationTime=None, ArtifactId=ITEM)]),
            source_signature="synthetic",
        )
        references = [
            row
            for row in gold["event_trace_edge"]
            if row["relation_type"] == "REPORTED_REFERENCE"
        ]
        self.assertEqual(len(references), 2)
        self.assertEqual(len({row["edge_key"] for row in references}), 2)
        self.assertEqual(
            json.loads(gold["event_case"][0]["artifact_labels_json"])[0][
                "label_timing"
            ],
            "EVENT_TIME_UNKNOWN_HINT",
        )

    def test_empty_malformed_or_changed_raw_scope_cannot_be_silently_published(self):
        with tempfile.TemporaryDirectory() as root:
            reader = runtime.MedallionReader(MagicMock(), "lh_monitor")
            documents, present = reader.activity_documents(root)
            self.assertFalse(present)
            self.assertEqual(documents, [])
            (Path(root) / "activity").mkdir()
            with self.assertRaisesRegex(ValueError, "availability changed"):
                reader.unchanged()

    def test_raw_content_change_and_byte_limit_fail_before_publication(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "activity/2026/01/01/20260101_00001.json"
            path.parent.mkdir(parents=True)
            path.write_text("[]")
            reader = runtime.MedallionReader(MagicMock(), "lh_monitor")
            reader.activity_documents(root)
            path.write_text("[{}]")
            with self.assertRaisesRegex(ValueError, "content changed"):
                reader.unchanged()
            with self.assertRaisesRegex(ValueError, "byte limit"):
                runtime.MedallionReader(MagicMock(), "lh_monitor").activity_documents(
                    root, max_file_bytes=1
                )
            path.write_text('"invalid payload"')
            with self.assertRaisesRegex(TypeError, "payload type"):
                runtime.MedallionReader(MagicMock(), "lh_monitor").activity_documents(
                    root
                )

    def test_publication_preflight_rejects_unowned_tables_before_any_write(self):
        spark, frame = MagicMock(), MagicMock()
        spark.catalog.tableExists.return_value = True
        with (
            patch.object(runtime, "md_frame", return_value=frame),
            patch.object(runtime, "md_properties", return_value={}),
            self.assertRaisesRegex(ValueError, "unowned"),
        ):
            runtime.md_publish(
                spark,
                silver(),
                md.SILVER_SCHEMAS,
                lakehouse="lh_monitor",
                layer="silver",
                write=True,
                unchanged=MagicMock(),
            )
        frame.write.format.assert_not_called()

    def test_preview_never_writes_and_source_failure_leaves_gate_building(self):
        spark, frame = MagicMock(), MagicMock()
        spark.catalog.tableExists.return_value = False
        frame.select.return_value.exceptAll.return_value.limit.return_value.count.return_value = 0
        spark.table.return_value.select.return_value.exceptAll.return_value.limit.return_value.count.return_value = 0
        with patch.object(runtime, "md_frame", return_value=frame):
            runtime.md_publish(
                spark,
                silver(),
                md.SILVER_SCHEMAS,
                lakehouse="lh_monitor",
                layer="silver",
                write=False,
                unchanged=MagicMock(),
            )
            frame.write.format.assert_not_called()
            unchanged = MagicMock(side_effect=[None, ValueError("changed source")])
            with self.assertRaisesRegex(ValueError, "changed source"):
                runtime.md_publish(
                    spark,
                    silver(),
                    md.SILVER_SCHEMAS,
                    lakehouse="lh_monitor",
                    layer="silver",
                    write=True,
                    unchanged=unchanged,
                )
            calls = frame.write.format.return_value.mode.return_value.saveAsTable.call_args_list
            self.assertEqual(
                sum(call.args[0].endswith(".`build`") for call in calls), 1
            )

    def test_medallion_notebooks_are_self_contained_and_preview_by_default(self):
        notebooks = generated_notebooks()
        for name in (
            "24_monitor_silver_events.ipynb",
            "25_monitor_gold_event_cases.ipynb",
        ):
            codes = [
                "".join(cell["source"])
                for cell in notebooks[name]["cells"]
                if cell["cell_type"] == "code"
            ]
            self.assertIn("WRITE_TABLES = False", codes[0])
            if name.startswith("24_"):
                self.assertIn("AUTO_DISCOVER_TENANT = True", codes[0])
                self.assertIn('TENANT_ID = ""', codes[0])
                self.assertIn("auto_discover_tenant=AUTO_DISCOVER_TENANT", codes[-1])
            self.assertTrue(
                notebooks[name]["cells"][1]["metadata"]["tags"] == ["parameters"]
            )
            namespace = {"__name__": "synthetic_notebook"}
            exec(compile(codes[1], name, "exec"), namespace)  # noqa: S102 - Trusted generated library, no Fabric execution.
            self.assertIn("build_silver", namespace)
            self.assertIn("build_gold", namespace)
            sample = namespace["build_silver"](
                {}, [], tenant_id=TENANT, source_signature="fixture"
            )
            self.assertEqual(sample["audit_event"], [])


class GoldEventQueryTests(unittest.TestCase):
    def gold_reader_fixture(self, *, state="ready", mixed=False, changing=False):
        frame, history, gate = MagicMock(), MagicMock(), MagicMock()
        frame.filter.return_value.limit.return_value.count.return_value = int(mixed)
        gate.collect.return_value = [
            {
                "state": state,
                "build_id": "gold-build",
                "source_build_id": "silver-build",
            }
        ]
        calls = {}

        def sql(query):
            if query.startswith("DESCRIBE HISTORY"):
                calls[query] = calls.get(query, 0) + 1
                history.first.return_value = {
                    "version": calls[query] if changing else 1
                }
                return history
            if "SELECT * FROM `lh_monitor`.`gold`.`build` " in query:
                return gate
            return frame

        spark = MagicMock()
        spark.sql.side_effect = sql
        return spark, frame

    def test_gold_view_setup_pins_and_validates_before_creating_session_views(self):
        spark, frame = self.gold_reader_fixture()
        with patch.dict(
            sys.modules,
            {
                "pyspark": SimpleNamespace(),
                "pyspark.sql": SimpleNamespace(functions=MagicMock()),
            },
        ):
            snapshot = open_gold_query_views(spark)
        self.assertEqual(snapshot["build_id"], "gold-build")
        self.assertEqual(len(snapshot["source_versions"]), 8)
        self.assertEqual(frame.createOrReplaceTempView.call_count, 7)
        selects = [
            call.args[0]
            for call in spark.sql.call_args_list
            if call.args[0].startswith("SELECT")
        ]
        self.assertTrue(all("VERSION AS OF 1" in query for query in selects))
        self.assertEqual(len(selects), 8)
        frame.write.format.assert_not_called()

    def test_gold_view_setup_rejects_unready_mixed_and_changing_builds(self):
        with patch.dict(
            sys.modules,
            {
                "pyspark": SimpleNamespace(),
                "pyspark.sql": SimpleNamespace(functions=MagicMock()),
            },
        ):
            for settings, message in (
                ({"state": "building"}, "not ready"),
                ({"mixed": True}, "Mixed or incomplete"),
                ({"changing": True}, "changed during setup"),
            ):
                spark, frame = self.gold_reader_fixture(**settings)
                with self.assertRaisesRegex(ValueError, message):
                    open_gold_query_views(spark)
                frame.createOrReplaceTempView.assert_not_called()

    def test_importable_gold_reader_preserves_parameters_and_runs_selected_query(self):
        notebook = generated_notebooks()["26_monitor_gold_investigation.ipynb"]
        codes = [
            "".join(cell["source"])
            for cell in notebook["cells"]
            if cell["cell_type"] == "code"
        ]
        namespace = {
            "__name__": "__main__",
            "spark": MagicMock(),
            "display": MagicMock(),
        }
        exec(compile(codes[0], "gold_reader_parameters", "exec"), namespace)  # noqa: S102 - Trusted generated cell.
        namespace.update(EVENTS_SQL="SELECT fixture", EXECUTE_QUERIES=False)
        exec(compile(codes[1], "gold_reader_library", "exec"), namespace)  # noqa: S102 - Trusted generated library.
        self.assertEqual(namespace["EVENTS_SQL"], "SELECT fixture")
        self.assertFalse(namespace["EXECUTE_QUERIES"])
        self.assertTrue(notebook["cells"][1]["metadata"]["tags"] == ["parameters"])
        namespace["open_gold_query_views"] = MagicMock(
            return_value={"build_id": "ready"}
        )
        selected = MagicMock()
        selected.columns = ["event_key"]
        selected.select.return_value.toLocalIterator.return_value = iter(
            [{"event_key": "a" * 64}]
        )
        namespace["spark"].sql.return_value = selected
        with patch("builtins.print"):
            for index, code in enumerate(codes[2:]):
                exec(compile(code, f"gold_reader_execution_{index}", "exec"), namespace)  # noqa: S102 - Mocked Spark, trusted generated cells.
        namespace["open_gold_query_views"].assert_called_once_with(
            namespace["spark"], lakehouse="lh_monitor"
        )
        namespace["spark"].sql.assert_called_once_with("SELECT fixture")
        namespace["display"].assert_called_once_with(selected)
        self.assertEqual(namespace["summary"]["events_processed"], 1)
        self.assertEqual(namespace["summary"]["queries_executed"], 0)

    def test_selected_keys_are_streamed_and_duplicate_events_run_once(self):
        events = MagicMock()
        events.columns = ["event_key", "operation"]
        first, second = "a" * 64, "b" * 64
        events.select.return_value.toLocalIterator.return_value = iter(
            [{"event_key": first}, {"event_key": first}, {"event_key": second}]
        )
        spark, display = MagicMock(), MagicMock()
        with patch("builtins.print"):
            summary = run_gold_event_queries(spark, display, events)
        events.select.assert_called_once_with("event_key")
        events.collect.assert_not_called()
        expected = [
            sql for key in (first, second) for _, sql in gold_event_queries(key)
        ]
        self.assertEqual([call.args[0] for call in spark.sql.call_args_list], expected)
        self.assertEqual(display.call_count, 6)
        self.assertEqual(
            summary,
            {"events_processed": 2, "queries_generated": 6, "queries_executed": 6},
        )

    def test_sql_only_mode_and_empty_selection_do_not_execute_investigations(self):
        events, spark, display = MagicMock(), MagicMock(), MagicMock()
        events.columns = ["event_key"]
        events.select.return_value.toLocalIterator.return_value = iter(
            [{"event_key": "a" * 64}]
        )
        with patch("builtins.print") as output:
            summary = run_gold_event_queries(
                spark, display, events, execute_queries=False
            )
        self.assertTrue(
            any("WHERE event_key =" in str(call) for call in output.call_args_list)
        )
        self.assertEqual(summary["queries_generated"], 3)
        self.assertEqual(summary["queries_executed"], 0)
        events.select.return_value.toLocalIterator.return_value = iter([])
        with patch("builtins.print"):
            empty = run_gold_event_queries(spark, display, events)
        self.assertEqual(empty["events_processed"], 0)
        spark.sql.assert_not_called()
        display.assert_not_called()

    def test_missing_or_unsafe_keys_are_rejected_before_queries_execute(self):
        events, spark, display = MagicMock(), MagicMock(), MagicMock()
        events.columns = ["operation"]
        with self.assertRaisesRegex(ValueError, "event_key column"):
            run_gold_event_queries(spark, display, events)
        events.columns = ["event_key"]
        for key in (None, "", "' OR 1=1 --", "g" * 64):
            events.select.return_value.toLocalIterator.return_value = iter(
                [{"event_key": key}]
            )
            with self.assertRaisesRegex(ValueError, "64 lowercase"):
                run_gold_event_queries(spark, display, events)
        spark.sql.assert_not_called()
        display.assert_not_called()


if __name__ == "__main__":
    unittest.main()
