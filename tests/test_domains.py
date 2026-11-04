"""B6: domains builds a new row per workspace and reads the right state key."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from env.modules import domains
from tests.helpers import make_context

FMT = "%Y-%m-%dT%H:%M:%S.%fZ"
ROOT = "https://api.fabric.microsoft.com/v1/admin/domains"


def _invoke(domain_list, workspaces):
    async def invoke(rest_api, headers=None, json=None):
        if rest_api == ROOT:
            return {"domains": domain_list}
        for did, ws in workspaces.items():
            if rest_api == f"{ROOT}/{did}/workspaces":
                return ws
        raise AssertionError(rest_api)
    return invoke


class DomainsTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_context(self):
        with self.assertRaises(RuntimeError):
            await domains.main(None)

    async def test_one_distinct_row_per_workspace(self):
        doms = [{"id": "d1", "displayName": "Sales"}, {"id": "d2", "displayName": "HR"}]
        ws = {"d1": {"value": [{"id": "w1", "displayName": "A"}, {"id": "w2", "displayName": "B"}]},
              "d2": {"value": [{"id": "w3", "displayName": "C"}]}}
        ctx = make_context({}, _invoke(doms, ws))
        await domains.main(ctx)
        rows = ctx.fm.save.await_args.kwargs["content"]
        self.assertEqual([(r["id"], r["workspaceId"], r["workspace"]) for r in rows],
                         [("d1", "w1", "A"), ("d1", "w2", "B"), ("d2", "w3", "C")])
        self.assertEqual(len({id(r) for r in rows}), 3)
        # source domain dicts are not mutated
        self.assertNotIn("workspace", doms[0])

    async def test_no_extra_trailing_row_after_loop(self):
        doms = [{"id": "d1"}]
        ws = {"d1": {"value": [{"id": "w1", "displayName": "A"}]}}
        ctx = make_context({}, _invoke(doms, ws))
        await domains.main(ctx)
        self.assertEqual(len(ctx.fm.save.await_args.kwargs["content"]), 1)

    async def test_empty_workspace_entries_are_skipped(self):
        doms = [{"id": "d1"}]
        ws = {"d1": {"value": [{}, {"id": "w1", "displayName": "A"}]}}
        ctx = make_context({}, _invoke(doms, ws))
        await domains.main(ctx)
        self.assertEqual(len(ctx.fm.save.await_args.kwargs["content"]), 1)

    async def _run(self, state, now):
        ctx = make_context(state, _invoke([{"id": "d1"}], {"d1": {"value": [{"id": "w"}]}}))
        with patch("env.modules.domains.utc_now", return_value=now):
            await domains.main(ctx)
        return ctx.fm.save.await_args.kwargs["path"]

    async def test_path_date_comes_from_utc_now_not_state(self):
        now = datetime(2024, 3, 9, 15, 0, 0)
        state = {"activity": {"lastRun": "2020-01-01T00:00:00.000000Z"},
                 "domains": {"lastRun": "2021-06-05T00:00:00.000000Z"}}
        self.assertEqual(await self._run(state, now), "domains/2024/03/09/")

    async def test_yesterday_last_run_saves_under_today(self):
        now = datetime(2024, 3, 9, 0, 0, 1)
        state = {"domains": {"lastRun": (now - timedelta(days=1)).strftime(FMT)}}
        self.assertEqual(await self._run(state, now), "domains/2024/03/09/")

    async def test_old_last_run_saves_under_today(self):
        now = datetime(2025, 1, 2, 23, 59, 59)
        state = {"domains": {"lastRun": "2019-12-31T23:59:59.000000Z"}}
        self.assertEqual(await self._run(state, now), "domains/2025/01/02/")

    async def test_missing_state_uses_today(self):
        now = datetime(2024, 7, 4, 12, 0, 0)
        for state in (None, {}, {"domains": None}, {"domains": {}}):
            with self.subTest(state=state):
                self.assertEqual(await self._run(state, now), "domains/2024/07/04/")

    async def test_date_is_zero_padded(self):
        self.assertEqual(await self._run({}, datetime(2024, 1, 5, 3, 0, 0)),
                         "domains/2024/01/05/")

    async def test_same_day_rerun_uses_same_path(self):
        state = {"domains": {"lastRun": "2020-01-01T00:00:00.000000Z"}}
        first = await self._run(state, datetime(2024, 3, 9, 0, 0, 0))
        second = await self._run(state, datetime(2024, 3, 9, 23, 59, 59, 999999))
        self.assertEqual(first, second)
        self.assertEqual(first, "domains/2024/03/09/")

    async def test_next_day_uses_new_path(self):
        first = await self._run({}, datetime(2024, 3, 9, 23, 59, 59))
        second = await self._run({}, datetime(2024, 3, 10, 0, 0, 0))
        self.assertNotEqual(first, second)
        self.assertEqual(second, "domains/2024/03/10/")

    async def test_json_string_state_ignored_for_path_date(self):
        ctx = make_context('{"domains": {"lastRun": "2024-03-09T01:00:00.000000Z"}}',
                           _invoke([{"id": "d1"}], {"d1": {"value": [{"id": "w"}]}}))
        with patch("env.modules.domains.utc_now", return_value=datetime(2026, 10, 14, 8)):
            await domains.main(ctx)
        self.assertEqual(ctx.fm.save.await_args.kwargs["path"], "domains/2026/10/14/")

    async def test_domains_list_error_returns_false(self):
        ctx = make_context({}, AsyncMock(return_value={"ERROR": "HTTP 403"}))
        self.assertIs(await domains.main(ctx), False)
        ctx.fm.save.assert_not_awaited()

    async def test_workspace_listing_error_returns_false(self):
        async def invoke(rest_api, headers=None, json=None):
            if rest_api == ROOT:
                return {"domains": [{"id": "d1"}]}
            return {"ERROR": "HTTP 500"}

        ctx = make_context({}, invoke)
        self.assertIs(await domains.main(ctx), False)
        ctx.fm.save.assert_not_awaited()

    async def test_no_domains_saves_nothing(self):
        ctx = make_context({}, AsyncMock(return_value={"domains": []}))
        await domains.main(ctx)
        ctx.fm.save.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
