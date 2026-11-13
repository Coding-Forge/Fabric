import asyncio
import json as jsonlib
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import aiohttp
import requests

DEFAULT_MAX_RETRIES = 6
BACKOFF_BASE_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 60.0
# Power BI admin throttling can ask for a long pause, so Retry-After is honored up to an hour.
MAX_RETRY_AFTER_SECONDS = 3600.0

_logger = logging.getLogger(__name__)


def is_retryable(status: int) -> bool:
    """429, 5xx and transport failures (status 0) are retried; other 4xx are not."""
    return status == 0 or status == 429 or 500 <= status < 600


def url_path(url: str) -> str:
    """Path only, so query strings (continuation tokens) never reach the logs."""
    return urlsplit(url).path or "/"


def parse_retry_after(value) -> float | None:
    if value is None:
        return None
    value = str(value).strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


def retry_wait(attempt: int, retry_after=None) -> float:
    """Seconds to wait after failed attempt number `attempt` (1-based)."""
    hinted = parse_retry_after(retry_after)
    if hinted is not None:
        return min(max(hinted, 1.0), MAX_RETRY_AFTER_SECONDS)
    backoff = min(MAX_BACKOFF_SECONDS, BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))
    return backoff + random.uniform(0, 1)


def _log_retry(
    logger, status: int, attempt: int, max_retries: int, wait: float, url: str
) -> None:
    logger.warning(
        "HTTP retry: status=%s attempt=%d/%d wait=%.1fs path=%s",
        status if status else "network-error",
        attempt,
        max_retries + 1,
        wait,
        url_path(url),
    )


@dataclass(frozen=True)
class HttpResponse:
    status: int
    text: str = ""
    retry_after: str | None = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self):
        return jsonlib.loads(self.text) if self.text.strip() else {}

    def error(self) -> dict:
        """Error dict keeping the legacy "ERROR" key, with the real status code added."""
        return {
            "ERROR": f"HTTP {self.status}" if self.status else "Network error",
            "status_code": self.status,
            "message": self.text[:500],
        }


async def aio_request(
    method: str,
    url: str,
    *,
    headers=None,
    json_body=None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    logger=None,
    timeout=None,
    connector_kwargs=None,
    sleep=None,
) -> HttpResponse:
    """aiohttp request that retries 429/5xx/network errors with Retry-After or exponential backoff."""
    logger = logger or _logger
    sleep = sleep or asyncio.sleep
    attempt = 0
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(**(connector_kwargs or {})), timeout=timeout
    ) as session:
        while True:
            attempt += 1
            try:
                async with session.request(
                    method, url, headers=headers, json=json_body
                ) as response:
                    result = HttpResponse(
                        status=response.status,
                        text=await response.text(errors="replace"),
                        retry_after=response.headers.get("Retry-After"),
                    )
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                result = HttpResponse(status=0, text=f"{type(exc).__name__}: {exc}")

            if result.ok or not is_retryable(result.status) or attempt > max_retries:
                return result

            wait = retry_wait(attempt, result.retry_after)
            _log_retry(logger, result.status, attempt, max_retries, wait, url)
            await sleep(wait)


async def async_request_with_retry(
    method: str,
    url: str,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    logger=None,
    **request_kwargs,
):
    """Run the synchronous retry helper in a worker thread from async code."""
    return await asyncio.to_thread(
        request_with_retry,
        method,
        url,
        max_retries=max_retries,
        logger=logger,
        **request_kwargs,
    )


def request_with_retry(
    method: str,
    url: str,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    logger=None,
    sleep=None,
    **request_kwargs,
):
    """
    requests call with the same retry policy. Blocking: call it from asyncio.to_thread, never
    directly from async code. Returns the last response; re-raises the last network error.
    """
    logger = logger or _logger
    sleep = sleep or time.sleep
    attempt = 0
    while True:
        attempt += 1
        try:
            response = requests.request(method, url, **request_kwargs)
        except requests.RequestException:
            if attempt > max_retries:
                raise
            status, retry_after = 0, None
        else:
            if not is_retryable(response.status_code) or attempt > max_retries:
                return response
            status, retry_after = (
                response.status_code,
                response.headers.get("Retry-After"),
            )

        wait = retry_wait(attempt, retry_after)
        _log_retry(logger, status, attempt, max_retries, wait, url)
        sleep(wait)
