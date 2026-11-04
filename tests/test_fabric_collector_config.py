"""Opt-in scope validation and public scheduler/configuration integration."""

import json
import os
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

from app import monitor
from env import audit as audit_module
from env.audit import Audits
from env.modules import FabricItemJobHistory
from tests.fabric_helpers import NAMES, CollectorTestCase, item


class CollectorScopeTests(CollectorTestCase):
    async def test_bad_scopes_reject_before_authentication_or_storage(self):
        from env.modules import FabricItemAccessPermissions

        for key, collect, maximum in (
            ("FABRIC_ITEM_ACCESS_SCOPE", FabricItemAccessPermissions, 50),
            ("FABRIC_ITEM_JOB_SCOPE", FabricItemJobHistory, 100),
        ):
            for raw in (
                "not-json",
                "null",
                "[]",
                "{}",
                "[1]",
                json.dumps([{**item(), "workspaceId": "not-a-uuid"}]),
                json.dumps([{**item(), "type": "../Notebook"}]),
                json.dumps([item(), item()]),
                json.dumps([item(number=100 + i) for i in range(maximum + 1)]),
            ):
                with self.subTest(key=key, raw=raw[:60]):
                    ctx = self.context()
                    with (
                        patch.dict(os.environ, {key: raw}),
                        self.assertRaises((ValueError, TypeError)),
                    ):
                        await collect(ctx)
                    ctx._safe_get.assert_not_awaited()
                    ctx.clients["tenant"].get_headers.assert_not_called()
                    ctx.fm.save_snapshot.assert_not_awaited()

    async def test_unsupported_job_type_cannot_masquerade_as_empty_history(self):
        ctx = self.context()
        with (
            patch.dict(
                os.environ, {"FABRIC_ITEM_JOB_SCOPE": json.dumps([item(kind="Report")])}
            ),
            self.assertRaisesRegex(ValueError, "supports Notebook"),
        ):
            await FabricItemJobHistory(ctx)
        ctx._safe_get.assert_not_awaited()
        ctx.fm.save_snapshot.assert_not_awaited()


class CollectorRegistrationTests(CollectorTestCase):
    async def test_entrypoint_cron_settings_control_real_public_dispatch(self):
        expressions = ("0 1 * * *", "0 2 * * *", "0 3 * * *", "0 4 * * *", "0 5 * * *")
        # Avoid real auth/storage setup but retain app -> Audits -> Context -> cron
        # selection and the public named dispatch path.
        audit = Audits()
        audit.context.logger = MagicMock()
        audit.fm = MagicMock()
        old = "2025-12-01T00:00:00.000000Z"
        state = {name.lower(): {"lastRun": old} for name in NAMES}
        audit.fm.read = AsyncMock(return_value=state)
        audit.fm.save = AsyncMock()
        env = {
            "TENANT_ID": "offline-tenant",
            "CLIENT_ID": "offline-client",
            "CLIENT_SECRET": "offline-placeholder",
            "APPLICATION_MODULES": ",".join(NAMES),
            "LAKEHOUSE_NAME": "OfflineLakehouse",
            "WORKSPACE_NAME": "OfflineWorkspace",
            **{name.upper() + "_CRON": cron for name, cron in zip(NAMES, expressions)},
        }

        async def collector(context):
            """Offline configured collector."""
            return True

        modules = {name: AsyncMock(side_effect=collector) for name in NAMES}
        for module in modules.values():
            module.__doc__ = collector.__doc__
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, env, clear=True))
            stack.enter_context(patch.object(monitor, "Audits", return_value=audit))
            stack.enter_context(patch.object(audit, "_Audits__setup_clients"))
            due = stack.enter_context(
                patch.object(
                    audit_module,
                    "is_function_due",
                    return_value=True,
                )
            )
            for name, module in modules.items():
                stack.enter_context(patch.object(audit_module, name, module))
            await monitor.main()
        self.assertEqual([c.args[0] for c in due.call_args_list], list(expressions))
        for name in NAMES:
            modules[name].assert_awaited_once_with(audit.context)
            self.assertNotEqual(state[name.lower()]["lastRun"], old)

    async def test_unselected_new_collectors_do_not_run_with_scope_configuration_present(
        self,
    ):
        audit = Audits()
        audit.context.ApplicationModules = "Activity"
        audit.context.logger = MagicMock()
        audit.fm = MagicMock(
            read=AsyncMock(
                return_value={"activity": {"lastRun": "2025-12-01T00:00:00.000000Z"}}
            ),
            save=AsyncMock(),
        )

        async def activity(context):
            """Offline activity."""
            return True

        with ExitStack() as stack:
            stack.enter_context(
                patch.dict(
                    os.environ,
                    {
                        "FABRIC_ITEM_ACCESS_SCOPE": json.dumps([item()]),
                        "FABRIC_ITEM_JOB_SCOPE": json.dumps([item()]),
                    },
                )
            )
            stack.enter_context(patch.object(audit, "_Audits__setup_clients"))
            stack.enter_context(patch.object(audit_module, "Activity", activity))
            collectors = [
                stack.enter_context(patch.object(audit_module, name, AsyncMock()))
                for name in NAMES
            ]
            await audit.run()
        for collector in collectors:
            collector.assert_not_awaited()
