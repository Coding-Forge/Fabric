"""Bounded permission cycles, persisted cursors and linked immutable evidence."""

import copy
import json
import os
from datetime import timedelta
from unittest.mock import AsyncMock, patch

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
            await audit.run()
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
            await audit.run()
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
        with patch.object(audit, "_Audits__setup_clients"):
            await audit.run()
        self.assertEqual(state[MODULE]["lastRun"], old)
        final = self.assert_finished(MODULE, False)
        self.assertIs(final["execution"]["cycleHealthy"], True)
        self.assertIs(final["execution"]["cycleFinished"], False)
        self.assertLessEqual(audit.context._safe_get.await_count, 6)
        self.assertEqual(
            self.files[PROGRESS]["task"], audit.context._safe_get.await_count
        )
