"""B4: roles retry / Retry-After / pagination."""
import unittest
from unittest.mock import AsyncMock, patch

from env.modules import roles
from tests.helpers import make_context

WS = roles.WORKSPACES_URL


def _err(status=429, retry=None):
    return {"ERROR": f"HTTP {status}", "status": status, "retryAfter": retry, "message": ""}


class RolesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sleep = AsyncMock()
        p = patch.object(roles.asyncio, "sleep", self.sleep)
        p.start()
        self.addCleanup(p.stop)

    async def test_requires_context(self):
        with self.assertRaises(RuntimeError):
            await roles.main(None)

    async def test_paginates_workspaces_and_saves_groups(self):
        urls = []

        async def invoke(rest_api, headers=None, json=None):
            urls.append(rest_api)
            if rest_api == WS:
                return {"workspaces": [{"id": "a"}, {"id": "b"}], "continuationToken": "tok+= x"}
            if rest_api.startswith(WS + "?continuationToken="):
                return {"workspaces": [{"id": "c"}, {"id": "a"}]}
            return {"value": [{"id": "g1"}]}

        ctx = make_context(invoke=invoke)
        await roles.main(ctx)

        self.assertEqual(urls[1], f"{WS}?continuationToken=tok%2B%3D%20x")  # token is URL-quoted
        self.assertEqual(len(urls), 3)
        self.assertIn("$skip=0", urls[2])
        ctx.fm.save.assert_awaited_once()
        self.assertEqual(ctx.fm.save.await_args.kwargs["content"], [{"id": "g1"}])
        self.sleep.assert_not_awaited()

    async def test_fabric_inventory_and_powerbi_roles_use_separate_audiences(self):
        invoke = AsyncMock(side_effect=[
            {"workspaces": [{"id": "workspace"}]}, {"value": []},
        ])
        ctx = make_context(invoke=invoke)
        await roles.main(ctx)
        self.assertEqual(
            invoke.await_args_list[0].kwargs["headers"], ctx.clients["tenant"].get_headers
        )
        self.assertEqual(
            invoke.await_args_list[1].kwargs["headers"], ctx.clients["pbi"].get_headers
        )

    async def test_group_pages_use_skip_steps_of_5000(self):
        ids = [{"id": str(i)} for i in range(5001)]
        urls = []

        async def invoke(rest_api, headers=None, json=None):
            urls.append(rest_api)
            if rest_api == WS:
                return {"workspaces": ids}
            return {"value": [{"id": rest_api[-4:]}]}

        ctx = make_context(invoke=invoke)
        await roles.main(ctx)
        group_urls = urls[1:]
        self.assertEqual(len(group_urls), 2)
        self.assertTrue(group_urls[0].endswith("$skip=0"))
        self.assertTrue(group_urls[1].endswith("$skip=5000"))
        self.assertEqual(len(ctx.fm.save.await_args.kwargs["content"]), 2)

    async def test_transport_failures_are_not_retried_by_a_second_loop(self):
        for status in (401, 403, 429, 500, 503):
            with self.subTest(status=status):
                invoke = AsyncMock(return_value=_err(status, "3600"))
                ctx = make_context(invoke=invoke)
                with self.assertRaises(RuntimeError):
                    await roles.main(ctx)
                self.assertEqual(invoke.await_count, 1)
                self.sleep.assert_not_awaited()
                ctx.fm.save.assert_not_awaited()

    async def test_none_result_is_treated_as_failure(self):
        invoke = AsyncMock(return_value=None)
        ctx = make_context(invoke=invoke)
        with self.assertRaises(RuntimeError):
            await roles.main(ctx)
        self.assertEqual(invoke.await_count, 1)

    async def test_failure_on_second_page_aborts_without_saving(self):
        seq = [{"workspaces": [{"id": "a"}], "continuationToken": "t"}] + [_err(500)] * 3
        ctx = make_context(invoke=AsyncMock(side_effect=seq))
        with self.assertRaises(RuntimeError):
            await roles.main(ctx)
        ctx.fm.save.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
