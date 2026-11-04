"""B1-B3: catalog polling caps, error handling and lastFullScan persistence."""

import asyncio
import os
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from env.context import utc_now
from env.modules import catalog
from env.utility.file_management import File_Management
from tests.helpers import make_context

FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _ts(days_ago):
    return (utc_now() - timedelta(days=days_ago)).strftime(FMT)


def _make_invoke(workspace_ids=("w1",), get_info=None, status=None, scan_result=None, modified=None):
    """Build an ``invokeAPI`` fake routed on the URL."""
    calls = []

    async def invoke(rest_api, headers=None, json=None):
        calls.append(rest_api)
        if rest_api.startswith("admin/workspaces/modified"):
            return modified if modified is not None else {"value": [{"id": i} for i in workspace_ids]}
        if rest_api.startswith("admin/workspaces/getInfo"):
            return get_info if get_info is not None else {"id": "scan1", "status": "Running"}
        if rest_api.startswith("admin/workspaces/scanStatus"):
            return status() if callable(status) else (status or {"status": "Succeeded"})
        if rest_api.startswith("admin/workspaces/scanResult"):
            return scan_result if scan_result is not None else {"workspaces": []}
        raise AssertionError(rest_api)

    invoke.calls = calls
    return invoke


def _count(invoke, prefix):
    return sum(1 for c in invoke.calls if c.startswith(prefix))


class CatalogTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sleep = AsyncMock()
        p = patch.object(catalog.asyncio, "sleep", self.sleep)
        p.start()
        self.addCleanup(p.stop)

    def _state(self, last_run_days=1, full_scan_days=None):
        cat = {"lastRun": _ts(last_run_days)}
        if full_scan_days is not None:
            cat["lastFullScan"] = _ts(full_scan_days)
        return {"catalog": cat}

    async def test_requires_context(self):
        with self.assertRaises(RuntimeError):
            await catalog.main(None)

    async def test_full_scan_persists_last_full_scan(self):
        state = self._state()
        ctx = make_context(state, _make_invoke())
        self.assertTrue(await catalog.main(ctx))
        stamp = state["catalog"]["lastFullScan"]
        self.assertLess(abs(utc_now() - datetime.strptime(stamp, FMT)), timedelta(minutes=1))
        name = ctx.fm.save.await_args.kwargs["file_name"]
        self.assertIn("fullscan", name)

    async def test_recent_full_scan_is_incremental_and_not_rewritten(self):
        state = self._state(full_scan_days=5)
        before = state["catalog"]["lastFullScan"]
        ctx = make_context(state, _make_invoke())
        self.assertTrue(await catalog.main(ctx))
        self.assertEqual(state["catalog"]["lastFullScan"], before)
        self.assertNotIn("fullscan", ctx.fm.save.await_args.kwargs["file_name"])

    async def test_stale_full_scan_triggers_new_full_scan(self):
        state = self._state(full_scan_days=catalog.FullScanAfterDays + 1)
        old = state["catalog"]["lastFullScan"]
        ctx = make_context(state, _make_invoke())
        await catalog.main(ctx)
        self.assertNotEqual(state["catalog"]["lastFullScan"], old)

    async def test_missing_catalog_state_does_not_crash(self):
        state = {}
        ctx = make_context(state, _make_invoke())
        self.assertTrue(await catalog.main(ctx))
        self.assertIn("lastFullScan", state["catalog"])

    async def test_last_full_scan_not_persisted_when_scan_fails(self):
        state = self._state()
        ctx = make_context(state, _make_invoke(get_info={"ERROR": "HTTP 429"}))
        self.assertIs(await catalog.main(ctx), False)
        self.assertNotIn("lastFullScan", state["catalog"])

    async def test_polling_sleeps_between_status_checks(self):
        statuses = iter([{"status": "Running"}, {"status": "Running"}, {"status": "Succeeded"}])
        inv = _make_invoke(status=lambda: next(statuses))
        ctx = make_context(self._state(), inv)
        self.assertTrue(await catalog.main(ctx))
        poll_sleeps = [c for c in self.sleep.await_args_list if c.args == (catalog.scanStatusSleepSeconds,)]
        self.assertEqual(len(poll_sleeps), 3)
        self.assertEqual(_count(inv, "admin/workspaces/scanStatus"), 3)

    async def test_polling_is_capped_when_scan_never_finishes(self):
        inv = _make_invoke(status={"status": "Running"})
        state = self._state()
        ctx = make_context(state, inv)
        self.assertIs(await catalog.main(ctx), False)
        self.assertEqual(_count(inv, "admin/workspaces/scanStatus"), catalog.MAX_SCAN_STATUS_ATTEMPTS)
        self.assertEqual(_count(inv, "admin/workspaces/scanResult"), 0)
        ctx.fm.save.assert_not_awaited()
        self.assertNotIn("lastFullScan", state["catalog"])

    async def test_persistent_status_errors_fail_batch_after_cap(self):
        inv = _make_invoke(status={"ERROR": "HTTP 500"})
        ctx = make_context(self._state(), inv)
        self.assertIs(await catalog.main(ctx), False)
        self.assertEqual(_count(inv, "admin/workspaces/scanStatus"), catalog.MAX_SCAN_STATUS_ERRORS)

    async def test_status_error_counter_resets_after_success(self):
        seq = [{"ERROR": "x"}] * (catalog.MAX_SCAN_STATUS_ERRORS - 1) + [{"status": "Running"}] \
            + [{"ERROR": "x"}] * (catalog.MAX_SCAN_STATUS_ERRORS - 1) + [{"status": "Succeeded"}]
        it = iter(seq)
        inv = _make_invoke(status=lambda: next(it))
        ctx = make_context(self._state(), inv)
        self.assertTrue(await catalog.main(ctx))

    async def test_none_status_result_is_handled(self):
        it = iter([None, {"status": "Succeeded"}])
        inv = _make_invoke(status=lambda: next(it))
        ctx = make_context(self._state(), inv)
        self.assertTrue(await catalog.main(ctx))

    async def test_scan_ending_in_failed_status_fails_batch(self):
        inv = _make_invoke(get_info={"id": "s", "status": "Failed"})
        ctx = make_context(self._state(), inv)
        self.assertIs(await catalog.main(ctx), False)
        self.assertEqual(_count(inv, "admin/workspaces/scanResult"), 0)

    async def test_lowercase_error_key_in_scan_result_is_detected_as_error_dict(self):
        # scan result with "ERROR" (the invokeAPI error dict) is not saved
        inv = _make_invoke(status={"status": "Succeeded"}, scan_result={"ERROR": "HTTP 500"})
        ctx = make_context(self._state(), inv)
        self.assertIs(await catalog.main(ctx), False)
        ctx.fm.save.assert_not_awaited()

    async def test_none_scan_result_does_not_raise(self):
        class NoneResult(dict):
            pass

        async def invoke(rest_api, headers=None, json=None):
            if rest_api.startswith("admin/workspaces/modified"):
                return {"value": [{"id": "w"}]}
            if rest_api.startswith("admin/workspaces/getInfo"):
                return {"id": "s", "status": "Succeeded"}
            return None

        ctx = make_context(self._state(), invoke)
        self.assertIs(await catalog.main(ctx), False)

    async def test_none_get_info_result_does_not_raise(self):
        async def invoke(rest_api, headers=None, json=None):
            if rest_api.startswith("admin/workspaces/modified"):
                return {"value": [{"id": "w"}]}
            return None

        ctx = make_context(self._state(), invoke)
        self.assertIs(await catalog.main(ctx), False)

    async def test_modified_workspaces_error_returns_false(self):
        ctx = make_context(self._state(), _make_invoke(modified={"ERROR": "HTTP 500"}))
        self.assertIs(await catalog.main(ctx), False)

    async def test_no_modified_workspaces_returns_true_without_scanning(self):
        state = self._state()
        inv = _make_invoke(modified={"value": []})
        ctx = make_context(state, inv)
        self.assertTrue(await catalog.main(ctx))
        self.assertEqual(_count(inv, "admin/workspaces/getInfo"), 0)

    async def test_empty_discovery_preserves_state_without_scanning_or_saving(self):
        now = datetime(2026, 10, 20, 12)
        last_run = (now - timedelta(days=1)).strftime(FMT)
        states = {
            "no_catalog": {},
            "missing_full_scan": {"catalog": {"lastRun": last_run}},
            "due_full_scan": {
                "catalog": {
                    "lastRun": last_run,
                    "lastFullScan": (
                        now - timedelta(days=catalog.FullScanAfterDays + 1)
                    ).strftime(FMT),
                }
            },
            "incremental": {
                "catalog": {
                    "lastRun": last_run,
                    "lastFullScan": (now - timedelta(days=5)).strftime(FMT),
                }
            },
        }
        with patch.object(catalog, "utc_now", return_value=now):
            for mode, initial_state in states.items():
                for payload in ([], {"value": []}):
                    with self.subTest(mode=mode, payload=payload):
                        state = deepcopy(initial_state)
                        invoke = AsyncMock(return_value=payload)
                        ctx = make_context(state, invoke)

                        self.assertIs(await catalog.main(ctx), True)

                        invoke.assert_awaited_once()
                        url = invoke.await_args.kwargs["rest_api"]
                        self.assertTrue(url.startswith("admin/workspaces/modified?"))
                        if mode == "incremental":
                            self.assertIn("modifiedSince=2026-10-19T", url)
                        else:
                            self.assertIn("modifiedSince=2026-09-20T", url)
                        ctx.fm.save.assert_not_called()
                        self.assertEqual(state, initial_state)
                        ctx.logger.info.assert_called()
                        ctx.logger.error.assert_not_called()

    async def test_invalid_discovery_response_fails_before_scanning_or_saving(self):
        payloads = (
            None,
            {"ERROR": "HTTP 500"},
            {"error": {"code": "DiscoveryFailed"}},
            {"value": [], "error": {"code": "DiscoveryFailed"}},
            {},
            {"unexpected": []},
            {"value": None},
            {"value": {}},
            {"value": "not a list"},
            {"value": 1},
            "",
            "unexpected",
            0,
            True,
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                state = self._state(full_scan_days=5)
                before = deepcopy(state)
                invoke = AsyncMock(return_value=payload)
                ctx = make_context(state, invoke)

                self.assertIs(await catalog.main(ctx), False)

                invoke.assert_awaited_once()
                self.assertTrue(
                    invoke.await_args.kwargs["rest_api"].startswith(
                        "admin/workspaces/modified?"
                    )
                )
                ctx.fm.save.assert_not_called()
                self.assertEqual(state, before)
                ctx.logger.error.assert_called()
                ctx.logger.info.assert_not_called()

    async def test_invalid_discovery_records_reject_entire_list_before_scanning(self):
        invalid_records = (
            None,
            "w2",
            {},
            {"id": None},
            {"id": 1},
            {"id": ""},
            {"id": " \t"},
            {"id": "w2", "ERROR": "HTTP 500"},
            {"id": "w2", "error": {"code": "DiscoveryFailed"}},
        )
        for record in invalid_records:
            for valid_prefix in ([], [{"id": "w1"}]):
                records = valid_prefix + [record]
                for payload in (records, {"value": records}):
                    with self.subTest(record=record, payload=payload):
                        state = self._state()
                        before = deepcopy(state)
                        invoke = AsyncMock(return_value=payload)
                        ctx = make_context(state, invoke)

                        self.assertIs(await catalog.main(ctx), False)

                        invoke.assert_awaited_once()
                        self.assertTrue(
                            invoke.await_args.kwargs["rest_api"].startswith(
                                "admin/workspaces/modified?"
                            )
                        )
                        ctx.fm.save.assert_not_called()
                        self.assertEqual(state, before)
                        ctx.logger.error.assert_called()
                        ctx.logger.info.assert_not_called()

    async def test_workspaces_are_batched_by_100(self):
        inv = _make_invoke(workspace_ids=[str(i) for i in range(250)])
        ctx = make_context(self._state(), inv)
        self.assertTrue(await catalog.main(ctx))
        self.assertEqual(_count(inv, "admin/workspaces/getInfo"), 3)

    async def test_batch_pause_uses_asyncio_sleep(self):
        # the pause happens between batches, so two batches are needed
        inv = _make_invoke(workspace_ids=[str(i) for i in range(1700)])
        ctx = make_context(self._state(), inv)
        await catalog.main(ctx)
        self.assertIn(30, [c.args[0] for c in self.sleep.await_args_list])

    def _batch_pauses(self):
        return [c for c in self.sleep.await_args_list if c.args == (30,)]

    async def test_no_batch_pause_after_final_batch_single_batch(self):
        ctx = make_context(self._state(), _make_invoke())
        self.assertTrue(await catalog.main(ctx))
        self.assertEqual(self._batch_pauses(), [])

    async def test_batch_pause_only_between_batches(self):
        # 17 groups of 100 -> 2 batches (16 + 1): exactly one pause between them
        inv = _make_invoke(workspace_ids=[str(i) for i in range(1700)])
        ctx = make_context(self._state(), inv)
        self.assertTrue(await catalog.main(ctx))
        self.assertEqual(_count(inv, "admin/workspaces/getInfo"), 17)
        self.assertEqual(len(self._batch_pauses()), 1)


class CatalogParallelGroupTests(unittest.IsolatedAsyncioTestCase):
    """E3: parallel scan groups -- partial failure, per-batch headers, no shared-state mixups."""

    def setUp(self):
        self.sleep = AsyncMock()
        p = patch.object(catalog.asyncio, "sleep", self.sleep)
        p.start()
        self.addCleanup(p.stop)

    def _state(self):
        return {"catalog": {"lastRun": _ts(1)}}

    def _router(self, n, fail_first_ids=(), raise_first_ids=(), headers_seen=None):
        """invokeAPI fake: scan id is derived from the first workspace id of the group."""
        async def invoke(rest_api, headers=None, json=None):
            if rest_api.startswith("admin/workspaces/modified"):
                return {"value": [{"id": str(i)} for i in range(n)]}
            if rest_api.startswith("admin/workspaces/getInfo"):
                first = json["workspaces"][0]
                if headers_seen is not None:
                    headers_seen.append(headers)
                if first in raise_first_ids:
                    raise RuntimeError("boom")
                if first in fail_first_ids:
                    return {"ERROR": "HTTP 500", "status": 500}
                return {"id": f"scan-{first}", "status": "Running"}
            if rest_api.startswith("admin/workspaces/scanStatus"):
                await asyncio.sleep(0)  # let sibling groups interleave
                return {"status": "Succeeded"}
            if rest_api.startswith("admin/workspaces/scanResult"):
                await asyncio.sleep(0)
                return {"scanId": rest_api.rsplit("/", 1)[1]}
            raise AssertionError(rest_api)
        return invoke

    def _saved(self, ctx):
        return {c.kwargs["file_name"]: c.kwargs["content"] for c in ctx.fm.save.await_args_list}

    async def test_partial_failure_returns_false_and_skips_last_full_scan(self):
        state = self._state()
        ctx = make_context(state, self._router(300, fail_first_ids={"100"}))
        self.assertIs(await catalog.main(ctx), False)
        self.assertNotIn("lastFullScan", state["catalog"])
        # the healthy groups were still saved
        self.assertEqual(len(ctx.fm.save.await_args_list), 2)
        ctx.logger.error.assert_called()

    async def test_raising_group_counts_as_failure_but_siblings_finish(self):
        state = self._state()
        ctx = make_context(state, self._router(300, raise_first_ids={"0"}))
        self.assertIs(await catalog.main(ctx), False)
        self.assertNotIn("lastFullScan", state["catalog"])
        self.assertEqual(len(ctx.fm.save.await_args_list), 2)

    async def test_all_groups_succeed_persists_last_full_scan(self):
        state = self._state()
        ctx = make_context(state, self._router(300))
        self.assertTrue(await catalog.main(ctx))
        self.assertIn("lastFullScan", state["catalog"])
        self.assertEqual(len(ctx.fm.save.await_args_list), 3)

    async def test_failure_in_later_batch_still_fails_run(self):
        state = self._state()
        ctx = make_context(state, self._router(1700, fail_first_ids={"1600"}))
        self.assertIs(await catalog.main(ctx), False)
        self.assertNotIn("lastFullScan", state["catalog"])
        self.assertEqual(len(ctx.fm.save.await_args_list), 16)

    async def test_failed_incremental_scan_does_not_touch_existing_last_full_scan(self):
        state = {"catalog": {"lastRun": _ts(1), "lastFullScan": _ts(2)}}
        before = state["catalog"]["lastFullScan"]
        ctx = make_context(state, self._router(200, fail_first_ids={"100"}))
        self.assertIs(await catalog.main(ctx), False)
        self.assertEqual(state["catalog"]["lastFullScan"], before)

    async def test_headers_refreshed_once_per_batch(self):
        tokens = iter(f"tok{i}" for i in range(100))
        seen = []
        ctx = make_context(self._state(), self._router(1700, headers_seen=seen))
        ctx.clients["pbi"].get_headers.side_effect = lambda *a, **k: {"Authorization": next(tokens)}
        self.assertTrue(await catalog.main(ctx))
        # 1 for the modified-workspaces call + 1 per batch (16 groups + 1 group = 2 batches)
        self.assertEqual(ctx.clients["pbi"].get_headers.call_count, 3)
        first_batch = {h["Authorization"] for h in seen[:16]}
        second_batch = {h["Authorization"] for h in seen[16:]}
        self.assertEqual(first_batch, {"tok1"})
        self.assertEqual(second_batch, {"tok2"})

    async def test_token_failure_on_refresh_propagates(self):
        calls = {"n": 0}

        def get_headers(*a, **k):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("token")
            return {"Authorization": "t"}

        ctx = make_context(self._state(), self._router(100))
        ctx.clients["pbi"].get_headers.side_effect = get_headers
        with self.assertRaises(RuntimeError):
            await catalog.main(ctx)

    async def test_each_group_saved_once_with_its_own_result(self):
        n_groups = 40
        ctx = make_context(self._state(), self._router(n_groups * 100))
        self.assertTrue(await catalog.main(ctx))
        saved = self._saved(ctx)
        self.assertEqual(len(saved), n_groups)  # no file overwritten / duplicated
        for name, content in saved.items():
            index = int(name.split("_")[1].split(".")[0])
            self.assertEqual(content, {"scanId": f"scan-{(index - 1) * 100}"})
        indexes = sorted(int(n.split("_")[1].split(".")[0]) for n in saved)
        self.assertEqual(indexes, list(range(1, n_groups + 1)))

    async def test_each_group_posts_its_own_workspaces(self):
        bodies = []

        base = self._router(250)

        async def invoke(rest_api, headers=None, json=None):
            if json:
                bodies.append(list(json["workspaces"]))
            return await base(rest_api, headers=headers, json=json)

        ctx = make_context(self._state(), invoke)
        self.assertTrue(await catalog.main(ctx))
        self.assertEqual(sorted(len(b) for b in bodies), [50, 100, 100])
        flat = [w for b in bodies for w in b]
        self.assertEqual(sorted(flat, key=int), [str(i) for i in range(250)])


class CatalogLineageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        environment = patch.dict(
            os.environ, {"CATALOG_LINEAGE_ENABLED": "true", "DRY_RUN": "false"}
        )
        environment.start()
        self.addCleanup(environment.stop)
        sleep = patch.object(catalog.asyncio, "sleep", AsyncMock())
        sleep.start()
        self.addCleanup(sleep.stop)

    def _context(self, invoke=None):
        ctx = make_context(
            {"catalog": {"lastRun": _ts(1)}},
            invoke or _make_invoke(scan_result={"workspaces": [{"id": "w1"}]}),
        )
        ctx.fm.save_snapshot = AsyncMock()
        return ctx

    async def test_enabled_adds_snapshot_without_extra_api_calls(self):
        invoke = _make_invoke(
            scan_result={
                "workspaces": [
                    {
                        "id": "w1",
                        "reports": [
                            {"id": "r1", "datasetId": "outside"},
                        ],
                    }
                ]
            }
        )
        ctx = self._context(invoke)
        initial_state = deepcopy(ctx.current_state)
        with patch.object(
            catalog, "utc_now", return_value=datetime(2026, 11, 3, 23, 59)
        ):
            self.assertTrue(await catalog.main(ctx))
        enabled_calls = list(invoke.calls)
        ctx.fm.save.assert_awaited_once()
        ctx.fm.save_snapshot.assert_awaited_once()
        saved = ctx.fm.save_snapshot.await_args.kwargs
        self.assertEqual(saved["path"], "lineage_edges/2026/11/03/")
        self.assertEqual(saved["file_name"], "scan1.lineage_edges.json")
        self.assertEqual(saved["content"]["scanMode"], "full")
        self.assertEqual(
            saved["content"]["observedAtUtc"], "2026-11-03T23:59:00.000000Z"
        )
        self.assertEqual(saved["content"]["edges"][0]["RelatedItemId"], "outside")
        self.assertIn("lastFullScan", ctx.current_state["catalog"])

        invoke.calls.clear()
        ctx.current_state = initial_state
        ctx.fm.save_snapshot.reset_mock()
        os.environ.pop("CATALOG_LINEAGE_ENABLED")
        with patch.object(
            catalog, "utc_now", return_value=datetime(2026, 11, 3, 23, 59)
        ):
            self.assertTrue(await catalog.main(ctx))
        self.assertEqual(invoke.calls, enabled_calls)
        ctx.fm.save_snapshot.assert_not_awaited()

    async def test_empty_snapshot_and_no_discovery_are_distinct(self):
        ctx = self._context()
        self.assertTrue(await catalog.main(ctx))
        content = ctx.fm.save_snapshot.await_args.kwargs["content"]
        self.assertEqual(content["edges"], [])
        self.assertEqual(content["returnedWorkspaceIds"], ["w1"])
        self.assertTrue(content["complete"])

        ctx = self._context(_make_invoke(modified=[]))
        self.assertTrue(await catalog.main(ctx))
        ctx.fm.save_snapshot.assert_not_awaited()
        self.assertNotIn("lastFullScan", ctx.current_state["catalog"])

    async def test_extraction_or_storage_failure_preserves_checkpoints(self):
        for failure in ("extraction", "storage", "scan_id"):
            for full_scan in (True, False):
                with self.subTest(failure=failure, full_scan=full_scan):
                    invoke = _make_invoke(
                        scan_result={"workspaces": {}}
                        if failure == "extraction"
                        else {"workspaces": [{"id": "w1"}]},
                        get_info={"id": "../unsafe", "status": "Succeeded"}
                        if failure == "scan_id"
                        else None,
                    )
                    ctx = self._context(invoke)
                    if not full_scan:
                        ctx.current_state["catalog"]["lastFullScan"] = _ts(2)
                    before = deepcopy(ctx.current_state)
                    if failure == "storage":
                        ctx.fm.save_snapshot.side_effect = RuntimeError("write failed")
                    self.assertFalse(await catalog.main(ctx))
                    self.assertEqual(ctx.current_state, before)
                    ctx.fm.save.assert_awaited_once()
                    if failure != "storage":
                        ctx.fm.save_snapshot.assert_not_awaited()

    async def test_parallel_failure_keeps_successful_batch_observations(self):
        async def invoke(rest_api, headers=None, json=None):
            if rest_api.startswith("admin/workspaces/modified"):
                return [{"id": str(i)} for i in range(101)]
            if rest_api.startswith("admin/workspaces/getInfo"):
                return {"id": f"scan-{json['workspaces'][0]}", "status": "Succeeded"}
            return {"workspaces": []}

        ctx = self._context(invoke)

        async def save_snapshot(**kwargs):
            if kwargs["content"]["scanId"] == "scan-0":
                raise RuntimeError("write failed")

        ctx.fm.save_snapshot.side_effect = save_snapshot
        self.assertFalse(await catalog.main(ctx))
        self.assertEqual(ctx.fm.save_snapshot.await_count, 2)
        self.assertEqual(
            {call.kwargs["file_name"] for call in ctx.fm.save_snapshot.await_args_list},
            {"scan-0.lineage_edges.json", "scan-100.lineage_edges.json"},
        )
        self.assertNotIn("lastFullScan", ctx.current_state["catalog"])

    async def test_real_local_snapshot_round_trip_and_dry_run_failure(self):
        moment = utc_now()
        with (
            tempfile.TemporaryDirectory() as output,
            patch.object(catalog, "utc_now", return_value=moment),
        ):
            ctx = self._context()
            ctx.OutputPath = output
            ctx.fm = File_Management()
            ctx.fm.content(ctx)
            self.assertTrue(await catalog.main(ctx))
            day = moment.strftime("%Y/%m/%d")
            saved = await ctx.fm.read_snapshot(
                f"lineage_edges/{day}/", "scan1.lineage_edges.json"
            )
            self.assertEqual(saved["edges"], [])
            self.assertEqual(saved["returnedWorkspaceIds"], ["w1"])
            before = deepcopy(ctx.current_state)
            os.environ["DRY_RUN"] = "true"
            self.assertFalse(await catalog.main(ctx))
            self.assertEqual(ctx.current_state, before)


if __name__ == "__main__":
    unittest.main()
