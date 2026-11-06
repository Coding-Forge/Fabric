"""Tenant settings module: failure handling and save behavior."""
import unittest
from unittest.mock import AsyncMock, MagicMock

from env.modules import tenant
from tests.helpers import make_context

URL = "https://api.fabric.microsoft.com/v1/admin/tenantsettings"


def _ctx(result):
    ctx = make_context(invoke=AsyncMock(return_value=result))
    ctx.clients["tenant"] = MagicMock()
    ctx.clients["tenant"].get_headers.return_value = {"Authorization": "x"}
    return ctx


class TenantTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_context(self):
        with self.assertRaises(RuntimeError):
            await tenant.main(None)

    async def test_success_saves_settings_with_json_header(self):
        payload = {"tenantSettings": [{"settingName": "a"}]}
        ctx = _ctx(payload)
        await tenant.main(ctx)
        ctx.invokeAPI.assert_awaited_once()
        kwargs = ctx.invokeAPI.await_args.kwargs
        self.assertEqual(kwargs["rest_api"], URL)
        self.assertEqual(kwargs["headers"]()["Content-Type"], "application/json")
        self.assertEqual(kwargs["headers"]()["Authorization"], "x")
        ctx.fm.save.assert_awaited_once()
        save = ctx.fm.save.await_args.kwargs
        self.assertEqual(save["file_name"], "tenant-settings.json")
        self.assertEqual(save["content"], payload)
        self.assertTrue(save["path"].startswith("tenant/"))
        self.assertTrue(save["path"].endswith("/"))

    async def test_failure_returns_false_and_does_not_save(self):
        for bad in (None, {}, {"ERROR": "boom"}):
            ctx = _ctx(bad)
            self.assertIs(await tenant.main(ctx), False)
            ctx.fm.save.assert_not_awaited()
            ctx.logger.error.assert_called()


if __name__ == "__main__":
    unittest.main()
