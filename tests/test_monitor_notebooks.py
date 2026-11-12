"""Offline contract, immutable evidence and uploadable notebook regression tests."""

import ast
import copy
import json
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from env.modules import fabricconnections as connection_collector
from env.utility.lineage_edges import scan_snapshot
from env.utility.notebook_references import notebook_references
from notebooks import monitor_analytics as analytics
from notebooks import monitor_estate_analytics as estate
from notebooks import monitor_fabric_runtime as runtime
from notebooks import monitor_validation as validation
from notebooks import monitor_visualizations as visualizations
from notebooks.build_monitor_notebooks import ROOT, generated_notebooks
from tests.fabric_helpers import CollectorTestCase, inventory, item

WORKSPACE = "00000000-0000-0000-0000-000000000001"
ITEM = "00000000-0000-0000-0000-000000000002"
OTHER = "00000000-0000-0000-0000-000000000003"
PARENT = {"workspaceId": WORKSPACE, "itemId": ITEM, "type": "Notebook"}
SCOPED = "fabricitemaccesspermissions"
TENANT = SCOPED + "_tenant"


def doc(path, value):
    return analytics.document(path, json.dumps(value).encode())


def run(module, number, parent, values, *, execution=None, complete=True, success=True):
    folder = f"{module}/2026/01/01/{number:032x}"
    observed = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
        seconds=number * 10
    )
    resource = {
        "runId": f"{number:032x}",
        "observedAt": observed.isoformat(),
        "complete": success,
        "coverage": "Synthetic test scope",
        "parent": parent,
    }
    if success:
        resource["records"] = values
    else:
        resource["error"] = "Resource incomplete"
    name, endpoint = analytics._resource_name_endpoint(module, resource)
    resource["requestPath"] = endpoint
    manifest = {
        "runId": resource["runId"],
        "observedAt": (observed + timedelta(seconds=1)).isoformat(),
        "complete": complete,
        "finished": True,
        "coverage": resource["coverage"],
        "errors": [] if success else ["Resource incomplete"],
        "resources": [{"file": name, "parent": parent, "complete": success}],
        "execution": execution or {},
    }
    return [
        doc(folder + "/" + name, resource),
        doc(folder + "/manifest.json", manifest),
    ]


def permission_cycle(module=SCOPED, *, empty=False, failed=False, kind="Notebook"):
    parent = {**PARENT, "type": kind}
    inventory_parent = {"observationUnit": "inventoryPage", "inventoryComplete": True}
    tenant = module == TENANT
    if not tenant:
        inventory_parent["workspaceId"] = WORKSPACE
    execution = {
        "cycleFinished": False,
        "cycleHealthy": True,
        "cycleEvidence": [],
        "deferred": False,
        "attempts": 1,
    }
    if tenant:
        execution.update(
            scopeMode="tenant",
            phase="inventory",
            inventoryComplete=True,
            discoveredItems=1,
            nextItem=0,
            resourceOutcome="succeeded",
        )
    else:
        execution.update(nextTask=1, taskCount=2)
    first = run(
        module, 1, inventory_parent, [parent], execution=execution, complete=False
    )
    last_execution = {
        **execution,
        "cycleFinished": True,
        "cycleHealthy": not failed,
        "cycleEvidence": [first[1]["path"]],
    }
    if tenant:
        last_execution.update(
            phase="access",
            nextItem=1,
            resourceOutcome="failed" if failed else "succeeded",
        )
    else:
        last_execution["nextTask"] = 2
    access = [
        {
            "principal": {
                "id": "test-principal",
                "type": "User",
                "displayName": "Not exported",
            },
            "itemAccessDetails": {
                "type": kind,
                "permissions": ["Read"],
                "additionalPermissions": [],
            },
        }
    ]
    return first + run(
        module,
        2,
        parent,
        [] if empty else access,
        execution=last_execution,
        complete=not failed,
        success=not failed,
    )


class ObservationTests(unittest.TestCase):
    def test_unfinished_manifest_can_commit_without_colliding_with_health_history(self):
        complete = run("fabricitemjobhistory", 1, PARENT, [])
        initial = copy.deepcopy(complete[1]["value"])
        initial.update(finished=False, complete=False, resources=[])
        before = analytics.transform([doc(complete[1]["path"], initial)])
        after = analytics.transform(complete)
        old = next(
            r
            for r in before["collection_health"]
            if r["module"] == "fabricitemjobhistory"
        )
        new = next(
            r
            for r in after["collection_health"]
            if r["module"] == "fabricitemjobhistory"
        )
        self.assertNotEqual(old["observation_id"], new["observation_id"])
        self.assertEqual(old["coverage_status"], "unfinished")
        self.assertEqual(new["coverage_status"], "success")

    def test_unknown_permission_attempt_prevents_silent_successful_cycle_fallback(self):
        documents = permission_cycle(TENANT)
        path = f"{TENANT}/2026/01/01/{3:032x}/manifest.json"
        documents.append(doc(path, {"runId": f"{3:032x}"}))
        selected = analytics.selected_permission_cycle(
            analytics.transform(documents), "Tenant"
        )
        self.assertFalse(selected["chain_valid"])
        self.assertIsNone(selected["observed_at_utc"])

    def test_scoped_and_tenant_are_separate_and_successful_empty_is_explicit(self):
        output = analytics.transform(
            permission_cycle() + permission_cycle(TENANT, empty=True)
        )
        self.assertEqual(len(output["permission_grants"]), 1)
        self.assertEqual(output["permission_grants"][0]["mode"], "Scoped")
        tenant = analytics.selected_permission_cycle(output, "Tenant")
        self.assertTrue(tenant["chain_valid"])
        self.assertTrue(tenant["cycle_finished"])
        coverage = [
            r
            for r in output["permission_resources"]
            if r["mode"] == "Tenant" and r["observation_unit"] == "item_access"
        ]
        self.assertEqual(coverage[0]["record_count"], 0)
        self.assertEqual(coverage[0]["coverage_status"], "success")
        serialized = json.dumps(output["permission_grants"])
        self.assertNotIn("Not exported", serialized)
        self.assertNotIn("displayName", serialized)

    def test_failed_access_has_unknown_count_and_does_not_import_grants(self):
        output = analytics.transform(permission_cycle(TENANT, failed=True))
        selected = analytics.selected_permission_cycle(output, "Tenant")
        self.assertTrue(selected["chain_valid"])
        self.assertFalse(selected["cycle_healthy"])
        self.assertEqual(output["permission_grants"], [])
        failed = [
            r
            for r in output["permission_resources"]
            if r["coverage_status"] == "failed"
        ]
        self.assertIsNone(failed[0]["record_count"])

    def test_power_bi_nullable_metadata_is_valid_without_exporting_names(self):
        documents = permission_cycle(TENANT, kind="SemanticModel")
        value = copy.deepcopy(documents[2]["value"])
        value["records"][0]["itemAccessDetails"].update(
            type=None, additionalPermissions=None
        )
        documents[2] = doc(documents[2]["path"], value)
        output = analytics.transform(documents)
        self.assertEqual(len(output["permission_grants"]), 1)
        self.assertEqual(
            output["permission_grants"][0]["additional_permissions_json"], "null"
        )

    def test_broken_cyclic_cross_mode_and_completed_predecessor_chains_are_rejected(
        self,
    ):
        for mutation in (
            "missing",
            "cycle",
            "cross_mode",
            "cursor",
            "health",
            "complete",
        ):
            with self.subTest(mutation=mutation):
                documents = permission_cycle(TENANT)
                manifest = copy.deepcopy(documents[3]["value"])
                if mutation == "missing":
                    manifest["execution"]["cycleEvidence"] = ["missing/manifest.json"]
                elif mutation == "cycle":
                    manifest["execution"]["cycleEvidence"] = [documents[3]["path"]]
                elif mutation == "cross_mode":
                    manifest["execution"]["cycleEvidence"] = [
                        permission_cycle()[1]["path"]
                    ]
                    documents += permission_cycle()
                elif mutation == "cursor":
                    manifest["execution"]["nextItem"] = 0
                elif mutation == "health":
                    manifest["execution"]["cycleHealthy"] = False
                else:
                    prior = copy.deepcopy(documents[1]["value"])
                    prior["execution"]["cycleFinished"] = True
                    documents[1] = doc(documents[1]["path"], prior)
                documents[3] = doc(documents[3]["path"], manifest)
                output = analytics.transform(documents)
                self.assertEqual(
                    [r for r in output["permission_grants"] if r["mode"] == "Tenant"],
                    [],
                )
                self.assertFalse(
                    analytics.selected_permission_cycle(output, "Tenant")["chain_valid"]
                )

    def test_inventory_order_not_merely_cursor_is_enforced(self):
        documents = permission_cycle(TENANT)
        parent = {**PARENT, "itemId": OTHER}
        resource = copy.deepcopy(documents[2]["value"])
        resource["parent"] = parent
        name, resource["requestPath"] = analytics._resource_name_endpoint(
            TENANT, resource
        )
        documents[2] = doc(str(Path(documents[2]["path"]).parent / name), resource)
        manifest = copy.deepcopy(documents[3]["value"])
        manifest["resources"][0].update(parent=parent, file=name)
        documents[3] = doc(documents[3]["path"], manifest)
        output = analytics.transform(documents)
        self.assertEqual(output["permission_grants"], [])

    def test_empty_tenant_discovery_is_success_but_not_missing_evidence(self):
        execution = {
            "scopeMode": "tenant",
            "phase": "inventory",
            "inventoryComplete": True,
            "discoveredItems": 0,
            "nextItem": 0,
            "cycleFinished": True,
            "cycleHealthy": True,
            "cycleEvidence": [],
            "deferred": False,
            "attempts": 1,
            "resourceOutcome": "succeeded",
        }
        documents = run(
            TENANT,
            1,
            {"observationUnit": "inventoryPage", "inventoryComplete": True},
            [],
            execution=execution,
        )
        selected = analytics.selected_permission_cycle(
            analytics.transform(documents), "Tenant"
        )
        self.assertTrue(selected["chain_valid"])
        self.assertEqual(selected["selected_items"], 0)
        self.assertIsNone(
            analytics.selected_permission_cycle(analytics.transform([]), "Tenant")
        )

    def test_duplicate_grants_and_reruns_have_stable_keys_and_detect_source_changes(
        self,
    ):
        documents = permission_cycle()
        resource = copy.deepcopy(documents[2]["value"])
        resource["records"] *= 2
        documents[2] = doc(documents[2]["path"], resource)
        first = analytics.transform(documents)
        self.assertEqual(first, analytics.transform(reversed(documents)))
        self.assertEqual(len(first["permission_grants"]), 1)
        resource["records"][0]["itemAccessDetails"]["permissions"] = ["Write"]
        changed = analytics.transform(
            documents[:2] + [doc(documents[2]["path"], resource), documents[3]]
        )
        previous = next(
            r
            for r in first["permission_resources"]
            if r["observation_unit"] == "item_access"
        )
        same = next(
            r
            for r in changed["permission_resources"]
            if r["observation_id"] == previous["observation_id"]
        )
        self.assertNotEqual(previous["record_sha256"], same["record_sha256"])

    def test_unattempted_deferral_preserves_cursor_and_health(self):
        documents = permission_cycle(TENANT)
        resource = copy.deepcopy(documents[2]["value"])
        resource.update(complete=False, error="Deferred")
        del resource["records"]
        documents[2] = doc(documents[2]["path"], resource)
        manifest = copy.deepcopy(documents[3]["value"])
        manifest.update(complete=False)
        manifest["resources"][0]["complete"] = False
        manifest["execution"].update(
            nextItem=0,
            cycleFinished=False,
            attempts=0,
            deferred=True,
            resourceOutcome="deferred",
        )
        documents[3] = doc(documents[3]["path"], manifest)
        output = analytics.transform(documents)
        selected = analytics.selected_permission_cycle(output, "Tenant")
        self.assertTrue(selected["chain_valid"])
        self.assertTrue(selected["cycle_healthy"])
        self.assertFalse(selected["cycle_finished"])
        self.assertEqual(output["permission_grants"], [])

    def test_new_cycle_selection_does_not_union_old_grants(self):
        old = permission_cycle(TENANT)
        newer = permission_cycle(TENANT, empty=True)
        mapping = {
            f"{1:032x}": f"{11:032x}",
            f"{2:032x}": f"{12:032x}",
            "00:00:10": "00:02:10",
            "00:00:11": "00:02:11",
            "00:00:20": "00:02:20",
            "00:00:21": "00:02:21",
        }
        encoded = json.dumps(newer)
        for source, destination in mapping.items():
            encoded = encoded.replace(source, destination)
        newer = [doc(entry["path"], entry["value"]) for entry in json.loads(encoded)]
        output = analytics.transform(old + newer)
        selected = analytics.selected_permission_cycle(output, "Tenant")
        self.assertEqual(selected["cycle_id"], f"{11:032x}")
        self.assertEqual(
            [
                r
                for r in output["permission_grants"]
                if r["cycle_id"] == selected["cycle_id"]
            ],
            [],
        )
        self.assertEqual(len(output["permission_grants"]), 1)

    def test_job_empty_failed_and_latest_status_history_remain_distinct(self):
        job = {
            "id": "job-1",
            "itemId": ITEM,
            "jobType": "RunNotebook",
            "invokeType": "Manual",
            "status": "InProgress",
            "startTimeUtc": "2026-01-01T00:00:00Z",
        }
        first = run("fabricitemjobhistory", 1, PARENT, [job])
        job = {**job, "status": "Completed", "endTimeUtc": "2026-01-01T00:00:30Z"}
        documents = first + run("fabricitemjobhistory", 4, PARENT, [job])
        documents += run("fabricitemjobhistory", 5, PARENT, [])
        documents += run(
            "fabricitemjobhistory", 6, PARENT, None, success=False, complete=False
        )
        output = analytics.transform(documents)
        self.assertEqual(len(output["job_observations"]), 2)
        current = analytics.latest(
            output["job_observations"], ["workspace_id", "item_id", "job_id"]
        )
        self.assertEqual(current[0]["status"], "Completed")
        self.assertEqual(current[0]["duration_seconds"], 30.0)
        counts = {
            r["coverage_status"]: r["record_count"]
            for r in output["job_resources"]
            if r["run_id"] in {f"{5:032x}", f"{6:032x}"}
        }
        self.assertEqual(counts, {"success": 0, "failed": None})

    def test_invalid_missing_unfinished_and_clock_inverted_runs_do_not_publish_jobs(
        self,
    ):
        base = run("fabricitemjobhistory", 1, PARENT, [])
        cases = [
            base[:1],
            [base[0], doc(base[1]["path"], [])],
            [base[0], analytics.document(base[1]["path"], b"{")],
        ]
        manifest = copy.deepcopy(base[1]["value"])
        manifest.update(finished=False, complete=False, resources=[])
        cases.append([base[0], doc(base[1]["path"], manifest)])
        manifest = copy.deepcopy(base[1]["value"])
        manifest["observedAt"] = "2026-01-01T00:00:00Z"
        cases.append([base[0], doc(base[1]["path"], manifest)])
        for documents in cases:
            with self.subTest(documents=documents):
                output = analytics.transform(documents)
                self.assertEqual(output["job_resources"], [])
                self.assertEqual(output["job_observations"], [])
                self.assertTrue(
                    any(
                        r["coverage_status"] in {"invalid", "unfinished"}
                        for r in output["collection_health"]
                    )
                )

    def test_unlisted_resource_and_endpoint_mismatch_are_not_admitted(self):
        for mutation in ("extra", "endpoint"):
            documents = run("fabricitemjobhistory", 1, PARENT, [])
            if mutation == "extra":
                documents.append(
                    doc(str(Path(documents[0]["path"]).parent / "other.json"), {})
                )
            else:
                resource = {**documents[0]["value"], "requestPath": "wrong"}
                documents[0] = doc(documents[0]["path"], resource)
            self.assertEqual(analytics.transform(documents)["job_resources"], [])

    def test_scanner_zero_edges_keep_item_inventory_and_external_ids(self):
        scan = scan_snapshot(
            {
                "workspaces": [
                    {
                        "id": WORKSPACE,
                        "reports": [
                            {"id": ITEM, "datasetId": OTHER},
                            {"id": WORKSPACE},
                        ],
                    }
                ]
            },
            "scan-1",
            [WORKSPACE],
            "2026-01-01T00:00:00Z",
        )
        path = "lineage_edges/2026/01/01/scan-1.lineage_edges.json"
        output = analytics.transform([doc(path, scan)])
        self.assertEqual(len(output["inventory"]), 2)
        resources = {r["item_id"]: r for r in output["lineage_resources"]}
        self.assertEqual(resources[WORKSPACE]["record_count"], 0)
        edge = output["lineage_edges"][0]
        self.assertEqual(edge["related_item_id"], OTHER)
        self.assertIsNone(edge["related_workspace_id"])
        self.assertFalse(edge["runtime_verified"])

    def test_raw_catalog_is_unverified_and_does_not_invent_observation_time(self):
        source = doc(
            "catalog/scans/2026/01/01/20260101_00000.scanResults.fullscan.json",
            {
                "workspaces": [
                    {"id": WORKSPACE, "reports": [{"id": ITEM, "datasetId": OTHER}]}
                ]
            },
        )
        output = analytics.transform([source], scanner_extractor=scan_snapshot)
        self.assertEqual(len(output["lineage_edges"]), 1)
        edge = output["lineage_edges"][0]
        self.assertEqual(edge["coverage_status"], "legacy_unverified")
        self.assertIsNone(edge["observed_at_utc"])
        self.assertEqual(edge["source_path"], source["path"])

    def test_static_references_export_no_definition_or_failure_payload(self):
        refs = {
            "schemaVersion": 1,
            "evidence": "static_inference",
            "runtimeVerified": False,
            "references": [
                {
                    "operation": "read",
                    "kind": "table",
                    "reference": "dbo.input",
                    "resolution": "unresolved",
                }
            ],
            "diagnostics": [{"cell": 1, "reason": "dynamic_or_missing_target"}],
        }
        values = [
            {
                "notebookReferences": refs,
                "decodedParts": {
                    "secret": "never-export-this",
                    "notebook-content.ipynb": {
                        "cells": [],
                        "metadata": {
                            "dependencies": {
                                "lakehouse": {
                                    "default_lakehouse": OTHER,
                                    "default_lakehouse_workspace_id": WORKSPACE,
                                    "default_lakehouse_name": "never-export-this",
                                }
                            }
                        },
                    },
                },
            }
        ]
        output = analytics.transform(run("fabricitemdefinitions", 1, PARENT, values))
        self.assertEqual(
            output["lineage_edges"][0]["evidence_type"], "static_inference"
        )
        self.assertEqual(len(output["lineage_diagnostics"]), 1)
        self.assertNotIn("never-export-this", json.dumps(output))
        configured = next(
            edge
            for edge in output["lineage_edges"]
            if edge["evidence_type"] == "configuration_metadata"
        )
        self.assertEqual(configured["related_item_id"], OTHER)
        self.assertEqual(configured["related_workspace_id"], WORKSPACE)
        self.assertEqual(configured["relation_type"], "default_lakehouse")
        self.assertEqual(configured["direction"], "association")
        self.assertEqual(configured["resolution"], "configured_id")
        self.assertFalse(configured["runtime_verified"])

    def test_notebook_configuration_distinguishes_empty_missing_and_failed_coverage(
        self,
    ):
        raw = {"cells": []}
        record = {"notebookReferences": notebook_references(raw)}
        for kind, expected, count in (
            ("empty", "success", 0),
            ("missing", "missing", None),
            ("failed", "failed", None),
        ):
            with self.subTest(kind=kind):
                value = copy.deepcopy(record)
                if kind != "missing":
                    value["decodedParts"] = {"notebook-content.ipynb": raw}
                documents = run(
                    "fabricitemdefinitions",
                    1,
                    PARENT,
                    [value],
                    success=kind != "failed",
                    complete=kind != "failed",
                )
                output = analytics.transform(documents)
                coverage = next(
                    row
                    for row in output["lineage_resources"]
                    if row["evidence_type"] == "configuration_metadata"
                )
                self.assertEqual(coverage["coverage_status"], expected)
                self.assertEqual(coverage["record_count"], count)
                self.assertEqual(output["lineage_edges"], [])
                self.assertEqual(output, analytics.transform(documents))
                manifest = copy.deepcopy(documents[1]["value"])
                manifest["finished"] = False
                unfinished = [documents[0], doc(documents[1]["path"], manifest)]
                self.assertEqual(
                    analytics.transform(unfinished)["lineage_resources"], []
                )

    def test_invalid_configuration_does_not_discard_independent_static_references(self):
        raw = {
            "cells": [{"cell_type": "code", "source": 'spark.table("db.input")'}],
            "metadata": {
                "dependencies": {
                    "lakehouse": {"default_lakehouse": "SYNTHETIC_PRIVATE_INVALID_ID"}
                }
            },
        }
        documents = run(
            "fabricitemdefinitions",
            1,
            PARENT,
            [
                {
                    "notebookReferences": notebook_references(raw),
                    "decodedParts": {"notebook-content.ipynb": raw},
                }
            ],
        )
        output = analytics.transform(documents)
        self.assertEqual(
            [edge["evidence_type"] for edge in output["lineage_edges"]],
            ["static_inference"],
        )
        coverage = next(
            row
            for row in output["lineage_resources"]
            if row["evidence_type"] == "configuration_metadata"
        )
        self.assertEqual(coverage["coverage_status"], "invalid")
        self.assertIsNone(coverage["record_count"])
        self.assertEqual(
            output["lineage_diagnostics"][0]["reason"],
            "invalid_configured_identifier",
        )
        self.assertNotIn("SYNTHETIC_PRIVATE", json.dumps(output))

    def test_legacy_inventory_does_not_claim_successful_snapshot(self):
        path = "items/2026/01/01/fabricitems_00001.json"
        output = analytics.transform(
            [doc(path, [{"id": ITEM, "workspaceId": WORKSPACE, "type": "Notebook"}])]
        )
        self.assertEqual(output["inventory"][0]["coverage_status"], "legacy_unverified")
        self.assertIsNone(output["inventory"][0]["observed_at_utc"])
        health = next(
            r for r in output["collection_health"] if r["source_path"] == path
        )
        self.assertIsNone(health["complete"])

    def test_path_escape_duplicate_source_and_nonfinite_json_are_rejected(self):
        with self.assertRaises(ValueError):
            analytics.document("../outside.json", b"{}")
        value = doc("items/2026/01/01/a.json", [])
        with self.assertRaises(ValueError):
            analytics.transform([value, value])
        self.assertEqual(
            analytics.document("a.json", b'{"value":NaN}')["issue"], "malformed_json"
        )

    def test_raw_reader_is_bounded_and_never_touches_control_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "monitor"
            (root / "items").mkdir(parents=True)
            data = root / "items/data.json"
            data.write_text("[]")
            control = root / "items/request_gate.json"
            control.write_text("Do not read or mutate this ledger")
            with patch.object(analytics, "LAKEHOUSE_FILES", str(base)):
                loaded = analytics.load_documents(str(root))
                self.assertEqual(
                    [entry["path"] for entry in loaded], ["items/data.json"]
                )
                with self.assertRaises(ValueError):
                    analytics.load_documents(str(root), max_bytes=1)
                self.assertEqual(data.read_text(), "[]")
                self.assertEqual(
                    control.read_text(), "Do not read or mutate this ledger"
                )
        with self.assertRaises(ValueError):
            analytics.load_documents("/tmp/not-a-lakehouse")


class RelationshipVisualizationTests(unittest.TestCase):
    def test_configured_associations_are_not_drawn_as_dataflow_arrows(self):
        entries = [
            {
                "item_id": ITEM,
                "item_type": "Notebook",
                "related_item_id": OTHER,
                "related_type": "Lakehouse",
                "reference": OTHER,
                "direction": "association",
                "evidence_type": "configuration_metadata",
            },
            {
                "item_id": ITEM,
                "item_type": "Notebook",
                "related_item_id": None,
                "related_type": "table",
                "reference": "db.input",
                "direction": "upstream",
                "evidence_type": "static_inference",
            },
            {
                "item_id": ITEM,
                "item_type": "Lakehouse",
                "related_item_id": OTHER,
                "related_type": "FabricItem",
                "reference": OTHER,
                "direction": "association",
                "evidence_type": "shortcut_configuration",
            },
        ]
        frame, pyplot, axis = MagicMock(), MagicMock(), MagicMock()
        frame.orderBy.return_value.limit.return_value.collect.return_value = entries
        pyplot.subplots.return_value = (None, axis)
        with patch.dict(
            "sys.modules",
            {
                "matplotlib": SimpleNamespace(pyplot=pyplot),
                "matplotlib.pyplot": pyplot,
                "matplotlib.lines": SimpleNamespace(Line2D=MagicMock()),
            },
        ):
            visualizations.graph_lineage(frame, 10)
        configured, static, shortcut = [
            call.kwargs["arrowprops"] for call in axis.annotate.call_args_list
        ]
        self.assertEqual(configured["arrowstyle"], "-")
        self.assertEqual(configured["linestyle"], "--")
        self.assertEqual(configured["color"], "tab:green")
        self.assertEqual(static["arrowstyle"], "->")
        self.assertEqual(static["color"], "tab:orange")
        self.assertEqual(shortcut, configured)


class PersistenceTests(unittest.TestCase):
    def test_hash_or_source_mutation_aborts_before_creating_other_tables(self):
        for guard_counts in ([1], [0, 1]):
            with self.subTest(guard_counts=guard_counts):
                spark = MagicMock()
                spark.catalog.tableExists.side_effect = [False, True]
                spark.sql.return_value.collect.return_value = [
                    {"key": "monitor.contract", "value": "1"},
                    {"key": "monitor.dataset", "value": "job_resources"},
                ]
                frame, existing = MagicMock(), MagicMock()
                frame.schema.fields = existing.schema.fields = []
                existing.alias.return_value = existing
                existing.join.return_value.filter.return_value.limit.return_value.count.side_effect = guard_counts
                delta = MagicMock()
                delta.forName.return_value.toDF.return_value = existing
                modules = {
                    "delta": SimpleNamespace(),
                    "delta.tables": SimpleNamespace(DeltaTable=delta),
                    "pyspark": SimpleNamespace(),
                    "pyspark.sql": SimpleNamespace(functions=MagicMock()),
                }
                with (
                    patch.dict("sys.modules", modules),
                    patch.object(runtime, "to_frame", return_value=frame),
                    self.assertRaises(ValueError),
                ):
                    runtime.publish(
                        spark,
                        analytics.transform([]),
                        ["inventory", "job_resources"],
                        "monitor_",
                        write=True,
                    )
                self.assertTrue(
                    all(
                        call.args[0].startswith("SHOW ")
                        for call in spark.sql.call_args_list
                    )
                )

    def test_preview_has_no_sql_writes_and_foreign_table_aborts_all_writes(self):
        spark = MagicMock()
        spark.catalog.tableExists.return_value = False
        modules = {
            "delta": SimpleNamespace(),
            "delta.tables": SimpleNamespace(DeltaTable=MagicMock()),
            "pyspark": SimpleNamespace(),
            "pyspark.sql": SimpleNamespace(functions=MagicMock()),
        }
        output = analytics.transform([])
        with (
            patch.dict("sys.modules", modules),
            patch.object(runtime, "to_frame", return_value=MagicMock()),
        ):
            runtime.publish(spark, output, ["inventory"], "monitor_", write=False)
            spark.sql.assert_not_called()
            spark.catalog.tableExists.side_effect = [False, True]
            spark.sql.return_value.collect.return_value = [
                {"key": "monitor.contract", "value": "foreign"}
            ]
            with self.assertRaisesRegex(ValueError, "not owned"):
                runtime.publish(
                    spark,
                    output,
                    ["inventory", "job_resources"],
                    "monitor_",
                    write=True,
                )
            self.assertTrue(
                all(
                    call.args[0].startswith("SHOW ")
                    for call in spark.sql.call_args_list
                )
            )

    def test_unsafe_table_prefix_cannot_become_sql(self):
        for prefix in ("raw_", "monitor_;DROP TABLE x;", "monitor_/../"):
            with self.assertRaises(ValueError):
                runtime.table_name(prefix, "inventory")


class CollectorCompatibilityTests(CollectorTestCase):
    async def test_real_paginated_scoped_and_tenant_outputs_preserve_failed_coverage(
        self,
    ):
        for mode, module in (("scoped", SCOPED), ("tenant", TENANT)):
            with (
                self.subTest(mode=mode),
                patch.dict(
                    "os.environ",
                    {
                        "FABRIC_ITEM_ACCESS_MODE": mode,
                        "FABRIC_ITEM_ACCESS_SCOPE": json.dumps([item(10), item(11)]),
                    },
                ),
            ):
                self.files.clear()
                grant = {
                    "principal": {"id": "test-principal", "type": "User"},
                    "itemAccessDetails": {"type": "Notebook", "permissions": ["Read"]},
                }
                context = self.context(
                    inventory(item(10), token="next"),
                    inventory(item(11)),
                    {"accessDetails": [grant]},
                    {"ERROR": "Denied", "status": 403},
                )
                self.assertFalse(await self.permissions(context))
                documents = [
                    doc(path, value)
                    for path, value in self.files.items()
                    if path.startswith(module + "/")
                    and Path(path).name
                    not in {
                        "request_gate.json",
                        "progress.json",
                        "tenant_progress.json",
                    }
                ]
                output = analytics.transform(documents)
                self.assertEqual(len(output["permission_grants"]), 1)
                selected = analytics.selected_permission_cycle(
                    output, "Scoped" if mode == "scoped" else "Tenant"
                )
                self.assertTrue(selected["chain_valid"])
                self.assertTrue(selected["cycle_finished"])
                self.assertFalse(selected["cycle_healthy"])
                self.assertEqual(len(output["permission_resources"]), 4)

    async def test_real_connection_collector_outputs_match_domain_contract(self):
        context = self.context(
            {
                "value": [
                    {
                        "id": "connection-1",
                        "displayName": None,
                        "connectivityType": "ShareableCloud",
                        "connectionDetails": {"type": "SQL"},
                    }
                ],
                "continuationToken": "next",
            },
            {"value": []},
        )
        self.assertTrue(await connection_collector.main(context))
        documents = [
            doc(path, value)
            for path, value in self.files.items()
            if path.startswith("fabricconnections/")
            and Path(path).name != "request_gate.json"
        ]
        output = analytics.transform(
            documents,
            scanner_extractor=scan_snapshot,
            estate_extractor=estate.transform_estate,
        )
        self.assertEqual(len(output["connection_observations"]), 1)
        self.assertIsNone(output["connection_observations"][0]["connection_name"])
        self.assertEqual(output["estate_coverage"][0]["coverage_status"], "success")


class EstateNotebookTests(unittest.TestCase):
    def transform(self, documents):
        return analytics.transform(
            documents,
            scanner_extractor=scan_snapshot,
            estate_extractor=estate.transform_estate,
        )

    def connection_run(self, entries, *, finished=True, failed=False):
        folder = f"fabricconnections/2026/11/05/{1:032x}"
        resource = {
            "runId": f"{1:032x}",
            "observedAt": "2026-11-05T00:00:00Z",
            "complete": not failed,
            "parent": {},
            "requestPath": "connections",
        }
        resource.update({"error": "Denied"} if failed else {"records": entries})
        manifest = {
            "runId": resource["runId"],
            "observedAt": "2026-11-05T00:00:01Z",
            "finished": finished,
            "complete": finished and not failed,
            "errors": ["Denied"] if failed else [],
            "resources": [
                {"file": "connections.json", "parent": {}, "complete": not failed}
            ]
            if finished
            else [],
        }
        return [
            doc(folder + "/manifest.json", manifest),
            *([doc(folder + "/connections.json", resource)] if finished else []),
        ]

    def test_activity_events_keep_actual_utc_time_and_exclude_actor_payload(self):
        events = [
            {
                "Id": "event-1",
                "CreationTime": "2026-11-05T00:15:00",
                "Operation": "ViewReport",
                "Workload": "PowerBI",
                "UserId": "fake-user@example.test",
                "UserType": 0,
                "IsSuccess": True,
                "WorkspaceId": WORKSPACE,
                "ReportId": ITEM,
                "ClientIP": "DO_NOT_KEEP_IP",
                "Payload": "DO_NOT_KEEP_PAYLOAD",
            }
        ]
        original = doc("activity/2026/11/05/20261105_00001.json", events)
        result = self.transform([original])
        event = result["activity_events"][0]
        self.assertEqual(event["event_time_utc"], "2026-11-05T00:15:00.000000Z")
        self.assertIsNone(event["observed_at_utc"])
        self.assertEqual(event["coverage_status"], "legacy_unverified")
        self.assertEqual(len(event["actor_key"]), 64)
        self.assertTrue(event["is_success"])
        serialized = json.dumps(result)
        for excluded in (
            "fake-user@example.test",
            "DO_NOT_KEEP_IP",
            "DO_NOT_KEEP_PAYLOAD",
        ):
            self.assertNotIn(excluded, serialized)
        changed = copy.deepcopy(events)
        changed[0]["Operation"] = "ExportReport"
        newer = self.transform([doc(original["path"], changed)])
        self.assertNotEqual(
            event["observation_id"], newer["activity_events"][0]["observation_id"]
        )

    def test_schema_distinguishes_not_returned_from_empty_and_omits_expressions(self):
        model = {
            "id": "model-returned",
            "name": "Model",
            "tables": [
                {
                    "name": "Sales",
                    "columns": [{"name": "Amount", "dataType": "Decimal"}],
                    "measures": [{"name": "Total", "expression": "DO_NOT_KEEP_DAX"}],
                }
            ],
            "relationships": [
                {
                    "fromTable": "Sales",
                    "fromColumn": "DateId",
                    "toTable": "Calendar",
                    "toColumn": "Id",
                    "isActive": True,
                }
            ],
        }
        raw = {
            "workspaces": [
                {
                    "id": WORKSPACE,
                    "name": "Workspace",
                    "datasets": [
                        model,
                        {"id": "model-missing"},
                        {"id": "model-empty", "tables": []},
                        {"id": "model-null", "tables": None},
                    ],
                    "reports": [{"id": ITEM, "name": "Report"}],
                }
            ]
        }
        result = self.transform(
            [doc("catalog/scans/2026/11/05/20261105_00001.scanResults.json", raw)]
        )
        models = {entry["item_id"]: entry for entry in result["catalog_models"]}
        self.assertIsNone(models["model-missing"]["table_count"])
        self.assertEqual(models["model-missing"]["schema_coverage"], "not_returned")
        self.assertEqual(models["model-empty"]["table_count"], 0)
        self.assertIsNone(models["model-null"]["table_count"])
        self.assertEqual(models["model-null"]["schema_coverage"], "not_returned")
        self.assertEqual(models["model-returned"]["table_count"], 1)
        self.assertEqual(result["model_columns"][0]["column_name"], "Amount")
        self.assertTrue(result["model_measures"][0]["expression_returned"])
        self.assertEqual(len(result["model_relationships"]), 1)
        self.assertNotIn("DO_NOT_KEEP_DAX", json.dumps(result))

    def test_legacy_schema_coverage_does_not_trust_unverified_timestamps(self):
        raw = {
            "workspaces": [],
            "observedAt": "2026-11-05T00:00:00Z",
            "scanId": "unverified",
        }
        result = self.transform(
            [doc("catalog/scans/2026/11/05/20261105_00001.scanResults.json", raw)]
        )
        self.assertIsNone(result["estate_coverage"][0]["observed_at_utc"])
        self.assertIsNone(result["estate_coverage"][0]["run_id"])

    def test_nullable_refreshable_metadata_stays_unknown_not_zero(self):
        result = self.transform(
            [
                doc(
                    "datasetrefreshable/2026/11/05/workspaces.datasets.refreshable.json",
                    [
                        {
                            "id": ITEM,
                            "kind": "Dataflow",
                            "group": None,
                            "capacity": None,
                            "refreshSchedule": None,
                        }
                    ],
                )
            ]
        )
        entry = result["refreshable_observations"][0]
        self.assertEqual(entry["item_type"], "Dataflow")
        self.assertIsNone(entry["schedule_enabled"])
        self.assertIsNone(entry["refresh_failures"])

    def test_connections_accept_real_envelope_and_separate_failed_empty_unfinished(
        self,
    ):
        entry = {
            "id": "connection-1",
            "displayName": None,
            "connectivityType": "OnPremisesGateway",
            "gatewayId": "gateway-1",
            "privacyLevel": "Organizational",
            "connectionDetails": {"type": "SQL", "path": "DO_NOT_KEEP_PATH"},
            "credentialDetails": "DO_NOT_KEEP_CREDENTIAL",
        }
        result = self.transform(self.connection_run([entry]))
        connection = result["connection_observations"][0]
        self.assertIsNone(connection["connection_name"])
        self.assertEqual(connection["gateway_id"], "gateway-1")
        self.assertEqual(connection["observed_at_utc"], "2026-11-05T00:00:00.000000Z")
        self.assertNotIn("DO_NOT_KEEP", json.dumps(result))
        empty = self.transform(self.connection_run([]))
        self.assertEqual(empty["estate_coverage"][0]["record_count"], 0)
        failed = self.transform(self.connection_run([], failed=True))
        self.assertEqual(failed["estate_coverage"][0]["coverage_status"], "failed")
        self.assertIsNone(failed["estate_coverage"][0]["record_count"])
        unfinished = self.transform(self.connection_run([], finished=False))
        self.assertEqual(
            unfinished["estate_coverage"][0]["coverage_status"], "unfinished"
        )
        self.assertEqual(unfinished["connection_observations"], [])

    def test_legacy_encoded_gateway_arrays_keep_status_without_connection_details(self):
        folder = "gateways/2026/11/05/"
        raw = [
            doc(
                folder + "gateways.json",
                json.dumps([{"id": "gateway-1", "name": "Gateway"}]),
            ),
            doc(
                folder + "datasource_details.json",
                json.dumps(
                    [
                        {
                            "id": "source-1",
                            "gatewayId": "gateway-1",
                            "datasourceType": "Sql",
                            "datasourceName": "Source",
                            "connectionDetails": "DO_NOT_KEEP_CONNECTION",
                        }
                    ]
                ),
            ),
            doc(
                folder + "status.json",
                json.dumps(
                    [
                        {
                            "gatewayId": "gateway-1",
                            "datasourceId": "source-1",
                            "error": {
                                "code": "success",
                                "pbi.error": {
                                    "details": [
                                        {
                                            "detail": 200,
                                            "message": "DO_NOT_KEEP_MESSAGE",
                                        }
                                    ]
                                },
                            },
                        }
                    ]
                ),
            ),
            doc(folder + "users.json", [{"emailAddress": "DO_NOT_KEEP_USER"}]),
        ]
        result = self.transform(raw)
        self.assertEqual(len(result["gateway_datasources"]), 1)
        self.assertEqual(result["gateway_status"][0]["http_status"], 200)
        self.assertEqual(
            result["gateway_status"][0]["connectivity_observation"], "success_response"
        )
        self.assertIsNone(result["gateway_status"][0]["observed_at_utc"])
        self.assertNotIn("DO_NOT_KEEP", json.dumps(result))

    def test_refresh_history_is_distinct_from_fabric_jobs_and_durations_stay_unknown(
        self,
    ):
        folder = "datasetrefresh/2026/11/05/workspaces.datasets.refreshes.json"
        raw = [
            {
                "workspace_id": WORKSPACE,
                "dataset_id": ITEM,
                "requestId": "refresh-1",
                "status": "Completed",
                "startTime": "2026-11-05T00:00:00Z",
                "endTime": "2026-11-05T00:02:00Z",
            },
            {
                "workspace_id": WORKSPACE,
                "dataset_id": ITEM,
                "requestId": "refresh-2",
                "status": "Failed",
                "startTime": "2026-11-05T01:00:00Z",
                "endTime": "2026-11-05T00:59:00Z",
                "serviceExceptionJson": '{"errorCode":"RefreshFailed","message":"DO_NOT_KEEP_MESSAGE"}',
            },
        ]
        result = self.transform(
            [
                doc(folder, raw),
                doc(
                    "datasetrefreshable/2026/11/05/workspaces.datasets.refreshable.json",
                    [
                        {
                            "id": ITEM,
                            "group": {"id": WORKSPACE},
                            "capacity": {"id": "capacity-1"},
                            "refreshCount": 5,
                            "refreshSchedule": {"enabled": True},
                            "configuredBy": "DO_NOT_KEEP_USER",
                        }
                    ],
                ),
            ]
        )
        history = {
            entry["refresh_id"]: entry for entry in result["refresh_observations"]
        }
        self.assertEqual(history["refresh-1"]["duration_seconds"], 120)
        self.assertIsNone(history["refresh-2"]["duration_seconds"])
        self.assertEqual(history["refresh-2"]["failure_code"], "RefreshFailed")
        self.assertEqual(result["job_observations"], [])
        self.assertIsNone(result["refreshable_observations"][0]["refresh_failures"])
        self.assertNotIn("DO_NOT_KEEP", json.dumps(result))

    def test_malformed_recognized_files_are_quarantined_not_successful_empty(self):
        for path, value, dataset in (
            (
                "activity/2026/11/05/20261105_00001.json",
                [{"Operation": "Valid"}, {"Operation": None}],
                "activity_events",
            ),
            (
                "catalog/scans/2026/11/05/20261105_00001.scanResults.json",
                {
                    "workspaces": [
                        {"id": WORKSPACE, "datasets": [{"id": ITEM, "tables": {}}]}
                    ]
                },
                "catalog_models",
            ),
            (
                "gateways/2026/11/05/status.json",
                [{"gatewayId": "g", "datasourceId": "d", "error": []}],
                "gateway_status",
            ),
        ):
            with self.subTest(path=path):
                result = self.transform([doc(path, value)])
                self.assertEqual(result[dataset], [])
                self.assertEqual(
                    result["estate_coverage"][0]["coverage_status"], "invalid"
                )
                self.assertIsNone(result["estate_coverage"][0]["record_count"])

    def test_source_scoped_reader_does_not_load_other_domains_and_can_flag_absence(
        self,
    ):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "monitor"
            activity = root / "activity/2026/11/05/20261105_00001.json"
            activity.parent.mkdir(parents=True)
            activity.write_text('[{"Operation":"ViewReport"}]')
            other = root / "gateways/2026/11/05/gateways.json"
            other.parent.mkdir(parents=True)
            other.write_text("x" * 4096)
            with patch.object(analytics, "LAKEHOUSE_FILES", folder):
                loaded = analytics.load_documents(
                    root, source_prefixes=["activity"], max_bytes=128
                )
                self.assertEqual(len(loaded), 1)
                self.assertEqual(
                    analytics.load_documents(
                        root, source_prefixes=["datasetrefresh"], allow_empty=True
                    ),
                    [],
                )
                with self.assertRaises(ValueError):
                    analytics.load_documents(root, source_prefixes=["datasetrefresh"])
                with self.assertRaises(ValueError):
                    analytics.load_documents(root, source_prefixes=["arbitrary_folder"])
            result = self.transform([])
            self.assertEqual(result["estate_coverage"], [])

    def test_estate_catalog_includes_fabric_items_without_inventing_physical_schema(
        self,
    ):
        result = self.transform(
            [
                doc(
                    "items/2026/11/05/items.json",
                    [
                        {
                            "id": ITEM,
                            "workspaceId": WORKSPACE,
                            "type": "Warehouse",
                            "displayName": "Warehouse",
                        }
                    ],
                ),
                doc(
                    "workspaces/2026/11/05/workspaces.json",
                    [{"id": WORKSPACE, "name": "Workspace"}],
                ),
            ]
        )
        self.assertEqual(result["catalog_items"][0]["item_type"], "Warehouse")
        self.assertEqual(result["catalog_workspaces"][0]["workspace_id"], WORKSPACE)
        self.assertEqual(result["model_tables"], [])
        self.assertTrue(
            all(
                "physical_schema" in entry["issue"]
                for entry in result["estate_coverage"]
            )
        )


class ValidationNotebookTests(unittest.TestCase):
    def snapshot(self):
        return {
            "baseline_version": 1,
            "contract_version": analytics.SCHEMA_VERSION,
            "captured_at_utc": "2026-01-01T00:00:00.000000Z",
            "prefix": "monitor_",
            "raw_root": "monitor",
            "permission_mode": "Scoped",
            "raw": validation.validation_raw_digest([doc("items/a.json", [])]),
            "tables": {
                dataset: {
                    "table_id": WORKSPACE,
                    "version": 7,
                    "rows": 1,
                    "unique_ids": 1,
                    "invalid_metadata_rows": 0,
                }
                for dataset in analytics.SCHEMAS
            },
        }

    def test_persistent_baseline_roundtrip_refuses_overwrite_and_invalid_versions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "baseline.json"
            original = self.snapshot()
            validation.validation_save_baseline(path, original)
            self.assertEqual(validation.validation_load_baseline(path), original)
            with self.assertRaisesRegex(ValueError, "already exists"):
                validation.validation_save_baseline(path, {**original, "raw": {}})
            self.assertEqual(validation.validation_load_baseline(path), original)
            for invalid in ("7; DROP TABLE x", True, -1):
                damaged = copy.deepcopy(original)
                damaged["tables"]["inventory"]["version"] = invalid
                path.write_text(json.dumps(damaged))
                with self.assertRaisesRegex(ValueError, "Invalid validation baseline"):
                    validation.validation_load_baseline(path)
            path.write_bytes(b"x" * (validation.MAX_BASELINE_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "safety limit"):
                validation.validation_load_baseline(path)

    def test_baseline_cannot_escape_into_raw_or_follow_symlinks(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(validation, "LAKEHOUSE_FILES", folder),
        ):
            raw = Path(folder) / "monitor"
            self.assertEqual(
                validation.validation_baseline_path("test.json", raw),
                Path(folder) / "monitor_validation/test.json",
            )
            for name in ("../test.json", "/tmp/test.json", "a/b.json"):
                with self.assertRaises(ValueError):
                    validation.validation_baseline_path(name, raw)
            with self.assertRaises(ValueError):
                validation.validation_baseline_path("test.json", folder)
            destination = Path(folder) / "monitor_validation"
            destination.symlink_to(raw, target_is_directory=True)
            with self.assertRaises(ValueError):
                validation.validation_baseline_path("test.json", raw)

    def test_freshness_distinguishes_unknown_stale_and_future(self):
        now = "2026-01-02T00:00:00.000000Z"
        for observed, expected in (
            (None, "UNKNOWN"),
            ("2026-01-01T00:00:00.000000Z", "WITHIN_THRESHOLD"),
            ("2025-12-31T23:59:59.000000Z", "STALE"),
            ("2026-01-02T00:00:01.000000Z", "CLOCK_AHEAD"),
            ("invalid", "INVALID_TIMESTAMP"),
        ):
            self.assertEqual(
                validation.validation_freshness(observed, now, 24), expected
            )
        for threshold in (True, 0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                validation.validation_freshness(None, now, threshold)

    def test_raw_digest_is_order_independent_and_detects_same_path_changes(self):
        a, b = doc("items/a.json", []), doc("items/b.json", [1])
        self.assertEqual(
            validation.validation_raw_digest([a, b]),
            validation.validation_raw_digest([b, a]),
        )
        self.assertNotEqual(
            validation.validation_raw_digest([a, b]),
            validation.validation_raw_digest([doc("items/a.json", [2]), b]),
        )

    def test_changed_raw_or_scope_is_not_a_failed_idempotence_claim(self):
        baseline = self.snapshot()
        for key, value in (
            ("raw", {**baseline["raw"], "sha256": "f" * 64}),
            ("prefix", "monitor_test_"),
            ("permission_mode", "Tenant"),
            ("raw_root", "different"),
        ):
            current = {**baseline, key: value}
            spark = MagicMock()
            checks = validation.validation_compare(spark, current, {}, baseline)
            self.assertEqual(checks[0]["status"], "NOT_COMPARABLE")
            spark.sql.assert_not_called()

    def test_replacement_count_changes_and_unavailable_history_do_not_pass(self):
        baseline = self.snapshot()
        for key, value, expected in (
            ("table_id", OTHER, "FAIL"),
            ("rows", 2, "FAIL"),
            ("version", 8, "UNVERIFIED"),
        ):
            current = copy.deepcopy(baseline)
            current["tables"]["inventory"][key] = value
            with patch.object(
                validation,
                "validation_version_frame",
                side_effect=OSError("private error details"),
            ):
                checks = validation.validation_compare(
                    MagicMock(), current, {}, baseline
                )
            result = next(entry for entry in checks if entry["check"] == "inventory")
            self.assertEqual(result["status"], expected)
            self.assertNotIn("private error details", json.dumps(checks))

    def test_new_commit_with_identical_rows_passes_but_same_count_mutation_fails(self):
        class Frame:
            def __init__(self, rows):
                self.rows = rows

            def select(self, *columns):
                return self

            def exceptAll(self, other):
                return Frame(
                    list((Counter(self.rows) - Counter(other.rows)).elements())
                )

            def limit(self, count):
                return Frame(self.rows[:count])

            def count(self):
                return len(self.rows)

        baseline = self.snapshot()
        current = copy.deepcopy(baseline)
        current["tables"]["inventory"]["version"] = 8
        old = Frame([("observation", "original content")])
        frames = {dataset: old for dataset in analytics.SCHEMAS}
        with patch.object(validation, "validation_version_frame", return_value=old):
            checks = validation.validation_compare(
                MagicMock(), current, frames, baseline
            )
            self.assertTrue(all(entry["status"] == "PASS" for entry in checks))
            frames["inventory"] = Frame([("observation", "mutated content")])
            checks = validation.validation_compare(
                MagicMock(), current, frames, baseline
            )
            self.assertEqual(
                next(entry for entry in checks if entry["check"] == "inventory")[
                    "status"
                ],
                "FAIL",
            )

    def test_capture_survives_restart_and_compare_does_not_write_baseline_or_tables(
        self,
    ):
        spark = MagicMock()
        frames = {}
        for dataset in analytics.SCHEMAS:
            frame = MagicMock()
            frame.schema.fields = [
                SimpleNamespace(name=key, dataType=kind)
                for key, kind in {
                    **analytics.COMMON,
                    **analytics.SCHEMAS[dataset],
                }.items()
            ]
            frame.select.return_value = frame
            frame.exceptAll.return_value.limit.return_value.count.return_value = 0
            frames[dataset] = frame
        spark.sql.side_effect = lambda query: frames[
            query.split()[3].removeprefix("monitor_")
        ]
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(validation, "LAKEHOUSE_FILES", folder),
            patch.object(
                validation, "load_documents", return_value=[doc("items/a.json", [])]
            ),
            patch.object(validation, "read_curated"),
            patch.object(
                validation, "validation_table_identity", return_value=(WORKSPACE, 7)
            ),
            patch.object(
                validation,
                "validation_table_metrics",
                return_value={
                    "rows": 1,
                    "unique_ids": 1,
                    "invalid_metadata_rows": 0,
                },
            ),
            patch.object(validation, "validation_reports"),
            patch.object(
                validation,
                "to_frame",
                side_effect=lambda _, dataset, rows: SimpleNamespace(
                    schema=SimpleNamespace(
                        fields=[
                            SimpleNamespace(name=key, dataType=kind)
                            for key, kind in {
                                **analytics.COMMON,
                                **analytics.SCHEMAS[dataset],
                            }.items()
                        ]
                    ),
                ),
            ),
        ):
            kwargs = {
                "raw_root": str(Path(folder) / "monitor"),
                "prefix": "monitor_",
                "permission_mode": "Scoped",
                "baseline_name": "test.json",
            }
            captured = validation.validate_rerun(
                spark, MagicMock(), action="capture", **kwargs
            )
            path = Path(folder) / "monitor_validation/test.json"
            saved = path.read_bytes()
            self.assertNotIn(b"principal", saved)
            del captured
            with patch.object(validation, "validation_save_baseline") as save:
                checks = validation.validate_rerun(
                    spark, MagicMock(), action="compare", **kwargs
                )
                save.assert_not_called()
            self.assertTrue(all(entry["status"] == "PASS" for entry in checks))
            self.assertEqual(path.read_bytes(), saved)
            self.assertTrue(
                all(
                    call.args[0].startswith("SELECT * FROM ")
                    for call in spark.sql.call_args_list
                )
            )
            for metrics in (
                {"rows": 2, "unique_ids": 1, "invalid_metadata_rows": 0},
                {"rows": 1, "unique_ids": 1, "invalid_metadata_rows": 1},
            ):
                with (
                    patch.object(
                        validation, "validation_table_metrics", return_value=metrics
                    ),
                    self.assertRaisesRegex(ValueError, "invalid metadata"),
                ):
                    validation.validate_rerun(
                        spark,
                        MagicMock(),
                        action="capture",
                        **{**kwargs, "baseline_name": "invalid.json"},
                    )
                self.assertFalse((path.parent / "invalid.json").exists())
            frames["inventory"].schema.fields.append(
                SimpleNamespace(name="unexpected", dataType="string")
            )
            with self.assertRaisesRegex(ValueError, "schema differs"):
                validation.validate_rerun(
                    spark,
                    MagicMock(),
                    action="capture",
                    **{**kwargs, "baseline_name": "wrong-schema.json"},
                )
            self.assertFalse((path.parent / "wrong-schema.json").exists())

    def test_mid_validation_source_or_table_change_is_rejected(self):
        snapshot = self.snapshot()
        with self.assertRaisesRegex(ValueError, "Raw evidence changed"):
            validation.validation_assert_stable(
                MagicMock(), snapshot, lambda: [doc("items/a.json", ["new"])]
            )
        with (
            patch.object(
                validation, "validation_table_identity", return_value=(WORKSPACE, 8)
            ),
            self.assertRaisesRegex(ValueError, "table changed"),
        ):
            validation.validation_assert_stable(
                MagicMock(), snapshot, lambda: [doc("items/a.json", [])]
            )

    def test_untrusted_version_never_becomes_sql(self):
        spark = MagicMock()
        for version in ("0; DROP TABLE x", True, -1):
            with self.assertRaises(ValueError):
                validation.validation_version_frame(
                    spark, "monitor_", "inventory", version
                )
        spark.sql.assert_not_called()

    def test_existing_core_baseline_remains_valid_and_new_table_selection_is_not_comparable(
        self,
    ):
        baseline = self.snapshot()
        baseline["tables"] = {
            key: value
            for key, value in baseline["tables"].items()
            if key in analytics.CORE_DATASETS
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "baseline.json"
            validation.validation_save_baseline(path, baseline)
            self.assertEqual(validation.validation_load_baseline(path), baseline)
        checks = validation.validation_compare(
            MagicMock(), self.snapshot(), {}, baseline
        )
        self.assertEqual(checks[0]["status"], "NOT_COMPARABLE")


class UploadableNotebookTests(unittest.TestCase):
    def orchestrator_namespace(
        self, run, names=None, *, include_pipeline_activity=False
    ):
        notebook = generated_notebooks()["nb_orchestrator.ipynb"]
        namespace = {
            "notebookutils": SimpleNamespace(notebook=SimpleNamespace(run=run)),
            "spark": MagicMock(),
            "display": MagicMock(),
        }
        config, execute = [
            "".join(cell["source"])
            for cell in notebook["cells"]
            if cell["cell_type"] == "code"
        ]
        if include_pipeline_activity:
            config = config.replace(
                "INCLUDE_PIPELINE_ACTIVITY = False", "INCLUDE_PIPELINE_ACTIVITY = True"
            )
        exec(compile(config, "orchestrator_parameters", "exec"), namespace)  # noqa: S102 - Trusted generated cell.
        if names is not None:
            namespace["NOTEBOOKS"] = names
        return namespace, execute

    def test_orchestrator_runs_all_writers_serially_with_preview_parameters(self):
        run = MagicMock(return_value="")
        namespace, execute = self.orchestrator_namespace(run)
        writers = {
            name.removesuffix(".ipynb")
            for name in generated_notebooks()
            if name[:2] not in {"05", "06", "22"} and name != "nb_orchestrator.ipynb"
        }
        self.assertEqual(set(namespace["NOTEBOOKS"]), writers)
        self.assertEqual(len(namespace["NOTEBOOKS"]), 19)
        exec(compile(execute, "orchestrator_execution", "exec"), namespace)  # noqa: S102 - Trusted generated cell with mocked Fabric APIs.
        self.assertEqual(
            [call.args[0] for call in run.call_args_list], namespace["NOTEBOOKS"]
        )
        for call in run.call_args_list:
            self.assertEqual(call.args[1], 3600)
            self.assertEqual(
                call.args[2],
                {
                    "RAW_ROOT": "/lakehouse/default/Files/monitor",
                    "TABLE_PREFIX": "monitor_",
                    "WRITE_TABLES": False,
                    "PERMISSION_MODE": "Scoped",
                    "INCLUDE_SHORTCUTS": False,
                    "INCLUDE_EVENTSTREAM_TOPOLOGY": False,
                },
            )
        self.assertTrue(
            all(result["status"] == "Succeeded" for result in namespace["results"])
        )
        namespace["display"].assert_called_once()

    def test_pipeline_activity_writer_requires_explicit_orchestrator_opt_in(self):
        run = MagicMock(return_value="")
        namespace, execute = self.orchestrator_namespace(
            run, include_pipeline_activity=True
        )
        exec(compile(execute, "orchestrator_execution", "exec"), namespace)  # noqa: S102 - Trusted generated cell with mocked Fabric APIs.
        self.assertEqual(run.call_count, 20)
        self.assertEqual(run.call_args.args[0], "22_monitor_pipeline_activity")

    def test_shortcut_opt_in_reaches_existing_writers_without_adding_children(self):
        run = MagicMock(return_value="")
        namespace, execute = self.orchestrator_namespace(run)
        namespace["INCLUDE_SHORTCUTS"] = True
        exec(compile(execute, "shortcut_orchestration", "exec"), namespace)  # noqa: S102 - Trusted generated code with mocked Fabric calls.
        self.assertEqual(run.call_count, 19)
        self.assertTrue(
            all(call.args[2]["INCLUDE_SHORTCUTS"] for call in run.call_args_list)
        )

    def test_orchestrator_reports_named_failures_after_attempting_remaining_children(
        self,
    ):
        run = MagicMock(
            side_effect=[RuntimeError("first error"), "", ValueError("last error")]
        )
        namespace, execute = self.orchestrator_namespace(
            run, ["first", "middle", "last"]
        )
        namespace.update(
            RAW_ROOT="/lakehouse/default/Files/custom",
            TABLE_PREFIX="monitor_custom_",
            WRITE_TABLES=True,
            PERMISSION_MODE="Tenant",
            NOTEBOOK_TIMEOUT_SECONDS=120,
        )
        with self.assertRaisesRegex(RuntimeError, "Failed notebooks: first, last"):
            exec(compile(execute, "orchestrator_execution", "exec"), namespace)  # noqa: S102 - Trusted generated cell with mocked Fabric APIs.
        self.assertEqual(run.call_count, 3)
        self.assertEqual(
            namespace["results"],
            [
                {"notebook": "first", "status": "Failed", "error": "first error"},
                {"notebook": "middle", "status": "Succeeded", "error": ""},
                {"notebook": "last", "status": "Failed", "error": "last error"},
            ],
        )
        self.assertEqual(run.call_args.args[1], 120)
        self.assertEqual(run.call_args.args[2]["WRITE_TABLES"], True)
        self.assertEqual(run.call_args.args[2]["PERMISSION_MODE"], "Tenant")
        self.assertEqual(run.call_args.args[2]["TABLE_PREFIX"], "monitor_custom_")
        namespace["display"].assert_called_once()

    def test_orchestrator_rejects_invalid_selection_before_running_children(self):
        for names in ([], ["same", "same"], ["valid", ""], ["valid", None], "name"):
            with self.subTest(names=names):
                run = MagicMock()
                namespace, execute = self.orchestrator_namespace(run, names)
                with self.assertRaisesRegex(ValueError, "NOTEBOOKS"):
                    exec(compile(execute, "orchestrator_execution", "exec"), namespace)  # noqa: S102 - Trusted generated cell with mocked Fabric APIs.
                run.assert_not_called()

    def test_generated_files_are_current_clear_and_python310_compatible(self):
        for name, notebook in generated_notebooks().items():
            with self.subTest(name=name):
                self.assertEqual(json.loads((ROOT / name).read_text()), notebook)
                self.assertEqual(notebook["nbformat"], 4)
                self.assertEqual(
                    len({c["id"] for c in notebook["cells"]}), len(notebook["cells"])
                )
                namespace = {"__name__": "fabric_notebook"}
                for cell in notebook["cells"]:
                    if cell["cell_type"] != "code":
                        continue
                    source = "".join(cell["source"])
                    tree = ast.parse(source, feature_version=(3, 10))
                    self.assertIsNone(cell["execution_count"])
                    self.assertEqual(cell["outputs"], [])
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ImportFrom):
                            self.assertFalse(
                                (node.module or "").startswith(("env.", "notebooks."))
                            )
                    # Execute embedded library cells, not Fabric orchestration or visual rendering.
                    if any(
                        isinstance(n, (ast.FunctionDef, ast.ClassDef))
                        for n in tree.body
                    ):
                        exec(compile(tree, name, "exec"), namespace)  # noqa: S102 - Trusted generated library cells only.
                if name == "nb_orchestrator.ipynb":
                    continue
                self.assertIn("transform", namespace)
                if name.startswith("06"):
                    self.assertEqual(
                        namespace["validation_freshness"](
                            None, "2026-01-01T00:00:00Z", 24
                        ),
                        "UNKNOWN",
                    )
                if not name.startswith("05"):
                    transformed = namespace["transform"](permission_cycle())
                    self.assertEqual(len(transformed["permission_grants"]), 1)
