"""E5: admin paging helper, new admin modules and their cron wiring."""
import importlib
import os
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app import monitor
from env import modules as modules_pkg
from env.audit import Audits
from env.context import Context
from env.utility.admin_paging import fetch_all_pages
from tests.helpers import make_context

URL = "https://example.test/v1/admin/things"
FIXED = datetime(2024, 3, 7, 23, 59, 58)
DATE_PATH = "2024/03/07/"

gitconnections = importlib.import_module("env.modules.gitconnections")
tags = importlib.import_module("env.modules.tags")
delegatedsettings = importlib.import_module("env.modules.delegatedsettings")
widelysharedlinks = importlib.import_module("env.modules.widelysharedlinks")


def _seq(*responses):
    """AsyncMock returning responses in order (exceptions are raised)."""
    return AsyncMock(side_effect=list(responses))


class FetchAllPagesTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_page(self):
        ctx = make_context(invoke=_seq({"value": [1, 2]}))
        res = await fetch_all_pages(ctx, URL, {"h": "1"}, "value", "L")
        self.assertEqual(res, [1, 2])
        ctx.invokeAPI.assert_awaited_once_with(URL, headers={"h": "1"})

    async def test_multi_page_quotes_token_and_uses_separator(self):
        tok1, tok2 = "a b+c/d=&?", "next%token"
        ctx = make_context(invoke=_seq(
            {"value": [1], "continuationToken": tok1},
            {"value": [2], "continuationToken": tok2},
            {"value": [3]},
        ))
        res = await fetch_all_pages(ctx, URL, {}, "value", "L")
        self.assertEqual(res, [1, 2, 3])
        urls = [c.args[0] for c in ctx.invokeAPI.await_args_list]
        self.assertEqual(urls[0], URL)
        self.assertEqual(urls[1], f"{URL}?continuationToken=a%20b%2Bc%2Fd%3D%26%3F")
        self.assertEqual(urls[2], f"{URL}?continuationToken=next%25token")

    async def test_existing_query_uses_ampersand(self):
        url = URL + "?x=1"
        ctx = make_context(invoke=_seq({"value": [1], "continuationToken": "t"}, {"value": []}))
        await fetch_all_pages(ctx, url, {}, "value", "L")
        self.assertEqual(ctx.invokeAPI.await_args_list[1].args[0], url + "&continuationToken=t")

    async def test_missing_or_null_list_key_treated_as_empty(self):
        ctx = make_context(invoke=_seq({"value": None, "continuationToken": "t"}, {"other": 1}))
        self.assertEqual(await fetch_all_pages(ctx, URL, {}, "value", "L"), [])

    async def test_empty_token_ends_paging(self):
        ctx = make_context(invoke=_seq({"value": [1], "continuationToken": ""}))
        self.assertEqual(await fetch_all_pages(ctx, URL, {}, "value", "L"), [1])
        self.assertEqual(ctx.invokeAPI.await_count, 1)

    async def test_repeated_token_guard(self):
        ctx = make_context(invoke=_seq(
            {"value": [1], "continuationToken": "t"},
            {"value": [2], "continuationToken": "t"},
            {"value": [3]},  # must never be requested
        ))
        self.assertIsNone(await fetch_all_pages(ctx, URL, {}, "value", "L"))
        self.assertEqual(ctx.invokeAPI.await_count, 2)
        ctx.logger.error.assert_called_once()
        self.assertIn("repeated", ctx.logger.error.call_args.args[0])

    async def test_non_adjacent_repeated_token_detected(self):
        ctx = make_context(invoke=_seq(
            {"continuationToken": "a"}, {"continuationToken": "b"},
            {"continuationToken": "a"}, {"value": []},
        ))
        self.assertIsNone(await fetch_all_pages(ctx, URL, {}, "value", "L"))
        self.assertEqual(ctx.invokeAPI.await_count, 3)

    async def test_403_and_404_warn_and_return_none(self):
        for status in (403, 404):
            with self.subTest(status=status):
                ctx = make_context(invoke=_seq({"ERROR": "x", "status": status}))
                self.assertIsNone(await fetch_all_pages(ctx, URL, {}, "value", "Lbl"))
                ctx.logger.warning.assert_called_once()
                self.assertIn(str(status), ctx.logger.warning.call_args.args[0])
                self.assertIn("Lbl", ctx.logger.warning.call_args.args[0])
                ctx.logger.error.assert_not_called()

    async def test_other_errors_log_error_and_return_none(self):
        for resp in ({"ERROR": "x", "status": 500}, {"ERROR": "x"}, {}, None, "str", []):
            with self.subTest(resp=resp):
                ctx = make_context(invoke=_seq(resp))
                self.assertIsNone(await fetch_all_pages(ctx, URL, {}, "value", "L"))
                ctx.logger.error.assert_called_once()
                ctx.logger.warning.assert_not_called()

    async def test_error_on_later_page_discards_results(self):
        ctx = make_context(invoke=_seq(
            {"value": [1], "continuationToken": "t"}, {"ERROR": "x", "status": 429}))
        self.assertIsNone(await fetch_all_pages(ctx, URL, {}, "value", "L"))

    async def test_403_on_later_page_warns(self):
        ctx = make_context(invoke=_seq(
            {"value": [1], "continuationToken": "t"}, {"ERROR": "x", "status": 403}))
        self.assertIsNone(await fetch_all_pages(ctx, URL, {}, "value", "L"))
        ctx.logger.warning.assert_called_once()


class _ModuleBase:
    mod = None

    def patch_now(self):
        p = patch.object(self.mod, "utc_now", return_value=FIXED)
        p.start()
        self.addCleanup(p.stop)

    async def test_none_context_raises(self):
        with self.assertRaises(RuntimeError):
            await self.mod.main(None)
        with self.assertRaises(RuntimeError):
            await self.mod.main()


class _SimpleModuleTests(_ModuleBase):
    url = None
    folder = None
    filename = None

    async def test_success_saves_items(self):
        self.patch_now()
        ctx = make_context(invoke=_seq({"value": [{"id": 1}], "continuationToken": "a/b"},
                                       {"value": [{"id": 2}]}))
        self.assertTrue(await self.mod.main(ctx))
        urls = [c.args[0] for c in ctx.invokeAPI.await_args_list]
        self.assertEqual(urls, [self.url, f"{self.url}?continuationToken=a%2Fb"])
        for c in ctx.invokeAPI.await_args_list:
            self.assertEqual(c.kwargs["headers"], ctx.clients["pbi"].get_headers)
        ctx.fm.save.assert_awaited_once_with(
            f"{self.folder}/{DATE_PATH}", self.filename, [{"id": 1}, {"id": 2}])

    async def test_empty_result_is_saved(self):
        self.patch_now()
        ctx = make_context(invoke=_seq({"value": []}))
        self.assertTrue(await self.mod.main(ctx))
        ctx.fm.save.assert_awaited_once_with(f"{self.folder}/{DATE_PATH}", self.filename, [])

    async def test_failure_returns_false_and_saves_nothing(self):
        for resp in ({"ERROR": "x", "status": 403}, {"ERROR": "x", "status": 404},
                     {"ERROR": "x", "status": 500}):
            with self.subTest(resp=resp):
                ctx = make_context(invoke=_seq(resp))
                self.assertIs(await self.mod.main(ctx), False)
                ctx.fm.save.assert_not_awaited()

    async def test_zero_pad_date(self):
        p = patch.object(self.mod, "utc_now", return_value=datetime(2025, 1, 2))
        p.start()
        self.addCleanup(p.stop)
        ctx = make_context(invoke=_seq({"value": []}))
        await self.mod.main(ctx)
        self.assertEqual(ctx.fm.save.await_args.args[0], f"{self.folder}/2025/01/02/")


class GitConnectionsTests(_SimpleModuleTests, unittest.IsolatedAsyncioTestCase):
    mod = gitconnections
    url = "https://api.fabric.microsoft.com/v1/admin/workspaces/discoverGitConnections"
    folder = "gitconnections"
    filename = "gitconnections.json"


class TagsTests(_SimpleModuleTests, unittest.IsolatedAsyncioTestCase):
    mod = tags
    url = "https://api.fabric.microsoft.com/v1/admin/tags"
    folder = "tags"
    filename = "tags.json"


class DelegatedSettingsTests(_ModuleBase, unittest.IsolatedAsyncioTestCase):
    mod = delegatedsettings
    base = "https://api.fabric.microsoft.com/v1/admin"

    def _invoke(self, by_scope):
        async def invoke(url, headers=None):
            for scope, resp in by_scope.items():
                if f"/admin/{scope}/delegatedTenantSettingOverrides" in url:
                    return resp
            raise AssertionError(url)
        return AsyncMock(side_effect=invoke)

    async def test_all_scopes_saved(self):
        self.patch_now()
        ctx = make_context(invoke=self._invoke({
            "capacities": {"value": [1]}, "domains": {"value": [2]}, "workspaces": {"value": []}}))
        self.assertTrue(await self.mod.main(ctx))
        urls = [c.args[0] for c in ctx.invokeAPI.await_args_list]
        self.assertEqual(urls, [f"{self.base}/{s}/delegatedTenantSettingOverrides"
                                for s in ("capacities", "domains", "workspaces")])
        saved = [c.args for c in ctx.fm.save.await_args_list]
        self.assertEqual(saved, [
            (f"delegatedsettings/capacities/{DATE_PATH}", "capacities.json", [1]),
            (f"delegatedsettings/domains/{DATE_PATH}", "domains.json", [2]),
            (f"delegatedsettings/workspaces/{DATE_PATH}", "workspaces.json", []),
        ])

    async def test_partial_failure_saves_successes_returns_false(self):
        self.patch_now()
        ctx = make_context(invoke=self._invoke({
            "capacities": {"ERROR": "x", "status": 403},
            "domains": {"value": [2]},
            "workspaces": {"value": [3]}}))
        self.assertIs(await self.mod.main(ctx), False)
        saved = [c.args for c in ctx.fm.save.await_args_list]
        self.assertEqual(saved, [
            (f"delegatedsettings/domains/{DATE_PATH}", "domains.json", [2]),
            (f"delegatedsettings/workspaces/{DATE_PATH}", "workspaces.json", [3]),
        ])

    async def test_all_fail(self):
        ctx = make_context(invoke=self._invoke({s: {"ERROR": "x", "status": 500}
                                                for s in ("capacities", "domains", "workspaces")}))
        self.assertIs(await self.mod.main(ctx), False)
        ctx.fm.save.assert_not_awaited()
        self.assertEqual(ctx.invokeAPI.await_count, 3)

    async def test_pagination_per_scope(self):
        self.patch_now()
        ctx = make_context(invoke=_seq(
            {"value": [1], "continuationToken": "t"}, {"value": [2]},
            {"value": []}, {"value": []}))
        self.assertTrue(await self.mod.main(ctx))
        self.assertEqual(ctx.fm.save.await_args_list[0].args[2], [1, 2])


class WidelySharedLinksTests(_ModuleBase, unittest.IsolatedAsyncioTestCase):
    mod = widelysharedlinks
    base = "https://api.powerbi.com/v1.0/myorg/admin/widelySharedArtifacts"

    async def test_both_saved(self):
        self.patch_now()
        ctx = make_context(invoke=_seq(
            {"artifactAccessEntities": [{"a": 1}], "continuationToken": "x y"},
            {"artifactAccessEntities": [{"a": 2}]},
            {"artifactAccessEntities": [{"b": 1}]}))
        self.assertTrue(await self.mod.main(ctx))
        urls = [c.args[0] for c in ctx.invokeAPI.await_args_list]
        self.assertEqual(urls, [
            f"{self.base}/linksSharedToWholeOrganization",
            f"{self.base}/linksSharedToWholeOrganization?continuationToken=x%20y",
            f"{self.base}/publishedToWeb"])
        saved = [c.args for c in ctx.fm.save.await_args_list]
        self.assertEqual(saved, [
            (f"widelysharedlinks/{DATE_PATH}", "widelysharedlinks_organization.json",
             [{"a": 1}, {"a": 2}]),
            (f"widelysharedlinks/{DATE_PATH}", "widelysharedlinks_publishedtoweb.json", [{"b": 1}]),
        ])

    async def test_empty_results_saved(self):
        self.patch_now()
        ctx = make_context(invoke=_seq({}, {}))  # {} is a failure
        self.assertIs(await self.mod.main(ctx), False)
        ctx.fm.save.assert_not_awaited()
        ctx = make_context(invoke=_seq({"artifactAccessEntities": []}, {"artifactAccessEntities": None}))
        self.assertTrue(await self.mod.main(ctx))
        self.assertEqual([c.args[2] for c in ctx.fm.save.await_args_list], [[], []])

    async def test_first_fails_second_still_saved(self):
        self.patch_now()
        ctx = make_context(invoke=_seq({"ERROR": "x", "status": 404},
                                       {"artifactAccessEntities": [1]}))
        self.assertIs(await self.mod.main(ctx), False)
        ctx.fm.save.assert_awaited_once_with(
            f"widelysharedlinks/{DATE_PATH}", "widelysharedlinks_publishedtoweb.json", [1])

    async def test_second_fails_first_still_saved(self):
        self.patch_now()
        ctx = make_context(invoke=_seq({"artifactAccessEntities": [1]},
                                       {"ERROR": "x", "status": 500}))
        self.assertIs(await self.mod.main(ctx), False)
        ctx.fm.save.assert_awaited_once_with(
            f"widelysharedlinks/{DATE_PATH}", "widelysharedlinks_organization.json", [1])


NEW = ("GitConnections", "Tags", "DelegatedSettings", "WidelySharedLinks")


class ContextCronTests(unittest.TestCase):
    def test_defaults_none_and_get_cron(self):
        ctx = Context()
        for name in NEW:
            with self.subTest(name=name):
                self.assertIsNone(getattr(ctx, f"{name}_cron"))
                self.assertIsNone(ctx.get_cron(name))

    def test_setters_roundtrip_independently(self):
        ctx = Context()
        for i, name in enumerate(NEW):
            getattr(ctx, f"set_{name}_cron")(f"{i} * * * *")
        for i, name in enumerate(NEW):
            with self.subTest(name=name):
                self.assertEqual(ctx.get_cron(name), f"{i} * * * *")
                self.assertEqual(getattr(ctx, f"{name}_cron"), f"{i} * * * *")

    def test_unknown_cron_name_none(self):
        self.assertIsNone(Context().get_cron("Nope"))


class AuditWiringTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_state_has_new_entries(self):
        a = Audits()
        a.fm = MagicMock()
        a.fm.save = AsyncMock()
        with patch.object(Audits, "_default_last_run", return_value="STAMP"):
            state = await a.create_state()
        for key in ("gitconnections", "tags", "delegatedsettings", "widelysharedlinks"):
            with self.subTest(key=key):
                self.assertEqual(state[key], {"lastRun": "STAMP"})
        a.fm.save.assert_awaited_once_with("", "state.yaml", state)

    def test_audit_setters_forward_to_context(self):
        a = Audits()
        a.context = MagicMock()
        for name in NEW:
            getattr(a, f"set_{name}_cron")("c-" + name)
            getattr(a.context, f"set_{name}_cron").assert_called_once_with("c-" + name)


class MonitorCronMapTests(unittest.IsolatedAsyncioTestCase):
    async def test_env_vars_call_setters(self):
        env = {"APPLICATION_MODULES": "Activity", "LAKEHOUSE_NAME": "lh", "WORKSPACE_NAME": "ws",
               "TENANT_ID": "T", "CLIENT_ID": "C", "CLIENT_SECRET": "S",
               "GITCONNECTIONS_CRON": "1 * * * *", "TAGS_CRON": "2 * * * *",
               "DELEGATEDSETTINGS_CRON": "3 * * * *", "WIDELYSHAREDLINKS_CRON": "4 * * * *"}
        audit = MagicMock()

        async def noop():
            return None
        audit.run = MagicMock(side_effect=noop)
        with patch.dict(os.environ, env, clear=True), \
                patch.object(monitor, "Audits", return_value=audit):
            await monitor.main()
        audit.set_GitConnections_cron.assert_called_once_with("1 * * * *")
        audit.set_Tags_cron.assert_called_once_with("2 * * * *")
        audit.set_DelegatedSettings_cron.assert_called_once_with("3 * * * *")
        audit.set_WidelySharedLinks_cron.assert_called_once_with("4 * * * *")
        audit.set_Roles_cron.assert_not_called()


class ExportTests(unittest.TestCase):
    def test_exports(self):
        self.assertIs(modules_pkg.GitConnections, gitconnections.main)
        self.assertIs(modules_pkg.Tags, tags.main)
        self.assertIs(modules_pkg.DelegatedSettings, delegatedsettings.main)
        self.assertIs(modules_pkg.WidelySharedLinks, widelysharedlinks.main)


if __name__ == "__main__":
    unittest.main()
