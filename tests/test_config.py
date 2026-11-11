"""Merged profile/CLI configuration preserves collector and local-output safeguards."""

import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app import monitor
from env.config import build_audit
from env.notebook import run

CREDS = {"TENANT_ID": "tenant", "CLIENT_ID": "client", "CLIENT_SECRET": "test-secret"}


class ConfigTests(unittest.TestCase):
    def test_cli_overrides_profile_without_running_collection(self):
        with (
            patch(
                "env.config.load_profile",
                return_value={
                    "APPLICATION_MODULES": "Activity",
                    "CLOUD_ENVIRONMENT": "Commercial",
                },
            ),
            patch.object(monitor, "main", new_callable=AsyncMock) as main,
        ):
            monitor.cli(
                [
                    "--profile",
                    "unused.json",
                    "--modules",
                    "FabricItemDefinitions",
                    "--base",
                    "--cloud-environment",
                    "GccHigh",
                    "--env-file",
                    "unused.env",
                ]
            )
        main.assert_awaited_once_with(
            settings={
                "APPLICATION_MODULES": "FabricItemDefinitions",
                "CLOUD_ENVIRONMENT": "GccHigh",
                "ALL_WORKSPACES": True,
            },
            env_file="unused.env",
        )

    def test_profile_local_output_overrides_remote_storage_and_environment_credentials(
        self,
    ):
        with (
            tempfile.TemporaryDirectory() as output,
            patch.dict(
                os.environ, {"COMMERCIAL_TENANT_ID": "environment-tenant"}, clear=True
            ),
        ):
            audit = build_audit(
                {
                    **CREDS,
                    "LOCAL_OUTPUT_PATH": output,
                    "OUTPUT_PATH": "unused",
                    "STORAGE_ACCOUNT_URL": "https://unused.blob.test",
                    "STORAGE_ACCOUNT_CONTAINER_NAME": "unused",
                    "LAKEHOUSE_NAME": "unused",
                    "FABRICITEMDEFINITIONS_CRON": "0 0 * * *",
                }
            )
        self.assertEqual(audit.context.OutputPath, output)
        self.assertFalse(audit.context.on_fabric)
        self.assertIsNone(audit.context.StorageAccountContainerName)
        self.assertIsNone(audit.context.LakehouseName)
        self.assertEqual(audit.context.ServicePrincipal["TenantId"], "tenant")
        self.assertEqual(audit.context.get_cron("FabricItemDefinitions"), "0 0 * * *")

    def test_local_aliases_and_canonical_environment_precedence(self):
        with (
            tempfile.TemporaryDirectory() as output,
            patch.dict(
                os.environ,
                {
                    "TenantId": "legacy",
                    **CREDS,
                    "LOCAL_OUTPUT_PATH": output,
                    "COMMERCIAL_TENANT_ID": "commercial",
                },
                clear=True,
            ),
        ):
            audit = build_audit()
            self.assertEqual(audit.context.ServicePrincipal["TenantId"], "commercial")
            os.environ.pop("COMMERCIAL_TENANT_ID")
            audit = build_audit()
            self.assertEqual(audit.context.ServicePrincipal["TenantId"], "tenant")

    def test_sovereign_local_output_does_not_use_commercial_aliases(self):
        with (
            tempfile.TemporaryDirectory() as output,
            patch.dict(
                os.environ,
                {
                    "COMMERCIAL_TENANT_ID": "wrong-cloud",
                },
                clear=True,
            ),
        ):
            audit = build_audit(
                {
                    **CREDS,
                    "CLOUD_ENVIRONMENT": "GccHigh",
                    "LOCAL_OUTPUT_PATH": output,
                }
            )
        self.assertEqual(audit.context.cloud.name, "GccHigh")
        self.assertEqual(audit.context.ServicePrincipal["TenantId"], "tenant")

    def test_sovereign_onelake_is_rejected(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaisesRegex(RuntimeError, "OneLake"),
        ):
            build_audit(
                {**CREDS, "CLOUD_ENVIRONMENT": "Dod", "LAKEHOUSE_NAME": "unused"}
            )


class EntryPointTests(unittest.IsolatedAsyncioTestCase):
    async def test_notebook_uses_collector_crons_without_loading_dotenv(self):
        audit = MagicMock(run=AsyncMock(return_value=True))
        with (
            patch("env.config.Audits", return_value=audit),
            patch.dict(os.environ, {}, clear=True),
        ):
            await run(
                {
                    **CREDS,
                    "OUTPUT_PATH": "unused",
                    "FABRICITEMJOBHISTORY_CRON": "0 0 * * *",
                    "CAPACITY_METRICS_CRON": "0 1 * * *",
                }
            )
        audit.set_FabricItemJobHistory_cron.assert_called_once_with("0 0 * * *")
        audit.set_CapacityMetrics_cron.assert_called_once_with("0 1 * * *")
        audit.run.assert_awaited_once()

    async def test_main_reports_failure_after_audit_has_saved_checkpoints(self):
        audit = MagicMock(run=AsyncMock(return_value=False))
        with (
            patch.object(monitor, "Audits", return_value=audit),
            patch.dict(os.environ, CREDS, clear=True),
            self.assertRaisesRegex(RuntimeError, "run failed"),
        ):
            await monitor.main()
