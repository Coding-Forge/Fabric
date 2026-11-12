"""Offline definition export, resumable coverage and non-disclosing transport."""

import asyncio
import base64
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app import monitor
from env.audit import Audits
from env.config import run_monitor
from env.context import Context, utc_stamp
from env.modules import FabricItemDefinitions
from env.utility.file_management import File_Management
from notebooks import monitor_analytics as analytics
from tests.fabric_helpers import ROOT, WORKSPACE, CollectorTestCase, inventory, item
from tests.test_context import _FakeResponse, _FakeSession
from tests.test_notebook_references import notebook
from tests.test_pipeline_references import activity, dataset, pipeline

MODULE = "fabricitemdefinitions"
OPERATION = "00000000-0000-0000-0000-000000000099"


def definition(content, kind="Notebook"):
    path = "notebook-content.ipynb" if kind == "Notebook" else "pipeline-content.json"
    return {
        "status": 200,
        "body": {
            "definition": {
                "parts": [
                    {
                        "path": path,
                        "payloadType": "InlineBase64",
                        "payload": base64.b64encode(
                            json.dumps(content).encode()
                        ).decode(),
                    }
                ]
            }
        },
    }


class DefinitionsTests(CollectorTestCase):
    def context(self, *responses):
        ctx = super().context(*responses)
        ctx._safe_definition_request = AsyncMock(side_effect=ctx._safe_get.side_effect)
        return ctx

    async def test_cooldown_is_nonfatal_in_function_and_shared_entry_points(self):
        self.files[MODULE + "/request_gate.json"] = {
            "nextRequestUtc": "2026-01-03T00:00:00.000000Z",
            "pending": False,
            "blocked": False,
        }
        old = "2025-12-01T00:00:00.000000Z"
        state = {MODULE: {"lastRun": old}}
        audit = Audits()
        audit.context = self.context()
        audit.context.ApplicationModules = "FabricItemDefinitions"
        audit.fm = audit.context.fm
        audit.fm.read = AsyncMock(return_value=state)

        for entry_point in (monitor.main, run_monitor):
            with (
                self.subTest(entry_point=entry_point.__name__),
                patch.object(audit, "_Audits__setup_clients"),
                patch.object(monitor.config, "build_audit", return_value=audit),
            ):
                await entry_point()
                self.assertEqual(state[MODULE]["lastRun"], old)
                self.assertIn(MODULE, audit.context.deferred_modules)
                audit.context._safe_get.assert_not_awaited()
                audit.context.clients["tenant"].get_headers.assert_not_called()
                audit.context.logger.error.assert_not_called()
                audit.context.logger.warning.assert_not_called()
                audit.context.logger.info.assert_any_call(
                    "Run finished: %d succeeded, %d deferred, %d failed. "
                    "Deferred: %s. Failed: %s.",
                    0,
                    1,
                    0,
                    "FabricItemDefinitions",
                    "none",
                )
                self.assert_finished(MODULE, False)

    async def test_unauthorized_export_still_fails_after_other_modules_save(self):
        old = "2025-12-01T00:00:00.000000Z"
        state = {MODULE: {"lastRun": old}, "apps": {"lastRun": old}}
        audit = Audits()
        audit.context = self.context(
            inventory(item()), {"ERROR": "private body", "status": 401}
        )
        audit.context.ApplicationModules = "FabricItemDefinitions,Apps"
        audit.fm = audit.context.fm
        audit.fm.read = AsyncMock(return_value=state)
        with (
            patch.object(audit, "_Audits__setup_clients"),
            patch("env.audit.Apps", AsyncMock(return_value=True)),
            patch.object(monitor.config, "build_audit", return_value=audit),
            self.assertRaisesRegex(RuntimeError, "run failed"),
        ):
            await monitor.main()
        audit.fm.save.assert_awaited()
        self.assertNotEqual(state["apps"]["lastRun"], old)
        self.assertEqual(state[MODULE]["lastRun"], old)
        self.assertNotIn(MODULE, audit.context.deferred_modules)
        audit.context.logger.error.assert_any_call(
            "%s definition retrieval incomplete: HTTP %s errorCode=%s",
            MODULE,
            401,
            "unavailable",
        )
        audit.context.logger.error.assert_any_call(
            "Run finished: %d succeeded, %d deferred, %d failed. "
            "Deferred: %s. Failed: %s.",
            1,
            0,
            1,
            "none",
            "FabricItemDefinitions",
        )
        self.assertNotIn("private body", str(audit.context.logger.mock_calls))

    async def test_unsafe_request_gates_are_failures_not_expected_pauses(self):
        for flag in ("pending", "blocked"):
            with self.subTest(flag=flag):
                self.files.clear()
                self.files[MODULE + "/request_gate.json"] = {
                    "nextRequestUtc": utc_stamp(self.now),
                    flag: True,
                }
                ctx = self.context()
                self.assertFalse(await FabricItemDefinitions(ctx))
                self.assertNotIn(MODULE, ctx.deferred_modules)
                ctx.logger.error.assert_called()
                ctx._safe_get.assert_not_awaited()
                ctx.clients["tenant"].get_headers.assert_not_called()

    async def test_pausing_a_sweep_with_prior_failures_remains_a_failed_outcome(self):
        ctx = self.context(
            inventory(item(), item(11)),
            {"ERROR": "denied", "status": 401, "retryAfter": "3600"},
        )
        self.assertFalse(await FabricItemDefinitions(ctx))
        self.assertNotIn(MODULE, ctx.deferred_modules)
        self.assertIs(self.files[MODULE + "/progress.json"]["healthy"], False)
        restarted = self.context()
        self.assertFalse(await FabricItemDefinitions(restarted))
        self.assertNotIn(MODULE, restarted.deferred_modules)
        restarted._safe_definition_request.assert_not_awaited()
        restarted.logger.warning.assert_called()

    async def test_real_local_writer_persists_readable_pipeline_json_and_manifest(self):
        content = {"properties": {"activities": []}}
        ctx = self.context(
            inventory(item(kind="DataPipeline")), definition(content, "DataPipeline")
        )
        with tempfile.TemporaryDirectory() as root:
            ctx.OutputPath = root
            ctx.fm = File_Management()
            ctx.fm.content(ctx)
            self.assertTrue(await FabricItemDefinitions(ctx))
            files = list((Path(root) / MODULE).glob("*/*/*/*/*.json"))
            resources = [
                json.loads(p.read_text())
                for p in files
                if p.name.endswith(item()["itemId"] + ".json")
            ]
            self.assertEqual(
                resources[0]["records"][0]["decodedParts"]["pipeline-content.json"],
                content,
            )
            manifests = [
                json.loads(p.read_text()) for p in files if p.name == "manifest.json"
            ]
            self.assertEqual(len(manifests), 1)
            self.assertIs(manifests[0]["complete"], True)
            self.assertFalse((Path(root) / "state.yaml").exists())

    async def test_inventory_pages_resume_across_admission_windows(self):
        clock = SimpleNamespace(
            **{
                **vars(asyncio),
                "get_running_loop": lambda: SimpleNamespace(time=lambda: self.elapsed),
            }
        )
        with (
            patch("env.modules.fabricitemdefinitions.asyncio", clock),
            patch("env.utility.fabric_collection.asyncio", clock),
        ):
            ctx = self.context(*(inventory(item(), token=str(i)) for i in range(1, 5)))
            self.assertFalse(await FabricItemDefinitions(ctx))
            self.assertEqual(
                self.files[MODULE + "/progress.json"]["continuationToken"], "4"
            )
            self.assertEqual(ctx._safe_get.await_count, 4)
            self.advance(24)
            resumed = self.context(inventory(item()), definition(notebook()))
            self.assertTrue(await FabricItemDefinitions(resumed))
            self.assertEqual(
                self.urls(resumed), [ROOT + "admin/items?continuationToken=4"]
            )

    async def test_tenant_paging_captures_decoded_json_and_static_references(self):
        note, pipeline = item(), item(11, "DataPipeline")
        raw = {"properties": {"activities": [{"name": "untouched", "type": "Copy"}]}}
        ctx = self.context(
            inventory(note, item(12, "Lakehouse"), token="a /+?"),
            inventory(pipeline),
            definition(
                notebook(
                    'spark.read.table("db.input")\ndf.write.saveAsTable("db.output")'
                )
            ),
            definition(raw, "DataPipeline"),
        )
        self.assertTrue(await FabricItemDefinitions(ctx))
        self.assertEqual(
            self.urls(ctx),
            [
                ROOT + "admin/items",
                ROOT + "admin/items?continuationToken=a%20%2F%2B%3F",
            ],
        )
        self.assertGreaterEqual(
            (self.request_times[1] - self.request_times[0]).total_seconds(), 19
        )
        calls = ctx._safe_definition_request.await_args_list
        self.assertEqual([c.args[2] for c in calls], ["POST", "POST"])
        self.assertEqual(
            calls[0].args[0],
            ROOT
            + f"workspaces/{WORKSPACE}/notebooks/{note['itemId']}/getDefinition?format=ipynb",
        )
        resources = self.resources(MODULE)
        self.assertEqual(len(resources), 3)
        self.assertEqual(
            resources[1]["records"][0]["notebookReferences"]["evidence"],
            "static_inference",
        )
        record = resources[2]["records"][0]
        self.assertEqual(record["decodedParts"]["pipeline-content.json"], raw)
        self.assertNotIn("notebookReferences", record)
        self.assertIn("pipelineReferences", record)
        self.assertNotIn("pipelineReferences", resources[1]["records"][0])
        self.assert_finished(MODULE, True)
        self.assertEqual(self.files[MODULE + "/progress.json"], {"finished": True})

    async def test_retained_notebook_metadata_adds_associations_without_more_requests(
        self,
    ):
        raw = notebook()
        raw["metadata"] = {
            "dependencies": {"lakehouse": {"default_lakehouse": OPERATION}}
        }
        ctx = self.context(inventory(item()), definition(raw))
        self.assertTrue(await FabricItemDefinitions(ctx))
        self.assertEqual(ctx._safe_get.await_count, 1)
        self.assertEqual(ctx._safe_definition_request.await_count, 1)
        documents = [
            analytics.document(path, json.dumps(value).encode())
            for path, value in self.files.items()
            if path.startswith(MODULE + "/")
            and Path(path).name not in {"request_gate.json", "progress.json"}
        ]
        output = analytics.transform(documents)
        self.assertEqual(len(output["lineage_edges"]), 1)
        configured = output["lineage_edges"][0]
        self.assertEqual(configured["related_item_id"], OPERATION)
        self.assertIsNone(configured["related_workspace_id"])
        self.assertEqual(configured["direction"], "association")
        captured = self.resources(MODULE)[1]["records"][0]
        self.assertEqual(captured["decodedParts"]["notebook-content.ipynb"], raw)

    async def test_pipeline_capture_adds_references_without_mutation_or_more_requests(
        self,
    ):
        target = item(kind="DataPipeline")
        note = item(11)
        raw = pipeline(
            activity(
                "TridentNotebook", notebookId=note["itemId"], workspaceId=WORKSPACE
            ),
            activity(
                "Copy",
                source={
                    "datasetSettings": dataset(
                        "SqlServerTable", schema="dbo", table="input"
                    )
                },
                sink={"datasetSettings": dataset("LakehouseTable", table="output")},
            ),
        )
        response = definition(raw, "DataPipeline")
        ctx = self.context(inventory(target), response)
        self.assertTrue(await FabricItemDefinitions(ctx))
        record = self.resources(MODULE)[-1]["records"][0]
        self.assertEqual(record["definition"], response["body"]["definition"])
        self.assertEqual(record["decodedParts"]["pipeline-content.json"], raw)
        analysis = record["pipelineReferences"]
        self.assertTrue(analysis["complete"])
        self.assertEqual(
            {
                (r["operation"], r["kind"], r["reference"])
                for r in analysis["references"]
            },
            {
                ("execute", "notebook", note["itemId"]),
                ("read", "table", "input"),
                ("write", "table", "output"),
            },
        )
        ctx._safe_get.assert_awaited_once()
        ctx._safe_definition_request.assert_awaited_once()
        self.assert_finished(MODULE, True)

    async def test_partial_static_analysis_does_not_turn_successful_capture_into_failure(
        self,
    ):
        raw = pipeline(
            activity(
                "TridentNotebook",
                notebookId="@pipeline().parameters.notebook",
                workspaceId=WORKSPACE,
            )
        )
        ctx = self.context(
            inventory(item(kind="DataPipeline")), definition(raw, "DataPipeline")
        )
        self.assertTrue(await FabricItemDefinitions(ctx))
        resource = self.resources(MODULE)[-1]
        self.assertTrue(resource["complete"])
        analysis = resource["records"][0]["pipelineReferences"]
        self.assertFalse(analysis["complete"])
        self.assertEqual(analysis["references"], [])
        self.assertTrue(analysis["diagnostics"])
        self.assert_finished(MODULE, True)

    async def test_malformed_pipeline_analysis_fails_resource_without_hiding_next_item(
        self,
    ):
        ctx = self.context(
            inventory(item(kind="DataPipeline"), item(11)),
            definition({"properties": {"activities": {}}}, "DataPipeline"),
            definition(notebook()),
        )
        self.assertFalse(await FabricItemDefinitions(ctx))
        resources = self.resources(MODULE)[1:]
        self.assertEqual(
            [resource["complete"] for resource in resources], [False, True]
        )
        self.assertNotIn("records", resources[0])
        self.assert_finished(MODULE, False)

    async def test_long_running_export_resumes_after_cooldown_without_reposting(self):
        target = item()
        ctx = self.context(
            inventory(target),
            {"status": 202, "operationId": OPERATION, "retryAfter": "120", "body": {}},
        )
        self.assertFalse(await FabricItemDefinitions(ctx))
        progress = self.files[MODULE + "/progress.json"]
        self.assertEqual(progress["operationId"], OPERATION)
        self.assertEqual(progress["nextItem"], 0)
        waiting = self.context()
        self.assertFalse(await FabricItemDefinitions(waiting))
        waiting.clients["tenant"].get_headers.assert_not_called()
        self.advance(120)
        resumed = self.context(
            {"status": 200, "body": {"status": "Succeeded"}},
            definition(notebook("spark.table('db.source')")),
        )
        self.assertTrue(await FabricItemDefinitions(resumed))
        resumed._safe_get.assert_not_awaited()
        calls = resumed._safe_definition_request.await_args_list
        self.assertEqual(
            [c.args[0] for c in calls],
            [
                ROOT + f"operations/{OPERATION}",
                ROOT + f"operations/{OPERATION}/result",
            ],
        )
        self.assertEqual([c.args[2] for c in calls], ["GET", "GET"])
        manifest = self.assert_finished(MODULE, True)
        self.assertEqual(len(manifest["execution"]["evidence"]), 2)

    async def test_denied_item_does_not_hide_other_definitions_or_complete_coverage(
        self,
    ):
        ctx = self.context(
            inventory(item(), item(11, "DataPipeline")),
            {"ERROR": "private body not retained", "status": 403},
            definition({"properties": {"activities": []}}, "DataPipeline"),
        )
        self.assertFalse(await FabricItemDefinitions(ctx))
        resources = self.resources(MODULE)[1:]
        self.assertEqual([r["complete"] for r in resources], [False, True])
        self.assertNotIn("private body", json.dumps(self.files))
        manifest = self.assert_finished(MODULE, False)
        self.assertIn(
            {
                "error": "Definition retrieval incomplete",
                "status": 403,
                "errorCode": "unavailable",
            },
            manifest["errors"],
        )

    async def test_definition_diagnostics_do_not_retain_untrusted_error_values(self):
        ctx = self.context(
            inventory(item()),
            {
                "ERROR": "private-response",
                "status": True,
                "errorCode": "private-provider-code",
                "message": "private-body",
            },
        )
        self.assertFalse(await FabricItemDefinitions(ctx))
        manifest = self.assert_finished(MODULE, False)
        self.assertIn(
            {
                "error": "Definition retrieval incomplete",
                "status": None,
                "errorCode": "unrecognized",
            },
            manifest["errors"],
        )
        persisted = json.dumps(self.files)
        for value in ("private-response", "private-provider-code", "private-body"):
            self.assertNotIn(value, persisted)
            self.assertNotIn(value, str(ctx.logger.mock_calls))

    async def test_empty_inventory_is_explicit_success_and_invalid_inventory_is_not(
        self,
    ):
        self.assertTrue(await FabricItemDefinitions(self.context(inventory())))
        self.assertEqual(self.resources(MODULE)[-1]["records"], [])
        self.files.clear()
        malformed = inventory(item())
        malformed["itemEntities"][0]["workspaceId"] = "../not-a-workspace"
        ctx = self.context(malformed)
        self.assertFalse(await FabricItemDefinitions(ctx))
        ctx._safe_definition_request.assert_not_awaited()
        self.assert_finished(MODULE, False)

    async def test_bad_payloads_and_missing_operation_id_are_explicit_failures(self):
        valid = definition(notebook("spark.table('db.source')"))
        for response in (
            {**valid, "body": {"definition": {"parts": []}}},
            {
                **valid,
                "body": {
                    "definition": {
                        "parts": [
                            {
                                "path": "pipeline-content.json",
                                "payload": "***",
                                "payloadType": "InlineBase64",
                            }
                        ]
                    }
                },
            },
            {"status": 202, "body": {}},
        ):
            with self.subTest(response=response):
                self.files.clear()
                ctx = self.context(inventory(item()), response)
                self.assertFalse(await FabricItemDefinitions(ctx))
                resource = self.resources(MODULE)[-1]
                self.assertIs(resource["complete"], False)
                self.assertNotIn("records", resource)

    async def test_throttled_export_reserves_cooldown_and_does_not_advance_cursor(self):
        ctx = self.context(
            inventory(item()),
            {"ERROR": "throttled", "status": 429, "retryAfter": "3600"},
        )
        self.assertFalse(await FabricItemDefinitions(ctx))
        self.assertEqual(self.files[MODULE + "/progress.json"]["nextItem"], 0)
        restarted = self.context()
        self.assertFalse(await FabricItemDefinitions(restarted))
        restarted._safe_definition_request.assert_not_awaited()
        restarted.clients["tenant"].get_headers.assert_not_called()

    async def test_snapshot_failure_keeps_cursor_and_manifest_unfinished(self):
        ctx = self.context(inventory(item()), definition(notebook()))
        real_save = ctx.fm.save_snapshot.side_effect

        async def fail_item(path, name, value):
            if name.endswith(item()["itemId"] + ".json"):
                raise RuntimeError("Storage unavailable")
            await real_save(path, name, value)

        ctx.fm.save_snapshot.side_effect = fail_item
        with self.assertRaises(RuntimeError):
            await FabricItemDefinitions(ctx)
        self.assertEqual(self.files[MODULE + "/progress.json"]["nextItem"], 0)
        self.assertFalse(self.manifests(MODULE)[-1]["finished"])

    async def test_corrupt_progress_blocks_before_auth_or_requests(self):
        self.files[MODULE + "/progress.json"] = {"phase": "definitions", "items": []}
        ctx = self.context()
        with self.assertRaisesRegex(ValueError, "Invalid definition progress"):
            await FabricItemDefinitions(ctx)
        ctx._safe_get.assert_not_awaited()
        ctx._safe_definition_request.assert_not_awaited()
        ctx.clients["tenant"].get_headers.assert_not_called()

    async def test_crash_after_an_earlier_item_cannot_commit_healthy_sweep_on_resume(
        self,
    ):
        first, second = item(), item(11)
        ctx = self.context(
            inventory(first, second), definition(notebook()), definition(notebook())
        )
        real_save = ctx.fm.save_snapshot.side_effect

        async def fail_second(path, name, value):
            if name.endswith(second["itemId"] + ".json"):
                raise RuntimeError("Storage unavailable")
            await real_save(path, name, value)

        ctx.fm.save_snapshot.side_effect = fail_second
        with self.assertRaises(RuntimeError):
            await FabricItemDefinitions(ctx)
        self.assertEqual(self.files[MODULE + "/progress.json"]["nextItem"], 1)
        resumed = self.context(definition(notebook()))
        self.assertFalse(await FabricItemDefinitions(resumed))
        resumed._safe_get.assert_not_awaited()
        self.assertTrue(
            self.assert_finished(MODULE, False)["execution"]["sweepComplete"]
        )


class DefinitionTransportTests(CollectorTestCase):
    async def test_success_and_failure_bodies_do_not_reach_logs(self):
        class Session(_FakeSession):
            def request(self, method, *args, **kwargs):
                return self.response

        for status in (200, 403, 429):
            ctx = self.context()
            payload = definition(notebook('spark.table("PRIVATE_CODE")'))["body"]
            if status != 200:
                payload = {"errorCode": "PRIVATE_CODE", "message": "PRIVATE_CODE"}
            response = _FakeResponse(
                status=status, headers={"Retry-After": "90"}, json_body=payload
            )
            with patch(
                "env.context.aiohttp.ClientSession", return_value=Session(response)
            ):
                result = await Context._safe_definition_request(
                    ctx, ROOT + f"operations/{OPERATION}/result", {}, "GET"
                )
            if status == 200:
                self.assertEqual(result["body"], payload)
            else:
                self.assertEqual(result["status"], status)
                self.assertEqual(result["errorCode"], "unrecognized")
                self.assertNotIn("PRIVATE_CODE", json.dumps(result))
            self.assertNotIn("PRIVATE_CODE", str(ctx.logger.mock_calls))

    async def test_export_202_does_not_parse_empty_body_or_follow_location(self):
        ctx = self.context()
        response = _FakeResponse(
            status=202,
            headers={
                "x-ms-operation-id": OPERATION,
                "Retry-After": "30",
                "Location": "https://must-not-follow.invalid/private",
            },
        )
        response.json = AsyncMock(side_effect=AssertionError("202 has no JSON body"))

        class Session(_FakeSession):
            def request(self, method, *args, **kwargs):
                self.calls.append((method, args, kwargs))
                return self.response

        session = Session(response)
        url = (
            ROOT
            + f"workspaces/{WORKSPACE}/notebooks/{item()['itemId']}/getDefinition?format=ipynb"
        )
        with patch("env.context.aiohttp.ClientSession", return_value=session):
            result = await Context._safe_definition_request(
                ctx, url, {"Authorization": "PRIVATE_TOKEN"}, "POST"
            )
        self.assertEqual(
            result,
            {"status": 202, "retryAfter": "30", "operationId": OPERATION, "body": {}},
        )
        response.json.assert_not_awaited()
        self.assertEqual(len(session.calls), 1)
        self.assertIs(session.calls[0][2]["allow_redirects"], False)
        self.assertNotIn("PRIVATE_TOKEN", str(ctx.logger.mock_calls))

    async def test_transport_refuses_nonexport_posts_and_external_urls(self):
        ctx = self.context()
        with patch("env.context.aiohttp.ClientSession") as session:
            for url, method in (
                (ROOT + f"workspaces/{WORKSPACE}/items", "POST"),
                (ROOT + f"operations/{OPERATION}/result", "POST"),
                ("https://example.invalid/v1/operations/" + OPERATION, "GET"),
                (ROOT + f"operations/{OPERATION}?secret=x", "GET"),
            ):
                result = await Context._safe_definition_request(ctx, url, {}, method)
                self.assertIn("ERROR", result)
            session.assert_not_called()
