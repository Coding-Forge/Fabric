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
            invoke.await_args_list[0].kwargs["headers"], ctx.clients["tenant"].get_headers.return_value
        )
        self.assertEqual(
            invoke.await_args_list[1].kwargs["headers"], ctx.clients["pbi"].get_headers.return_value
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

    async def test_retry_after_header_is_honoured(self):
        invoke = AsyncMock(side_effect=[_err(429, "7"), {"workspaces": []}, {"value": []}])
        ctx = make_context(invoke=invoke)
        await roles.main(ctx)
        self.sleep.assert_awaited_once_with(7)

    async def test_non_numeric_or_missing_retry_after_uses_default(self):
        invoke = AsyncMock(side_effect=[_err(429, "Wed, 21 Oct"), _err(500, None),
                                        {"workspaces": []}, {"value": []}])
        ctx = make_context(invoke=invoke)
        await roles.main(ctx)
        self.assertEqual([c.args[0] for c in self.sleep.await_args_list],
                         [roles.DEFAULT_RETRY_SECONDS, roles.DEFAULT_RETRY_SECONDS])

    async def test_gives_up_after_max_attempts_and_raises(self):
        invoke = AsyncMock(return_value=_err(500))
        ctx = make_context(invoke=invoke)
        with self.assertRaises(RuntimeError):
            await roles.main(ctx)
        self.assertEqual(invoke.await_count, roles.MAX_ATTEMPTS)
        # no sleep after the final attempt
        self.assertEqual(self.sleep.await_count, roles.MAX_ATTEMPTS - 1)
        ctx.fm.save.assert_not_awaited()

    async def test_none_result_is_treated_as_failure(self):
        invoke = AsyncMock(return_value=None)
        ctx = make_context(invoke=invoke)
        with self.assertRaises(RuntimeError):
            await roles.main(ctx)
        self.assertEqual(invoke.await_count, roles.MAX_ATTEMPTS)

    async def test_failure_on_second_page_aborts_without_saving(self):
        seq = [{"workspaces": [{"id": "a"}], "continuationToken": "t"}] + [_err(500)] * 3
        ctx = make_context(invoke=AsyncMock(side_effect=seq))
        with self.assertRaises(RuntimeError):
            await roles.main(ctx)
        ctx.fm.save.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
