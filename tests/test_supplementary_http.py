import asyncio
import logging
from unittest import mock

import pytest
import requests

from env.config import build_audit
from env.context import Context
from env.modules import catalog, itemjobs
from env.utility import http
from env.utility.http import parse_retry_after, request_with_retry, retry_wait
from tests.test_workspace_filter import FakeContext, WORKSPACE_ID


def test_retry_after_is_honored_and_backoff_is_capped():
    assert parse_retry_after("7") == 7
    assert parse_retry_after("garbage") is None
    assert retry_wait(1, "12") == 12
    assert retry_wait(1, "0") == 1
    assert retry_wait(10) <= http.MAX_BACKOFF_SECONDS + 1
    assert retry_wait(2) >= 4


class FakeResponse:
    def __init__(self, status, headers=None, text=""):
        self.status_code = status
        self.headers = headers or {}
        self.text = text


def test_sync_helper_retries_429_with_retry_after_and_logs(caplog):
    caplog.set_level(logging.WARNING)
    responses = [FakeResponse(429, {"Retry-After": "3"}), FakeResponse(200)]
    sleeps = []
    with mock.patch("requests.request", side_effect=responses):
        r = request_with_retry(
            "GET", "https://x.test/v1/items?secret=abc", max_retries=3, sleep=sleeps.append
        )
    assert r.status_code == 200
    assert sleeps == [3]
    assert "status=429 attempt=1/4 wait=3.0s path=/v1/items" in caplog.text
    assert "secret" not in caplog.text


def test_async_sync_helper_retries_without_blocking_callers():
    responses = [FakeResponse(429, {"Retry-After": "4"}), FakeResponse(200)]
    waits = []

    async def run():
        with mock.patch("requests.request", side_effect=responses):
            return await http.async_request_with_retry(
                "GET",
                "https://x.test/v1/items",
                max_retries=2,
                sleep=waits.append,
            )

    response = asyncio.run(run())
    assert response.status_code == 200
    assert waits == [4]


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_sync_helper_does_not_retry_client_errors(status):
    sleeps = []
    with mock.patch("requests.request", return_value=FakeResponse(status)) as req:
        r = request_with_retry("GET", "https://x.test/a", max_retries=3, sleep=sleeps.append)
    assert r.status_code == status
    assert req.call_count == 1 and sleeps == []


def test_sync_helper_gives_up_after_max_retries_and_retries_network_errors():
    with mock.patch("requests.request", return_value=FakeResponse(503)) as req:
        r = request_with_retry("GET", "https://x.test/a", max_retries=2, sleep=lambda _: None)
    assert r.status_code == 503 and req.call_count == 3

    with mock.patch("requests.request", side_effect=requests.ConnectionError("boom")) as req:
        with pytest.raises(requests.ConnectionError):
            request_with_retry("GET", "https://x.test/a", max_retries=1, sleep=lambda _: None)
    assert req.call_count == 2


def test_settings_defaults_and_wiring():
    context = Context()
    assert (context.http_max_retries, context.scan_status_poll_seconds, context.itemjobs_concurrency) == (6, 15, 3)

    audit = build_audit({
        "TENANT_ID": "t", "CLIENT_ID": "c", "CLIENT_SECRET": "s",
        "HTTP_MAX_RETRIES": "2", "SCAN_STATUS_POLL_SECONDS": "5", "ITEMJOBS_CONCURRENCY": "1",
    })
    assert (audit.context.http_max_retries, audit.context.scan_status_poll_seconds,
            audit.context.itemjobs_concurrency) == (2, 5, 1)
    with pytest.raises(ValueError):
        context.set_itemjobs_concurrency(0)


class ScanContext(FakeContext):
    def __init__(self, statuses):
        super().__init__(include_ids={WORKSPACE_ID})
        self.statuses = list(statuses)

    async def invokeAPI(self, rest_api, headers=None, json=None):
        self.api_calls.append((rest_api, json))
        if "getInfo" in rest_api:
            return {"id": "scan-id", "status": "Running"}
        if "scanStatus" in rest_api:
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            if status == "ERROR":
                return {"ERROR": "HTTP 404", "status_code": 404, "message": ""}
            return {"status": status}
        return {"workspaces": [{"id": WORKSPACE_ID}]}


def _run_catalog(monkeypatch, context):
    waits = []

    async def fake_sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    asyncio.run(catalog.main(context))
    return waits


def test_catalog_polls_at_configured_interval_without_long_sleep(monkeypatch):
    context = ScanContext(["Running", "Succeeded"])
    context.scan_status_poll_seconds = 7
    waits = _run_catalog(monkeypatch, context)

    assert waits.count(7) == 2
    assert 3700 not in waits
    assert any(path.startswith("catalog/scans/") for path, _, _ in context.fm.saved)


def test_catalog_logs_failed_scan_and_saves_nothing(monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger="test.workspace_filter")
    context = ScanContext(["Failed"])
    _run_catalog(monkeypatch, context)

    assert "Scan scan-id ended with status Failed" in caplog.text
    assert not any(path.startswith("catalog/scans/") for path, _, _ in context.fm.saved)


def test_catalog_stops_when_scan_status_errors(monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger="test.workspace_filter")
    context = ScanContext(["ERROR"])
    waits = _run_catalog(monkeypatch, context)

    assert "Scan status error for scan-id" in caplog.text
    assert len([url for url, _ in context.api_calls if "scanStatus" in url]) == catalog.MAX_SCAN_STATUS_ERRORS
    assert 3700 not in waits
    assert not any(path.startswith("catalog/scans/") for path, _, _ in context.fm.saved)


def test_itemjobs_semaphore_uses_setting(monkeypatch):
    sizes = []
    real = asyncio.Semaphore

    def spy(value):
        sizes.append(value)
        return real(value)

    monkeypatch.setattr(asyncio, "Semaphore", spy)
    context = FakeContext(include_ids={WORKSPACE_ID})
    context.itemjobs_concurrency = 2
    with mock.patch("requests.request", return_value=FakeResponse(404)):
        asyncio.run(itemjobs.main(context))
    assert sizes == [2]
