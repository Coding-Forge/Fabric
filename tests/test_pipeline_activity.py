"""Explicit-run collection and allowlisted read-only POSTs, entirely offline."""

import asyncio
import copy
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app import monitor
from env import audit as audit_module
from env.audit import Audits
from env.context import Context
from env.modules import FabricPipelineActivityRuns
from env.utility.pipeline_activity import activity_query_body
from tests.fabric_helpers import ROOT, WORKSPACE, CollectorTestCase, inventory, item
from tests.test_context import _FakeResponse, _FakeSession

MODULE = "fabricpipelineactivityruns"
RUN = "00000000-0000-0000-0000-000000000010"
ACTIVITY = "00000000-0000-0000-0000-000000000011"
CHILD = "00000000-0000-0000-0000-000000000012"
PARENT = {
    "workspaceId": WORKSPACE,
    "pipelineRunId": RUN,
    "lastUpdatedAfter": "2026-01-01T00:00:00.000000Z",
    "lastUpdatedBefore": "2026-01-02T00:00:00.000000Z",
}
URL = (
    ROOT + f"workspaces/{WORKSPACE}/datapipelines/pipelineruns/{RUN}/queryactivityruns"
)
PRIVATE = "SYNTHETIC_PRIVATE_PAYLOAD"


def activity(**changes):
    return {
        "pipelineRunId": RUN,
        "activityRunId": ACTIVITY,
        "activityName": "Copy",
        "activityType": "Copy",
        "status": "Succeeded",
        "activityRunStart": "2026-01-01T01:00:00Z",
        "activityRunEnd": None,
        "durationInMs": None,
        "output": {},
        **changes,
    }


class PipelineActivityTests(CollectorTestCase):
    def setUp(self):
        super().setUp()
        setting = patch.dict(
            os.environ, {"FABRIC_PIPELINE_ACTIVITY_SCOPE": json.dumps([PARENT])}
        )
        setting.start()
        self.addCleanup(setting.stop)

    def context(self, *responses):
        ctx = super().context(*responses)
        ctx._safe_activity_query = AsyncMock(side_effect=ctx._safe_get.side_effect)
        return ctx

    async def test_invalid_scopes_fail_before_auth_storage_or_requests(self):
        for value in (
            None,
            [],
            {},
            [1],
            [PARENT, PARENT],
            [{**PARENT, "workspaceId": "invalid"}],
            [{**PARENT, "pipelineRunId": "invalid"}],
            [{**PARENT, "itemId": RUN}],
            [{**PARENT, "lastUpdatedAfter": "2026-01-01T00:00:00"}],
            [{**PARENT, "lastUpdatedAfter": "2026-01-01T00:00:00+01:00"}],
            [{**PARENT, "lastUpdatedAfter": PARENT["lastUpdatedBefore"]}],
        ):
            with (
                self.subTest(value=value),
                patch.dict(
                    os.environ, {"FABRIC_PIPELINE_ACTIVITY_SCOPE": json.dumps(value)}
                ),
            ):
                ctx = self.context()
                with self.assertRaises(ValueError):
                    await FabricPipelineActivityRuns(ctx)
                ctx.clients["tenant"].get_headers.assert_not_called()
                ctx.fm.save_snapshot.assert_not_awaited()
                ctx._safe_activity_query.assert_not_awaited()

    async def test_metrics_keep_zero_unknown_and_child_identity_without_traversal(self):
        record = activity(
            activityType="ExecutePipeline",
            activityRunStart="2025-12-31T23:00:00Z",
            input={"secret": PRIVATE},
            error={"message": PRIVATE},
            output={
                "rowsRead": 0,
                "dataWritten": 12,
                "pipelineRunId": CHILD,
                "secret": PRIVATE,
            },
        )
        ctx = self.context({"value": [record, record]})
        self.assertTrue(await FabricPipelineActivityRuns(ctx))
        ctx._safe_activity_query.assert_awaited_once()
        ctx._safe_get.assert_not_awaited()
        captured = self.resources(MODULE)[0]
        self.assertEqual(captured["parent"], PARENT)
        self.assertEqual(len(captured["records"]), 1)
        result = captured["records"][0]
        self.assertEqual(result["output"]["rowsRead"], 0)
        self.assertIsNone(result["output"]["rowsCopied"])
        self.assertEqual(result["output"]["dataWritten"], 12)
        self.assertEqual(result["childPipelineRunId"], CHILD)
        self.assertEqual(result["activityRunStart"], "2025-12-31T23:00:00.000000Z")
        self.assertIsNone(result["activityRunEnd"])
        self.assertIsNone(result["durationInMs"])
        self.assertNotIn(PRIVATE, json.dumps(self.files))
        self.assert_finished(MODULE, True)

    async def test_reruns_retain_separate_observations_without_following_children(self):
        for _ in range(2):
            ctx = self.context({"value": [activity()]})
            self.assertTrue(await FabricPipelineActivityRuns(ctx))
            ctx._safe_activity_query.assert_awaited_once()
        snapshots = self.resources(MODULE)
        self.assertEqual(len(snapshots), 2)
        self.assertNotEqual(snapshots[0]["runId"], snapshots[1]["runId"])
        self.assertEqual(snapshots[0]["records"], snapshots[1]["records"])

    async def test_empty_failed_and_malformed_are_distinct(self):
        for response, success in (
            ({"value": []}, True),
            ({"ERROR": PRIVATE, "status": 403, "message": PRIVATE}, False),
            ({"value": {}}, False),
            ({"value": [activity(pipelineRunId=CHILD)]}, False),
            ({"value": [activity(activityRunId=PRIVATE)]}, False),
            ({"value": [activity(output={"rowsRead": True})]}, False),
            ({"value": [activity(output={"rowsRead": -1})]}, False),
            ({"value": [activity(output={"rowsRead": 1.5})]}, False),
            ({"value": [activity(output={"throughput": float("nan")})]}, False),
            ({"value": [activity(durationInMs=float("inf"))]}, False),
            ({"value": [activity(output=PRIVATE)]}, False),
            ({"value": [activity(), activity(status="Failed")]}, False),
        ):
            with self.subTest(response=response):
                self.files.clear()
                ctx = self.context(response)
                self.assertEqual(await FabricPipelineActivityRuns(ctx), success)
                snapshot = self.resources(MODULE)[0]
                self.assertEqual(snapshot["complete"], success)
                if success:
                    self.assertEqual(snapshot["records"], [])
                else:
                    self.assertNotIn("records", snapshot)
                self.assertNotIn(PRIVATE, json.dumps(self.files))
                self.assert_finished(MODULE, success)

    async def test_retry_uses_durable_cooldown_and_refreshes_rejected_token(self):
        ctx = self.context(
            {"ERROR": "throttled", "status": 429, "retryAfter": "2"},
            {"ERROR": "expired", "status": 401},
            {"value": [activity()]},
        )
        self.assertTrue(await FabricPipelineActivityRuns(ctx))
        self.assertEqual(ctx._safe_activity_query.await_count, 3)
        self.assertGreaterEqual(
            (self.request_times[1] - self.request_times[0]).total_seconds(), 2
        )
        ctx.clients["tenant"].get_headers.assert_any_call(force_refresh=True)
        self.assertFalse(self.files[MODULE + "/request_gate.json"]["pending"])

    async def test_long_cooldown_defers_and_fresh_context_cannot_bypass_it(self):
        ctx = self.context({"ERROR": "throttled", "status": 429, "retryAfter": "3600"})
        self.assertFalse(await FabricPipelineActivityRuns(ctx))
        self.assertIn(MODULE, ctx.deferred_modules)
        ctx._safe_activity_query.assert_awaited_once()
        resumed = self.context()
        self.assertFalse(await FabricPipelineActivityRuns(resumed))
        resumed.clients["tenant"].get_headers.assert_not_called()
        resumed._safe_activity_query.assert_not_awaited()

    async def test_query_transport_posts_documented_array_without_redirects(self):
        ctx = self.context()
        session = _FakeSession(_FakeResponse(200, json_body=[activity()]))
        with patch("env.context.aiohttp.ClientSession", return_value=session):
            result = await Context._safe_activity_query(
                ctx, URL, {"Authorization": "offline"}, activity_query_body(PARENT)
            )
        self.assertEqual(result, {"value": [activity()]})
        method, args, kwargs = session.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(args, (URL,))
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["json"], activity_query_body(PARENT))

    async def test_wrappers_and_unexpected_pagination_are_not_empty_successes(self):
        for body in ({"value": []}, {"value": [], "continuationToken": PRIVATE}, None):
            with self.subTest(body=body):
                ctx = self.context()
                session = _FakeSession(_FakeResponse(200, json_body=body))
                with patch("env.context.aiohttp.ClientSession", return_value=session):
                    result = await Context._safe_activity_query(
                        ctx, URL, {}, activity_query_body(PARENT)
                    )
                self.assertIn("ERROR", result)

    async def test_disallowed_post_routes_and_bodies_never_dispatch_or_authenticate(
        self,
    ):
        body = activity_query_body(PARENT)
        for url, query, extra in (
            (URL, body, {}),
            (
                URL.replace("api.fabric.microsoft.com", "example.invalid"),
                body,
                {"request_gate": AsyncMock()},
            ),
            (
                URL + "?continuationToken=unapproved",
                body,
                {"request_gate": AsyncMock()},
            ),
            (
                ROOT + f"workspaces/{WORKSPACE}/items/{RUN}/jobs/instances",
                body,
                {"request_gate": AsyncMock()},
            ),
            (
                URL,
                {**body, "filters": [{"operand": "secret"}]},
                {"request_gate": AsyncMock()},
            ),
            (URL, body, {"request_gate": AsyncMock(), "json": {}}),
        ):
            with self.subTest(url=url, query=query):
                ctx = self.context()
                with self.assertRaises(ValueError):
                    await ctx.invokeAPI(
                        url,
                        headers=ctx.clients["tenant"].get_headers,
                        activity_query=copy.deepcopy(query),
                        **extra,
                    )
                ctx._safe_activity_query.assert_not_awaited()
                ctx.clients["tenant"].get_headers.assert_not_called()

    async def test_public_dispatch_and_cron_advance_only_successful_checkpoint(self):
        settings = {
            "TENANT_ID": "offline-tenant",
            "CLIENT_ID": "offline-client",
            "CLIENT_SECRET": "offline-placeholder",
            "LAKEHOUSE_NAME": "OfflineLakehouse",
            "WORKSPACE_NAME": "OfflineWorkspace",
            "APPLICATION_MODULES": "FabricPipelineActivityRuns",
            "FABRICPIPELINEACTIVITYRUNS_CRON": "0 1 * * *",
        }
        for success in (True, False):
            with self.subTest(success=success):
                self.files.clear()
                audit = Audits()
                audit.context = self.context(
                    {"value": [activity()]}
                    if success
                    else {"ERROR": "Denied", "status": 403}
                )
                old = "2025-12-01T00:00:00.000000Z"
                state = {MODULE: {"lastRun": old}}
                audit.fm = MagicMock(
                    read=AsyncMock(return_value=state),
                    save=AsyncMock(),
                    read_snapshot=audit.context.fm.read_snapshot,
                    save_snapshot=audit.context.fm.save_snapshot,
                )
                with (
                    patch.object(monitor, "Audits", return_value=audit),
                    patch.object(audit, "_Audits__setup_clients"),
                    patch.object(
                        audit_module, "is_function_due", return_value=True
                    ) as due,
                ):
                    if success:
                        await monitor.main(settings)
                    else:
                        with self.assertRaises(RuntimeError):
                            await monitor.main(settings)
                due.assert_called_once_with(
                    "0 1 * * *", audit.context.convert_dt_str(old)
                )
                self.assertEqual(state[MODULE]["lastRun"] != old, success)
        self.assertIn("FabricPipelineActivityRuns", audit_module.FABRIC_ONLY_MODULES)


class PipelineDiscoveryTests(CollectorTestCase):
    def setUp(self):
        super().setUp()
        setting = patch.dict(
            os.environ,
            {
                "FABRIC_PIPELINE_ACTIVITY_LOOKBACK_HOURS": "24",
                "FABRIC_PIPELINE_ACTIVITY_EXCLUDE_WORKSPACE_IDS": "",
            },
        )
        setting.start()
        self.addCleanup(setting.stop)
        os.environ.pop("FABRIC_PIPELINE_ACTIVITY_SCOPE", None)
        scheduler = SimpleNamespace(
            **{
                **vars(asyncio),
                "get_running_loop": lambda: SimpleNamespace(time=lambda: self.elapsed),
                "sleep": self.sleep,
            }
        )
        for target in (
            "env.modules.fabricpipelineactivityruns.asyncio",
            "env.utility.fabric_collection.asyncio",
        ):
            clock = patch(target, scheduler)
            clock.start()
            self.addCleanup(clock.stop)
        self.pipeline = item(2, "DataPipeline")

    def context(self, *responses):
        ctx = super().context(*responses)
        ctx._safe_activity_query = AsyncMock(side_effect=ctx._safe_get.side_effect)
        return ctx

    def jobs(self, *identities, target=None, token=None):
        result = {
            "value": [
                {
                    "id": identity,
                    "itemId": (target or self.pipeline)["itemId"],
                    "failureReason": PRIVATE,
                }
                for identity in identities
            ]
        }
        if token:
            result["continuationToken"] = token
        return result

    async def test_discovers_pipelines_across_pages_but_never_polls_opted_out_workspaces(
        self,
    ):
        excluded = item(3, "DataPipeline", workspace=CHILD)
        os.environ["FABRIC_PIPELINE_ACTIVITY_EXCLUDE_WORKSPACE_IDS"] = CHILD.upper()
        ctx = self.context(
            inventory(self.pipeline, excluded, item(4), token="next/+=page"),
            inventory(self.pipeline),
            self.jobs(RUN),
            {"value": [activity(input=PRIVATE)]},
        )
        self.assertTrue(await FabricPipelineActivityRuns(ctx))
        self.assertEqual(
            self.urls(ctx),
            [
                ROOT + "admin/items?type=DataPipeline",
                ROOT
                + "admin/items?type=DataPipeline&continuationToken=next%2F%2B%3Dpage",
                ROOT
                + f"workspaces/{WORKSPACE}/items/{self.pipeline['itemId']}/jobs/instances",
            ],
        )
        self.assertGreaterEqual(
            (self.request_times[1] - self.request_times[0]).total_seconds(), 18
        )
        ctx._safe_activity_query.assert_awaited_once()
        parent = self.resources(MODULE)[-1]["parent"]
        self.assertEqual(parent["itemId"], self.pipeline["itemId"])
        self.assertEqual(parent["lastUpdatedAfter"], "2026-01-01T03:04:05.000000Z")
        self.assertEqual(parent["lastUpdatedBefore"], "2026-01-02T03:04:05.000000Z")
        self.assertNotIn(PRIVATE, json.dumps(self.files))
        self.assertTrue(
            self.assert_finished(MODULE, True)["execution"]["sweepComplete"]
        )

    async def test_job_pagination_deduplicates_ids_before_activity_queries(self):
        ctx = self.context(
            inventory(self.pipeline),
            self.jobs(RUN, token="jobs+page"),
            self.jobs(RUN, CHILD),
            {"value": [activity()]},
            {"value": [activity(pipelineRunId=CHILD, activityRunId=CHILD)]},
        )
        self.assertTrue(await FabricPipelineActivityRuns(ctx))
        self.assertTrue(self.urls(ctx)[-1].endswith("?continuationToken=jobs%2Bpage"))
        self.assertEqual(ctx._safe_activity_query.await_count, 2)
        self.assertNotIn(PRIVATE, json.dumps(self.files))

    async def test_no_discovered_pipelines_is_an_explicit_empty_success(self):
        ctx = self.context(inventory())
        self.assertTrue(await FabricPipelineActivityRuns(ctx))
        ctx._safe_activity_query.assert_not_awaited()
        self.assertEqual(self.resources(MODULE)[0]["records"], [])
        self.assert_finished(MODULE, True)

    async def test_invalid_options_fail_before_authentication_or_storage(self):
        for key, value in (
            ("FABRIC_PIPELINE_ACTIVITY_LOOKBACK_HOURS", "0"),
            ("FABRIC_PIPELINE_ACTIVITY_LOOKBACK_HOURS", "1.5"),
            ("FABRIC_PIPELINE_ACTIVITY_LOOKBACK_HOURS", "999999999999999"),
            ("FABRIC_PIPELINE_ACTIVITY_EXCLUDE_WORKSPACE_IDS", PRIVATE),
            ("FABRIC_PIPELINE_ACTIVITY_SCOPE", ""),
        ):
            with (
                self.subTest(key=key, value=value),
                patch.dict(os.environ, {key: value}),
            ):
                ctx = self.context()
                with self.assertRaises(ValueError) as raised:
                    await FabricPipelineActivityRuns(ctx)
                self.assertNotIn(PRIVATE, str(raised.exception))
                ctx.fm.read_snapshot.assert_not_awaited()
                ctx.fm.save_snapshot.assert_not_awaited()
                ctx.clients["tenant"].get_headers.assert_not_called()

    async def test_workspace_exclusion_also_wins_over_explicit_run_scope(self):
        with patch.dict(
            os.environ,
            {
                "FABRIC_PIPELINE_ACTIVITY_SCOPE": json.dumps([PARENT]),
                "FABRIC_PIPELINE_ACTIVITY_EXCLUDE_WORKSPACE_IDS": WORKSPACE,
            },
        ):
            ctx = self.context()
            self.assertTrue(await FabricPipelineActivityRuns(ctx))
        ctx._safe_get.assert_not_awaited()
        ctx._safe_activity_query.assert_not_awaited()

    async def test_failed_or_malformed_inventory_never_becomes_zero_activity(self):
        for response in (
            {"ERROR": PRIVATE, "status": 403},
            {"itemEntities": [{"type": "DataPipeline", "workspaceId": PRIVATE}]},
        ):
            with self.subTest(response=response):
                self.files.clear()
                ctx = self.context(response)
                self.assertFalse(await FabricPipelineActivityRuns(ctx))
                ctx._safe_activity_query.assert_not_awaited()
                snapshot = self.resources(MODULE)[0]
                self.assertFalse(snapshot["complete"])
                self.assertNotIn("records", snapshot)
                self.assertNotIn(PRIVATE, json.dumps(self.files))

    async def test_denied_pipeline_does_not_hide_other_pipeline_results(self):
        second = item(3, "DataPipeline")
        ctx = self.context(
            inventory(self.pipeline, second),
            {"ERROR": PRIVATE, "status": 403},
            self.jobs(RUN, target=second),
            {"value": [activity()]},
        )
        self.assertFalse(await FabricPipelineActivityRuns(ctx))
        self.assertEqual(ctx._safe_get.await_count, 3)
        ctx._safe_activity_query.assert_awaited_once()
        self.assertTrue(self.resources(MODULE)[-1]["complete"])
        manifest = self.assert_finished(MODULE, False)
        self.assertFalse(manifest["execution"]["sweepHealthy"])
        self.assertTrue(manifest["execution"]["sweepComplete"])
        self.assertNotIn(PRIVATE, json.dumps(self.files))

    async def test_wrong_job_parent_or_run_id_never_dispatches_activity_query(self):
        for jobs in (
            {"value": [{"id": RUN, "itemId": CHILD}]},
            {"value": [{"id": PRIVATE, "itemId": self.pipeline["itemId"]}]},
        ):
            with self.subTest(jobs=jobs):
                self.files.clear()
                ctx = self.context(inventory(self.pipeline), jobs)
                self.assertFalse(await FabricPipelineActivityRuns(ctx))
                ctx._safe_activity_query.assert_not_awaited()
                self.assertFalse(self.resources(MODULE)[-1]["complete"])
                self.assertNotIn(PRIVATE, json.dumps(self.files))

    async def test_inventory_resume_keeps_page_cursor_and_original_query_window(self):
        ctx = self.context(
            inventory(self.pipeline, token="next"),
            {"ERROR": "throttled", "status": 429, "retryAfter": "3600"},
        )
        self.assertFalse(await FabricPipelineActivityRuns(ctx))
        saved = copy.deepcopy(self.files[MODULE + "/progress.json"])
        self.assertEqual(saved["continuationToken"], "next")
        blocked = self.context()
        self.assertFalse(await FabricPipelineActivityRuns(blocked))
        blocked.clients["tenant"].get_headers.assert_not_called()
        self.advance(3600)
        resumed = self.context(inventory(), self.jobs())
        self.assertTrue(await FabricPipelineActivityRuns(resumed))
        self.assertEqual(
            self.urls(resumed)[0],
            ROOT + "admin/items?type=DataPipeline&continuationToken=next",
        )
        self.assertEqual(
            self.assert_finished(MODULE, True)["execution"]["window"], saved["window"]
        )

    async def test_activity_resume_does_not_repeat_inventory_or_already_completed_runs(
        self,
    ):
        ctx = self.context(
            inventory(self.pipeline),
            self.jobs(RUN, CHILD),
            {"value": [activity()]},
            {"ERROR": "throttled", "status": 429, "retryAfter": "3600"},
        )
        self.assertFalse(await FabricPipelineActivityRuns(ctx))
        saved = copy.deepcopy(self.files[MODULE + "/progress.json"])
        self.assertEqual(saved["nextRun"], 1)
        self.advance(25 * 3600)
        resumed = self.context({"value": [activity(pipelineRunId=CHILD)]})
        self.assertTrue(await FabricPipelineActivityRuns(resumed))
        resumed._safe_get.assert_not_awaited()
        resumed._safe_activity_query.assert_awaited_once()
        manifest = self.assert_finished(MODULE, True)
        self.assertEqual(manifest["execution"]["window"], saved["window"])
        self.assertEqual(len(manifest["execution"]["evidence"]), 2)
        fresh = self.context(inventory())
        self.assertTrue(await FabricPipelineActivityRuns(fresh))
        self.assertNotEqual(
            self.assert_finished(MODULE, True)["execution"]["window"], saved["window"]
        )

    async def test_scope_change_discards_pending_runs_before_resource_requests(self):
        ctx = self.context(
            inventory(self.pipeline),
            self.jobs(RUN),
            {"ERROR": "throttled", "status": 429, "retryAfter": "3600"},
        )
        self.assertFalse(await FabricPipelineActivityRuns(ctx))
        os.environ["FABRIC_PIPELINE_ACTIVITY_EXCLUDE_WORKSPACE_IDS"] = WORKSPACE
        self.advance(3600)
        resumed = self.context(inventory(self.pipeline))
        self.assertTrue(await FabricPipelineActivityRuns(resumed))
        resumed._safe_get.assert_awaited_once()
        resumed._safe_activity_query.assert_not_awaited()
        self.assertEqual(self.resources(MODULE)[-1]["records"], [])

    async def test_corrupt_progress_blocks_requests_without_disclosing_payload(self):
        self.files[MODULE + "/progress.json"] = {"phase": PRIVATE}
        ctx = self.context()
        with self.assertRaisesRegex(ValueError, "Invalid pipeline activity progress"):
            await FabricPipelineActivityRuns(ctx)
        ctx.clients["tenant"].get_headers.assert_not_called()
        ctx.fm.save_snapshot.assert_not_awaited()

    async def test_invocation_budget_preserves_completed_runs_for_the_next_slice(self):
        ctx = self.context(
            inventory(self.pipeline),
            self.jobs(RUN, CHILD),
            {"value": [activity()]},
        )
        request = ctx._safe_activity_query.side_effect

        async def slow_activity(*args, **kwargs):
            result = await request(*args, **kwargs)
            self.advance(80)
            return result

        ctx._safe_activity_query.side_effect = slow_activity
        self.assertFalse(await FabricPipelineActivityRuns(ctx))
        ctx._safe_activity_query.assert_awaited_once()
        self.assertEqual(self.files[MODULE + "/progress.json"]["nextRun"], 1)
        self.assert_finished(MODULE, False)
        resumed = self.context({"value": [activity(pipelineRunId=CHILD)]})
        self.assertTrue(await FabricPipelineActivityRuns(resumed))
        resumed._safe_get.assert_not_awaited()
        resumed._safe_activity_query.assert_awaited_once()

    async def test_unfinished_manifest_replays_instead_of_skipping_uncommitted_evidence(
        self,
    ):
        ctx = self.context(
            inventory(self.pipeline),
            self.jobs(RUN),
            {"value": [activity()]},
        )
        save = ctx.fm.save_snapshot.side_effect

        async def fail_activity_write(path, name, value):
            if name == f"{WORKSPACE}_{RUN}.json":
                raise RuntimeError("Synthetic storage failure")
            return await save(path, name, value)

        ctx.fm.save_snapshot.side_effect = fail_activity_write
        with self.assertRaisesRegex(RuntimeError, "Synthetic storage failure"):
            await FabricPipelineActivityRuns(ctx)
        self.assertFalse(self.manifests(MODULE)[-1]["finished"])
        self.assertEqual(self.files[MODULE + "/progress.json"]["phase"], "inventory")
        resumed = self.context(
            inventory(self.pipeline),
            self.jobs(RUN),
            {"value": [activity()]},
        )
        self.assertTrue(await FabricPipelineActivityRuns(resumed))
        self.assertEqual(resumed._safe_get.await_count, 2)
        resumed._safe_activity_query.assert_awaited_once()

    async def test_denial_stays_unhealthy_after_resuming(self):
        ctx = self.context(
            inventory(self.pipeline),
            self.jobs(RUN, CHILD),
            {"ERROR": "Denied", "status": 403},
            {"ERROR": "throttled", "status": 429, "retryAfter": "3600"},
        )
        self.assertFalse(await FabricPipelineActivityRuns(ctx))
        self.assertFalse(self.files[MODULE + "/progress.json"]["healthy"])
        self.advance(3600)
        resumed = self.context({"value": [activity(pipelineRunId=CHILD)]})
        self.assertFalse(await FabricPipelineActivityRuns(resumed))
        self.assertTrue(self.resources(MODULE)[-1]["complete"])
        self.assertFalse(
            self.assert_finished(MODULE, False)["execution"]["sweepHealthy"]
        )
        self.assertNotIn(MODULE, resumed.deferred_modules)

    async def test_repeated_discovery_tokens_fail_without_partial_activity_queries(
        self,
    ):
        ctx = self.context(
            inventory(self.pipeline, token="repeat"),
            inventory(self.pipeline, token="repeat"),
        )
        self.assertFalse(await FabricPipelineActivityRuns(ctx))
        self.assertEqual(ctx._safe_get.await_count, 2)
        ctx._safe_activity_query.assert_not_awaited()
        self.assertNotIn("records", self.resources(MODULE)[-1])
