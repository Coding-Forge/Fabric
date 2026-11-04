"""B12, B13: activity 30-day clamp and failed-day handling."""
import re
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from env.context import utc_now, utc_stamp
from env.modules import activity
from tests.helpers import make_context

FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _state(days_ago):
    return {"activity": {"lastRun": (utc_now() - timedelta(days=days_ago)).strftime(FMT)}}


def _start(url):
    return re.search(r"startDateTime='([^']+)'", url).group(1)


def _midnight(days_ago):
    d = utc_now() - timedelta(days=days_ago)
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


class ActivityTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_context(self):
        with self.assertRaises(RuntimeError):
            await activity.main(None)

    async def test_old_checkpoint_is_clamped_to_30_days(self):
        invoke = AsyncMock(return_value={"activityEventEntities": []})
        ctx = make_context(_state(500), invoke)
        result = await activity.main(ctx)
        self.assertTrue(result)
        first = invoke.await_args_list[0].kwargs["rest_api"]
        self.assertEqual(_start(first), _midnight(activity.MAX_LOOKBACK_DAYS).strftime("%Y-%m-%dT%H:%M:%SZ"))
        # 30 days back through today inclusive
        self.assertEqual(invoke.await_count, activity.MAX_LOOKBACK_DAYS + 1)
        ctx.logger.warning.assert_called()

    async def test_recent_checkpoint_is_not_clamped(self):
        invoke = AsyncMock(return_value={"activityEventEntities": []})
        ctx = make_context(_state(2), invoke)
        await activity.main(ctx)
        first = invoke.await_args_list[0].kwargs["rest_api"]
        self.assertEqual(_start(first), _midnight(2).strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertEqual(invoke.await_count, 3)
        ctx.logger.warning.assert_not_called()

    async def test_day_window_is_24h_minus_one_second(self):
        invoke = AsyncMock(return_value={"activityEventEntities": []})
        ctx = make_context(_state(0), invoke)
        await activity.main(ctx)
        url = invoke.await_args_list[0].kwargs["rest_api"]
        self.assertIn("endDateTime='" + _midnight(0).strftime("%Y-%m-%d") + "T23:59:59Z'", url)

    async def test_failed_day_stops_and_returns_false(self):
        invoke = AsyncMock(side_effect=[{"activityEventEntities": []},
                                        {"ERROR": "HTTP 429", "status": 429},
                                        {"activityEventEntities": []}])
        ctx = make_context(_state(5), invoke)
        result = await activity.main(ctx)
        self.assertIs(result, False)
        self.assertEqual(invoke.await_count, 2)  # did not continue past the failed day
        ctx.logger.error.assert_called()

    async def test_none_result_counts_as_failure(self):
        ctx = make_context(_state(1), AsyncMock(return_value=None))
        self.assertIs(await activity.main(ctx), False)

    async def test_pages_are_saved_and_continuation_followed(self):
        invoke = AsyncMock(side_effect=[
            {"activityEventEntities": [{"a": 1}],
             "continuationUri": "https://x/y?continuationToken='t'"},
            {"activityEventEntities": [{"a": 2}]},
        ])
        ctx = make_context(_state(0), invoke)
        self.assertTrue(await activity.main(ctx))
        self.assertEqual(invoke.await_args_list[1].kwargs["rest_api"], "https://x/y?continuationToken='t'")
        self.assertEqual(invoke.await_args_list[1].kwargs["headers"]["Content-Type"], "application/json")
        names = [c.kwargs["file_name"] for c in ctx.fm.save.await_args_list]
        self.assertTrue(names[0].endswith("_00001.json"))
        self.assertTrue(names[1].endswith("_00002.json"))

    async def test_failure_on_continuation_page_returns_false(self):
        invoke = AsyncMock(side_effect=[
            {"activityEventEntities": [{"a": 1}],
             "continuationUri": "https://x/y?continuationToken='t'"},
            {"ERROR": "HTTP 500"},
        ])
        ctx = make_context(_state(0), invoke)
        self.assertIs(await activity.main(ctx), False)

    async def test_json_string_state_supported(self):
        import json
        invoke = AsyncMock(return_value={"activityEventEntities": []})
        ctx = make_context(json.dumps(_state(0)), invoke)
        self.assertTrue(await activity.main(ctx))

    async def test_bad_checkpoint_raises_value_error(self):
        ctx = make_context({"activity": {"lastRun": "junk"}}, AsyncMock())
        with self.assertRaises(ValueError):
            await activity.main(ctx)


class ActivityCheckpointTests(unittest.IsolatedAsyncioTestCase):
    """E2: per-day checkpoint written to current_state, in UTC."""

    async def test_checkpoint_advances_after_each_completed_day(self):
        seen = []
        state = _state(3)

        async def invoke(rest_api, headers=None, json=None):
            seen.append(state["activity"]["lastRun"])
            return {"activityEventEntities": []}

        ctx = make_context(state, invoke)
        self.assertTrue(await activity.main(ctx))
        # day D-3 sees the original checkpoint, then midnight of each following day
        self.assertEqual(seen[1], utc_stamp(_midnight(2)))
        self.assertEqual(seen[2], utc_stamp(_midnight(1)))
        self.assertEqual(seen[3], utc_stamp(_midnight(0)))

    async def test_failure_leaves_checkpoint_at_first_unfinished_day(self):
        state = _state(3)
        invoke = AsyncMock(side_effect=[{"activityEventEntities": []},
                                        {"activityEventEntities": []},
                                        {"ERROR": "HTTP 500"}])
        ctx = make_context(state, invoke)
        self.assertIs(await activity.main(ctx), False)
        self.assertEqual(state["activity"]["lastRun"], utc_stamp(_midnight(1)))

    async def test_failure_on_first_day_keeps_original_checkpoint(self):
        state = _state(3)
        original = state["activity"]["lastRun"]
        ctx = make_context(state, AsyncMock(return_value={"ERROR": "HTTP 429"}))
        self.assertIs(await activity.main(ctx), False)
        self.assertEqual(state["activity"]["lastRun"], original)

    async def test_checkpoint_not_written_for_future_day(self):
        state = _state(0)
        original = state["activity"]["lastRun"]
        ctx = make_context(state, AsyncMock(return_value={"activityEventEntities": []}))
        self.assertTrue(await activity.main(ctx))
        self.assertEqual(state["activity"]["lastRun"], original)

    async def test_checkpoint_stamp_is_utc_formatted(self):
        state = _state(2)
        ctx = make_context(state, AsyncMock(side_effect=[{"activityEventEntities": []}, {"ERROR": "x"}]))
        await activity.main(ctx)
        stamp = state["activity"]["lastRun"]
        parsed = datetime.strptime(stamp, FMT)
        self.assertEqual(parsed, _midnight(1))

    async def test_string_state_is_not_checkpointed_and_does_not_crash(self):
        import json
        ctx = make_context(json.dumps(_state(2)), AsyncMock(return_value={"activityEventEntities": []}))
        self.assertTrue(await activity.main(ctx))
        self.assertIsInstance(ctx.current_state, str)

    async def test_clamp_uses_utc_midnight(self):
        invoke = AsyncMock(return_value={"activityEventEntities": []})
        ctx = make_context(_state(100), invoke)
        await activity.main(ctx)
        first = _start(invoke.await_args_list[0].kwargs["rest_api"])
        self.assertEqual(first, _midnight(activity.MAX_LOOKBACK_DAYS).strftime("%Y-%m-%dT%H:%M:%SZ"))


if __name__ == "__main__":
    unittest.main()
