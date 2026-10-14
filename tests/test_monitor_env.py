"""B16: app/monitor.py environment variable aliases."""
import os
import unittest
from unittest.mock import MagicMock, patch

from app import monitor

BASE_ENV = {"APPLICATION_MODULES": "Activity", "LAKEHOUSE_NAME": "lh", "WORKSPACE_NAME": "ws"}


class GetEnvTests(unittest.TestCase):
    def test_canonical_name_wins(self):
        with patch.dict(os.environ, {"TENANT_ID": "canon", "TenantId": "legacy"}, clear=True):
            self.assertEqual(monitor._get_env("TENANT_ID", "TenantId"), "canon")

    def test_falls_back_to_alias(self):
        with patch.dict(os.environ, {"TenantId": "legacy"}, clear=True):
            self.assertEqual(monitor._get_env("TENANT_ID", "TenantId"), "legacy")

    def test_empty_canonical_falls_back(self):
        with patch.dict(os.environ, {"TENANT_ID": "", "TenantId": "legacy"}, clear=True):
            self.assertEqual(monitor._get_env("TENANT_ID", "TenantId"), "legacy")

    def test_missing_raises_key_error_naming_canonical(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(KeyError) as cm:
                monitor._get_env("TENANT_ID", "TenantId")
        self.assertEqual(cm.exception.args[0], "TENANT_ID")


class MainTests(unittest.IsolatedAsyncioTestCase):
    async def _main(self, env):
        audit = MagicMock()
        audit.run = MagicMock(side_effect=lambda: _noop())
        with patch.dict(os.environ, env, clear=True), patch.object(monitor, "Audits", return_value=audit):
            await monitor.main()
        return audit

    async def test_legacy_credential_names_are_accepted(self):
        audit = await self._main({**BASE_ENV, "TenantId": "t", "ClientId": "c", "ClientSecret": "s"})
        audit.set_ServicePrincipal.assert_called_once_with(tenant_id="t", client_id="c", client_secret="s")

    async def test_canonical_names_take_priority(self):
        audit = await self._main({**BASE_ENV, "TENANT_ID": "T", "CLIENT_ID": "C", "CLIENT_SECRET": "S",
                                  "TenantId": "t", "ClientId": "c", "ClientSecret": "s"})
        audit.set_ServicePrincipal.assert_called_once_with(tenant_id="T", client_id="C", client_secret="S")

    async def test_missing_credentials_raise(self):
        with self.assertRaises(KeyError):
            await self._main({**BASE_ENV, "TENANT_ID": "T", "CLIENT_ID": "C"})

    async def test_storage_connection_string_alias(self):
        audit = await self._main({**BASE_ENV, "TENANT_ID": "T", "CLIENT_ID": "C", "CLIENT_SECRET": "S",
                                  "STORAGE_ACCOUNT_CONNECTION_STRING": "conn",
                                  "STORAGE_ACCOUNT_CONTAINER_NAME": "box"})
        audit.set_StorageAccountConnStr.assert_called_once_with("conn")
        audit.set_StorageAccountContainerName.assert_called_once_with("box")
        audit.set_on_fabric.assert_called_once_with(False)
        audit.set_LakehouseName.assert_not_called()

    async def test_canonical_storage_conn_str_preferred_over_alias(self):
        audit = await self._main({**BASE_ENV, "TENANT_ID": "T", "CLIENT_ID": "C", "CLIENT_SECRET": "S",
                                  "STORAGE_ACCOUNT_CONN_STR": "canon",
                                  "STORAGE_ACCOUNT_CONNECTION_STRING": "alias",
                                  "STORAGE_ACCOUNT_CONTAINER_NAME": "box"})
        audit.set_StorageAccountConnStr.assert_called_once_with("canon")

    async def test_new_module_cron_env_vars_are_wired(self):
        audit = await self._main({**BASE_ENV, "TENANT_ID": "T", "CLIENT_ID": "C", "CLIENT_SECRET": "S",
                                  "FABRICITEMS_CRON": "1 * * * *", "WORKSPACES_CRON": "2 * * * *",
                                  "CAPACITYMETRICS_CRON": "3 * * * *", "DOMAINS_CRON": "4 * * * *"})
        audit.set_FabricItems_cron.assert_called_once_with("1 * * * *")
        audit.set_Workspaces_cron.assert_called_once_with("2 * * * *")
        audit.set_CapacityMetrics_cron.assert_called_once_with("3 * * * *")
        audit.set_Domains_cron.assert_called_once_with("4 * * * *")
        audit.set_Roles_cron.assert_not_called()


async def _noop():
    return None


if __name__ == "__main__":
    unittest.main()
