"""B10, B11, invokeAPI error dict: Context behavior."""
import os
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from env import context as ctx_mod
from env.context import Context, _error_result


class ConvertDtStrTests(unittest.TestCase):
    def setUp(self):
        self.ctx = Context()
        self.ctx.logger = MagicMock()

    def test_parses_valid_string(self):
        self.assertEqual(self.ctx.convert_dt_str("2024-05-31T01:02:03.000004Z"),
                         datetime(2024, 5, 31, 1, 2, 3, 4))

    def test_accepts_datetime(self):
        dt = datetime(2024, 1, 2, 3, 4, 5, 6)
        self.assertEqual(self.ctx.convert_dt_str(dt), dt)

    def test_bad_string_raises_value_error_not_exit(self):
        for bad in ("not-a-date", "2024-05-31", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.ctx.convert_dt_str(bad)
        self.ctx.logger.error.assert_called()

    def test_none_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.ctx.convert_dt_str(None)

    def test_does_not_raise_system_exit(self):
        try:
            self.ctx.convert_dt_str("bad")
        except SystemExit:  # pragma: no cover
            self.fail("convert_dt_str must not call exit()")
        except ValueError:
            pass


class GetCronTests(unittest.TestCase):
    def test_every_module_returns_its_configured_cron(self):
        ctx = Context()
        names = ["Activity", "Apps", "Catalog", "Graph", "Tenant", "RefreshHistory",
                 "Refreshables", "Gateway", "Capacity", "Roles", "Domains",
                 "FabricItems", "Workspaces", "CapacityMetrics"]
        for n in names:
            setattr(ctx, f"{n}_cron", f"cron-{n}")
        for n in names:
            with self.subTest(module=n):
                self.assertEqual(ctx.get_cron(n), f"cron-{n}")

    def test_new_module_setters_feed_get_cron(self):
        ctx = Context()
        ctx.set_Domains_cron("1 * * * *")
        ctx.set_FabricItems_cron("2 * * * *")
        ctx.set_Workspaces_cron("3 * * * *")
        ctx.set_CapacityMetrics_cron("4 * * * *")
        self.assertEqual(ctx.get_cron("Domains"), "1 * * * *")
        self.assertEqual(ctx.get_cron("FabricItems"), "2 * * * *")
        self.assertEqual(ctx.get_cron("Workspaces"), "3 * * * *")
        self.assertEqual(ctx.get_cron("CapacityMetrics"), "4 * * * *")

    def test_unset_and_unknown_return_none(self):
        ctx = Context()
        self.assertIsNone(ctx.get_cron("Domains"))
        self.assertIsNone(ctx.get_cron("Nope"))


class _FakeResponse:
    def __init__(self, status=200, headers=None, body="", json_body=None, text_exc=None):
        self.status = status
        self.ok = status < 400
        self.headers = headers or {}
        self._body = body
        self._json = json_body
        self._text_exc = text_exc

    async def text(self):
        if self._text_exc:
            raise self._text_exc
        return self._body

    async def json(self, *a, **k):
        return self._json

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def get(self, *a, **k):
        self.calls.append(("GET", a, k))
        return self.response

    def post(self, *a, **k):
        self.calls.append(("POST", a, k))
        return self.response


class InvokeApiErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_relative_request_uses_sovereign_root(self):
        for cloud, host in (
            ("Gcc", "api.powerbigov.us"),
            ("GccHigh", "api.high.powerbigov.us"),
            ("Dod", "api.mil.powerbigov.us"),
        ):
            with self.subTest(cloud=cloud):
                ctx = Context()
                ctx.set_ServicePrincipal("client", "test-secret", "tenant", cloud)
                session = _FakeSession(_FakeResponse(200, json_body={"value": []}))
                with patch.object(ctx_mod.aiohttp, "ClientSession", return_value=session):
                    await ctx.invokeAPI("admin/groups", headers={"test": "headers"})
                self.assertEqual(
                    session.calls[0][1][0], f"https://{host}/v1.0/myorg/admin/groups"
                )

    def setUp(self):
        # retryable statuses (429/503/504) back off via asyncio.sleep; keep tests instant
        self.clock = 0.0
        self.sleep = AsyncMock(side_effect=self.advance)
        clock = patch("env.utility.http_retry.monotonic", side_effect=lambda: self.clock)
        clock.start()
        self.addCleanup(clock.stop)
        p = patch.object(ctx_mod.asyncio, "sleep", self.sleep)
        p.start()
        self.addCleanup(p.stop)
        env = patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for k in ("API_MAX_RETRIES", "API_MAX_CONCURRENCY", "API_MAX_RETRY_DELAY"):
            os.environ.pop(k, None)

    def advance(self, delay):
        self.clock += delay

    async def _invoke(self, response, *args, **kwargs):
        session = _FakeSession(response)
        with patch.object(ctx_mod.aiohttp, "ClientSession", return_value=session), \
                patch.object(ctx_mod.aiohttp, "TCPConnector", MagicMock()):
            result = await Context().invokeAPI(*args, **kwargs)
        return result, session

    async def test_error_result_fields(self):
        r = _FakeResponse(429, {"Retry-After": "12"}, body="slow down")
        self.assertEqual(await _error_result(r), {
            "ERROR": "HTTP 429", "status": 429, "retryAfter": "12", "message": "slow down"})

    async def test_error_result_without_retry_after_or_body(self):
        r = _FakeResponse(500, text_exc=aiohttp.ClientError("boom"))
        out = await _error_result(r)
        self.assertEqual(out["status"], 500)
        self.assertIsNone(out["retryAfter"])
        self.assertEqual(out["message"], "")

    async def test_get_with_headers_non_ok_returns_error_dict(self):
        result, _ = await self._invoke(_FakeResponse(403, body="no"), "admin/groups", headers={"a": "b"})
        self.assertEqual(result["ERROR"], "HTTP 403")
        self.assertEqual(result["message"], "no")

    async def test_get_uses_powerbi_root_for_relative_url(self):
        result, s = await self._invoke(_FakeResponse(200, json_body={"value": [1]}), "admin/groups", headers={"a": "b"})
        self.assertEqual(result, {"value": [1]})
        self.assertEqual(s.calls[0][1][0], "https://api.powerbi.com/v1.0/myorg/admin/groups")

    async def test_post_non_ok_returns_error_dict_with_retry_after(self):
        r = _FakeResponse(429, {"Retry-After": "5"})
        result, s = await self._invoke(r, "admin/workspaces/getInfo", headers={"a": "b"}, json={"w": []})
        self.assertEqual(result["status"], 429)
        self.assertEqual(result["retryAfter"], "5")
        self.assertEqual(s.calls[0][0], "POST")
        # 1 initial attempt + API_MAX_RETRIES retries, honouring Retry-After: 5
        self.assertEqual(len(s.calls), 4)
        self.assertEqual([c.args[0] for c in self.sleep.await_args_list], [5.0, 5.0, 5.0])

    async def test_get_without_headers_non_ok_returns_error_dict(self):
        result, _ = await self._invoke(_FakeResponse(404), "https://example.test/x")
        self.assertEqual(result["ERROR"], "HTTP 404")

    async def test_continuation_url_non_ok_returns_error_dict(self):
        url = "https://api.powerbi.com/v1.0/myorg/admin/activityevents?continuationToken='abc'"
        result, s = await self._invoke(_FakeResponse(503), url, headers={"a": "b"})
        self.assertEqual(result["ERROR"], "HTTP 503")
        self.assertEqual(self.sleep.await_count, 3)
        self.assertEqual(s.calls[0][1][0], url) if s.calls[0][1] else self.assertEqual(s.calls[0][2]["url"], url)

    async def test_success_returns_json(self):
        result, _ = await self._invoke(_FakeResponse(200, json_body={"a": 1}), "https://example.test/x")
        self.assertEqual(result, {"a": 1})


if __name__ == "__main__":
    unittest.main()
