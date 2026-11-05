"""Bounded permission cycles, persisted cursors and linked immutable evidence."""

import copy
import json
import os
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from app import monitor
from env.audit import Audits
from env.context import utc_stamp
from tests.fabric_helpers import ROOT, WORKSPACE, CollectorTestCase, inventory, item

MODULE = "fabricitemaccesspermissions"
PROGRESS = MODULE + "/progress.json"


def access(kind="Notebook"):
    return {
        "principal": {"id": "principal-1", "type": "User"},
        "itemAccessDetails": {
            "type": kind,
            "permissions": ["Read"],
            "additionalPermissions": [],
        },
    }


class PermissionCycleTests(CollectorTestCase):
    def setUp(self):
        super().setUp()
        self.targets = [item(10 + i) for i in range(4)]
        patcher = patch.dict(
            os.environ, {"FABRIC_ITEM_ACCESS_SCOPE": json.dumps(self.targets)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def configure(self, targets):
        os.environ["FABRIC_ITEM_ACCESS_SCOPE"] = json.dumps(targets)

    def evidence_chain(self, final):
        chain = [final]
        seen = set()
        while chain[-1]["execution"]["cycleEvidence"]:
            links = chain[-1]["execution"]["cycleEvidence"]
            self.assertEqual(len(links), 1)
            self.assertNotIn(links[0], seen)
            seen.add(links[0])
            chain.append(self.files[links[0]])
        return chain

    async def test_paginated_inventory_resumes_next_task_after_restart_and_finishes_chain(
        self,
    ):
        token = "a /+?&"
        ctx = self.context(
            inventory(self.targets[0], token=token),
            inventory(*self.targets[1:]),
            {"accessDetails": [access()]},
            {"accessDetails": []},
            {"accessDetails": [access()]},
        )
        self.assertFalse(await self.permissions(ctx))
        self.assertIn(MODULE, ctx.deferred_modules)
        self.assertEqual(ctx._safe_get.await_count, 5)
        progress = copy.deepcopy(self.files[PROGRESS])
        self.assertEqual(progress["task"], 4)
        self.assertIs(progress["inventoryComplete"], True)
        self.assertIs(progress["healthy"], True)
        self.assertEqual(progress["discovered"], [i["itemId"] for i in self.targets])
        first_progress = next(value for path, value in self.writes if path == PROGRESS)
        self.assertEqual(first_progress["token"], token)
        self.assertEqual(first_progress["tokens"], [token])
        self.assertEqual(first_progress["task"], 0)
        self.assertEqual(
            self.urls(ctx)[1],
            ROOT + f"admin/items?workspaceId={WORKSPACE}"
            "&continuationToken=a%20%2F%2B%3F%26",
        )
        self.assertTrue(all(not m["complete"] for m in self.manifests(MODULE)))
        self.assertLessEqual(self.elapsed, 150)
        for earlier, later in zip(self.request_times, self.request_times[1:]):
            self.assertGreaterEqual((later - earlier).total_seconds(), 24)
        before = copy.deepcopy(self.files)
        self.advance(24)
        restarted = self.context({"accessDetails": [access()]})
        self.assertTrue(await self.permissions(restarted))
        self.assertNotIn(MODULE, restarted.deferred_modules)
        self.assertEqual(
            self.urls(restarted),
            [
                ROOT
                + f"admin/workspaces/{WORKSPACE}/items/{self.targets[-1]['itemId']}/users"
            ],
        )
        final = self.assert_finished(MODULE, True)
        chain = self.evidence_chain(final)
        # The sixth slice cannot wait until t=120 within the t=115 admission
        # deadline. Its unattempted deferral remains linked immutable evidence.
        attempted = [m for m in chain if not m["execution"]["deferred"]]
        deferred = [m for m in chain if m["execution"]["deferred"]]
        self.assertEqual(len(attempted), 6)
        self.assertEqual(len(deferred), 1)
        self.assertEqual(len(chain), len(attempted) + len(deferred))
        self.assertTrue(all(m["finished"] for m in chain))
        self.assertTrue(all(m["execution"]["attempts"] == 1 for m in attempted))
        self.assertEqual(deferred[0]["execution"]["attempts"], 0)
        self.assertEqual(deferred[0]["execution"]["nextTask"], progress["task"])
        self.assertIs(deferred[0]["execution"]["cycleHealthy"], True)
        self.assertIs(deferred[0]["complete"], False)
        self.assertEqual(sum(len(m["resources"]) for m in attempted), 6)
        self.assertEqual(len(deferred[0]["resources"]), 1)
        self.assertEqual(self.files[PROGRESS]["task"], 0)
        self.assertEqual(self.files[PROGRESS]["evidence"], [])
        self.assertIs(self.files[PROGRESS]["healthy"], True)
        for path, value in before.items():
            if path.endswith("/manifest.json"):
                self.assertEqual(self.files[path], value)

    async def test_attempted_throttled_inventory_page_advances_fairly_but_marks_cycle_unhealthy(
        self,
    ):
        self.configure([self.targets[0]])
        ctx = self.context(
            inventory(token="next /page"),
            {"ERROR": "throttled", "status": 429, "retryAfter": "3600"},
        )
        self.assertFalse(await self.permissions(ctx))
        self.assertNotIn(MODULE, ctx.deferred_modules)
        # An attempted throttled inventory page advances fairly to the next task,
        # but does not claim the inventory was complete.
        self.assertEqual(self.files[PROGRESS]["task"], 1)
        self.assertIs(self.files[PROGRESS]["inventoryComplete"], False)
        self.assertIs(self.files[PROGRESS]["healthy"], False)
        inventory_pages = self.resources(MODULE)
        self.assertEqual(inventory_pages[0]["records"], [])
        first_manifest = self.manifests(MODULE)[0]
        self.assertEqual(first_manifest["execution"]["nextTask"], 0)
        self.assertTrue(self.urls(ctx)[1].endswith("continuationToken=next%20%2Fpage"))

    async def test_paused_unhealthy_cycle_is_not_reclassified_as_healthy_deferral(self):
        targets = [item(10 + i) for i in range(7)]
        self.configure(targets)
        ctx = self.context(
            inventory(*targets),
            {"ERROR": "denied", "status": 401},
            *[{"accessDetails": []}] * 3,
        )
        self.assertFalse(await self.permissions(ctx))
        self.assertIs(self.files[PROGRESS]["healthy"], False)
        self.assertNotIn(MODULE, ctx.deferred_modules)
        self.files[MODULE + "/request_gate.json"]["nextRequestUtc"] = (
            "2026-01-03T00:00:00.000000Z"
        )
        restarted = self.context()
        self.assertFalse(await self.permissions(restarted))
        restarted._safe_get.assert_not_awaited()
        self.assertNotIn(MODULE, restarted.deferred_modules)
        self.assertIs(self.files[PROGRESS]["healthy"], False)
        restarted.logger.warning.assert_called()

    async def test_unattempted_defer_preserves_inventory_token_and_health(self):
        self.configure([self.targets[0]])
        # Simulate request duration as well as the scheduler's inter-slice delay.
        ctx = self.context(inventory(token="page/2"), inventory(token="page/3"))
        request = ctx._safe_get.side_effect

        async def slow_request(*args, **kwargs):
            response = await request(*args, **kwargs)
            self.advance(30)
            return response

        ctx._safe_get.side_effect = slow_request
        # Inject a long gate after page two; the next slice must defer without an attempt.
        save = ctx.fm.save_snapshot.side_effect

        async def cooldown_after_second_page(path, name, value):
            await save(path, name, value)
            if name == "progress.json" and value["token"] == "page/3":
                self.files[MODULE + "/request_gate.json"]["nextRequestUtc"] = (
                    "2026-01-03T00:00:00.000000Z"
                )

        ctx.fm.save_snapshot.side_effect = cooldown_after_second_page
        self.assertFalse(await self.permissions(ctx))
        progress = self.files[PROGRESS]
        self.assertEqual(progress["task"], 0)
        self.assertEqual(progress["token"], "page/3")
        self.assertEqual(progress["tokens"], ["page/2", "page/3"])
        self.assertIs(progress["healthy"], True)
        self.assertEqual(ctx._safe_get.await_count, 2)
        restarted = self.context(inventory(self.targets[0]), {"accessDetails": []})
        self.assertFalse(await self.permissions(restarted))
        self.assertIn(MODULE, restarted.deferred_modules)
        restarted._safe_get.assert_not_awaited()
        self.assertEqual(self.files[PROGRESS]["token"], "page/3")
        self.assertIs(self.files[PROGRESS]["healthy"], True)
        self.advance(86400)
        self.assertTrue(await self.permissions(restarted))
        self.assertTrue(self.urls(restarted)[0].endswith("continuationToken=page%2F3"))

    async def test_failed_target_does_not_starve_later_targets_and_next_cycle_can_succeed(
        self,
    ):
        targets = self.targets[:2]
        self.configure(targets)
        ctx = self.context(
            inventory(*targets),
            {"ERROR": "denied", "status": 403},
            {"accessDetails": []},
        )
        self.assertFalse(await self.permissions(ctx))
        resources = self.resources(MODULE)
        self.assertEqual([r["complete"] for r in resources], [True, False, True])
        self.assertEqual(resources[-1]["parent"], targets[1])
        self.assertNotIn("records", resources[1])
        final = self.assert_finished(MODULE, False)
        self.assertIs(final["execution"]["cycleFinished"], True)
        self.assertIs(final["execution"]["cycleHealthy"], False)
        self.assertEqual(len(self.evidence_chain(final)), 3)
        self.assertEqual(self.files[PROGRESS]["task"], 0)
        self.advance(24)
        self.assertTrue(
            await self.permissions(
                self.context(
                    inventory(*targets), {"accessDetails": []}, {"accessDetails": []}
                )
            )
        )
        self.assertEqual(
            len(self.evidence_chain(self.assert_finished(MODULE, True))), 3
        )

    async def test_missing_inventory_item_is_incomplete_without_requesting_its_permissions(
        self,
    ):
        self.configure(self.targets[:2])
        ctx = self.context(inventory(self.targets[1]), {"accessDetails": []})
        self.assertFalse(await self.permissions(ctx))
        self.assertEqual(ctx._safe_get.await_count, 2)
        resources = self.resources(MODULE)
        self.assertNotIn("records", resources[1])
        self.assertEqual(resources[2]["parent"], self.targets[1])
        self.assertEqual(resources[2]["records"], [])
        self.assert_finished(MODULE, False)

    async def test_invalid_inventory_context_and_repeated_pagination_are_incomplete(
        self,
    ):
        self.configure(self.targets[:1])
        wrong_workspace = item(workspace=item(99)["itemId"])
        for pages in (
            [inventory(wrong_workspace)],
            [inventory({**self.targets[0], "type": "Report"})],
            [
                inventory(self.targets[0], token="repeat"),
                inventory(self.targets[0], token="repeat"),
            ],
        ):
            with self.subTest(pages=pages):
                self.files.clear()
                ctx = self.context(*pages)
                self.assertFalse(await self.permissions(ctx))
                self.assert_finished(MODULE, False)
                self.assertTrue(any(not r["complete"] for r in self.resources(MODULE)))
                self.assertFalse(any("/users" in url for url in self.urls(ctx)))
                self.advance(24)

    async def test_identical_inventory_page_overlap_keeps_distinct_targets(self):
        self.configure(self.targets[:2])
        ctx = self.context(
            inventory(self.targets[0], token="next"),
            inventory(*self.targets[:2]),
            {"accessDetails": [access()]},
            {"accessDetails": []},
        )
        self.assertTrue(await self.permissions(ctx))
        inventories = [
            resource
            for resource in self.resources(MODULE)
            if resource["parent"].get("observationUnit") == "inventoryPage"
        ]
        self.assertEqual(
            [
                record["itemId"]
                for resource in inventories
                for record in resource["records"]
            ],
            [target["itemId"] for target in self.targets[:2]],
        )
        self.assertEqual(ctx._safe_get.await_count, 4)
        self.assert_finished(MODULE, True)

    async def test_conflicting_type_on_overlapping_page_still_fails_inventory(self):
        self.configure(self.targets[:1])
        ctx = self.context(
            inventory(self.targets[0], token="next"),
            inventory({**self.targets[0], "type": "Report"}),
        )
        self.assertFalse(await self.permissions(ctx))
        self.assert_finished(MODULE, False)
        self.assertFalse(any("/users" in url for url in self.urls(ctx)))

    async def test_permission_schema_and_unexpected_pagination_fail_not_empty_success(
        self,
    ):
        self.configure(self.targets[:1])
        for response in (
            {"accessDetails": [{**access(), "principal": {"type": "User"}}]},
            {"accessDetails": [access("Report")]},
            {
                "accessDetails": [
                    {
                        **access(),
                        "itemAccessDetails": {"type": "Notebook", "permissions": [123]},
                    }
                ]
            },
            {"accessDetails": [], "continuationToken": "not-supported"},
            {},
        ):
            with self.subTest(response=response):
                self.files.clear()
                ctx = self.context(inventory(self.targets[0]), response)
                self.assertFalse(await self.permissions(ctx))
                self.assertNotIn("records", self.resources(MODULE)[-1])
                self.assert_finished(MODULE, False)
                self.advance(24)

    async def test_report_access_uses_type_query_and_retains_valid_permission_details(
        self,
    ):
        target = item(kind="Report")
        self.configure([target])
        ctx = self.context(inventory(target), {"accessDetails": [access("Report")]})
        self.assertTrue(await self.permissions(ctx))
        self.assertEqual(
            self.urls(ctx)[-1],
            ROOT
            + f"admin/workspaces/{WORKSPACE}/items/{target['itemId']}/users?type=Report",
        )
        resource = self.resources(MODULE)[-1]
        self.assertEqual(resource["parent"], target)
        self.assertEqual(resource["records"], [access("Report")])

    async def test_query_typed_power_bi_null_metadata_is_preserved(self):
        for kind in ("Report", "Dashboard", "SemanticModel", "App", "Dataflow"):
            for detail_type, additional in (
                (None, None),
                (None, ["ReadAll"]),
                (kind, None),
            ):
                with self.subTest(
                    kind=kind, detail_type=detail_type, additional=additional
                ):
                    self.files.clear()
                    target = item(kind=kind)
                    self.configure([target])
                    record = access(kind)
                    record["itemAccessDetails"].update(
                        type=detail_type, additionalPermissions=additional
                    )
                    ctx = self.context(inventory(target), {"accessDetails": [record]})
                    self.assertTrue(await self.permissions(ctx))
                    resource = self.resources(MODULE)[-1]
                    self.assertEqual(resource["parent"], target)
                    self.assertEqual(resource["records"], [record])
                    self.assertTrue(self.urls(ctx)[-1].endswith(f"/users?type={kind}"))
                    self.assert_finished(MODULE, True)
                    self.advance(24)

    async def test_null_compatibility_still_rejects_malformed_or_conflicting_access(
        self,
    ):
        cases = []
        for change in (
            {"type": "Dashboard"},
            {"type": 123},
            {"permissions": None},
            {"permissions": [123]},
            {"additionalPermissions": "ReadAll"},
            {"additionalPermissions": [123]},
        ):
            record = access("Report")
            record["itemAccessDetails"].update(change)
            cases.append(("Report", record))
        missing_type = access("Report")
        del missing_type["itemAccessDetails"]["type"]
        cases.append(("Report", missing_type))
        for principal in (
            None,
            {"id": None, "type": "User"},
            {"id": "p", "type": None},
        ):
            cases.append(("Report", {**access("Report"), "principal": principal}))
        for change in ({"type": None}, {"additionalPermissions": None}):
            record = access()
            record["itemAccessDetails"].update(change)
            cases.append(("Notebook", record))
        for kind, record in cases:
            with self.subTest(kind=kind, record=record):
                self.files.clear()
                target = item(kind=kind)
                self.configure([target])
                ctx = self.context(inventory(target), {"accessDetails": [record]})
                self.assertFalse(await self.permissions(ctx))
                self.assertNotIn("records", self.resources(MODULE)[-1])
                self.assert_finished(MODULE, False)
                self.advance(24)

    async def test_multiple_workspaces_reset_discovery_and_keep_correct_parent(self):
        targets = [self.targets[0], item(20, workspace=item(90)["itemId"])]
        self.configure(targets)
        ctx = self.context(
            inventory(targets[0]),
            {"accessDetails": []},
            inventory(targets[1]),
            {"accessDetails": []},
        )
        self.assertTrue(await self.permissions(ctx))
        resources = self.resources(MODULE)
        self.assertEqual(resources[1]["parent"], targets[0])
        self.assertEqual(resources[3]["parent"], targets[1])
        self.assertIn(f"workspaceId={targets[1]['workspaceId']}", self.urls(ctx)[2])

    async def test_request_duration_is_counted_in_150_second_admission_budget(self):
        budget, reserve, request_duration, max_slices = 150, 35, 30, 6
        started = self.now
        ctx = self.context(inventory(*self.targets), *[{"accessDetails": []}] * 4)
        request = ctx._safe_get.side_effect

        async def slow_request(*args, **kwargs):
            response = await request(*args, **kwargs)
            self.advance(request_duration)
            return response

        ctx._safe_get.side_effect = slow_request
        self.assertFalse(await self.permissions(ctx))
        # Thirty-second requests already outlast the durable pacing gate, so
        # no fixed inter-slice sleep should consume additional admission budget.
        admitted_starts = list(range(0, budget - reserve + 1, request_duration))[
            :max_slices
        ]
        self.assertEqual(ctx._safe_get.await_count, len(admitted_starts))
        self.assertEqual(
            [(stamp - started).total_seconds() for stamp in self.request_times],
            admitted_starts,
        )
        self.assertEqual(self.elapsed, len(admitted_starts) * request_duration)
        self.assertLessEqual(admitted_starts[-1] + reserve, budget)
        self.assertGreater(self.elapsed + reserve, budget)
        self.assertLessEqual(self.elapsed, budget)
        self.sleep.assert_not_awaited()
        self.assertEqual(self.files[PROGRESS]["task"], len(admitted_starts))
        self.assertIs(self.files[PROGRESS]["healthy"], True)

    async def test_two_second_remaining_gate_wait_progresses_in_same_invocation(self):
        self.configure(self.targets[:1])
        ctx = self.context(inventory(self.targets[0]), {"accessDetails": []})
        request = ctx._safe_get.side_effect
        started = self.now
        reservations = []

        async def observed_request(*args, **kwargs):
            ledger = copy.deepcopy(self.files[MODULE + "/request_gate.json"])
            self.assertIs(ledger["pending"], True)
            self.assertEqual(
                ledger["nextRequestUtc"],
                utc_stamp(self.now + timedelta(seconds=24)),
            )
            reservations.append(ledger)
            response = await request(*args, **kwargs)
            self.advance(22)
            return response

        ctx._safe_get.side_effect = observed_request
        self.assertTrue(await self.permissions(ctx))
        self.sleep.assert_awaited_once_with(2)
        self.assertEqual(
            [(stamp - started).total_seconds() for stamp in self.request_times],
            [0, 24],
        )
        self.assertEqual(len(reservations), 2)
        manifests = self.manifests(MODULE)
        self.assertEqual([m["execution"]["attempts"] for m in manifests], [1, 1])
        self.assertTrue(all(not m["execution"]["deferred"] for m in manifests))
        self.assertEqual(self.files[PROGRESS]["task"], 0)
        self.assertIs(self.files[PROGRESS]["healthy"], True)
        self.assert_finished(MODULE, True)

    async def test_scope_changes_and_corrupt_cursor_block_before_http(self):
        self.configure(self.targets[:1])
        # Finish the first attempt with a transport timeout so the cursor stays on
        # inventory with its saved token and evidence.
        ctx = self.context(inventory(token="next"), TimeoutError())
        self.assertFalse(await self.permissions(ctx))
        saved = copy.deepcopy(self.files[PROGRESS])
        self.configure(self.targets[:2])
        restarted = self.context()
        with self.assertRaisesRegex(ValueError, "scope changed"):
            await self.permissions(restarted)
        restarted._safe_get.assert_not_awaited()
        self.configure(self.targets[:1])
        for changes in (
            {"task": True},
            {"task": 99},
            {"tokens": ["different"]},
            {"evidence": ["one", "two"]},
            {"healthy": "true"},
        ):
            with self.subTest(changes=changes):
                self.files[PROGRESS] = {**saved, **changes}
                with self.assertRaisesRegex(RuntimeError, "progress"):
                    await self.permissions(restarted)
                restarted._safe_get.assert_not_awaited()

    async def test_manifest_failure_does_not_commit_cursor(self):
        self.configure(self.targets[:1])
        ctx = self.context(inventory(self.targets[0]))
        save = ctx.fm.save_snapshot.side_effect

        async def fail_manifest(path, name, value):
            if name == "manifest.json" and value["finished"]:
                raise RuntimeError("Cannot commit manifest")
            await save(path, name, value)

        ctx.fm.save_snapshot.side_effect = fail_manifest
        with self.assertRaisesRegex(RuntimeError, "Cannot commit manifest"):
            await self.permissions(ctx)
        self.assertNotIn(PROGRESS, self.files)
        self.assertIs(self.manifests(MODULE)[0]["finished"], False)

    async def test_real_dispatch_only_advances_checkpoint_after_completed_healthy_cycle(
        self,
    ):
        self.configure(self.targets[:1])
        old = "2025-12-01T00:00:00.000000Z"
        state = {MODULE: {"lastRun": old}}
        audit = Audits()
        audit.context = self.context(
            inventory(self.targets[0]),
            {"ERROR": "throttled", "status": 429, "retryAfter": "3600"},
        )
        audit.context.ApplicationModules = "FabricItemAccessPermissions"
        audit.fm = audit.context.fm
        audit.fm.read = AsyncMock(return_value=state)
        audit.fm.save = AsyncMock()
        # Leave the collector and public dispatch registration real.
        with patch.object(audit, "_Audits__setup_clients"):
            self.assertIs(await audit.run(), False)
        self.assertEqual(state[MODULE]["lastRun"], old)
        self.assert_finished(MODULE, False)
        # The failed cycle resets; a later healthy cycle alone earns a checkpoint.
        self.advance(3600)
        audit.context = self.context(inventory(self.targets[0]), {"accessDetails": []})
        audit.context.ApplicationModules = "FabricItemAccessPermissions"
        audit.fm = audit.context.fm
        audit.fm.read = AsyncMock(return_value=state)
        audit.fm.save = AsyncMock()
        with patch.object(audit, "_Audits__setup_clients"):
            self.assertIs(await audit.run(), True)
        self.assertNotEqual(state[MODULE]["lastRun"], old)
        self.assert_finished(MODULE, True)

    async def test_healthy_but_unfinished_cycle_does_not_advance_checkpoint(self):
        old = "2025-12-01T00:00:00.000000Z"
        state = {MODULE: {"lastRun": old}}
        # Seven selected items plus inventory cannot fit in the six-slice cap;
        # the remaining targets must wait for another scheduler invocation.
        targets = [item(10 + i) for i in range(7)]
        self.configure(targets)
        audit = Audits()
        audit.context = self.context(inventory(*targets), *[{"accessDetails": []}] * 6)
        audit.context.ApplicationModules = "FabricItemAccessPermissions"
        audit.fm = audit.context.fm
        audit.fm.read = AsyncMock(return_value=state)
        audit.fm.save = AsyncMock()
        with (
            patch.object(audit, "_Audits__setup_clients"),
            patch.object(monitor.config, "build_audit", return_value=audit),
        ):
            await monitor.main()
        audit.context.logger.error.assert_not_called()
        audit.context.logger.warning.assert_not_called()
        audit.context.logger.info.assert_any_call(
            "Run finished: %d succeeded, %d deferred, %d failed. "
            "Deferred: %s. Failed: %s.",
            0,
            1,
            0,
            "FabricItemAccessPermissions",
            "none",
        )
        coverage = [
            call
            for call in audit.context.logger.info.call_args_list
            if call.args[0] == "%s coverage: %s"
        ]
        self.assertEqual(len(coverage), 1)
        self.assertEqual(state[MODULE]["lastRun"], old)
        final = self.assert_finished(MODULE, False)
        self.assertIs(final["execution"]["cycleHealthy"], True)
        self.assertIs(final["execution"]["cycleFinished"], False)
        self.assertLessEqual(audit.context._safe_get.await_count, 6)
        self.assertEqual(
            self.files[PROGRESS]["task"], audit.context._safe_get.await_count
        )


TENANT_MODULE = MODULE + "_tenant"
TENANT_PROGRESS = MODULE + "/tenant_progress.json"


class TenantPermissionTests(CollectorTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch.dict(
            os.environ,
            {
                "FABRIC_ITEM_ACCESS_MODE": "tenant",
                "FABRIC_ITEM_ACCESS_SCOPE": "ignored in opt-in tenant mode",
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_nullable_power_bi_metadata_is_preserved_in_tenant_cycle(self):
        targets = [
            item(10 + i, kind)
            for i, kind in enumerate(("Report", "SemanticModel", "App", "Dashboard"))
        ]
        records = []
        for target in targets:
            record = access(target["type"])
            record["itemAccessDetails"].update(type=None, additionalPermissions=None)
            records.append(record)
        ctx = self.context(
            inventory(*targets),
            *[{"accessDetails": [record]} for record in records],
        )
        self.assertTrue(await self.permissions(ctx))
        resources = self.resources(TENANT_MODULE)[1:]
        self.assertEqual([resource["parent"] for resource in resources], targets)
        self.assertEqual(
            [resource["records"] for resource in resources], [[r] for r in records]
        )
        self.assertEqual(ctx._safe_get.await_count, 5)
        self.assertTrue(
            self.assert_finished(TENANT_MODULE, True)["execution"]["cycleHealthy"]
        )

    async def test_discovers_more_than_fifty_items_across_workspaces_and_resumes(self):
        targets = [
            item(
                100 + i,
                kind="Report" if i == 0 else "Notebook",
                workspace=WORKSPACE if i < 30 else item(99)["itemId"],
            )
            for i in range(55)
        ]
        scoped_progress = {"existing": "scoped cycle must not change"}
        self.files[PROGRESS] = scoped_progress
        ctx = self.context(inventory(*targets), *[{"accessDetails": []}] * len(targets))
        for _ in range(20):
            complete = await self.permissions(ctx)
            if complete:
                break
            self.assertIn(MODULE, ctx.deferred_modules)
            self.advance(24)
        self.assertTrue(complete)
        self.assertEqual(ctx._safe_get.await_count, len(targets) + 1)
        self.assertEqual(self.files[PROGRESS], scoped_progress)
        self.assertEqual(self.urls(ctx)[0], ROOT + "admin/items?state=active")
        self.assertTrue(self.urls(ctx)[1].endswith("/users?type=Report"))
        self.assertEqual(
            {
                tuple(sorted(r["parent"].items()))
                for r in self.resources(TENANT_MODULE)[1:]
            },
            {tuple(sorted(target.items())) for target in targets},
        )
        for earlier, later in zip(self.request_times, self.request_times[1:]):
            self.assertGreaterEqual((later - earlier).total_seconds(), 24)
        final = self.assert_finished(TENANT_MODULE, True)
        self.assertEqual(final["execution"]["discoveredItems"], 55)
        self.assertEqual(final["execution"]["scopeMode"], "tenant")
        self.assertTrue(final["execution"]["inventoryComplete"])
        self.assertNotIn(MODULE, ctx.deferred_modules)
        self.assertEqual(self.files[TENANT_PROGRESS]["items"], [])
        self.assertIn(MODULE + "/request_gate.json", self.files)
        self.assertNotIn(TENANT_MODULE + "/request_gate.json", self.files)

    async def test_paginated_discovery_deduplicates_and_links_slices_across_restart(
        self,
    ):
        targets = [item(10 + i) for i in range(3)]
        token = "page /+?&"
        ctx = self.context(
            inventory(targets[0], token=token),
            inventory(*targets[:2], token="last"),
            inventory(*targets[1:]),
            {"accessDetails": []},
            {"accessDetails": []},
        )
        self.assertFalse(await self.permissions(ctx))
        progress = self.files[TENANT_PROGRESS]
        self.assertEqual(progress["items"], targets)
        self.assertEqual(progress["phase"], "access")
        self.assertEqual(progress["cursor"], 2)
        self.assertTrue(progress["healthy"])
        self.assertTrue(
            self.urls(ctx)[1].endswith("continuationToken=page%20%2F%2B%3F%26")
        )
        self.advance(24)
        restarted = self.context({"accessDetails": [access()]})
        self.assertTrue(await self.permissions(restarted))
        final = self.assert_finished(TENANT_MODULE, True)
        chain = [final]
        while chain[-1]["execution"]["cycleEvidence"]:
            link = chain[-1]["execution"]["cycleEvidence"][0]
            chain.append(self.files[link])
        self.assertEqual(sum(m["execution"]["attempts"] for m in chain), 6)
        self.assertEqual(len(chain), 7)
        self.assertTrue(all(m["finished"] for m in chain))
        discovered = [
            row
            for resource in self.resources(TENANT_MODULE)
            if resource["parent"].get("observationUnit") == "inventoryPage"
            for row in resource.get("records", [])
        ]
        self.assertEqual(discovered, targets)
        self.assertTrue(
            all(
                resource["requestPath"] == "admin/items?state=active"
                for resource in self.resources(TENANT_MODULE)
                if resource["parent"].get("observationUnit") == "inventoryPage"
            )
        )

    async def test_healthy_inventory_pause_resumes_the_saved_page_before_access(self):
        target = item()
        ctx = self.context(*[inventory(target, token=f"page-{i}") for i in range(4)])
        request = ctx._safe_get.side_effect

        async def slow_page(*args, **kwargs):
            response = await request(*args, **kwargs)
            self.advance(30)
            return response

        ctx._safe_get.side_effect = slow_page
        self.assertFalse(await self.permissions(ctx))
        self.assertEqual(self.files[TENANT_PROGRESS]["token"], "page-3")
        self.assertTrue(self.files[TENANT_PROGRESS]["healthy"])
        self.assertIn(MODULE, ctx.deferred_modules)
        restarted = self.context(inventory(target), {"accessDetails": []})
        self.assertTrue(await self.permissions(restarted))
        self.assertTrue(self.urls(restarted)[0].endswith("continuationToken=page-3"))
        self.assertEqual(
            self.assert_finished(TENANT_MODULE, True)["execution"]["discoveredItems"], 1
        )

    async def test_empty_active_inventory_is_success_without_access_requests(self):
        ctx = self.context(inventory())
        self.assertTrue(await self.permissions(ctx))
        self.assertEqual(ctx._safe_get.await_count, 1)
        self.assertEqual(self.resources(TENANT_MODULE)[0]["records"], [])
        final = self.assert_finished(TENANT_MODULE, True)
        self.assertEqual(final["execution"]["discoveredItems"], 0)

    async def test_unsupported_and_denied_items_are_not_empty_success_and_do_not_starve(
        self,
    ):
        targets = [item(10, "FutureType"), item(11), item(12)]
        ctx = self.context(
            inventory(*targets),
            {"ERROR": "unsupported", "status": 400, "errorCode": "InvalidItemType"},
            {"ERROR": "denied", "status": 403},
            {"accessDetails": []},
        )
        self.assertFalse(await self.permissions(ctx))
        manifests = self.manifests(TENANT_MODULE)
        self.assertEqual(
            [m["execution"]["resourceOutcome"] for m in manifests],
            ["succeeded", "unsupported", "denied", "succeeded"],
        )
        resources = self.resources(TENANT_MODULE)
        self.assertNotIn("records", resources[1])
        self.assertNotIn("records", resources[2])
        self.assertEqual(resources[-1]["records"], [])
        final = self.assert_finished(TENANT_MODULE, False)
        self.assertTrue(final["execution"]["cycleFinished"])
        self.assertFalse(final["execution"]["cycleHealthy"])
        self.assertNotIn(MODULE, ctx.deferred_modules)
        self.assertEqual(self.files[TENANT_PROGRESS]["items"], [])

    async def test_failed_inventory_retains_cursor_and_does_not_claim_complete_discovery(
        self,
    ):
        ctx = self.context(
            inventory(item(), token="next"),
            {"ERROR": "throttled", "status": 429, "retryAfter": "3600"},
        )
        self.assertFalse(await self.permissions(ctx))
        saved = self.files[TENANT_PROGRESS]
        self.assertEqual(saved["phase"], "inventory")
        self.assertEqual(saved["token"], "next")
        self.assertFalse(saved["healthy"])
        final = self.assert_finished(TENANT_MODULE, False)
        self.assertFalse(final["execution"]["inventoryComplete"])
        self.assertNotIn(MODULE, ctx.deferred_modules)
        self.advance(3600)
        restarted = self.context(inventory(), {"accessDetails": []})
        self.assertFalse(await self.permissions(restarted))
        self.assertTrue(self.urls(restarted)[0].endswith("continuationToken=next"))
        self.assertTrue(
            self.assert_finished(TENANT_MODULE, False)["execution"]["cycleFinished"]
        )

    async def test_invalid_inventory_and_repeated_tokens_never_publish_complete_discovery(
        self,
    ):
        for pages in (
            [inventory({**item(), "type": "../bad"})],
            [
                {
                    "itemEntities": [
                        {"id": "invalid", "workspaceId": WORKSPACE, "type": "Notebook"}
                    ]
                }
            ],
            [
                {
                    "itemEntities": [
                        {
                            "id": item()["itemId"],
                            "workspaceId": WORKSPACE,
                            "type": "Notebook",
                            "state": "Deleted",
                        }
                    ]
                }
            ],
            [inventory(item(), token="next"), inventory({**item(), "type": "Report"})],
            [inventory(item(), token="same"), inventory(item(), token="same")],
        ):
            with self.subTest(pages=pages):
                self.files.clear()
                ctx = self.context(*pages)
                self.assertFalse(await self.permissions(ctx))
                self.assertFalse(any("/users" in url for url in self.urls(ctx)))
                final = self.assert_finished(TENANT_MODULE, False)
                self.assertFalse(final["execution"]["inventoryComplete"])
                self.assertFalse(self.files[TENANT_PROGRESS]["healthy"])

    async def test_inherits_scoped_cooldown_and_blocks_unacknowledged_attempt(self):
        self.files[MODULE + "/request_gate.json"] = {
            "nextRequestUtc": utc_stamp(self.now + timedelta(seconds=48)),
            "blocked": False,
            "pending": False,
        }
        started = self.now
        ctx = self.context(inventory())
        self.assertTrue(await self.permissions(ctx))
        self.assertEqual((self.request_times[0] - started).total_seconds(), 48)
        self.files[MODULE + "/request_gate.json"]["pending"] = True
        restarted = self.context()
        self.assertFalse(await self.permissions(restarted))
        restarted._safe_get.assert_not_awaited()
        restarted.clients["tenant"].get_headers.assert_not_called()

    async def test_corrupt_progress_and_missing_committed_evidence_block_before_http(
        self,
    ):
        ctx = self.context(inventory(item(), token="next"))
        save = ctx.fm.save_snapshot.side_effect

        async def pause_inventory(path, name, value):
            await save(path, name, value)
            if name == "tenant_progress.json":
                self.files[MODULE + "/request_gate.json"]["nextRequestUtc"] = (
                    "2026-01-03T00:00:00.000000Z"
                )

        ctx.fm.save_snapshot.side_effect = pause_inventory
        self.assertFalse(await self.permissions(ctx))
        saved = copy.deepcopy(self.files[TENANT_PROGRESS])
        for changes in (
            {"cursor": True},
            {"phase": "other"},
            {"items": [{"itemId": "invalid"}]},
            {"tokens": ["wrong"]},
            {"evidence": ["../outside/manifest.json"]},
            {"schemaVersion": True},
        ):
            with self.subTest(changes=changes):
                self.files[TENANT_PROGRESS] = {**saved, **changes}
                restarted = self.context()
                with self.assertRaisesRegex(RuntimeError, "permission"):
                    await self.permissions(restarted)
                restarted._safe_get.assert_not_awaited()
        self.files[TENANT_PROGRESS] = saved
        del self.files[saved["evidence"][0]]
        restarted = self.context()
        with self.assertRaisesRegex(RuntimeError, "Uncommitted"):
            await self.permissions(restarted)
        restarted._safe_get.assert_not_awaited()

    async def test_manifest_failure_does_not_commit_tenant_cursor(self):
        ctx = self.context(inventory(item()))
        save = ctx.fm.save_snapshot.side_effect

        async def fail_manifest(path, name, value):
            if name == "manifest.json" and value["finished"]:
                raise RuntimeError("Cannot commit manifest")
            await save(path, name, value)

        ctx.fm.save_snapshot.side_effect = fail_manifest
        with self.assertRaisesRegex(RuntimeError, "Cannot commit manifest"):
            await self.permissions(ctx)
        self.assertNotIn(TENANT_PROGRESS, self.files)

    async def test_only_healthy_full_tenant_cycle_advances_audit_checkpoint(self):
        old = "2025-12-01T00:00:00.000000Z"
        state = {MODULE: {"lastRun": old}}
        for response, expected in (
            ({"ERROR": "denied", "status": 401}, False),
            ({"accessDetails": []}, True),
        ):
            self.advance(24)
            audit = Audits()
            audit.context = self.context(inventory(item()), response)
            audit.context.ApplicationModules = "FabricItemAccessPermissions"
            audit.fm = audit.context.fm
            audit.fm.read = AsyncMock(return_value=state)
            audit.fm.save = AsyncMock()
            with patch.object(audit, "_Audits__setup_clients"):
                self.assertIs(await audit.run(), expected)
            self.assertEqual(state[MODULE]["lastRun"] == old, not expected)

    async def test_invalid_mode_does_not_fall_back_to_broader_collection(self):
        os.environ["FABRIC_ITEM_ACCESS_MODE"] = "tennat"
        ctx = self.context()
        with self.assertRaisesRegex(ValueError, "MODE"):
            await self.permissions(ctx)
        ctx._safe_get.assert_not_awaited()
