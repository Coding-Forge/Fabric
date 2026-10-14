"""E1: http_retry helpers and Context.invokeAPI throttle handling."""
import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import AsyncMock, MagicMock, patch

from env import context as ctx_mod
from env.context import Context
from env.utility import http_retry

ENV_KEYS = ("API_MAX_RETRIES", "API_MAX_CONCURRENCY", "API_MAX_RETRY_DELAY")


class _EnvIsolated:
    def _isolate_env(self):
        p = patch.dict(os.environ)
        p.start()
        self.addCleanup(p.stop)
        for k in ENV_KEYS:
            os.environ.pop(k, None)


class EnvSettingTests(_EnvIsolated, unittest.TestCase):
    def setUp(self):
        self._isolate_env()

    def test_defaults(self):
        self.assertEqual(http_retry.max_retries(), 3)
        self.assertEqual(http_retry.max_concurrency(), 16)
        self.assertEqual(http_retry.max_delay_seconds(), 120.0)

    def test_overrides(self):
        os.environ.update(API_MAX_RETRIES="5", API_MAX_CONCURRENCY="4", API_MAX_RETRY_DELAY="30")
        self.assertEqual(http_retry.max_retries(), 5)
        self.assertEqual(http_retry.max_concurrency(), 4)
        self.assertEqual(http_retry.max_delay_seconds(), 30.0)

    def test_zero_retries_allowed_but_concurrency_floor_is_one(self):
        os.environ.update(API_MAX_RETRIES="0", API_MAX_CONCURRENCY="0")
        self.assertEqual(http_retry.max_retries(), 0)
        self.assertEqual(http_retry.max_concurrency(), 1)

    def test_negative_values_clamped_to_minimum(self):
        os.environ.update(API_MAX_RETRIES="-4", API_MAX_CONCURRENCY="-2", API_MAX_RETRY_DELAY="-9")
        self.assertEqual(http_retry.max_retries(), 0)
        self.assertEqual(http_retry.max_concurrency(), 1)
        self.assertEqual(http_retry.max_delay_seconds(), 0.0)

    def test_non_integer_falls_back_to_default(self):
        os.environ.update(API_MAX_RETRIES="lots", API_MAX_CONCURRENCY="x", API_MAX_RETRY_DELAY="1.5")
        self.assertEqual(http_retry.max_retries(), 3)
        self.assertEqual(http_retry.max_concurrency(), 16)
        self.assertEqual(http_retry.max_delay_seconds(), 120.0)

    def test_retryable_statuses(self):
        self.assertEqual(set(http_retry.RETRYABLE_STATUSES), {429, 503, 504})


class ParseRetryAfterTests(unittest.TestCase):
    def test_absent_values(self):
        for v in (None, "", "   "):
            with self.subTest(v=v):
                self.assertIsNone(http_retry.parse_retry_after(v))

    def test_seconds(self):
        self.assertEqual(http_retry.parse_retry_after("12"), 12.0)
        self.assertEqual(http_retry.parse_retry_after(" 7 "), 7.0)
        self.assertEqual(http_retry.parse_retry_after("0"), 0.0)

    def test_unparseable(self):
        for v in ("soon", "-5", "1.5", "Mon, 99 Foo 2020"):
            with self.subTest(v=v):
                self.assertIsNone(http_retry.parse_retry_after(v))

    def test_http_date_in_future(self):
        when = datetime.now(timezone.utc) + timedelta(seconds=90)
        got = http_retry.parse_retry_after(format_datetime(when, usegmt=True))
        self.assertIsNotNone(got)
        self.assertGreater(got, 80)
        self.assertLessEqual(got, 90)

    def test_http_date_in_past_is_zero(self):
        when = datetime.now(timezone.utc) - timedelta(hours=1)
        self.assertEqual(http_retry.parse_retry_after(format_datetime(when, usegmt=True)), 0.0)

    def test_http_date_non_gmt_offset(self):
        when = datetime.now(timezone(timedelta(hours=-5))) + timedelta(seconds=60)
        got = http_retry.parse_retry_after(format_datetime(when))
        self.assertGreater(got, 50)
        self.assertLessEqual(got, 60)

    def test_naive_http_date_treated_as_utc(self):
        when = datetime.now(timezone.utc) + timedelta(seconds=60)
        text = when.strftime("%a, %d %b %Y %H:%M:%S -0000")  # RFC 2822 "-0000" => naive
        got = http_retry.parse_retry_after(text)
        self.assertGreater(got, 50)
        self.assertLessEqual(got, 60)


class RetryDelayTests(_EnvIsolated, unittest.TestCase):
    def setUp(self):
        self._isolate_env()

    def test_exponential_backoff_without_header(self):
        self.assertEqual([http_retry.retry_delay(i) for i in range(4)], [2.0, 4.0, 8.0, 16.0])

    def test_retry_after_takes_precedence(self):
        self.assertEqual(http_retry.retry_delay(0, "7"), 7.0)
        self.assertEqual(http_retry.retry_delay(3, "1"), 1.0)

    def test_unparseable_header_falls_back_to_backoff(self):
        self.assertEqual(http_retry.retry_delay(1, "garbage"), 4.0)

    def test_default_cap(self):
        self.assertEqual(http_retry.retry_delay(0, "99999"), 120.0)
        self.assertEqual(http_retry.retry_delay(10), 120.0)

    def test_env_cap(self):
        os.environ["API_MAX_RETRY_DELAY"] = "5"
        self.assertEqual(http_retry.retry_delay(0, "60"), 5.0)
        self.assertEqual(http_retry.retry_delay(4), 5.0)
        self.assertEqual(http_retry.retry_delay(0, "3"), 3.0)

    def test_cap_zero_means_no_wait(self):
        os.environ["API_MAX_RETRY_DELAY"] = "0"
        self.assertEqual(http_retry.retry_delay(2, "30"), 0.0)

    def test_http_date_is_capped(self):
        os.environ["API_MAX_RETRY_DELAY"] = "10"
        when = datetime.now(timezone.utc) + timedelta(hours=1)
        self.assertEqual(http_retry.retry_delay(0, format_datetime(when, usegmt=True)), 10.0)


def _err(status, retry_after=None):
    return {"ERROR": f"HTTP {status}", "status": status, "retryAfter": retry_after, "message": ""}


class InvokeApiRetryTests(_EnvIsolated, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._isolate_env()
        self.sleep = AsyncMock()
        p = patch.object(ctx_mod.asyncio, "sleep", self.sleep)
        p.start()
        self.addCleanup(p.stop)
        self.ctx = Context()
        self.ctx.logger = MagicMock()

    def _once(self, *results):
        m = AsyncMock(side_effect=list(results))
        self.ctx._invoke_once = m
        return m

    def _slept(self):
        return [c.args[0] for c in self.sleep.await_args_list]

    async def test_retries_each_throttle_status_then_succeeds(self):
        for status in (429, 503, 504):
            with self.subTest(status=status):
                self.sleep.reset_mock()
                once = self._once(_err(status), {"ok": 1})
                self.assertEqual(await self.ctx.invokeAPI("x", headers={"a": "b"}), {"ok": 1})
                self.assertEqual(once.await_count, 2)
                self.assertEqual(self.sleep.await_count, 1)

    async def test_forwards_arguments_on_every_attempt(self):
        once = self._once(_err(503), {"ok": 1})
        await self.ctx.invokeAPI("p", headers={"h": 1}, json={"j": 2})
        for call in once.await_args_list:
            self.assertEqual(call.args, ("p",))
            self.assertEqual(call.kwargs, {"headers": {"h": 1}, "json": {"j": 2}})

    async def test_honours_retry_after_seconds(self):
        self._once(_err(429, "7"), {"ok": 1})
        await self.ctx.invokeAPI("x")
        self.assertEqual(self._slept(), [7.0])

    async def test_honours_retry_after_http_date(self):
        when = datetime.now(timezone.utc) + timedelta(seconds=45)
        self._once(_err(429, format_datetime(when, usegmt=True)), {"ok": 1})
        await self.ctx.invokeAPI("x")
        (delay,) = self._slept()
        self.assertGreater(delay, 35)
        self.assertLessEqual(delay, 45)

    async def test_exponential_backoff_when_no_retry_after(self):
        once = self._once(_err(503), _err(503), _err(503), {"ok": 1})
        self.assertEqual(await self.ctx.invokeAPI("x"), {"ok": 1})
        self.assertEqual(self._slept(), [2.0, 4.0, 8.0])
        self.assertEqual(once.await_count, 4)

    async def test_returns_last_error_when_retries_exhausted(self):
        once = self._once(*[_err(429, "1") for _ in range(4)], {"ok": "never"})
        result = await self.ctx.invokeAPI("x")
        self.assertEqual(result["status"], 429)
        self.assertEqual(once.await_count, 4)  # 1 + 3 retries
        self.assertEqual(self.sleep.await_count, 3)

    async def test_api_max_retries_env_respected(self):
        os.environ["API_MAX_RETRIES"] = "1"
        once = self._once(_err(503), _err(503), {"ok": "never"})
        result = await self.ctx.invokeAPI("x")
        self.assertEqual(result["status"], 503)
        self.assertEqual(once.await_count, 2)

    async def test_zero_retries_disables_retry(self):
        os.environ["API_MAX_RETRIES"] = "0"
        once = self._once(_err(429), {"ok": "never"})
        self.assertEqual((await self.ctx.invokeAPI("x"))["status"], 429)
        self.assertEqual(once.await_count, 1)
        self.sleep.assert_not_awaited()

    async def test_no_retry_on_non_retryable_errors(self):
        for status in (400, 401, 403, 404, 500):
            with self.subTest(status=status):
                self.sleep.reset_mock()
                once = self._once(_err(status), {"ok": "never"})
                result = await self.ctx.invokeAPI("x")
                self.assertEqual(result["status"], status)
                self.assertEqual(once.await_count, 1)
                self.sleep.assert_not_awaited()

    async def test_success_and_non_error_results_are_not_retried(self):
        for payload in ({"value": []}, None, ["a"], {"message": "No results found"}, {"error": "x"}):
            with self.subTest(payload=payload):
                once = self._once(payload, {"ok": "never"})
                self.assertEqual(await self.ctx.invokeAPI("x"), payload)
                self.assertEqual(once.await_count, 1)
        self.sleep.assert_not_awaited()

    async def test_error_dict_without_status_is_not_retried(self):
        once = self._once({"ERROR": "boom"}, {"ok": "never"})
        self.assertEqual(await self.ctx.invokeAPI("x"), {"ERROR": "boom"})
        self.assertEqual(once.await_count, 1)

    async def test_delay_is_capped_by_api_max_retry_delay(self):
        os.environ["API_MAX_RETRY_DELAY"] = "5"
        self._once(_err(429, "3600"), _err(503), _err(503), {"ok": 1})
        await self.ctx.invokeAPI("x")
        self.assertEqual(self._slept(), [5.0, 4.0, 5.0])

    async def test_other_exceptions_propagate_without_retry(self):
        once = AsyncMock(side_effect=RuntimeError("net"))
        self.ctx._invoke_once = once
        with self.assertRaises(RuntimeError):
            await self.ctx.invokeAPI("x")
        self.assertEqual(once.await_count, 1)

    async def test_retry_is_logged(self):
        self._once(_err(429, "1"), {"ok": 1})
        await self.ctx.invokeAPI("x")
        self.ctx.logger.warning.assert_called_once()


class InvokeApiConcurrencyTests(_EnvIsolated, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._isolate_env()

    async def _run_many(self, ctx, n, results=None):
        state = {"now": 0, "peak": 0}
        real_sleep = asyncio.sleep

        async def once(rest_api, headers=None, json=None):
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
            await real_sleep(0.01)
            state["now"] -= 1
            return {"ok": rest_api}

        ctx._invoke_once = once
        out = await asyncio.gather(*(ctx.invokeAPI(f"u{i}") for i in range(n)))
        return out, state

    async def test_concurrency_limited_to_env_value(self):
        os.environ["API_MAX_CONCURRENCY"] = "3"
        out, state = await self._run_many(Context(), 12)
        self.assertEqual(len(out), 12)
        self.assertEqual(state["peak"], 3)

    async def test_default_limit_is_16(self):
        out, state = await self._run_many(Context(), 40)
        self.assertEqual(state["peak"], http_retry.DEFAULT_MAX_CONCURRENCY)

    async def test_limit_of_one_serialises(self):
        os.environ["API_MAX_CONCURRENCY"] = "1"
        _, state = await self._run_many(Context(), 5)
        self.assertEqual(state["peak"], 1)

    async def test_semaphore_created_lazily_and_reused(self):
        ctx = Context()
        self.assertIsNone(ctx._api_semaphore)
        await self._run_many(ctx, 2)
        sem = ctx._api_semaphore
        self.assertIsInstance(sem, asyncio.Semaphore)
        await self._run_many(ctx, 2)
        self.assertIs(ctx._api_semaphore, sem)

    async def test_slot_released_while_sleeping_between_retries(self):
        """With one slot, a throttled request must not block others during its backoff."""
        os.environ["API_MAX_CONCURRENCY"] = "1"
        ctx = Context()
        ctx.logger = MagicMock()
        order = []
        real_sleep = asyncio.sleep

        async def fake_sleep(delay):
            for _ in range(5):
                await real_sleep(0)

        calls = {"a": 0}

        async def once(rest_api, headers=None, json=None):
            order.append(rest_api)
            if rest_api == "a":
                calls["a"] += 1
                return _err(429) if calls["a"] == 1 else {"ok": "a"}
            return {"ok": "b"}

        ctx._invoke_once = once
        with patch.object(ctx_mod.asyncio, "sleep", fake_sleep):
            ra, rb = await asyncio.gather(ctx.invokeAPI("a"), ctx.invokeAPI("b"))
        self.assertEqual((ra, rb), ({"ok": "a"}, {"ok": "b"}))
        self.assertEqual(order, ["a", "b", "a"])


if __name__ == "__main__":
    unittest.main()
