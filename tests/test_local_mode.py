"""LOCAL_OUTPUT_PATH local mode: env handling, File_Management routing, state round-trip."""

import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import yaml

from app import monitor
from env import audit as audit_mod
from env.audit import Audits
from env.utility.file_management import File_Management

CREDS = {"TENANT_ID": "T", "CLIENT_ID": "C", "CLIENT_SECRET": "S"}
SECRETS = (
    "com-tenant",
    "com-client",
    "com-secret",
    "std-tenant",
    "std-client",
    "std-secret",
)


async def _noop():
    return None


class LocalEnvTests(unittest.TestCase):
    def test_commercial_names_win_in_local_mode(self):
        env = {
            "LOCAL_OUTPUT_PATH": "/x",
            "COMMERCIAL_TENANT_ID": "com",
            "TENANT_ID": "std",
            "TenantId": "old",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(monitor._get_env("TENANT_ID", "TenantId"), "com")

    def test_each_credential_alias_in_local_mode(self):
        env = {
            "LOCAL_OUTPUT_PATH": "/x",
            "COMMERCIAL_CLIENT_ID": "cc",
            "COMMERCIAL_CLIENT_SECRET": "cs",
            "CLIENT_ID": "c",
            "CLIENT_SECRET": "s",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(monitor._get_env("CLIENT_ID", "ClientId"), "cc")
            self.assertEqual(monitor._get_env("CLIENT_SECRET", "ClientSecret"), "cs")

    def test_local_mode_falls_back_to_standard_then_legacy(self):
        with patch.dict(
            os.environ,
            {"LOCAL_OUTPUT_PATH": "/x", "TENANT_ID": "std", "TenantId": "old"},
            clear=True,
        ):
            self.assertEqual(monitor._get_env("TENANT_ID", "TenantId"), "std")
        with patch.dict(
            os.environ, {"LOCAL_OUTPUT_PATH": "/x", "TenantId": "old"}, clear=True
        ):
            self.assertEqual(monitor._get_env("TENANT_ID", "TenantId"), "old")

    def test_empty_commercial_value_falls_back(self):
        env = {
            "LOCAL_OUTPUT_PATH": "/x",
            "COMMERCIAL_TENANT_ID": "",
            "TENANT_ID": "std",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(monitor._get_env("TENANT_ID", "TenantId"), "std")

    def test_commercial_ignored_without_local_mode(self):
        with patch.dict(
            os.environ, {"COMMERCIAL_TENANT_ID": "com", "TENANT_ID": "std"}, clear=True
        ):
            self.assertEqual(monitor._get_env("TENANT_ID", "TenantId"), "std")
        with (
            patch.dict(os.environ, {"COMMERCIAL_TENANT_ID": "com"}, clear=True),
            self.assertRaises(KeyError),
        ):
            monitor._get_env("TENANT_ID", "TenantId")

    def test_empty_local_output_path_is_not_local_mode(self):
        env = {
            "LOCAL_OUTPUT_PATH": "",
            "COMMERCIAL_TENANT_ID": "com",
            "TENANT_ID": "std",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(monitor._get_env("TENANT_ID", "TenantId"), "std")

    def test_non_credential_names_unaffected_in_local_mode(self):
        with patch.dict(
            os.environ,
            {"LOCAL_OUTPUT_PATH": "/x", "COMMERCIAL_TENANT_ID": "com", "OTHER": "o"},
            clear=True,
        ):
            self.assertEqual(monitor._get_env("OTHER"), "o")
            with self.assertRaises(KeyError):
                monitor._get_env("MISSING")

    def test_missing_credential_in_local_mode_raises_key_error(self):
        with (
            patch.dict(os.environ, {"LOCAL_OUTPUT_PATH": "/x"}, clear=True),
            self.assertRaises(KeyError) as cm,
        ):
            monitor._get_env("CLIENT_ID", "ClientId")
        self.assertIn(cm.exception.args[0], ("CLIENT_ID", "COMMERCIAL_CLIENT_ID"))


class ResolveLocalPathTests(unittest.TestCase):
    def test_creates_nested_directory_and_returns_absolute(self):
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "a", "b")
            result = monitor._resolve_local_output_path(target)
            self.assertEqual(result, os.path.abspath(target))
            self.assertTrue(os.path.isdir(target))

    def test_expands_home(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"HOME": d}):
            result = monitor._resolve_local_output_path("~/out")
            self.assertEqual(result, os.path.join(os.path.abspath(d), "out"))
            self.assertTrue(os.path.isdir(result))

    def test_relative_path_is_made_absolute(self):
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            os.chdir(d)
            try:
                result = monitor._resolve_local_output_path("rel")
            finally:
                os.chdir(cwd)
            self.assertTrue(os.path.isabs(result))
            self.assertTrue(os.path.isdir(os.path.join(d, "rel")))

    def test_path_that_is_a_file_raises_runtime_error(self):
        with tempfile.NamedTemporaryFile() as f, self.assertRaises(RuntimeError) as cm:
            monitor._resolve_local_output_path(f.name)
        self.assertIn("LOCAL_OUTPUT_PATH", str(cm.exception))

    def test_uncreatable_path_raises_runtime_error(self):
        with tempfile.NamedTemporaryFile() as f, self.assertRaises(RuntimeError):
            monitor._resolve_local_output_path(os.path.join(f.name, "sub"))

    def test_non_writable_directory_raises_runtime_error(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch.object(monitor.os, "access", return_value=False),
            self.assertRaises(RuntimeError),
        ):
            monitor._resolve_local_output_path(d)


class LocalMainTests(unittest.IsolatedAsyncioTestCase):
    async def _main(self, env):
        audit = MagicMock()
        audit.run = MagicMock(side_effect=lambda: _noop())
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(monitor, "Audits", return_value=audit),
        ):
            await monitor.main()
        return audit

    async def test_local_mode_sets_output_path_and_not_on_fabric(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out")
            audit = await self._main(
                {"APPLICATION_MODULES": "Activity", "LOCAL_OUTPUT_PATH": out, **CREDS}
            )
            audit.set_OutputPath.assert_called_once_with(os.path.abspath(out))
            audit.set_on_fabric.assert_called_once_with(False)
            self.assertTrue(os.path.isdir(out))

    async def test_local_mode_ignores_blob_and_lakehouse_settings(self):
        with tempfile.TemporaryDirectory() as d:
            env = {
                "APPLICATION_MODULES": "Activity",
                "LOCAL_OUTPUT_PATH": d,
                "STORAGE_ACCOUNT_CONN_STR": "conn",
                "STORAGE_ACCOUNT_URL": "https://acct.blob.core.windows.net",
                "STORAGE_ACCOUNT_CONTAINER_NAME": "box",
                "LAKEHOUSE_NAME": "lh",
                "WORKSPACE_NAME": "ws",
                **CREDS,
            }
            audit = await self._main(env)
        audit.set_OutputPath.assert_called_once()
        audit.set_StorageAccountConnStr.assert_not_called()
        audit.set_StorageAccountContainerName.assert_not_called()
        audit.set_StorageAccountUrl.assert_not_called()
        audit.set_LakehouseName.assert_not_called()
        audit.set_WorkspaceName.assert_not_called()
        audit.run.assert_called_once()

    async def test_local_mode_uses_commercial_credentials(self):
        with tempfile.TemporaryDirectory() as d:
            env = {
                "APPLICATION_MODULES": "Activity",
                "LOCAL_OUTPUT_PATH": d,
                "COMMERCIAL_TENANT_ID": "ct",
                "COMMERCIAL_CLIENT_ID": "cc",
                "COMMERCIAL_CLIENT_SECRET": "cs",
                **CREDS,
            }
            audit = await self._main(env)
        audit.set_ServicePrincipal.assert_called_once_with(
            tenant_id="ct", client_id="cc", client_secret="cs"
        )

    async def test_commercial_credentials_ignored_without_local_mode(self):
        env = {
            "APPLICATION_MODULES": "Activity",
            "LAKEHOUSE_NAME": "lh",
            "WORKSPACE_NAME": "ws",
            "COMMERCIAL_TENANT_ID": "ct",
            "COMMERCIAL_CLIENT_ID": "cc",
            "COMMERCIAL_CLIENT_SECRET": "cs",
            **CREDS,
        }
        audit = await self._main(env)
        audit.set_ServicePrincipal.assert_called_once_with(
            tenant_id="T", client_id="C", client_secret="S"
        )
        audit.set_OutputPath.assert_not_called()

    async def test_unusable_local_path_raises_before_run(self):
        with tempfile.NamedTemporaryFile() as f, self.assertRaises(RuntimeError):
            await self._main(
                {
                    "APPLICATION_MODULES": "Activity",
                    "LOCAL_OUTPUT_PATH": f.name,
                    **CREDS,
                }
            )

    async def test_no_local_path_leaves_behaviour_unchanged(self):
        audit = await self._main(
            {
                "APPLICATION_MODULES": "Activity",
                "LAKEHOUSE_NAME": "lh",
                "WORKSPACE_NAME": "ws",
                **CREDS,
            }
        )
        audit.set_OutputPath.assert_not_called()
        audit.set_LakehouseName.assert_called_once()

    async def test_credential_values_are_never_logged(self):
        with tempfile.TemporaryDirectory() as d:
            env = {
                "APPLICATION_MODULES": "Activity",
                "LOCAL_OUTPUT_PATH": d,
                "COMMERCIAL_TENANT_ID": "com-tenant",
                "COMMERCIAL_CLIENT_ID": "com-client",
                "COMMERCIAL_CLIENT_SECRET": "com-secret",
                "TENANT_ID": "std-tenant",
                "CLIENT_ID": "std-client",
                "CLIENT_SECRET": "std-secret",
            }
            with self.assertLogs(level=logging.DEBUG) as cm:
                logging.getLogger().info("sentinel")
                with patch("sys.stdout") as out:
                    await self._main(env)
        text = "\n".join(cm.output) + "".join(str(c) for c in out.mock_calls)
        for secret in SECRETS:
            self.assertNotIn(secret, text)


def _ctx(**kw):
    base = {
        "StorageAccountContainerName": None,
        "StorageAccountContainerRootPath": None,
        "OutputPath": None,
        "LakehouseName": None,
        "PathInLakehouse": "p",
        "on_fabric": False,
        "logger": MagicMock(),
    }
    base.update(kw)
    return SimpleNamespace(**base)


class FileManagementLocalTests(unittest.IsolatedAsyncioTestCase):
    def test_content_prefers_local_without_blob_or_credential(self):
        ctx = _ctx(
            OutputPath="/tmp/x", StorageAccountContainerName="box", LakehouseName="lh"
        )
        fm = File_Management()
        with (
            patch("env.utility.file_management.Blob_File_Management") as blob,
            patch("env.utility.file_management.File_Table_Management") as ftm,
            patch("azure.identity.DefaultAzureCredential") as cred,
        ):
            fm.content(ctx)
        blob.assert_not_called()
        ftm.assert_not_called()
        cred.assert_not_called()
        self.assertIsNotNone(fm.lfm)
        self.assertEqual(fm.lfm.root_path, "/tmp/x")
        self.assertIsNone(fm.bfm)
        self.assertIsNone(fm.ftm)

    async def test_save_and_read_use_local_even_when_blob_configured(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = _ctx(
                OutputPath=d, StorageAccountContainerName="box", LakehouseName="lh"
            )
            fm = File_Management()
            fm.content(ctx)
            fm.bfm = MagicMock(write_to_file=AsyncMock(), read_from_file=AsyncMock())
            fm.ftm = MagicMock(write_json_to_file=AsyncMock())
            await fm.save("sub/", "f.json", {"a": 1})
            self.assertEqual(json.loads(Path(d, "sub", "f.json").read_text()), {"a": 1})
            self.assertEqual(
                json.loads(await fm.read(path="sub/", file_name="f.json")), {"a": 1}
            )
            fm.bfm.write_to_file.assert_not_awaited()
            fm.bfm.read_from_file.assert_not_awaited()
            fm.ftm.write_json_to_file.assert_not_awaited()

    async def test_save_string_content_and_missing_read_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            fm = File_Management()
            fm.content(_ctx(OutputPath=d))
            await fm.save("", "t.txt", "hello")
            self.assertEqual(Path(d, "t.txt").read_text(), "hello")
            self.assertIsNone(await fm.read(path="", file_name="absent.yaml"))

    async def test_local_save_oserror_is_reraised(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "blocker").write_text("file")
            ctx = _ctx(OutputPath=d)
            fm = File_Management()
            fm.content(ctx)
            with self.assertRaises(OSError):
                await fm.save("blocker/", "f.json", {"a": 1})
            ctx.logger.error.assert_called()

    async def test_local_non_oserror_is_still_swallowed(self):
        ctx = _ctx(OutputPath="/tmp/x")
        fm = File_Management()
        fm.context = ctx
        fm.lfm = MagicMock(save=AsyncMock(side_effect=ValueError("bad")))
        await fm.save("", "f", {"a": 1})
        ctx.logger.error.assert_called()

    async def test_blob_save_oserror_is_swallowed(self):
        ctx = _ctx(StorageAccountContainerName="box")
        fm = File_Management()
        fm.context = ctx
        fm.bfm = MagicMock(write_to_file=AsyncMock(side_effect=OSError("down")))
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DRY_RUN", None)
            await fm.save("", "f", {"a": 1})
        ctx.logger.error.assert_called()

    async def test_lakehouse_save_oserror_is_swallowed(self):
        ctx = _ctx(LakehouseName="lh")
        fm = File_Management()
        fm.context = ctx
        fm.ftm = MagicMock(write_json_to_file=AsyncMock(side_effect=OSError("down")))
        await fm.save("", "f", {"a": 1})
        ctx.logger.error.assert_called()


class StateParsingTests(unittest.IsolatedAsyncioTestCase):
    def _audit(self, state):
        a = Audits()
        a.context.ApplicationModules = "Activity"
        a.fm = MagicMock()
        a.fm.read = AsyncMock(return_value=state)
        a.fm.save = AsyncMock()
        a.context.logger = MagicMock()
        return a

    async def _run(self, a):
        calls = []

        async def fn(context):
            """Fake module"""
            calls.append(1)
            return True

        with (
            patch.object(audit_mod, "Activity", fn),
            patch.object(audit_mod, "PbiClient", MagicMock()),
            patch.object(audit_mod, "GraphClient", MagicMock()),
            patch.object(audit_mod, "TenantClient", MagicMock()),
        ):
            await a.run()
        return calls

    async def test_yaml_text_state_is_parsed(self):
        a = self._audit(
            "activity:\n  lastRun: '2020-01-01T00:00:00.000000Z'\n  extra: keep\n"
        )
        calls = await self._run(a)
        self.assertEqual(calls, [1])
        saved = a.fm.save.await_args.args[2]
        self.assertEqual(saved["activity"]["extra"], "keep")
        self.assertNotEqual(saved["activity"]["lastRun"], "2020-01-01T00:00:00.000000Z")

    async def test_json_text_state_is_parsed(self):
        a = self._audit(
            '{"activity": {"lastRun": "2020-01-01T00:00:00.000000Z", "extra": 1}}'
        )
        await self._run(a)
        self.assertEqual(a.fm.save.await_args.args[2]["activity"]["extra"], 1)

    async def test_blank_and_whitespace_start_fresh(self):
        for text in ("", "  \n\t"):
            a = self._audit(text)
            self.assertEqual(await self._run(a), [1])
            self.assertIn("tenant", a.fm.save.await_args_list[0].args[2])

    async def test_non_mapping_yaml_aborts(self):
        for text in ("- a\n- b\n", "just a string", "42"):
            a = self._audit(text)
            self.assertEqual(await self._run(a), [])
            a.fm.save.assert_not_awaited()
            a.context.logger.error.assert_called()

    async def test_non_mapping_parsed_value_aborts(self):
        a = self._audit(["x"])
        self.assertEqual(await self._run(a), [])
        a.fm.save.assert_not_awaited()

    async def test_malformed_yaml_aborts(self):
        a = self._audit("a: [unclosed\n")
        self.assertEqual(await self._run(a), [])
        a.fm.save.assert_not_awaited()

    async def test_yaml_null_document_starts_fresh(self):
        a = self._audit("null")
        self.assertEqual(await self._run(a), [1])

    async def test_python_object_tags_rejected(self):
        a = self._audit("!!python/object/apply:os.system ['echo hi']")
        self.assertEqual(await self._run(a), [])
        a.fm.save.assert_not_awaited()

    async def test_already_parsed_dict_unchanged(self):
        a = self._audit(
            {"activity": {"lastRun": "2020-01-01T00:00:00.000000Z", "k": "v"}}
        )
        self.assertEqual(await self._run(a), [1])
        self.assertEqual(a.fm.save.await_args.args[2]["activity"]["k"], "v")


class LocalRoundTripTests(unittest.IsolatedAsyncioTestCase):
    def _audit(self, out_dir, modules="Activity"):
        a = Audits()
        a.context.ApplicationModules = modules
        a.context.set_OutputPath(out_dir)
        a.context.logger = MagicMock()
        return a

    async def _run(self, a, **mods):
        patches = [patch.object(audit_mod, n, f) for n, f in mods.items()]
        patches += [
            patch.object(audit_mod, c, MagicMock())
            for c in ("PbiClient", "GraphClient", "TenantClient")
        ]
        for p in patches:
            p.start()
        try:
            await a.run()
        finally:
            for p in patches:
                p.stop()

    async def test_state_created_then_round_trips(self):
        async def ok(context):
            """Fake module"""
            await context.fm.save("activity/", "data.json", [{"id": 1}])
            return True

        with tempfile.TemporaryDirectory() as d:
            await self._run(self._audit(d), Activity=ok)
            state = yaml.safe_load(Path(d, "state.yaml").read_text())
            self.assertIn("activity", state)
            first = state["activity"]["lastRun"]
            self.assertEqual(
                json.loads(Path(d, "activity", "data.json").read_text()), [{"id": 1}]
            )
            # Second run reads the saved file back; extra keys survive.
            state["activity"]["extra"] = "keep"
            Path(d, "state.yaml").write_text(yaml.safe_dump(state))
            await self._run(self._audit(d), Activity=ok)
            state2 = yaml.safe_load(Path(d, "state.yaml").read_text())
            self.assertEqual(state2["activity"]["extra"], "keep")
            self.assertGreaterEqual(state2["activity"]["lastRun"], first)

    async def test_failed_local_write_marks_module_failed_and_keeps_last_run(self):
        old = "2020-01-01T00:00:00.000000Z"

        async def bad(context):
            """Fake module"""
            await context.fm.save("blocker/", "data.json", {"a": 1})
            return True

        with tempfile.TemporaryDirectory() as d:
            Path(d, "state.yaml").write_text(
                yaml.safe_dump({"activity": {"lastRun": old}})
            )
            Path(d, "blocker").write_text("a file, not a directory")
            a = self._audit(d)
            await self._run(a, Activity=bad)
            state = yaml.safe_load(Path(d, "state.yaml").read_text())
            self.assertEqual(state["activity"]["lastRun"], old)
            a.context.logger.warning.assert_called()

    async def test_failed_state_write_is_logged_not_raised(self):
        async def ok(context):
            """Fake module"""
            return True

        with tempfile.TemporaryDirectory() as d:
            a = self._audit(d)
            with patch(
                "env.utility.local.os.makedirs", side_effect=PermissionError("ro")
            ):
                await self._run(a, Activity=ok)
            a.context.logger.error.assert_called()
            self.assertFalse(Path(d, "state.yaml").exists())


if __name__ == "__main__":
    unittest.main()
