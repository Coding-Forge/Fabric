"""Request admission, durable cooldowns, strict snapshots and response validation."""

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from azure.core.exceptions import AzureError, ResourceNotFoundError

from env.context import Context, utc_stamp
from env.modules import FabricConnections
from env.utility.fabric_collection import FabricCollection
from env.utility.file_management import File_Management
from tests.fabric_helpers import (
    PRIVATE_MARKER,
    ROOT,
    CollectorTestCase,
    PrivateDiagnosticValue,
)
from tests.test_context import _FakeResponse, _FakeSession


class _DiagnosticReader:
    """Fragmented aiohttp-style content, using asyncio's real readexactly."""

    def __init__(self, body):
        self.body = body
        self.requests = []

    async def readexactly(self, size):
        self.requests.append(size)
        reader = asyncio.StreamReader()
        loop = asyncio.get_running_loop()
        for offset in range(0, len(self.body), 113):
            loop.call_soon(reader.feed_data, self.body[offset : offset + 113])
        loop.call_soon(reader.feed_eof)
        return await reader.readexactly(size)


class RequestGateTests(CollectorTestCase):
    def gate_clock(self):
        """Use the harness clock without changing asyncio's own bookkeeping."""
        return patch(
            "env.utility.fabric_collection.asyncio",
            SimpleNamespace(
                **{
                    **vars(asyncio),
                    "get_running_loop": lambda: SimpleNamespace(
                        time=lambda: self.elapsed
                    ),
                    "sleep": self.sleep,
                }
            ),
        )

    async def collection(self, ctx, module="fabricconnections", **kwargs):
        collection = FabricCollection(ctx, module, "Offline test scope", **kwargs)
        await collection.start()
        return collection

    async def test_each_retry_is_gated_and_final_response_observed(self):
        events = []
        ctx = self.context()
        responses = [
            {"ERROR": "throttled", "status": 429},
            {"ERROR": "unavailable", "status": 503},
        ]

        async def request(*args):
            events.append("request")
            return responses.pop(0)

        async def gate():
            events.append("gate")

        async def observe(response, attempt):
            events.append(("response", response["status"], attempt))
            return True

        ctx._safe_get.side_effect = request
        with patch.dict(os.environ, {"API_MAX_RETRIES": "1"}):
            result = await ctx.invokeAPI(
                ROOT + "connections", request_gate=gate, response_gate=observe
            )
        self.assertEqual(result["status"], 503)
        self.assertEqual(
            events,
            [
                "gate",
                "request",
                ("response", 429, 0),
                "gate",
                "request",
                ("response", 503, 1),
            ],
        )
        self.assertEqual([c.args[0] for c in self.sleep.await_args_list], [0.0])

    async def test_gated_post_and_orphan_observer_refuse_http(self):
        ctx = self.context()
        for kwargs in (
            {"json": {}, "request_gate": AsyncMock()},
            {"response_gate": AsyncMock()},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                await ctx.invokeAPI(ROOT + "connections", **kwargs)
        ctx._safe_get.assert_not_awaited()

    async def test_legacy_retry_preserves_server_delay_and_original_mock_target(self):
        ctx = self.context()
        ctx._invoke_once = AsyncMock(
            side_effect=[
                {"ERROR": "throttled", "status": 429, "retryAfter": "3600"},
                {"value": []},
            ]
        )
        with (
            patch.dict(os.environ, {"API_MAX_RETRY_DELAY": "5"}),
            patch("env.utility.http_retry.monotonic", side_effect=lambda: self.elapsed),
        ):
            self.assertEqual(await ctx.invokeAPI("legacy"), {"value": []})
        self.assertEqual([c.args[0] for c in self.sleep.await_args_list], [3600.0])
        ctx._safe_get.assert_not_awaited()
        self.assertEqual(ctx._invoke_once.await_count, 2)

    async def test_uncapped_cooldowns_persist_even_after_retry_exhaustion(self):
        fixed_datetime = MagicMock(wraps=datetime)
        fixed_datetime.now.side_effect = lambda tz: self.now.replace(
            tzinfo=timezone.utc
        )
        for header in (
            "3600",
            format_datetime(
                (self.now + timedelta(hours=2)).replace(tzinfo=timezone.utc),
                usegmt=True,
            ),
        ):
            with self.subTest(header=header):
                self.files.clear()
                ctx = self.context(
                    {"ERROR": "throttled", "status": 429, "retryAfter": header}
                )
                initial = self.now
                with (
                    patch.dict(os.environ, {"API_MAX_RETRIES": "0"}),
                    patch("env.utility.http_retry.datetime", fixed_datetime),
                ):
                    collection = await self.collection(ctx)
                    self.assertIsNone(await collection.pages("connections"))
                ledger = self.files["fabricconnections/request_gate.json"]
                deadline = ctx.convert_dt_str(ledger["nextRequestUtc"])
                self.assertGreaterEqual((deadline - initial).total_seconds(), 3600)
                self.assertIs(ledger["pending"], False)
                restarted = self.context({"value": []})
                resumed = await self.collection(restarted)
                self.assertIsNone(await resumed.pages("connections"))
                restarted._safe_get.assert_not_awaited()
                restarted.clients["tenant"].get_headers.assert_not_called()
                self.assertEqual(self.now, initial)
                self.advance((deadline - self.now).total_seconds())
                self.assertEqual(await resumed.pages("connections"), [])
                restarted._safe_get.assert_awaited_once()

    async def test_invalid_retry_headers_block_across_restart(self):
        for header in ("soon", "-1", "", "1.5", "9" * 400):
            with self.subTest(header=header):
                self.files.clear()
                ctx = self.context(
                    {"ERROR": "throttled", "status": 503, "retryAfter": header}
                )
                collection = await self.collection(ctx)
                self.assertIsNone(await collection.pages("connections"))
                self.assertIs(
                    self.files["fabricconnections/request_gate.json"]["blocked"], True
                )
                self.advance(86400)
                restarted = self.context()
                resumed = await self.collection(restarted)
                self.assertIsNone(await resumed.pages("connections"))
                restarted._safe_get.assert_not_awaited()
                restarted.clients["tenant"].get_headers.assert_not_called()

    async def test_short_server_cooldown_waits_before_retry_without_legacy_cap(self):
        ctx = self.context(
            {"ERROR": "throttled", "status": 429, "retryAfter": "25"},
            {"value": []},
        )
        with patch.dict(os.environ, {"API_MAX_RETRY_DELAY": "1"}):
            collection = await self.collection(ctx)
            self.assertEqual(await collection.pages("connections"), [])
        self.assertEqual(
            (self.request_times[1] - self.request_times[0]).total_seconds(), 25
        )

    async def test_last_exhausted_retry_persists_its_own_longer_cooldown(self):
        ctx = self.context(
            {"ERROR": "throttled", "status": 429, "retryAfter": "2"},
            {"ERROR": "throttled", "status": 429, "retryAfter": "3600"},
        )
        with patch.dict(os.environ, {"API_MAX_RETRIES": "1"}):
            collection = await self.collection(ctx)
            self.assertIsNone(await collection.pages("connections"))
        self.assertEqual(ctx._safe_get.await_count, 2)
        ledger = self.files["fabricconnections/request_gate.json"]
        self.assertEqual(
            ctx.convert_dt_str(ledger["nextRequestUtc"]),
            self.now + timedelta(seconds=3600),
        )
        self.assertIs(ledger["pending"], False)
        restarted = self.context()
        resumed = await self.collection(restarted)
        self.assertTrue((await resumed.page("connections"))["deferred"])
        restarted._safe_get.assert_not_awaited()

    async def test_non_permission_collectors_pace_pages_at_one_second(self):
        for module in (
            "fabricconnections",
            "fabricitemjobhistory",
            "fabricdeploymentpipelineoperations",
        ):
            with self.subTest(module=module):
                ctx = self.context(
                    {"value": [], "continuationToken": "next"}, {"value": []}
                )
                collection = await self.collection(ctx, module)
                self.assertEqual(await collection.pages("connections"), [])
                earlier, later = self.request_times[-2:]
                self.assertEqual((later - earlier).total_seconds(), 1)

    async def test_permission_reserves_19_seconds_plus_storage_margin_and_one_attempt(
        self,
    ):
        ctx = self.context({"value": [], "continuationToken": "next"}, {"value": []})
        collection = await self.collection(
            ctx, "fabricitemaccesspermissions", interval=19, single_attempt=True
        )
        start = self.now
        response = await collection.page("admin/items")
        self.assertEqual(response["continuationToken"], "next")
        ledger = self.files["fabricitemaccesspermissions/request_gate.json"]
        self.assertEqual(
            ctx.convert_dt_str(ledger["nextRequestUtc"]), start + timedelta(seconds=24)
        )
        self.advance(24)
        self.assertTrue((await collection.page("admin/items"))["deferred"])
        self.assertEqual(ctx._safe_get.await_count, 1)
        # A fresh process is allowed another slice only once the durable gate permits it.
        restarted = self.context({"value": []})
        resumed = await self.collection(
            restarted, "fabricitemaccesspermissions", interval=19, single_attempt=True
        )
        self.assertEqual(await resumed.page("admin/items"), {"value": []})

    async def test_permission_restart_before_reservation_expires_does_not_wait_or_request(
        self,
    ):
        ctx = self.context({"value": []})
        collection = await self.collection(
            ctx, "fabricitemaccesspermissions", interval=19, single_attempt=True
        )
        await collection.page("admin/items")
        self.advance(23)
        restarted = self.context()
        resumed = await self.collection(
            restarted, "fabricitemaccesspermissions", interval=19, single_attempt=True
        )
        self.assertTrue((await resumed.page("admin/items"))["deferred"])
        restarted._safe_get.assert_not_awaited()
        self.sleep.assert_not_awaited()

    async def test_transport_failure_leaves_pending_marker_and_blocks_restart(self):
        for error in (TimeoutError(), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                self.files.clear()
                ctx = self.context(error)
                collection = await self.collection(ctx)
                if isinstance(error, asyncio.CancelledError):
                    with self.assertRaises(asyncio.CancelledError):
                        await collection.page("connections")
                else:
                    self.assertIn("ERROR", await collection.page("connections"))
                self.assertIs(
                    self.files["fabricconnections/request_gate.json"]["pending"], True
                )
                self.advance(86400)
                restarted = self.context()
                resumed = await self.collection(restarted)
                self.assertTrue((await resumed.page("connections"))["deferred"])
                restarted._safe_get.assert_not_awaited()
                restarted.clients["tenant"].get_headers.assert_not_called()

    async def test_reservation_storage_failure_refuses_request(self):
        ctx = self.context({"value": []})
        collection = await self.collection(ctx)
        ctx.fm.save_snapshot.side_effect = RuntimeError("Storage unavailable")
        with self.assertRaisesRegex(RuntimeError, "Storage unavailable"):
            await collection.page("connections")
        ctx._safe_get.assert_not_awaited()

    async def test_unpersisted_response_leaves_durable_pending_marker(self):
        ctx = self.context({"value": []})
        collection = await self.collection(ctx)
        save = ctx.fm.save_snapshot.side_effect
        calls = 0

        async def fail_ack(path, name, value):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("Acknowledgement write failed")
            await save(path, name, value)

        ctx.fm.save_snapshot.side_effect = fail_ack
        with self.assertRaisesRegex(RuntimeError, "Acknowledgement"):
            await collection.page("connections")
        self.assertIs(
            self.files["fabricconnections/request_gate.json"]["pending"], True
        )
        restarted = self.context()
        resumed = await self.collection(restarted)
        self.assertTrue((await resumed.page("connections"))["deferred"])
        restarted._safe_get.assert_not_awaited()

    async def test_slow_permission_reservation_fails_closed_before_http(self):
        ctx = self.context({"value": []})
        collection = await self.collection(
            ctx, "fabricitemaccesspermissions", interval=19, single_attempt=True
        )
        save = ctx.fm.save_snapshot.side_effect

        async def slow_save(path, name, value):
            await save(path, name, value)
            self.advance(6)

        ctx.fm.save_snapshot.side_effect = slow_save
        with self.assertRaisesRegex(RuntimeError, "five-second margin"):
            await collection.page("admin/items")
        ctx._safe_get.assert_not_awaited()
        self.assertIs(
            self.files["fabricitemaccesspermissions/request_gate.json"]["pending"], True
        )

    async def test_budgeted_permission_wait_exactly_preserves_35_second_reserve(self):
        ledger_path = "fabricitemaccesspermissions/request_gate.json"
        for delay, admitted in ((115, True), (115.001, False)):
            with self.subTest(delay=delay), self.gate_clock():
                self.files.clear()
                self.sleep.reset_mock()
                started, monotonic = self.now, self.elapsed
                self.files[ledger_path] = {
                    "nextRequestUtc": utc_stamp(started + timedelta(seconds=delay)),
                    "pending": False,
                    "blocked": False,
                }
                ctx = self.context({"value": []})
                collection = await self.collection(
                    ctx,
                    "fabricitemaccesspermissions",
                    interval=19,
                    single_attempt=True,
                    request_deadline=monotonic + 150 - 35,
                )
                response = await collection.page("admin/items")
                if admitted:
                    self.assertEqual(response, {"value": []})
                    self.sleep.assert_awaited_once_with(115)
                    self.assertEqual(self.elapsed - monotonic, 115)
                    self.assertEqual(
                        self.request_times[-1], started + timedelta(seconds=115)
                    )
                    self.assertEqual(
                        ctx.convert_dt_str(self.files[ledger_path]["nextRequestUtc"]),
                        self.request_times[-1] + timedelta(seconds=24),
                    )
                else:
                    self.assertTrue(response["deferred"])
                    self.sleep.assert_not_awaited()
                    ctx._safe_get.assert_not_awaited()
                    ctx.clients["tenant"].get_headers.assert_not_called()
                    self.assertEqual(self.elapsed, monotonic)

    async def test_budget_expiry_in_setup_authentication_or_wait_refuses_http(self):
        for stage in ("setup", "authentication", "wait"):
            with self.subTest(stage=stage), self.gate_clock():
                self.files.clear()
                self.sleep.reset_mock()
                self.files["fabricitemaccesspermissions/request_gate.json"] = {
                    "nextRequestUtc": utc_stamp(self.now + timedelta(seconds=2)),
                }
                ctx = self.context({"value": []})
                if stage == "setup":
                    save = ctx.fm.save_snapshot.side_effect

                    async def slow_setup(path, name, value, save=save):
                        await save(path, name, value)
                        if name == "manifest.json":
                            self.advance(116)

                    ctx.fm.save_snapshot.side_effect = slow_setup
                elif stage == "authentication":

                    def slow_auth():
                        self.advance(116)
                        return {"Authorization": "offline-placeholder"}

                    ctx.clients["tenant"].get_headers.side_effect = slow_auth
                else:
                    self.sleep.side_effect = lambda seconds: self.advance(116)
                collection = await self.collection(
                    ctx,
                    "fabricitemaccesspermissions",
                    interval=19,
                    single_attempt=True,
                    request_deadline=self.elapsed + 115,
                )
                self.assertTrue((await collection.page("admin/items"))["deferred"])
                ctx._safe_get.assert_not_awaited()
                self.assertEqual(collection.attempts, 0)
                self.assertFalse(
                    self.files["fabricitemaccesspermissions/request_gate.json"].get(
                        "pending", False
                    )
                )
                if stage == "setup":
                    ctx.clients["tenant"].get_headers.assert_not_called()
                if stage == "wait":
                    self.sleep.assert_awaited_once_with(2)
                else:
                    self.sleep.assert_not_awaited()

    async def test_budgeted_wait_rechecks_utc_and_bounds_clock_anomaly_retries(self):
        for mode, admitted, delays in (
            ("early_then_ready", True, [2, 1]),
            ("stationary", False, [2, 2, 2]),
            ("receding", False, [2, 3, 4]),
            ("advanced", True, [2]),
            ("expired_monotonic", False, [2]),
        ):
            with self.subTest(mode=mode), self.gate_clock():
                self.files.clear()
                self.sleep.reset_mock()
                gate_time = self.now + timedelta(seconds=2)
                self.files["fabricitemaccesspermissions/request_gate.json"] = {
                    "nextRequestUtc": utc_stamp(gate_time),
                }

                def wake(seconds, mode=mode):
                    self.elapsed += 116 if mode == "expired_monotonic" else seconds
                    utc_seconds = {
                        "early_then_ready": 1,
                        "stationary": 0,
                        "receding": -1,
                        "advanced": 10,
                        "expired_monotonic": 10,
                    }[mode]
                    self.now += timedelta(seconds=utc_seconds)

                self.sleep.side_effect = wake
                ctx = self.context({"value": []})
                collection = await self.collection(
                    ctx,
                    "fabricitemaccesspermissions",
                    interval=19,
                    single_attempt=True,
                    request_deadline=self.elapsed + 115,
                )
                response = await collection.page("admin/items")
                self.assertEqual(
                    [call.args[0] for call in self.sleep.await_args_list], delays
                )
                if admitted:
                    self.assertEqual(response, {"value": []})
                    ctx._safe_get.assert_awaited_once()
                    self.assertGreaterEqual(self.request_times[-1], gate_time)
                else:
                    self.assertTrue(response["deferred"])
                    ctx._safe_get.assert_not_awaited()
                    self.assertEqual(collection.attempts, 0)

    async def test_budgeted_permission_cooldown_and_fail_closed_flags_survive_restart(
        self,
    ):
        with self.gate_clock():
            ctx = self.context(
                {"ERROR": "throttled", "status": 429, "retryAfter": "3600"}
            )
            collection = await self.collection(
                ctx,
                "fabricitemaccesspermissions",
                interval=19,
                single_attempt=True,
                request_deadline=self.elapsed + 115,
            )
            self.assertTrue((await collection.page("admin/items"))["attempted"])
            ctx._safe_get.assert_awaited_once()
            ledger_path = "fabricitemaccesspermissions/request_gate.json"
            saved = dict(self.files[ledger_path])
            self.assertEqual(
                ctx.convert_dt_str(saved["nextRequestUtc"]),
                self.now + timedelta(seconds=3600),
            )
            for flag in (None, "pending", "blocked"):
                with self.subTest(flag=flag):
                    self.files[ledger_path] = {
                        **saved,
                        **(
                            {flag: True, "nextRequestUtc": utc_stamp(self.now)}
                            if flag
                            else {}
                        ),
                    }
                    restarted = self.context({"value": []})
                    resumed = await self.collection(
                        restarted,
                        "fabricitemaccesspermissions",
                        interval=19,
                        single_attempt=True,
                        request_deadline=self.elapsed + 115,
                    )
                    self.assertTrue((await resumed.page("admin/items"))["deferred"])
                    restarted.clients["tenant"].get_headers.assert_not_called()
                    restarted._safe_get.assert_not_awaited()
                    self.assertEqual(resumed.attempts, 0)
                    if flag is None:
                        self.assertEqual(self.files[ledger_path], saved)
            self.sleep.assert_not_awaited()

    async def test_slow_reservation_uses_monotonic_guard_when_utc_does_not_advance(
        self,
    ):
        for utc_change in (0, -10):
            with self.subTest(utc_change=utc_change), self.gate_clock():
                self.files.clear()
                ctx = self.context({"value": []})
                collection = await self.collection(
                    ctx,
                    "fabricitemaccesspermissions",
                    interval=19,
                    single_attempt=True,
                    request_deadline=self.elapsed + 115,
                )
                save = ctx.fm.save_snapshot.side_effect

                async def slow_save(
                    path, name, value, save=save, utc_change=utc_change
                ):
                    await save(path, name, value)
                    if name == "request_gate.json":
                        self.elapsed += 5.001
                        self.now += timedelta(seconds=utc_change)

                ctx.fm.save_snapshot.side_effect = slow_save
                with self.assertRaisesRegex(RuntimeError, "five-second margin"):
                    await collection.page("admin/items")
                ctx._safe_get.assert_not_awaited()
                self.assertEqual(collection.attempts, 0)
                self.assertIs(
                    self.files["fabricitemaccesspermissions/request_gate.json"][
                        "pending"
                    ],
                    True,
                )
                restarted = self.context({"value": []})
                resumed = await self.collection(
                    restarted,
                    "fabricitemaccesspermissions",
                    interval=19,
                    single_attempt=True,
                    request_deadline=self.elapsed + 115,
                )
                self.assertTrue((await resumed.page("admin/items"))["deferred"])
                restarted.clients["tenant"].get_headers.assert_not_called()
                restarted._safe_get.assert_not_awaited()

    async def test_malformed_ledger_refuses_authentication_and_requests(self):
        for ledger in (
            {"nextRequestUtc": "invalid"},
            {"nextRequestUtc": utc_stamp(self.now), "pending": "false"},
            {"nextRequestUtc": utc_stamp(self.now), "blocked": 0},
        ):
            with self.subTest(ledger=ledger):
                self.files["fabricconnections/request_gate.json"] = ledger
                ctx = self.context()
                with self.assertRaisesRegex(RuntimeError, "ledger is invalid"):
                    await self.collection(ctx)
                ctx.clients["tenant"].get_headers.assert_not_called()
                ctx._safe_get.assert_not_awaited()


class StrictResponseTests(CollectorTestCase):
    async def collect_http_diagnostics(self, response):
        """Exercise production HTTP, retry observation and persisted diagnostics."""
        ctx = self.context()
        ctx._safe_get = Context._safe_get.__get__(ctx)
        ctx.clients["tenant"].get_headers.return_value = {
            "Authorization": PRIVATE_MARKER + "_HEADER"
        }
        session = _FakeSession(response)
        with (
            patch("env.context.aiohttp.ClientSession", return_value=session),
            patch("env.context.aiohttp.TCPConnector"),
        ):
            diagnostics, logs = await self.collect_diagnostics(ctx)
        self.assertIs(
            self.files["fabricconnections/request_gate.json"]["pending"], False
        )
        return diagnostics, logs, session

    def diagnostic_response(self, body, status=403, headers=None):
        response = _FakeResponse(status=status, headers=headers)
        response.content = _DiagnosticReader(body)
        response.json = AsyncMock(
            side_effect=AssertionError("Unexpected JSON fallback")
        )
        response.text = AsyncMock(side_effect=AssertionError("Unbounded body read"))
        return response

    def assert_error_code(self, diagnostics, code, status=403):
        self.assertEqual(
            diagnostics,
            [{"ERROR": "Fabric request failed", "status": status, "errorCode": code}],
        )
        self.assertEqual(
            self.manifests("fabricconnections")[-1]["errors"],
            [{"error": "Fabric request failed", "status": status, "errorCode": code}],
        )
        self.assertIs(type(diagnostics[0]["errorCode"]), str)

    async def test_http_error_codes_precedence_fallback_and_resanitization(self):
        cases = [
            ({"errorCode": "ItemNotFound"}, "ItemNotFound"),
            ({"errorCode": "EntityNotFound"}, "EntityNotFound"),
            (
                {"errorCode": "RequestDeniedByInboundPolicy"},
                "RequestDeniedByInboundPolicy",
            ),
            ({"error": {"code": "InvalidItemType"}}, "InvalidItemType"),
            (
                {"errorCode": PRIVATE_MARKER, "error": {"code": "ItemNotFound"}},
                "unrecognized",
            ),
            (
                {"errorCode": "InvalidItemType", "error": {"code": PRIVATE_MARKER}},
                "InvalidItemType",
            ),
            ({"errorCode": "unrecognized"}, "unrecognized"),
            ({"errorCode": "unavailable"}, "unavailable"),
            ({}, "unavailable"),
        ]
        for value in (None, 17, True, {}, [], ""):
            cases.extend(
                [
                    ({"errorCode": value}, "unavailable"),
                    (
                        {"errorCode": value, "error": {"code": "ItemNotFound"}},
                        "ItemNotFound",
                    ),
                    ({"error": {"code": value}}, "unavailable"),
                ]
            )
        for payload, expected in cases:
            with self.subTest(payload=payload):
                self.files.clear()
                payload.update(
                    status=504,
                    message=PRIVATE_MARKER + "_MESSAGE",
                    requestId=PRIVATE_MARKER + "_ID",
                    url=ROOT + "connections?token=" + PRIVATE_MARKER,
                )
                response = self.diagnostic_response(json.dumps(payload).encode())
                diagnostics, _, session = await self.collect_http_diagnostics(response)
                self.assert_error_code(diagnostics, expected)
                self.assertEqual(len(session.calls), 1)
                self.assertEqual(response.content.requests, [16 * 1024 + 1])
                response.json.assert_not_awaited()
                response.text.assert_not_awaited()

    async def test_actual_http_200_unhashable_status_reaches_observer_and_manifest(
        self,
    ):
        for key in ("error", "ERROR"):
            for status, expected in (
                ([], None),
                ({}, None),
                (100, 100),
                (599, 599),
                (99, None),
                (600, None),
                (True, None),
                (403.0, None),
                (None, None),
                (PrivateDiagnosticValue(), None),
            ):
                with self.subTest(key=key, status=status):
                    self.files.clear()
                    response = _FakeResponse(
                        json_body={
                            key: {"code": "ItemNotFound", "message": PRIVATE_MARKER},
                            "errorCode": "InvalidItemType",
                            "status": status,
                        }
                    )
                    diagnostics, _, session = await self.collect_http_diagnostics(
                        response
                    )
                    self.assert_error_code(diagnostics, "InvalidItemType", expected)
                    self.assertEqual(len(session.calls), 1)

    async def test_fragmented_error_body_byte_boundaries_use_real_json_parser(self):
        body = b'{"error":{"code":"ItemNotFound"}}'
        for size, expected in (
            (len(body), "ItemNotFound"),
            (16 * 1024, "ItemNotFound"),
            (16 * 1024 + 1, "unavailable"),
        ):
            with self.subTest(size=size):
                self.files.clear()
                response = self.diagnostic_response(body + b" " * (size - len(body)))
                diagnostics, _, session = await self.collect_http_diagnostics(response)
                self.assert_error_code(diagnostics, expected)
                self.assertEqual(response.content.requests, [16 * 1024 + 1])
                self.assertEqual(len(session.calls), 1)
                response.json.assert_not_awaited()
                response.text.assert_not_awaited()

    async def test_unreadable_error_bodies_preserve_http_status_without_raw_diagnostics(
        self,
    ):
        for body in (
            PRIVATE_MARKER.encode(),
            b'{"errorCode":"ItemNotFound","message":"\xff"}',
            aiohttp.ClientPayloadError(PRIVATE_MARKER + "_COMPRESSED"),
            aiohttp.ClientError(PRIVATE_MARKER),
            ValueError(PRIVATE_MARKER),
            UnicodeError(PRIVATE_MARKER),
            RecursionError(PRIVATE_MARKER),
        ):
            with self.subTest(kind=type(body).__name__):
                self.files.clear()
                response = self.diagnostic_response(
                    body if isinstance(body, bytes) else b""
                )
                if isinstance(body, Exception):
                    response.content = SimpleNamespace(
                        readexactly=AsyncMock(side_effect=body)
                    )
                diagnostics, _, session = await self.collect_http_diagnostics(response)
                self.assert_error_code(diagnostics, "unavailable")
                self.assertEqual(len(session.calls), 1)
                response.json.assert_not_awaited()
                response.text.assert_not_awaited()

    async def test_actual_http_retry_keeps_status_code_and_final_retry_after_ledger(
        self,
    ):
        observed = []
        observe = FabricCollection._observe_response

        async def record_response(collection, response, attempt):
            observed.append((response.copy(), attempt))
            return await observe(collection, response, attempt)

        response = self.diagnostic_response(
            json.dumps(
                {"errorCode": "ItemNotFound", "status": [], "message": PRIVATE_MARKER}
            ).encode(),
            status=504,
            headers={"Retry-After": "25", "X-Private": PRIVATE_MARKER},
        )
        with (
            patch.dict(os.environ, {"API_MAX_RETRIES": "1"}),
            patch.object(FabricCollection, "_observe_response", record_response),
        ):
            diagnostics, _, session = await self.collect_http_diagnostics(response)
        self.assertEqual(
            observed,
            [
                (
                    {
                        "ERROR": "HTTP request failed",
                        "status": 504,
                        "retryAfter": "25",
                        "errorCode": "ItemNotFound",
                    },
                    attempt,
                )
                for attempt in (0, 1)
            ],
        )
        self.assertEqual(
            diagnostics,
            [
                {
                    "ERROR": "Fabric request deferred after throttling",
                    "status": 504,
                    "errorCode": "ItemNotFound",
                    "deferred": True,
                    "attempted": True,
                }
            ],
        )
        self.assertEqual(
            self.manifests("fabricconnections")[-1]["errors"],
            [
                {
                    "error": "Fabric request failed",
                    "status": 504,
                    "errorCode": "ItemNotFound",
                }
            ],
        )
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(response.content.requests, [16 * 1024 + 1] * 2)
        ledger = self.files["fabricconnections/request_gate.json"]
        self.assertEqual(
            Context().convert_dt_str(ledger["nextRequestUtc"]),
            self.now + timedelta(seconds=25),
        )
        self.assertIn(25.0, [call.args[0] for call in self.sleep.await_args_list])

    async def test_diagnostic_deadline_preserves_status_and_cancellation_propagates(
        self,
    ):
        real_wait_for = asyncio.wait_for
        read_started = asyncio.Event()
        read_cancelled = asyncio.Event()

        async def stalled_read(size):
            self.assertEqual(size, 16 * 1024 + 1)
            read_started.set()
            try:
                await asyncio.Future()
            finally:
                read_cancelled.set()

        async def expire_immediately(awaitable, timeout):
            self.assertEqual(timeout, 1.0)
            task = asyncio.create_task(awaitable)
            await read_started.wait()
            return await real_wait_for(task, timeout=0)

        response = self.diagnostic_response(b'{"errorCode":"ItemNotFound"}')
        response.content = SimpleNamespace(
            readexactly=AsyncMock(side_effect=stalled_read)
        )
        # Change only the diagnostic deadline, not the event loop clock or parser.
        with patch(
            "env.context.asyncio",
            SimpleNamespace(**{**vars(asyncio), "wait_for": expire_immediately}),
        ):
            diagnostics, _, session = await self.collect_http_diagnostics(response)
        self.assert_error_code(diagnostics, "unavailable")
        self.assertEqual(len(session.calls), 1)
        response.content.readexactly.assert_awaited_once_with(16 * 1024 + 1)
        self.assertTrue(read_cancelled.is_set())

        self.files.clear()
        ctx = self.context()
        ctx._safe_get = Context._safe_get.__get__(ctx)
        ctx.logger = logging.getLogger(__name__)
        response.content = SimpleNamespace(
            readexactly=AsyncMock(side_effect=asyncio.CancelledError(PRIVATE_MARKER))
        )
        session = _FakeSession(response)
        with (
            patch("env.context.aiohttp.ClientSession", return_value=session),
            patch("env.context.aiohttp.TCPConnector"),
            self.assertLogs(ctx.logger, level="INFO") as logs,
            self.assertRaises(asyncio.CancelledError),
        ):
            await FabricConnections(ctx)
        self.assertEqual(len(session.calls), 1)
        self.assertIs(
            self.files["fabricconnections/request_gate.json"]["pending"], True
        )
        self.assert_sanitized(logs.output)

    async def test_json_only_adapter_fallback_is_deliberate_and_sanitized(self):
        class UntrustedString(str):
            def __repr__(self):
                return PRIVATE_MARKER

        for value, expected in (
            ("ItemNotFound", "ItemNotFound"),
            (PrivateDiagnosticValue(), "unavailable"),
            (UntrustedString("ItemNotFound"), "unavailable"),
        ):
            with self.subTest(kind=type(value).__name__):
                self.files.clear()
                response = _FakeResponse(status=403)
                response.json = AsyncMock(
                    return_value={"error": {"code": value, "message": PRIVATE_MARKER}}
                )
                diagnostics, _, session = await self.collect_http_diagnostics(response)
                self.assert_error_code(diagnostics, expected)
                response.json.assert_awaited_once_with(content_type=None)
                self.assertEqual(len(session.calls), 1)

    async def collect_diagnostics(self, ctx):
        """Observe real returned page errors, rendered logs and final snapshots."""
        diagnostics = []
        invoke = FabricCollection.invokeAPI

        async def observe(collection, *args, **kwargs):
            result = await invoke(collection, *args, **kwargs)
            diagnostics.append(result)
            return result

        ctx.logger = logging.getLogger(__name__)
        with (
            patch.object(FabricCollection, "invokeAPI", observe),
            self.assertLogs(ctx.logger, level="INFO") as logs,
        ):
            result = await FabricConnections(ctx)
        self.assertIs(result, False)
        self.assertNotIn("records", self.resources("fabricconnections")[-1])
        self.assert_finished("fabricconnections", False)
        self.assert_sanitized(logs.output, result, diagnostics)
        return diagnostics, "\n".join(logs.output)

    async def test_malformed_pages_and_disallowed_continuations_are_incomplete(self):
        for response, field, expected, observed, error in (
            (
                [PRIVATE_MARKER],
                "$",
                "object",
                "list",
                "Fabric request failed",
            ),
            (
                {},
                "$.value",
                "list",
                "missing",
                "Missing or malformed Fabric result list",
            ),
            (
                {"value": None},
                "$.value",
                "list",
                "null",
                "Missing or malformed Fabric result list",
            ),
            (
                {"value": {PRIVATE_MARKER: PRIVATE_MARKER}},
                "$.value",
                "list",
                "object",
                "Missing or malformed Fabric result list",
            ),
            (
                {"value": [PRIVATE_MARKER]},
                "$.value[]",
                "object",
                "string",
                "Missing or malformed Fabric result list",
            ),
            (
                {"value": [1]},
                "$.value[]",
                "object",
                "number",
                "Missing or malformed Fabric result list",
            ),
            (
                {"value": [], "continuationToken": ""},
                "$.continuationToken",
                "nonempty string or null",
                "empty string",
                "Malformed continuation token",
            ),
            (
                {"value": [], "continuationToken": 123},
                "$.continuationToken",
                "nonempty string or null",
                "number",
                "Malformed continuation token",
            ),
            (
                {"value": [], "continuationToken": {PRIVATE_MARKER: PRIVATE_MARKER}},
                "$.continuationToken",
                "nonempty string or null",
                "object",
                "Malformed continuation token",
            ),
            (
                {"value": [], "continuationToken": PrivateDiagnosticValue()},
                "$.continuationToken",
                "nonempty string or null",
                "other",
                "Malformed continuation token",
            ),
            (
                {"value": [], "continuationUri": "https://invalid/" + PRIVATE_MARKER},
                "$.continuationToken",
                "nonempty string when continuationUri is present",
                "missing",
                "Continuation URI without token; collection incomplete",
            ),
        ):
            with self.subTest(field=field, observed=observed):
                self.files.clear()
                diagnostics, logs = await self.collect_diagnostics(
                    self.context(response)
                )
                self.assertEqual(diagnostics[-1]["ERROR"], error)
                self.assertIn(
                    f"field={field} expected={expected} observed={observed}", logs
                )

    async def test_error_status_accepts_only_exact_int_http_range(self):
        for status, expected in (
            (100, 100),
            (200, 200),
            (403, 403),
            (404, 404),
            (599, 599),
            (99, None),
            (600, None),
            (-1, None),
            (True, None),
            (False, None),
            ("403", None),
            (403.0, None),
            (HTTPStatus.FORBIDDEN, None),
            (None, None),
            (PRIVATE_MARKER, None),
        ):
            with self.subTest(status=status):
                self.files.clear()
                diagnostics, logs = await self.collect_diagnostics(
                    self.context({"ERROR": PRIVATE_MARKER, "status": status})
                )
                self.assertEqual(
                    diagnostics,
                    [
                        {
                            "ERROR": "Fabric request failed",
                            "status": expected,
                            "errorCode": "unavailable",
                        }
                    ],
                )
                self.assertEqual(
                    self.manifests("fabricconnections")[-1]["errors"],
                    [
                        {
                            "error": "Fabric request failed",
                            "status": expected,
                            "errorCode": "unavailable",
                        }
                    ],
                )
                if expected is None:
                    self.assertIsNone(diagnostics[0]["status"])
                    self.assertIn("HTTP status unavailable", logs)
                else:
                    self.assertIs(type(diagnostics[0]["status"]), int)
                    self.assertIn(f"HTTP {expected}", logs)

    async def test_http_200_error_payload_sanitizes_status_through_final_manifest(self):
        for key in ("error", "ERROR"):
            for status, expected in ((PRIVATE_MARKER, None), (403, 403)):
                with self.subTest(key=key, status=status):
                    self.files.clear()
                    ctx = self.context()
                    ctx._safe_get = Context._safe_get.__get__(ctx)
                    response = _FakeResponse(
                        status=200,
                        json_body={
                            key: {"message": PRIVATE_MARKER},
                            "status": status,
                        },
                    )
                    with (
                        patch(
                            "env.context.aiohttp.ClientSession",
                            return_value=_FakeSession(response),
                        ),
                        patch("env.context.aiohttp.TCPConnector"),
                    ):
                        diagnostics, logs = await self.collect_diagnostics(ctx)
                    self.assertIn("Fabric GET: HTTP 200", logs)
                    self.assertEqual(
                        diagnostics,
                        [
                            {
                                "ERROR": "Fabric request failed",
                                "status": expected,
                                "errorCode": "unavailable",
                            }
                        ],
                    )
                    self.assertEqual(
                        self.manifests("fabricconnections")[-1]["errors"],
                        [
                            {
                                "error": "Fabric request failed",
                                "status": expected,
                                "errorCode": "unavailable",
                            }
                        ],
                    )

    async def test_http_200_invalid_json_and_nonobject_body_are_sanitized(self):
        for body, expected, observed in (
            (ValueError(PRIVATE_MARKER), "JSON object", "invalid JSON or content type"),
            ([PRIVATE_MARKER], "object", "list"),
            (PrivateDiagnosticValue(), "object", "other"),
        ):
            with self.subTest(observed=observed):
                self.files.clear()
                ctx = self.context()
                ctx._safe_get = Context._safe_get.__get__(ctx)
                response = _FakeResponse(status=200, json_body=body)
                if isinstance(body, Exception):
                    response.json = AsyncMock(side_effect=body)
                with (
                    patch(
                        "env.context.aiohttp.ClientSession",
                        return_value=_FakeSession(response),
                    ),
                    patch("env.context.aiohttp.TCPConnector"),
                ):
                    diagnostics, logs = await self.collect_diagnostics(ctx)
                self.assertIn("Fabric GET: HTTP 200", logs)
                self.assertIn(f"field=$ expected={expected} observed={observed}", logs)
                # The transport's specific error is intentionally replaced at
                # the collection boundary, never persisted as response content.
                self.assertEqual(
                    diagnostics,
                    [
                        {
                            "ERROR": "Fabric request failed",
                            "status": None,
                            "errorCode": "unavailable",
                        }
                    ],
                )

    async def test_repeated_token_discards_all_partial_records(self):
        ctx = self.context(
            {"value": [], "continuationToken": "repeat"},
            {"value": [], "continuationToken": "repeat"},
        )
        self.assertFalse(await FabricConnections(ctx))
        self.assertEqual(ctx._safe_get.await_count, 2)
        self.assertNotIn("records", self.resources("fabricconnections")[0])

    async def test_unpaged_access_rejects_tokens_and_unsafe_urls_never_authenticate(
        self,
    ):
        ctx = self.context({"accessDetails": [], "continuationToken": "next"})
        collection = FabricCollection(ctx, "fabricitemaccesspermissions", "Test scope")
        await collection.start()
        self.assertIn(
            "ERROR", await collection.page("admin/items", "accessDetails", paged=False)
        )
        ctx.clients["tenant"].get_headers.reset_mock()
        ctx._safe_get.reset_mock()
        for url in (
            "http://api.fabric.microsoft.com/v1/connections",
            "https://untrusted.invalid/v1/connections",
            ROOT + "connections#fragment",
            "https://api.fabric.microsoft.com/v2/connections",
        ):
            with self.subTest(url=url):
                self.assertIn("ERROR", await collection.invokeAPI(url, {}))
        ctx._safe_get.assert_not_awaited()
        ctx.clients["tenant"].get_headers.assert_not_called()

    async def test_safe_get_uses_30_second_timeout_no_redirects_and_sanitized_errors(
        self,
    ):
        ctx = Context()
        ctx.logger = logging.getLogger(__name__)
        response = _FakeResponse(status=429, headers={"Retry-After": "40"})
        response.content = SimpleNamespace(
            readexactly=AsyncMock(
                side_effect=asyncio.IncompleteReadError(
                    partial=b"SYNTHETIC_RESPONSE_SECRET", expected=16 * 1024 + 1
                )
            )
        )
        response.text = AsyncMock(return_value="SYNTHETIC_RESPONSE_SECRET")
        request = MagicMock()
        request.__aenter__ = AsyncMock(return_value=response)
        session = MagicMock()
        session.get.return_value = request
        session_context = MagicMock()
        session_context.__aenter__ = AsyncMock(return_value=session)
        with (
            patch(
                "env.context.aiohttp.ClientSession", return_value=session_context
            ) as factory,
            self.assertLogs(ctx.logger, level="INFO") as logs,
        ):
            result = await ctx._safe_get(ROOT + "connections?token=SYNTHETIC_QUERY", {})
        self.assertEqual(factory.call_args.kwargs["timeout"].total, 30)
        session.get.assert_called_once_with(
            ROOT + "connections?token=SYNTHETIC_QUERY",
            headers={},
            allow_redirects=False,
        )
        self.assertEqual(
            result,
            {
                "ERROR": "HTTP request failed",
                "status": 429,
                "retryAfter": "40",
                "errorCode": "unavailable",
            },
        )
        response.content.readexactly.assert_awaited_once_with(16 * 1024 + 1)
        response.text.assert_not_awaited()
        self.assertIn("Fabric GET failed: HTTP 429", "\n".join(logs.output))
        self.assertNotIn("SYNTHETIC_", "\n".join(logs.output))


class StrictSnapshotTests(CollectorTestCase):
    def storage(self, backend):
        ctx = self.context()
        ctx.OutputPath = None
        ctx.StorageAccountContainerName = None
        ctx.LakehouseName = None
        ctx.PathInLakehouse = "prefix"
        ctx.StorageAccountContainerRootPath = "root"
        ctx.on_fabric = False
        fm = File_Management()
        fm.context = ctx
        client = MagicMock()
        if backend == "local":
            ctx.OutputPath = "unused-mocked-local-path"
            fm.lfm = MagicMock(save=AsyncMock(), read=AsyncMock())
        elif backend == "blob":
            ctx.StorageAccountContainerName = "offline-container"
            fm.bfm = MagicMock()
            fm.bfm._get_client.return_value = client
        else:
            ctx.LakehouseName = "OfflineLakehouse"
            fm.ftm = MagicMock()
            fm.ftm.fsc.get_file_client.return_value = client
        return fm, client

    async def test_local_snapshots_round_trip_empty_records_under_temporary_root(self):
        with tempfile.TemporaryDirectory() as root:
            ctx = Context()
            ctx.OutputPath = root
            ctx.fm.content(ctx)
            envelope = {"complete": True, "records": []}
            await ctx.fm.save_snapshot(
                "fabricconnections/run/", "connections.json", envelope
            )
            self.assertEqual(
                await ctx.fm.read_snapshot(
                    "fabricconnections/run/", "connections.json"
                ),
                envelope,
            )
            self.assertIsNone(
                await ctx.fm.read_snapshot("fabricconnections/", "missing.json")
            )
            self.assertFalse((Path(root) / "state.yaml").exists())
            bad = Path(root) / "fabricconnections" / "bad.json"
            bad.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Snapshot control read failed"):
                await ctx.fm.read_snapshot("fabricconnections/", "bad.json")

    async def test_all_backends_surface_sanitized_write_and_read_failures(self):
        for backend in ("local", "blob", "lakehouse"):
            with self.subTest(backend=backend):
                fm, client = self.storage(backend)
                error = AzureError("SYNTHETIC_SDK_SECRET")
                if backend == "local":
                    fm.lfm.save.side_effect = OSError("SYNTHETIC_LOCAL_SECRET")
                    fm.lfm.read.side_effect = OSError("SYNTHETIC_LOCAL_SECRET")
                else:
                    client.upload_blob.side_effect = error
                    client.upload_data.side_effect = error
                    client.download_blob.side_effect = error
                    client.download_file.side_effect = error
                with self.assertRaisesRegex(
                    RuntimeError, "Snapshot write failed"
                ) as raised:
                    await fm.save_snapshot(
                        "fabricconnections/", "manifest.json", {"complete": False}
                    )
                self.assertNotIn("SYNTHETIC_", str(raised.exception))
                with self.assertRaisesRegex(
                    RuntimeError, "Snapshot control read failed"
                ) as raised:
                    await fm.read_snapshot("fabricconnections/", "request_gate.json")
                self.assertNotIn("SYNTHETIC_", str(raised.exception))

    async def test_remote_snapshots_use_strict_upload_not_legacy_suppressing_writer(
        self,
    ):
        for backend in ("blob", "lakehouse"):
            with self.subTest(backend=backend):
                fm, client = self.storage(backend)
                await fm.save_snapshot(
                    "fabricconnections/run/",
                    "connections.json",
                    {"complete": True, "records": []},
                )
                upload = client.upload_blob if backend == "blob" else client.upload_data
                upload.assert_called_once_with(
                    b'{"complete": true, "records": []}', overwrite=True
                )
                if backend == "blob":
                    fm.bfm._get_client.assert_called_once_with(
                        "root/fabricconnections/run/connections.json"
                    )
                    fm.bfm.write_to_file.assert_not_called()
                else:
                    fm.ftm.fsc.get_file_client.assert_called_once_with(
                        "OfflineLakehouse.Lakehouse/Files/prefix/fabricconnections/run/connections.json"
                    )
                    fm.ftm.write_json_to_file.assert_not_called()

    async def test_on_fabric_lakehouse_uses_strict_mounted_file_io(self):
        fm, _ = self.storage("lakehouse")
        fm.context.on_fabric = True
        mounted = MagicMock(
            save=AsyncMock(), read=AsyncMock(return_value='{"pending": true}')
        )
        with patch(
            "env.utility.file_management.Local_File_Management", return_value=mounted
        ) as local:
            await fm.save_snapshot(
                "fabricconnections/", "request_gate.json", {"pending": True}
            )
            self.assertEqual(
                await fm.read_snapshot("fabricconnections/", "request_gate.json"),
                {"pending": True},
            )
            mounted.save.assert_awaited_once_with(
                "prefix/fabricconnections/", "request_gate.json", b'{"pending": true}'
            )
            self.assertEqual(local.call_args.args, ("/lakehouse/default/Files",))
            mounted.save.side_effect = OSError("SYNTHETIC_MOUNT_SECRET")
            with self.assertRaisesRegex(RuntimeError, "Snapshot write failed"):
                await fm.save_snapshot(
                    "fabricconnections/", "request_gate.json", {"pending": True}
                )
            mounted.read.side_effect = OSError("SYNTHETIC_MOUNT_SECRET")
            with self.assertRaisesRegex(RuntimeError, "Snapshot control read failed"):
                await fm.read_snapshot("fabricconnections/", "request_gate.json")

    async def test_remote_missing_controls_only_not_found_is_absence(self):
        for backend in ("blob", "lakehouse"):
            with self.subTest(backend=backend):
                fm, client = self.storage(backend)
                download = (
                    client.download_blob if backend == "blob" else client.download_file
                )
                download.side_effect = ResourceNotFoundError("Missing")
                self.assertIsNone(
                    await fm.read_snapshot("fabricconnections/", "request_gate.json")
                )
                download.side_effect = None
                for raw in (b"[]", b"{invalid", b"null"):
                    download.return_value.readall.return_value = raw
                    with self.assertRaisesRegex(
                        RuntimeError, "Snapshot control read failed"
                    ):
                        await fm.read_snapshot(
                            "fabricconnections/", "request_gate.json"
                        )

    async def test_dry_run_and_unsafe_snapshot_targets_cannot_commit(self):
        fm, _ = self.storage("local")
        with (
            patch.dict(os.environ, {"DRY_RUN": "true"}),
            self.assertRaisesRegex(RuntimeError, "Dry-run"),
        ):
            await fm.save_snapshot(
                "fabricconnections/", "manifest.json", {"complete": True}
            )
        for path, name in (
            ("../", "state.json"),
            ("/absolute/", "manifest.json"),
            ("fabricconnections/", "../state.json"),
            ("fabricconnections/", "state.yaml"),
        ):
            with self.subTest(path=path, name=name), self.assertRaises(ValueError):
                await fm.save_snapshot(path, name, {"complete": True})
        fm.lfm.save.assert_not_awaited()

    async def test_failed_resource_or_final_manifest_write_never_returns_success(self):
        for failing_name in ("connections.json", "manifest.json"):
            with self.subTest(failing_name=failing_name):
                self.files.clear()
                ctx = self.context({"value": []})
                save = ctx.fm.save_snapshot.side_effect

                async def fail(path, name, value, *, target=failing_name, persist=save):
                    if name == target and (
                        name != "manifest.json" or value["finished"]
                    ):
                        raise RuntimeError("Snapshot unavailable")
                    await persist(path, name, value)

                ctx.fm.save_snapshot.side_effect = fail
                with self.assertRaisesRegex(RuntimeError, "Snapshot unavailable"):
                    await FabricConnections(ctx)
                manifest = self.manifests("fabricconnections")[0]
                self.assertIs(manifest["finished"], False)
                self.assertIs(manifest["complete"], False)

    async def test_clock_rollback_cannot_commit_a_successful_collection(self):
        ctx = self.context({"value": []})
        save = ctx.fm.save_snapshot.side_effect

        async def rollback_after_resource(path, name, value):
            await save(path, name, value)
            if name == "connections.json":
                self.advance(-2)

        ctx.fm.save_snapshot.side_effect = rollback_after_resource
        with self.assertRaisesRegex(RuntimeError, "Manifest UTC precedes"):
            await FabricConnections(ctx)
        manifest = self.manifests("fabricconnections")[0]
        self.assertIs(manifest["finished"], False)
        self.assertIs(manifest["complete"], False)
        self.assertTrue(self.resources("fabricconnections")[0]["complete"])
        self.assertEqual(ctx._safe_get.await_count, 1)

    async def test_final_manifest_checks_all_saved_resources_even_for_failed_runs(self):
        for complete in (True, False):
            with self.subTest(complete=complete):
                self.files.clear()
                collection = FabricCollection(
                    self.context(), "fabricitemjobhistory", "offline"
                )
                await collection.start()
                await collection.snapshot(
                    "first", "offline", {}, [] if complete else None
                )
                self.advance(-3)
                await collection.snapshot("second", "offline", {}, [])
                self.advance(1)
                with self.assertRaisesRegex(RuntimeError, "Manifest UTC precedes"):
                    await collection.finish(complete)
                manifest = self.manifests("fabricitemjobhistory")[0]
                self.assertIs(manifest["finished"], False)
                self.assertIs(manifest["complete"], False)

    async def test_final_manifest_accepts_equal_or_later_saved_resource_time(self):
        for seconds in (0, 1):
            with self.subTest(seconds=seconds):
                self.files.clear()
                collection = FabricCollection(
                    self.context(), "fabricitemjobhistory", "offline"
                )
                await collection.start()
                await collection.snapshot("first", "offline", {}, [])
                self.advance(2)
                await collection.snapshot("second", "offline", {}, [])
                self.advance(seconds)
                self.assertTrue(await collection.finish(True))
                manifest = self.manifests("fabricitemjobhistory")[0]
                self.assertTrue(manifest["finished"])
                self.assertTrue(manifest["complete"])
                self.assertTrue(
                    all(
                        resource["observedAt"] <= manifest["observedAt"]
                        for resource in self.resources("fabricitemjobhistory")
                    )
                )
