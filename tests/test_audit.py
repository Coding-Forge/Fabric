"""B7-B9, B12, B13: audit outcome and state-advance logic."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from env import audit as audit_mod
from env.audit import Audits
from env.context import utc_now

FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _ts(days_ago):
    return (utc_now() - timedelta(days=days_ago)).strftime(FMT)


def _module(name, result=True, exc=None):
    async def fn(context):
        """Fake module"""
        fn.calls += 1
        if exc:
            raise exc
        return result

    fn.calls = 0
    fn.__name__ = name
    return fn


class AuditRunTests(unittest.IsolatedAsyncioTestCase):
    def _audit(self, modules, state, read_exc=None):
        a = Audits()
        a.context.ApplicationModules = ",".join(modules)
        a.fm = MagicMock()
        if read_exc:
            a.fm.read = AsyncMock(side_effect=read_exc)
        else:
            a.fm.read = AsyncMock(return_value=state)
        a.fm.save = AsyncMock()
        a.context.logger = MagicMock()
        return a

    def _patches(self, **mods):
        ps = [patch.object(audit_mod, n, f) for n, f in mods.items()]
        ps += [patch.object(audit_mod, c, MagicMock()) for c in ("PbiClient", "GraphClient", "TenantClient")]
        return ps

    async def _run(self, a, **mods):
        ps = self._patches(**mods)
        for p in ps:
            p.start()
        try:
            await a.run()
        finally:
            for p in ps:
                p.stop()

    def _saved(self, a):
        a.fm.save.assert_awaited()
        return a.fm.save.await_args.args[2]

    async def test_last_run_advances_only_for_successful_modules(self):
        old = _ts(3)
        state = {"activity": {"lastRun": old}, "apps": {"lastRun": old},
                 "gateway": {"lastRun": old}, "tenant": {"lastRun": old}}
        ok = _module("Activity", True)
        returns_none = _module("Apps", None)       # None is not a failure signal
        returns_false = _module("Gateway", False)  # explicit failure
        raises = _module("Tenant", exc=RuntimeError("boom"))
        a = self._audit(["Activity", "Apps", "Gateway", "Tenant"], state)
        await self._run(a, Activity=ok, Apps=returns_none, Gateway=returns_false, Tenant=raises)

        saved = self._saved(a)
        self.assertNotEqual(saved["activity"]["lastRun"], old)
        self.assertNotEqual(saved["apps"]["lastRun"], old)
        self.assertEqual(saved["gateway"]["lastRun"], old)
        self.assertEqual(saved["tenant"]["lastRun"], old)

    async def test_exception_in_one_module_does_not_stop_others(self):
        old = _ts(2)
        state = {"activity": {"lastRun": old}, "roles": {"lastRun": old}}
        bad = _module("Activity", exc=ValueError("x"))
        good = _module("Roles", True)
        a = self._audit(["Activity", "Roles"], state)
        await self._run(a, Activity=bad, Roles=good)
        self.assertEqual(good.calls, 1)
        saved = self._saved(a)
        self.assertNotEqual(saved["roles"]["lastRun"], old)
        self.assertEqual(saved["activity"]["lastRun"], old)
        a.context.logger.error.assert_called()

    async def test_empty_state_is_created_with_seven_day_default(self):
        """B13: no checkpoint -> bounded look-back, not 2024-05-31."""
        mod = _module("Activity", False)
        a = self._audit(["Activity"], {})
        await self._run(a, Activity=mod)
        first_save = a.fm.save.await_args_list[0].args[2]
        seeded = datetime.strptime(first_save["activity"]["lastRun"], FMT)
        self.assertLess(abs(utc_now() - seeded - timedelta(days=7)), timedelta(minutes=1))

    async def test_module_without_checkpoint_gets_default_seed(self):
        state = {"apps": {"lastRun": _ts(1)}}
        mod = _module("Activity", False)
        a = self._audit(["Activity"], state)
        await self._run(a, Activity=mod)
        saved = self._saved(a)
        seeded = datetime.strptime(saved["activity"]["lastRun"], FMT)
        self.assertLess(abs(utc_now() - seeded - timedelta(days=7)), timedelta(minutes=1))
        self.assertEqual(mod.calls, 1)

    async def test_unparseable_checkpoint_is_rerun_with_default(self):
        mod = _module("Activity", False)
        a = self._audit(["Activity"], {"activity": {"lastRun": "garbage"}})
        await self._run(a, Activity=mod)
        self.assertEqual(mod.calls, 1)
        self.assertNotEqual(self._saved(a)["activity"]["lastRun"], "garbage")

    async def test_state_read_failure_aborts_run_without_saving(self):
        """A failed read must not be treated as empty state (would overwrite real checkpoints)."""
        mod = _module("Activity", True)
        a = self._audit(["Activity"], None, read_exc=OSError("blob down"))
        await self._run(a, Activity=mod)
        self.assertEqual(mod.calls, 0)
        a.fm.save.assert_not_awaited()
        a.context.logger.error.assert_called()

    async def test_missing_state_none_creates_fresh_state(self):
        mod = _module("Activity", True)
        a = self._audit(["Activity"], None)
        await self._run(a, Activity=mod)
        self.assertEqual(mod.calls, 1)
        self.assertIn("activity", self._saved(a))

    async def test_empty_string_state_creates_fresh_state(self):
        mod = _module("Activity", True)
        a = self._audit(["Activity"], "")
        await self._run(a, Activity=mod)
        self.assertEqual(mod.calls, 1)
        self.assertIn("activity", self._saved(a))

    async def test_invalid_json_string_state_aborts_without_saving(self):
        mod = _module("Activity", True)
        a = self._audit(["Activity"], "{not json")
        await self._run(a, Activity=mod)
        self.assertEqual(mod.calls, 0)
        a.fm.save.assert_not_awaited()

    async def test_null_module_state_entry_is_tolerated(self):
        """YAML `activity:` with no value loads as None."""
        mod = _module("Activity", True)
        a = self._audit(["Activity"], {"activity": None, "apps": {"lastRun": _ts(1)}})
        await self._run(a, Activity=mod)
        self.assertEqual(mod.calls, 1)
        saved = self._saved(a)
        self.assertIsInstance(saved["activity"], dict)
        self.assertIn("lastRun", saved["activity"])
        self.assertIn("apps", saved)

    async def test_null_module_entry_failed_module_still_seeded(self):
        mod = _module("Catalog", False)
        a = self._audit(["Catalog"], {"catalog": None})
        await self._run(a, Catalog=mod)
        seeded = datetime.strptime(self._saved(a)["catalog"]["lastRun"], FMT)
        self.assertLess(abs(utc_now() - seeded - timedelta(days=7)), timedelta(minutes=1))

    async def test_state_saved_even_when_all_modules_fail(self):
        old = _ts(1)
        mod = _module("Activity", exc=RuntimeError("x"))
        a = self._audit(["Activity"], {"activity": {"lastRun": old}})
        await self._run(a, Activity=mod)
        self.assertEqual(self._saved(a)["activity"]["lastRun"], old)

    async def test_nothing_due_runs_nothing_and_saves_nothing(self):
        mod = _module("Activity", True)
        a = self._audit(["Activity"], {"activity": {"lastRun": _ts(0)}})
        a.context.Activity_cron = "0 0 1 1 *"
        fake_cron = MagicMock()
        fake_cron.return_value.get_next.return_value = utc_now() + timedelta(days=30)
        with patch.object(audit_mod, "croniter", fake_cron):
            await self._run(a, Activity=mod)
        self.assertEqual(mod.calls, 0)
        a.fm.save.assert_not_awaited()

    async def test_json_string_state_is_parsed(self):
        old = _ts(2)
        mod = _module("Activity", True)
        a = self._audit(["Activity"], '{"activity": {"lastRun": "%s"}}' % old)
        await self._run(a, Activity=mod)
        self.assertNotEqual(self._saved(a)["activity"]["lastRun"], old)

    async def test_extra_state_keys_set_by_modules_are_persisted(self):
        """B1: modules mutate the shared state dict (catalog.lastFullScan)."""
        old = _ts(2)

        async def fn(context):
            """Fake catalog"""
            context.current_state["catalog"]["lastFullScan"] = "X"
            return True

        a = self._audit(["Catalog"], {"catalog": {"lastRun": old}})
        await self._run(a, Catalog=fn)
        saved = self._saved(a)
        self.assertEqual(saved["catalog"]["lastFullScan"], "X")
        self.assertNotEqual(saved["catalog"]["lastRun"], old)


class AuditMissingLastRunTests(unittest.IsolatedAsyncioTestCase):
    """A module with a state entry but no lastRun keeps its other keys (setdefault fix)."""

    _audit = AuditRunTests._audit
    _patches = AuditRunTests._patches
    _run = AuditRunTests._run
    _saved = AuditRunTests._saved

    async def test_missing_last_run_preserves_last_full_scan(self):
        full_scan = _ts(5)
        mod = _module("Catalog", False)
        a = self._audit(["Catalog"], {"catalog": {"lastFullScan": full_scan}})
        await self._run(a, Catalog=mod)
        saved = self._saved(a)
        self.assertEqual(mod.calls, 1)
        self.assertEqual(saved["catalog"]["lastFullScan"], full_scan)
        seeded = datetime.strptime(saved["catalog"]["lastRun"], FMT)
        self.assertLess(abs(utc_now() - seeded - timedelta(days=7)), timedelta(minutes=1))

    async def test_unparseable_last_run_preserves_other_keys(self):
        full_scan = _ts(5)
        mod = _module("Catalog", False)
        a = self._audit(["Catalog"], {"catalog": {"lastRun": "garbage", "lastFullScan": full_scan}})
        await self._run(a, Catalog=mod)
        saved = self._saved(a)
        self.assertEqual(saved["catalog"]["lastFullScan"], full_scan)
        self.assertNotEqual(saved["catalog"]["lastRun"], "garbage")



class ExcludeSettersTests(unittest.TestCase):
    def test_exclude_setters_set_attributes_without_type_error(self):
        """B7: the methods set the flags rather than calling a bool."""
        a = Audits()
        a.exclude_personal_workspaces(False)
        a.exclude_inactivate_workspaces(False)
        self.assertIs(a.context.exclude_personal_workspaces, False)
        self.assertIs(a.context.exclude_inactive_workspaces, False)
        a.exclude_personal_workspaces(True)
        a.exclude_inactivate_workspaces(True)
        self.assertIs(a.context.exclude_personal_workspaces, True)
        self.assertIs(a.context.exclude_inactive_workspaces, True)


if __name__ == "__main__":
    unittest.main()
