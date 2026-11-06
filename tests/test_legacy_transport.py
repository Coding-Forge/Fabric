"""Legacy collectors use real shared retry/authentication with offline transports."""

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from env.context import Context
from env.modules import fabricitems, gateway, roles
from env.utility import http_retry
from tests.fabric_helpers import deny_network
from tests.helpers import make_context


class LegacyTransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = 0.0
        for patcher in (
            patch.dict(
                os.environ, {"API_MAX_RETRIES": "2", "API_MAX_RETRY_DELAY": "5"}
            ),
            patch.object(http_retry, "monotonic", side_effect=lambda: self.clock),
            patch.object(asyncio, "sleep", AsyncMock(side_effect=self.advance)),
            *deny_network(),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def advance(self, delay):
        self.clock += delay

    def context(self, *responses):
        ctx = make_context()
        ctx.invokeAPI = Context.invokeAPI.__get__(ctx)
        ctx._invoke_once = AsyncMock(side_effect=responses)
        return ctx

    async def test_gateway_honors_full_cooldown_and_refreshes_token_after_wait(self):
        ctx = self.context()
        responses = [
            MagicMock(status_code=429, headers={"Retry-After": "3600"}),
            MagicMock(status_code=401),
            MagicMock(status_code=200),
        ]
        events = []

        def headers(**kwargs):
            events.append((self.clock, kwargs))
            return {"Authorization": f"synthetic-{len(events)}"}

        with patch.object(gateway.requests, "get", side_effect=responses) as get:
            result = await gateway._get(
                "https://api.powerbi.com/status", headers, context=ctx
            )
        self.assertIs(result, responses[2])
        self.assertEqual(events, [(0, {}), (3600, {}), (3600, {"force_refresh": True})])
        self.assertEqual(get.call_count, 3)
        responses[0].close.assert_called_once()
        responses[1].close.assert_called_once()
        responses[2].close.assert_not_called()

    async def test_gateway_and_shared_transport_share_final_response_cooldowns(self):
        os.environ["API_MAX_RETRIES"] = "0"
        ctx = self.context({"ok": True})
        response = MagicMock(status_code=429, headers={"Retry-After": "3600"})
        with patch.object(gateway.requests, "get", return_value=response):
            self.assertIs(
                await gateway._get("https://api.powerbi.com/status", {}, context=ctx),
                response,
            )
        self.assertEqual(self.clock, 0)
        await ctx.invokeAPI("admin/groups")
        self.assertEqual(self.clock, 3600)

    async def test_gateway_repeated_401_and_throttles_are_bounded(self):
        for status, expected in ((401, 2), (429, 3)):
            with self.subTest(status=status):
                ctx = self.context()
                response = MagicMock(status_code=status, headers={})
                provider = MagicMock(return_value={"Authorization": "synthetic"})
                with patch.object(
                    gateway.requests, "get", return_value=response
                ) as get:
                    await gateway._get(
                        "https://api.powerbi.com/status", provider, context=ctx
                    )
                self.assertEqual(get.call_count, expected)

    async def test_fabric_items_long_pagination_does_not_recurse_or_reuse_headers(self):
        pages = 1001
        responses = [
            {
                "itemEntities": [],
                **(
                    {
                        "continuationUri": f"https://api.fabric.microsoft.com/v1/admin/items?continuationToken={index}"
                    }
                    if index + 1 < pages
                    else {}
                ),
            }
            for index in range(pages)
        ]
        ctx = self.context(*responses)
        ctx.clients["tenant"].get_headers.side_effect = (
            {"Authorization": f"synthetic-{index}"} for index in range(pages)
        )
        self.assertTrue(await fabricitems.main(ctx))
        self.assertEqual(ctx.fm.save.await_count, pages)
        self.assertEqual(ctx.clients["tenant"].get_headers.call_count, pages)
        self.assertNotEqual(
            ctx._invoke_once.await_args_list[0].kwargs["headers"],
            ctx._invoke_once.await_args_list[-1].kwargs["headers"],
        )
        self.assertEqual(
            ctx.fm.save.await_args.kwargs["file_name"], "fabricitems_01001.json"
        )

    async def test_fabric_items_failure_is_not_saved_or_reported_as_success(self):
        os.environ["API_MAX_RETRIES"] = "0"
        ctx = self.context(
            {
                "itemEntities": [{"id": "item"}],
                "continuationUri": "https://api.fabric.microsoft.com/v1/admin/items?continuationToken=next",
            },
            {"ERROR": "throttled", "status": 429, "retryAfter": "3600"},
        )
        self.assertFalse(await fabricitems.main(ctx))
        ctx.fm.save.assert_awaited_once()
        self.assertEqual(ctx.fm.save.await_args.kwargs["content"], [{"id": "item"}])

    async def test_fabric_items_invalid_continuation_is_an_incomplete_inventory(self):
        url = "https://api.fabric.microsoft.com/v1/admin/items"
        for continuation in (url, 0, False, [], {"url": url}):
            with self.subTest(continuation=continuation):
                ctx = self.context(
                    {"itemEntities": [], "continuationUri": continuation}
                )
                self.assertFalse(await fabricitems.main(ctx))
                ctx._invoke_once.assert_awaited_once()

    async def test_roles_uses_only_the_shared_retry_budget(self):
        error = {"ERROR": "throttled", "status": 429, "retryAfter": "600"}
        ctx = self.context(error, error, error, {"workspaces": []})
        with self.assertRaises(RuntimeError):
            await roles.main(ctx)
        self.assertEqual(ctx._invoke_once.await_count, 3)
        self.assertEqual(self.clock, 1200)
        ctx.fm.save.assert_not_awaited()
