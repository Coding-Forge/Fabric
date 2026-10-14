"""All-UTC change: module save dates, no import-time ``today``, convert_dt_str,
is_function_due base time, and a source sweep for naive/local clock calls."""
import ast
import asyncio
import importlib
import io
import os
import re
import time
import tokenize
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import env.context as context_module
from env.audit import is_function_due
from tests.helpers import make_context

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULES = [
    "apps", "capacity", "capacity_metrics", "workspaces", "roles",
    "fabricitems", "tenant", "graph", "refreshables", "refreshhistory",
]
# Local zones whose calendar date differs from UTC at the chosen instant.
# 2024-03-31 20:30 UTC -> Tokyo 04-01 05:30, Kiritimati 04-01 10:30, Los Angeles 03-31 13:30
# 2024-04-01 03:30 UTC -> Los Angeles 03-31 20:30 (date behind UTC)
CASES = [
    ("Asia/Tokyo", datetime(2024, 3, 31, 20, 30, 15)),
    ("Pacific/Kiritimati", datetime(2024, 3, 31, 20, 30, 15)),
    ("America/Los_Angeles", datetime(2024, 4, 1, 3, 30, 15)),
    ("UTC", datetime(2024, 12, 31, 23, 59, 59)),
]


def _mod(name):
    return importlib.import_module(f"env.modules.{name}")


class TzMixin:
    def _set_tz(self, tz):
        old = os.environ.get("TZ")

        def restore():
            if old is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old
            time.tzset()

        self.addCleanup(restore)
        os.environ["TZ"] = tz
        time.tzset()


def build_context():
    """Context whose every API call returns a superset payload usable by all modules."""
    payload = {
        "value": [],
        "workspaces": [{"id": "w1"}],
        "itemEntities": [],
        "settings": [],
        "results": [],
    }
    ctx = make_context(
        state={"catalog": {"lastRun": "2024-01-01T00:00:00.000000Z",
                           "lastFullScan": "2024-01-01T00:00:00.000000Z"}},
        invoke=AsyncMock(side_effect=lambda *a, **k: dict(payload)),
    )
    for name in ("tenant", "graph"):
        ctx.clients[name] = MagicMock()
        ctx.clients[name].get_headers.return_value = {}
        ctx.clients[name].get_api_root.return_value = "https://graph.test/v1.0"
    ctx.impersonatedUserName = "user@example.com"
    ctx.capacity_metrics_dataset_id = "ds"
    ctx.GraphExtractGroups = False
    return ctx


def saved(ctx):
    """Return [(path, file_name)] for every fm.save call."""
    return [(c.kwargs.get("path"), c.kwargs.get("file_name")) for c in ctx.fm.save.await_args_list]


def date_dirs(path):
    m = re.search(r"(\d{4})/(\d{2})/(\d{2})/?$", path)
    return m.groups() if m else None


class ModuleSaveDateTests(TzMixin, unittest.TestCase):
    def _run(self, name, moment):
        ctx = build_context()
        with patch(f"env.modules.{name}.utc_now", return_value=moment):
            asyncio.run(_mod(name).main(ctx))
        return saved(ctx)

    def test_each_module_saves_under_utc_date_in_any_local_zone(self):
        for tz, moment in CASES:
            self._set_tz(tz)
            for name in MODULES:
                with self.subTest(tz=tz, module=name):
                    calls = self._run(name, moment)
                    self.assertTrue(calls, "module did not save anything")
                    for path, file_name in calls:
                        self.assertEqual(
                            date_dirs(path),
                            (f"{moment:%Y}", f"{moment:%m}", f"{moment:%d}"),
                            path,
                        )
                        if file_name.startswith(moment.strftime("%Y")) or name in (
                            "capacity", "capacity_metrics", "workspaces", "roles"
                        ):
                            self.assertTrue(file_name.startswith(moment.strftime("%Y%m%d")), file_name)

    def test_local_date_really_differs_from_utc_in_cases(self):
        """Guard: the chosen instants differ in local vs UTC date."""
        for tz in ("Asia/Tokyo", "Pacific/Kiritimati"):
            self._set_tz(tz)
            moment = datetime(2024, 3, 31, 20, 30, 15)
            local = moment.replace(tzinfo=timezone.utc).astimezone()
            self.assertNotEqual(local.date(), moment.date())
        self._set_tz("America/Los_Angeles")
        moment = datetime(2024, 4, 1, 3, 30, 15)
        self.assertNotEqual(moment.replace(tzinfo=timezone.utc).astimezone().date(), moment.date())

    def test_real_utc_now_drives_modules_when_local_date_differs(self):
        """Without patching module utc_now: fake the clock under env.context, local TZ differs."""
        for tz, moment in CASES[:3]:
            self._set_tz(tz)
            aware = moment.replace(tzinfo=timezone.utc)

            class FakeDT(datetime):
                @classmethod
                def now(cls, tzinfo=None):
                    # honour tz; naive request returns *local* wall time (the old bug)
                    return aware.astimezone(tzinfo) if tzinfo else aware.astimezone().replace(tzinfo=None)

            for name in MODULES:
                with self.subTest(tz=tz, module=name):
                    ctx = build_context()
                    with patch.object(context_module, "datetime", FakeDT):
                        asyncio.run(_mod(name).main(ctx))
                    for path, _ in saved(ctx):
                        self.assertEqual(date_dirs(path), (f"{moment:%Y}", f"{moment:%m}", f"{moment:%d}"))

    def test_apps_path_uses_utc_date(self):
        calls = self._run("apps", datetime(2024, 3, 31, 20, 30))
        self.assertEqual(calls, [("catalog/snapshots/2024/03/31/", "apps.json")])


class NoImportTimeTodayTests(unittest.TestCase):
    def test_no_module_level_today(self):
        for name in MODULES:
            with self.subTest(module=name):
                mod = _mod(name)
                self.assertFalse(hasattr(mod, "today"))
                tree = ast.parse(Path(mod.__file__).read_text())
                for node in tree.body:
                    targets = []
                    if isinstance(node, ast.Assign):
                        targets = [t for t in node.targets]
                    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                        targets = [node.target]
                    for t in targets:
                        for n in ast.walk(t):
                            if isinstance(n, ast.Name):
                                self.assertNotIn(n.id, ("today", "pivotDate"))

    def test_two_runs_on_different_dates_produce_two_dates(self):
        d1, d2 = datetime(2024, 3, 31, 23, 59), datetime(2024, 4, 1, 0, 1)
        for name in MODULES:
            with self.subTest(module=name):
                mod = _mod(name)
                results = []
                for moment in (d1, d2):
                    ctx = build_context()
                    with patch(f"env.modules.{name}.utc_now", return_value=moment):
                        asyncio.run(mod.main(ctx))
                    results.append({date_dirs(p) for p, _ in saved(ctx)})
                self.assertEqual(results[0], {("2024", "03", "31")})
                self.assertEqual(results[1], {("2024", "04", "01")})


class ConvertDtStrTests(unittest.TestCase):
    def setUp(self):
        self.ctx = make_context()

    def test_z_string(self):
        self.assertEqual(self.ctx.convert_dt_str("2024-05-06T07:08:09.123456Z"),
                         datetime(2024, 5, 6, 7, 8, 9, 123456))

    def test_offset_aware_positive_converted_to_naive_utc(self):
        tz = timezone(timedelta(hours=5, minutes=30))
        r = self.ctx.convert_dt_str(datetime(2024, 5, 6, 3, 0, 0, tzinfo=tz))
        self.assertEqual(r, datetime(2024, 5, 5, 21, 30))
        self.assertIsNone(r.tzinfo)

    def test_offset_aware_negative_converted_to_naive_utc(self):
        tz = timezone(timedelta(hours=-8))
        r = self.ctx.convert_dt_str(datetime(2024, 12, 31, 20, 0, 0, tzinfo=tz))
        self.assertEqual(r, datetime(2025, 1, 1, 4, 0))
        self.assertIsNone(r.tzinfo)

    def test_aware_utc_unchanged(self):
        self.assertEqual(self.ctx.convert_dt_str(datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)),
                         datetime(2024, 1, 2, 3, 4, 5))

    def test_naive_datetime_unchanged(self):
        self.assertEqual(self.ctx.convert_dt_str(datetime(2024, 1, 2, 3, 4, 5, 6)),
                         datetime(2024, 1, 2, 3, 4, 5, 6))

    def test_naive_datetime_not_shifted_by_local_tz(self):
        old = os.environ.get("TZ")
        self.addCleanup(lambda: (os.environ.pop("TZ", None) if old is None else os.environ.__setitem__("TZ", old), time.tzset()))
        os.environ["TZ"] = "Asia/Tokyo"
        time.tzset()
        self.assertEqual(self.ctx.convert_dt_str(datetime(2024, 1, 2, 3, 4, 5)), datetime(2024, 1, 2, 3, 4, 5))

    def test_invalid_raises_value_error(self):
        for bad in ("not a date", "2024-01-01", "2024-01-01T00:00:00Z", "", None, 12345):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.ctx.convert_dt_str(bad)


def _real_croniter_available():
    try:
        context_module  # noqa: B018
        import env.audit as audit
        audit.croniter("* * * * *", datetime(2024, 1, 1))
        return True
    except RuntimeError:
        return False


class IsFunctionDueUtcTests(TzMixin, unittest.TestCase):
    LAST = datetime(2024, 3, 31, 12, 0)  # naive UTC; "0 0 * * *" -> next 2024-04-01 00:00 UTC

    def test_no_cron_always_due(self):
        self.assertTrue(is_function_due(None, self.LAST))
        self.assertTrue(is_function_due("", self.LAST))

    def test_croniter_receives_naive_utc_base_time(self):
        """Stub-independent: croniter is seeded with last_run unchanged (UTC), no local conversion."""
        seen = {}

        class Fake:
            def __init__(self, expr, base):
                seen["args"] = (expr, base)

            def get_next(self, typ):
                return datetime(2024, 4, 1, 0, 0)

        for tz in ("Asia/Tokyo", "America/Los_Angeles"):
            self._set_tz(tz)
            with patch("env.audit.croniter", Fake):
                with patch("env.audit.utc_now", return_value=datetime(2024, 3, 31, 23, 59)):
                    self.assertFalse(is_function_due("0 0 * * *", self.LAST))
                with patch("env.audit.utc_now", return_value=datetime(2024, 4, 1, 0, 0)):
                    self.assertTrue(is_function_due("0 0 * * *", self.LAST))
            self.assertEqual(seen["args"], ("0 0 * * *", self.LAST))
            self.assertIsNone(seen["args"][1].tzinfo)

    @unittest.skipUnless(_real_croniter_available(), "real croniter not installed")
    def test_uses_utc_now_regardless_of_tz(self):
        for tz in ("UTC", "Asia/Tokyo", "Pacific/Kiritimati", "America/Los_Angeles"):
            self._set_tz(tz)
            with self.subTest(tz=tz, case="before"):
                with patch("env.audit.utc_now", return_value=datetime(2024, 3, 31, 23, 59)):
                    self.assertFalse(is_function_due("0 0 * * *", self.LAST))
            with self.subTest(tz=tz, case="at"):
                with patch("env.audit.utc_now", return_value=datetime(2024, 4, 1, 0, 0)):
                    self.assertTrue(is_function_due("0 0 * * *", self.LAST))

    @unittest.skipUnless(_real_croniter_available(), "real croniter not installed")
    def test_real_clock_utc_under_tz(self):
        """Unpatched utc_now: due-ness relies on UTC clock, not local wall time."""
        for tz in ("Asia/Tokyo", "America/Los_Angeles"):
            self._set_tz(tz)
            now = context_module.utc_now()
            with self.subTest(tz=tz):
                self.assertTrue(is_function_due("* * * * *", now - timedelta(minutes=5)))
                self.assertFalse(is_function_due("0 0 1 1 *", now))


class NoLocalClockSweepTests(unittest.TestCase):
    # ``datetime.now(timezone.utc)`` is an explicit aware-UTC call and is allowed anywhere
    # (e.g. env/utility/http_retry.py); every other form is local/naive and is flagged.
    PATTERN = re.compile(r"(datetime\.now\((?!timezone\.utc\))|datetime\.today\(|date\.today\(|utcnow\()")

    def _code_lines(self, path):
        """Yield (lineno, code-without-comments-and-strings)."""
        src = path.read_text(encoding="utf-8")
        per_line = {}
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.NAME, tokenize.OP):
                per_line.setdefault(tok.start[0], []).append(tok.string)
        for no, toks in per_line.items():
            yield no, "".join(toks)

    def test_no_naive_or_local_clock_calls(self):
        files = []
        for d in ("app", "env"):
            files += [p for p in (REPO_ROOT / d).rglob("*.py")
                      if p.name != "catalog_bkbk.py" and "__pycache__" not in p.parts]
        self.assertTrue(files)
        context_py = REPO_ROOT / "env" / "context.py"
        tree = ast.parse(context_py.read_text())
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "utc_now")
        allowed = set(range(fn.lineno, fn.end_lineno + 1))

        offenders = []
        for p in files:
            for no, code in self._code_lines(p):
                if self.PATTERN.search(code):
                    if p == context_py and no in allowed:
                        continue
                    offenders.append(f"{p.relative_to(REPO_ROOT)}:{no}: {code}")
        self.assertEqual(offenders, [])

    def test_utc_now_itself_uses_aware_utc(self):
        src = (REPO_ROOT / "env" / "context.py").read_text()
        self.assertIn("datetime.now(timezone.utc)", src)


if __name__ == "__main__":
    unittest.main()
