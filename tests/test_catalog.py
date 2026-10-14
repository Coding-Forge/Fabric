"""B1-B3: catalog polling caps, error handling and lastFullScan persistence."""
import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from env.modules import catalog
from env.context import utc_now
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


if __name__ == "__main__":
    unittest.main()
