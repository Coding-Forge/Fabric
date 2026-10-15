"""Unit tests for env.modules.capacity_metrics (executeQueries against the app model)."""

import asyncio
import os
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from env.modules import capacity_metrics as cm
from tests.helpers import make_context

CAP_A = "11111111-2222-3333-4444-555555555555"
CAP_B = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
NOW = datetime(2024, 5, 10, 13, 45, 12)
ENV_KEYS = (cm.DAYS_BACK_ENV, cm.INCLUDE_SUSPENDED_ENV)


def ok(rows):
    return {"results": [{"tables": [{"rows": rows}]}]}


def cap_row(cid, state="Active", name="n", sku="F2"):
    return {"[id]": cid, "[state]": state, "[name]": name, "[sku]": sku}


class FakeApi:
    """Routes executeQueries calls by query text; records every call."""

    def __init__(self, capacities, probe=None, group=None):
        self.capacities = capacities
        self.probe = probe if probe is not None else (lambda q: ok([{"[probe]": 1}]))
        self.group = group if group is not None else (lambda q: ok([{"x": 1}]))
        self.queries = []
        self.calls = []

    async def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        query = kwargs["json"]["queries"][0]["query"]
        self.queries.append(query)
        if query == cm.CAPACITIES_QUERY:
            return ok(self.capacities)
        if query.startswith("EVALUATE ROW("):
            return self.probe(query)
        return self.group(query)

    def group_queries(self):
        return [q for q in self.queries if q.startswith("DEFINE")]


def run(coro):
    return asyncio.run(coro)


def make(api, state=None, dataset="ds1"):
    ctx = make_context(state=state, invoke=api)
    ctx.capacity_metrics_dataset_id = dataset
    return ctx


def run_main(ctx, now=NOW, env=None):
    base = {k: "" for k in ENV_KEYS}
    base.update(env or {})
    with patch.dict(os.environ, base), patch.object(cm, "utc_now", return_value=now):
        return run(cm.main(ctx))


class ValidateCapacityIdTests(unittest.TestCase):
    def test_accepts_guid_any_case(self):
        self.assertEqual(cm.validate_capacity_id(CAP_A), CAP_A)
        self.assertEqual(cm.validate_capacity_id(CAP_A.upper()), CAP_A.upper())

    def test_rejects_bad_values(self):
        bad = [
            None,
            5,
            "",
            "not-a-guid",
            " " + CAP_A,
            CAP_A + "x",
            CAP_A[:-1],
            CAP_A.replace("-", ""),
            'x"} ; EVALUATE Foo //',
            CAP_A[:-1] + '"',
            "gggggggg-2222-3333-4444-555555555555",
        ]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                cm.validate_capacity_id(value)

    # KNOWN PRODUCTION BUG: _GUID_RE ends with ``$``, which also matches before a
    # trailing newline, so "<guid>\n" is accepted and embedded in the DAX text.
    def test_rejects_trailing_newline(self):
        with self.assertRaises(ValueError):
            cm.validate_capacity_id(CAP_A + "\n")

    def test_build_group_query_rejects_injection(self):
        evil = CAP_A[:-1] + '"} EVALUATE Secrets --'
        with self.assertRaises(ValueError):
            cm.build_group_query(evil, NOW, cm.UTILIZATION)


class BuildGroupQueryTests(unittest.TestCase):
    def test_contains_mparameter_treatas_and_values(self):
        q = cm.build_group_query(CAP_A, datetime(2024, 5, 7), cm.CARRY_OVER)
        self.assertIn("MPARAMETER", q)
        self.assertIn("TREATAS", q)
        self.assertEqual(q.count(CAP_A), 2)
        self.assertIn("DATE(2024,5,7)", q)
        for m in cm.CARRY_OVER.measures:
            self.assertIn(f"\"{m}\", 'All Measures'[{m}]", q)

    def test_each_version_group_builds(self):
        for version in cm.VERSIONS:
            for group in version.groups:
                q = cm.build_group_query(CAP_A, NOW, group)
                self.assertIn("SUMMARIZECOLUMNS", q)


class ConfigTests(unittest.TestCase):
    def _days(self, value):
        env = {} if value is None else {cm.DAYS_BACK_ENV: value}
        with patch.dict(os.environ, env):
            if value is None:
                os.environ.pop(cm.DAYS_BACK_ENV, None)
            return cm.get_days_back()

    def test_days_back(self):
        cases = {
            None: 3,
            "": 3,
            "  ": 3,
            "7": 7,
            " 5 ": 5,
            "1": 1,
            "0": 3,
            "-2": 3,
            "abc": 3,
            "2.5": 3,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(self._days(raw), expected)

    def test_days_back_clamped_to_max(self):
        self.assertEqual(cm.MAX_DAYS_BACK, 30)
        cases = {"30": 30, "31": 30, "365": 30, "999999": 30, "29": 29}
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(self._days(raw), expected)

    def test_include_suspended(self):
        for raw in ("1", "true", "TRUE", "Yes", " on "):
            with (
                self.subTest(raw=raw),
                patch.dict(os.environ, {cm.INCLUDE_SUSPENDED_ENV: raw}),
            ):
                self.assertTrue(cm.include_suspended())
        for raw in ("", "0", "false", "no", "off", "2", "y"):
            with (
                self.subTest(raw=raw),
                patch.dict(os.environ, {cm.INCLUDE_SUSPENDED_ENV: raw}),
            ):
                self.assertFalse(cm.include_suspended())
        with patch.dict(os.environ):
            os.environ.pop(cm.INCLUDE_SUSPENDED_ENV, None)
            self.assertFalse(cm.include_suspended())


class ComputeDaysTests(unittest.TestCase):
    def test_no_last_run_gives_days_back_plus_today(self):
        days = cm.compute_days(None, NOW, 3)
        self.assertEqual(days, [datetime(2024, 5, d) for d in (7, 8, 9, 10)])

    def test_days_are_midnight_and_ascending(self):
        days = cm.compute_days(None, NOW, 2)
        self.assertTrue(all(d.hour == d.minute == d.second == 0 for d in days))
        self.assertEqual(days, sorted(days))

    def test_recent_last_run_requeries_previous_day(self):
        days = cm.compute_days(datetime(2024, 5, 9, 22, 0), NOW, 7)
        self.assertEqual(days, [datetime(2024, 5, d) for d in (8, 9, 10)])

    def test_last_run_today_requeries_yesterday_and_today(self):
        days = cm.compute_days(datetime(2024, 5, 10, 1, 0), NOW, 7)
        self.assertEqual(days, [datetime(2024, 5, 9), datetime(2024, 5, 10)])

    def test_old_last_run_clamped_to_days_back(self):
        days = cm.compute_days(datetime(2024, 1, 1), NOW, 2)
        self.assertEqual(days[0], datetime(2024, 5, 8))
        self.assertEqual(days[-1], datetime(2024, 5, 10))

    def test_last_run_exactly_at_boundary(self):
        # previous_day == window start -> same either way
        days = cm.compute_days(datetime(2024, 5, 8, 6), NOW, 3)
        self.assertEqual(days[0], datetime(2024, 5, 7))

    def test_days_back_one(self):
        self.assertEqual(
            cm.compute_days(None, NOW, 1), [datetime(2024, 5, 9), datetime(2024, 5, 10)]
        )

    def test_future_last_run_does_not_produce_inverted_window(self):
        """lastRun in the future (clock skew): result must be a sane list, not negative-range junk."""
        days = cm.compute_days(datetime(2024, 5, 20), NOW, 3)
        self.assertTrue(all(d <= datetime(2024, 5, 10) for d in days))

    def test_far_future_last_run_returns_today(self):
        self.assertEqual(
            cm.compute_days(datetime(2030, 1, 1), NOW, 3), [datetime(2024, 5, 10)]
        )


class LastRunTests(unittest.TestCase):
    def test_valid_state_dict(self):
        ctx = make_context(
            state={cm.STATE_KEY: {"lastRun": "2024-05-09T10:00:00.000000Z"}}
        )
        self.assertEqual(cm._last_run(ctx), datetime(2024, 5, 9, 10))

    def test_valid_state_json_string(self):
        ctx = make_context(
            state='{"capacitymetrics": {"lastRun": "2024-05-09T10:00:00.000000Z"}}'
        )
        self.assertEqual(cm._last_run(ctx), datetime(2024, 5, 9, 10))

    def test_missing_variants(self):
        for state in (
            None,
            {},
            {cm.STATE_KEY: None},
            {cm.STATE_KEY: {}},
            {cm.STATE_KEY: {"lastRun": ""}},
            {cm.STATE_KEY: "oops"},
            {"other": {"lastRun": "2024-05-09T10:00:00.000000Z"}},
        ):
            with self.subTest(state=state):
                self.assertIsNone(cm._last_run(make_context(state=state)))

    def test_malformed_json_string_returns_none(self):
        for state in ("{not json", "", "   ", '{"capacitymetrics": '):
            with self.subTest(state=state):
                self.assertIsNone(cm._last_run(make_context(state=state)))

    def test_non_dict_state_returns_none(self):
        for state in ("[1, 2]", '"text"', "42", "null", [1, 2], 42):
            with self.subTest(state=state):
                self.assertIsNone(cm._last_run(make_context(state=state)))

    def test_unparseable_returns_none(self):
        ctx = make_context(state={cm.STATE_KEY: {"lastRun": "yesterday"}})
        self.assertIsNone(cm._last_run(ctx))


class ExecuteQueryTests(unittest.TestCase):
    def _q(self, response, **ctx_attrs):
        ctx = make_context(invoke=AsyncMock(return_value=response))
        for k, v in ctx_attrs.items():
            setattr(ctx, k, v)
        rows = run(cm._execute_query(ctx, "ds", {"h": "1"}, "Q"))
        return ctx, rows

    def test_returns_rows_and_builds_request(self):
        ctx, rows = self._q(ok([{"a": 1}]), impersonatedUserName="u@x.com")
        self.assertEqual(rows, [{"a": 1}])
        (url,), kwargs = ctx.invokeAPI.await_args
        self.assertEqual(url, "datasets/ds/executeQueries")
        self.assertEqual(kwargs["headers"], {"h": "1"})
        self.assertEqual(kwargs["json"]["queries"], [{"query": "Q"}])
        self.assertEqual(kwargs["json"]["impersonatedUserName"], "u@x.com")

    def test_no_impersonation_when_unset(self):
        ctx, _ = self._q(ok([]), impersonatedUserName=None)
        self.assertNotIn(
            "impersonatedUserName", ctx.invokeAPI.await_args.kwargs["json"]
        )

    def test_empty_tables_gives_empty_rows(self):
        self.assertEqual(self._q({"results": [{"tables": []}]})[1], [])
        self.assertEqual(self._q({"results": [{"tables": [{"rows": None}]}]})[1], [])

    def test_errors_raise_query_error(self):
        bad = [
            None,
            "str",
            [],
            {"ERROR": "HTTP 400", "message": "m", "status": 400},
            {"error": {"code": "x"}},
            {"results": []},
            {"results": "x"},
            {},
            {"results": [{"error": {"code": "bad"}}]},
        ]
        for resp in bad:
            with self.subTest(resp=resp), self.assertRaises(cm.QueryError):
                self._q(resp)

    def test_error_status_propagated(self):
        with self.assertRaises(cm.QueryError) as c:
            self._q({"ERROR": "HTTP 429", "message": "slow", "status": 429})
        self.assertEqual(c.exception.status, 429)
        self.assertIn("slow", str(c.exception))

    def test_error_message_truncated(self):
        with self.assertRaises(cm.QueryError) as c:
            self._q({"ERROR": "E", "message": "m" * 1000, "status": 500})
        self.assertLess(len(str(c.exception)), 400)


class DetectVersionTests(unittest.TestCase):
    def _detect(self, probe):
        api = FakeApi([], probe=probe)
        ctx = make(api)
        return api, ctx, run(cm.detect_version(ctx, "ds1", {}))

    def test_probe_ok_selects_carry_over(self):
        api, _, version = self._detect(lambda q: ok([{"[probe]": 1}]))
        self.assertIs(version, cm.VERSIONS[0])
        self.assertEqual(len(api.queries), 1)
        self.assertIn("Cumulative carry over %", api.queries[0])
        self.assertIn(cm.CARRY_OVER, version.groups)

    def test_http_400_falls_back_to_baseline(self):
        def probe(q):
            return {"ERROR": "HTTP 400", "message": "no measure", "status": 400}

        _, ctx, version = self._detect(probe)
        self.assertIs(version, cm.VERSIONS[-1])
        self.assertEqual(version.name, "baseline")
        self.assertNotIn(cm.CARRY_OVER, version.groups)
        ctx.logger.info.assert_called()

    def test_error_body_falls_back_to_baseline(self):
        _, _, version = self._detect(lambda q: {"results": [{"error": {"code": "x"}}]})
        self.assertEqual(version.name, "baseline")

    def test_status_none_without_error_body_raises(self):
        for resp in (None, "str", {}, {"results": []}):
            with self.subTest(resp=resp):
                with self.assertRaises(cm.QueryError) as c:
                    self._detect(lambda q, r=resp: r)
                self.assertIsNone(c.exception.status)
                self.assertFalse(c.exception.error_body)

    def test_status_none_with_error_body_falls_back(self):
        for resp in ({"error": {"code": "x"}}, {"results": [{"error": {"code": "x"}}]}):
            with self.subTest(resp=resp):
                _, _, version = self._detect(lambda q, r=resp: r)
                self.assertEqual(version.name, "baseline")

    def test_http_400_falls_back_even_without_error_body(self):
        _, _, version = self._detect(lambda q: {"ERROR": "HTTP 400", "status": 400})
        self.assertIs(version, cm.VERSIONS[-1])

    def test_other_http_failures_raise(self):
        for status in (401, 403, 429, 500, 503):
            with self.subTest(status=status):
                with self.assertRaises(cm.QueryError) as c:
                    self._detect(
                        lambda q, s=status: {"ERROR": f"HTTP {s}", "status": s}
                    )
                self.assertEqual(c.exception.status, status)

    def test_last_version_has_no_probe(self):
        self.assertIsNone(cm.VERSIONS[-1].probe_measure)


class GetCapacitiesTests(unittest.TestCase):
    def test_maps_row_keys(self):
        api = FakeApi([cap_row(CAP_A, "Active", "Name", "F64"), {"[id]": CAP_B}])
        caps = run(cm.get_capacities(make(api), "ds1", {}))
        self.assertEqual(
            caps[0], {"id": CAP_A, "state": "Active", "name": "Name", "sku": "F64"}
        )
        self.assertEqual(
            caps[1], {"id": CAP_B, "state": None, "name": None, "sku": None}
        )

    def test_error_raises(self):
        ctx = make(AsyncMock(return_value={"ERROR": "HTTP 500", "status": 500}))
        with self.assertRaises(cm.QueryError):
            run(cm.get_capacities(ctx, "ds1", {}))


class MainTests(unittest.TestCase):
    def test_none_context_raises(self):
        with self.assertRaises(RuntimeError):
            run(cm.main(None))

    def test_missing_dataset_returns_true_without_api(self):
        for dataset in (None, "", "   "):
            with self.subTest(dataset=dataset):
                api = AsyncMock()
                ctx = make(api, dataset=dataset)
                self.assertTrue(run_main(ctx))
                api.assert_not_awaited()
                ctx.fm.save.assert_not_awaited()
                ctx.logger.warning.assert_called()

    def test_happy_path_save_path_and_name(self):
        api = FakeApi([cap_row(CAP_A, name="Prod", sku="F64")])
        ctx = make(api)
        self.assertTrue(run_main(ctx))
        # carry-over: 2 groups; no lastRun, days_back default 3 -> 4 days
        self.assertEqual(ctx.fm.save.await_count, 8)
        for call in ctx.fm.save.await_args_list:
            self.assertEqual(call.kwargs["path"], "capacity_metrics/2024/05/10/")
        names = {c.kwargs["file_name"] for c in ctx.fm.save.await_args_list}
        self.assertIn(
            f"20240510_{CAP_A}_utilization_20240507.capacity_metrics.json", names
        )
        self.assertIn(
            f"20240510_{CAP_A}_carryover_20240510.capacity_metrics.json", names
        )
        content = next(
            c.kwargs["content"]
            for c in ctx.fm.save.await_args_list
            if c.kwargs["file_name"].endswith(
                "carryover_20240509.capacity_metrics.json"
            )
        )
        self.assertEqual(
            content,
            {
                "capacityId": CAP_A,
                "capacityName": "Prod",
                "sku": "F64",
                "date": "2024-05-09",
                "group": "carryover",
                "rows": [{"x": 1}],
            },
        )

    def test_run_date_prefix_is_utc_run_date_not_query_day(self):
        api = FakeApi([cap_row(CAP_A)])
        ctx = make(api)
        run_main(ctx, now=datetime(2024, 3, 31, 23, 59))
        for call in ctx.fm.save.await_args_list:
            self.assertTrue(call.kwargs["file_name"].startswith("20240331_"))
            self.assertTrue(call.kwargs["path"].endswith("/2024/03/31/"))

    def test_built_queries_have_mparameter_and_treatas(self):
        api = FakeApi([cap_row(CAP_A)])
        run_main(make(api))
        queries = api.group_queries()
        self.assertTrue(queries)
        for q in queries:
            self.assertIn("MPARAMETER", q)
            self.assertIn("TREATAS", q)
            self.assertIn(CAP_A, q)

    def test_days_back_env_and_last_run_limit_queries(self):
        api = FakeApi([cap_row(CAP_A)])
        ctx = make(
            api, state={cm.STATE_KEY: {"lastRun": "2024-05-10T01:00:00.000000Z"}}
        )
        self.assertTrue(run_main(ctx, env={cm.DAYS_BACK_ENV: "7"}))
        dates = {q.split("DATE(")[1].split(")")[0] for q in api.group_queries()}
        self.assertEqual(dates, {"2024,5,9", "2024,5,10"})

    def test_days_back_env_without_last_run(self):
        api = FakeApi([cap_row(CAP_A)])
        run_main(make(api), env={cm.DAYS_BACK_ENV: "1"})
        dates = {q.split("DATE(")[1].split(")")[0] for q in api.group_queries()}
        self.assertEqual(dates, {"2024,5,9", "2024,5,10"})

    def test_unparseable_last_run_uses_full_window(self):
        api = FakeApi([cap_row(CAP_A)])
        ctx = make(api, state={cm.STATE_KEY: {"lastRun": "garbage"}})
        self.assertTrue(run_main(ctx))
        dates = {q.split("DATE(")[1].split(")")[0] for q in api.group_queries()}
        self.assertEqual(len(dates), 4)

    def test_baseline_version_queries_only_utilization(self):
        api = FakeApi(
            [cap_row(CAP_A)], probe=lambda q: {"ERROR": "HTTP 400", "status": 400}
        )
        ctx = make(api)
        self.assertTrue(run_main(ctx))
        self.assertEqual(ctx.fm.save.await_count, 4)
        for call in ctx.fm.save.await_args_list:
            self.assertEqual(call.kwargs["content"]["group"], "utilization")
        self.assertNotIn("Carry over add %", "".join(api.group_queries()))

    def test_non_active_skipped_by_default(self):
        api = FakeApi([cap_row(CAP_A, "Active"), cap_row(CAP_B, "Suspended")])
        ctx = make(api)
        self.assertTrue(run_main(ctx))
        qs = "".join(api.group_queries())
        self.assertIn(CAP_A, qs)
        self.assertNotIn(CAP_B, qs)

    def test_non_active_included_with_flag(self):
        api = FakeApi([cap_row(CAP_A, "Active"), cap_row(CAP_B, "Suspended")])
        ctx = make(api)
        self.assertTrue(run_main(ctx, env={cm.INCLUDE_SUSPENDED_ENV: "true"}))
        qs = "".join(api.group_queries())
        self.assertIn(CAP_A, qs)
        self.assertIn(CAP_B, qs)

    def test_suspended_with_no_rows_does_not_warn(self):
        api = FakeApi([cap_row(CAP_B, "Suspended")], group=lambda q: ok([]))
        ctx = make(api)
        self.assertTrue(run_main(ctx, env={cm.INCLUDE_SUSPENDED_ENV: "1"}))
        ctx.logger.warning.assert_not_called()

    def test_failed_group_query_returns_false_but_others_run(self):
        def group(q):
            if CAP_A in q and "DATE(2024,5,8)" in q and "Carry over add" in q:
                return {"ERROR": "HTTP 400", "message": "bad dax", "status": 400}
            return ok([{"x": 1}])

        api = FakeApi([cap_row(CAP_A), cap_row(CAP_B)], group=group)
        ctx = make(api)
        self.assertFalse(run_main(ctx))
        # 2 capacities * 4 days * 2 groups = 16 queries, only 1 failed (non-fatal)
        self.assertEqual(len(api.group_queries()), 16)
        self.assertEqual(ctx.fm.save.await_count, 15)
        ctx.logger.error.assert_called()

    def test_dax_error_body_fails_soft_and_continues(self):
        api = FakeApi(
            [cap_row(CAP_A), cap_row(CAP_B)],
            group=lambda q: {"results": [{"error": {"code": "bad"}}]},
        )
        ctx = make(api)
        self.assertFalse(run_main(ctx))
        self.assertEqual(len(api.group_queries()), 16)

    def test_every_capacity_failing_still_attempts_all(self):
        api = FakeApi(
            [cap_row(CAP_A), cap_row(CAP_B)],
            group=lambda q: {"ERROR": "HTTP 400", "status": 400},
        )
        ctx = make(api)
        self.assertFalse(run_main(ctx))
        self.assertEqual(len(api.group_queries()), 16)
        ctx.fm.save.assert_not_awaited()

    def test_fatal_status_aborts_run(self):
        for status in (429, 500, 503):
            with self.subTest(status=status):
                api = FakeApi(
                    [cap_row(CAP_A), cap_row(CAP_B)],
                    group=lambda q, s=status: {"ERROR": f"HTTP {s}", "status": s},
                )
                ctx = make(api)
                self.assertFalse(run_main(ctx))
                self.assertEqual(len(api.group_queries()), 1)
                ctx.fm.save.assert_not_awaited()
                ctx.logger.error.assert_called()

    def test_abort_on_429_midway_skips_remaining(self):
        count = {"n": 0}

        def group(q):
            count["n"] += 1
            if count["n"] == 3:
                return {"ERROR": "HTTP 429", "status": 429}
            return ok([{"x": 1}])

        api = FakeApi([cap_row(CAP_A), cap_row(CAP_B)], group=group)
        ctx = make(api)
        self.assertFalse(run_main(ctx))
        self.assertEqual(len(api.group_queries()), 3)
        self.assertEqual(ctx.fm.save.await_count, 2)
        self.assertNotIn(CAP_B, "".join(api.group_queries()))

    def test_abort_on_500_returns_false_with_single_query(self):
        api = FakeApi(
            [cap_row(CAP_A)],
            group=lambda q: {"ERROR": "HTTP 500", "message": "boom", "status": 500},
        )
        ctx = make(api)
        self.assertFalse(run_main(ctx))
        self.assertEqual(len(api.group_queries()), 1)

    def test_is_fatal(self):
        for status, expected in (
            (429, True),
            (500, True),
            (503, True),
            (599, True),
            (400, False),
            (401, False),
            (403, False),
            (404, False),
            (499, False),
            (None, False),
        ):
            with self.subTest(status=status):
                self.assertEqual(cm._is_fatal(cm.QueryError("x", status)), expected)

    def test_days_back_clamped_limits_queries(self):
        api = FakeApi([cap_row(CAP_A)])
        self.assertTrue(run_main(make(api), env={cm.DAYS_BACK_ENV: "500"}))
        dates = {q.split("DATE(")[1].split(")")[0] for q in api.group_queries()}
        self.assertEqual(len(dates), 31)  # 30 days back + today

    def test_empty_results_for_active_capacity_warns_and_succeeds(self):
        api = FakeApi([cap_row(CAP_A)], group=lambda q: ok([]))
        ctx = make(api)
        self.assertTrue(run_main(ctx))
        ctx.fm.save.assert_not_awaited()
        ctx.logger.warning.assert_called_once()
        self.assertIn(CAP_A, ctx.logger.warning.call_args.args[0])
        self.assertIn("2024-05-07..2024-05-10", ctx.logger.warning.call_args.args[0])

    def test_invalid_capacity_id_skipped_counts_as_failure(self):
        evil = 'x"} EVALUATE Secrets'
        api = FakeApi([cap_row(evil), cap_row(None), cap_row(CAP_A)])
        ctx = make(api)
        self.assertFalse(run_main(ctx))
        qs = "".join(api.group_queries())
        self.assertNotIn("Secrets", qs)
        self.assertIn(CAP_A, qs)
        self.assertEqual(ctx.fm.save.await_count, 8)

    def test_setup_failure_on_capacities_returns_false(self):
        class Api(FakeApi):
            async def __call__(self, url, **kw):
                if kw["json"]["queries"][0]["query"] == cm.CAPACITIES_QUERY:
                    return {"ERROR": "HTTP 403", "status": 403}
                return await super().__call__(url, **kw)

        ctx = make(Api([]))
        self.assertFalse(run_main(ctx))
        ctx.fm.save.assert_not_awaited()

    def test_probe_throttled_returns_false_without_group_queries(self):
        api = FakeApi(
            [cap_row(CAP_A)], probe=lambda q: {"ERROR": "HTTP 429", "status": 429}
        )
        ctx = make(api)
        self.assertFalse(run_main(ctx))
        self.assertEqual(api.group_queries(), [])

    def test_no_capacities_succeeds(self):
        api = FakeApi([])
        ctx = make(api)
        self.assertTrue(run_main(ctx))
        ctx.fm.save.assert_not_awaited()

    def test_future_last_run_does_not_crash(self):
        api = FakeApi([cap_row(CAP_A)])
        ctx = make(
            api, state={cm.STATE_KEY: {"lastRun": "2024-06-01T00:00:00.000000Z"}}
        )
        # must not raise (e.g. IndexError on an empty day list)
        run_main(ctx)

    def test_uses_pbi_headers_for_calls(self):
        api = FakeApi([cap_row(CAP_A)])
        ctx = make(api)
        run_main(ctx)
        for _, kwargs in api.calls:
            self.assertEqual(
                kwargs["headers"], ctx.clients["pbi"].get_headers.return_value
            )
        self.assertTrue(all(u == "datasets/ds1/executeQueries" for u, _ in api.calls))


if __name__ == "__main__":
    unittest.main()
