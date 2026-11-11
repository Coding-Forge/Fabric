"""Helpers for throttle-aware HTTP retries (``Retry-After`` and exponential backoff)."""

import asyncio
import os
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import monotonic
from urllib.parse import urlsplit

# Statuses that are transient and safe to retry
RETRYABLE_STATUSES = frozenset({429, 503, 504})

DEFAULT_MAX_RETRIES = 3
DEFAULT_MAX_CONCURRENCY = 16
BASE_BACKOFF_SECONDS = 2.0
MAX_DELAY_SECONDS = 120.0  # default; override with API_MAX_RETRY_DELAY
RequestHeaders = dict[str, str] | Callable[..., dict[str, str]]


def _env_int(name: str, default: int, minimum: int) -> int:
    """Read an integer environment variable.

    :param name: Environment variable name.
    :param default: Value used when the variable is unset or not an integer.
    :param minimum: Lower bound applied to the result.
    :return: The parsed value, never below ``minimum``.
    """
    try:
        return max(minimum, int(os.environ.get(name, default)))
    except ValueError:
        return default


def max_retries() -> int:
    """Return the retry count (``API_MAX_RETRIES``, default 3, ``0`` disables retries)."""
    return _env_int("API_MAX_RETRIES", DEFAULT_MAX_RETRIES, 0)


def max_concurrency() -> int:
    """Return the cap on concurrent requests (``API_MAX_CONCURRENCY``, default 16)."""
    return _env_int("API_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY, 1)


def max_delay_seconds() -> float:
    """Return the fallback backoff cap; server Retry-After is never shortened."""
    return float(_env_int("API_MAX_RETRY_DELAY", int(MAX_DELAY_SECONDS), 0))


def parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header value.

    :param value: Header value, either delay seconds or an HTTP date.
    :return: Seconds to wait, or ``None`` when absent or unparseable.
    """
    if not value:
        return None
    text = str(value).strip()
    if text.isascii() and text.isdigit():
        return float(text)
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)  # noqa: UP017
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())  # noqa: UP017


def retry_delay(attempt: int, retry_after: str | None = None) -> float:
    """Compute how long to wait before retrying.

    :param attempt: Zero-based index of the attempt that just failed.
    :param retry_after: Raw ``Retry-After`` header value, if any; it takes precedence.
    :return: Full server delay, or capped exponential fallback when unavailable.
    """
    delay = parse_retry_after(retry_after)
    if delay is not None:
        return delay
    return min(BASE_BACKOFF_SECONDS * (2**attempt), max_delay_seconds())


async def resolve_headers(
    headers: RequestHeaders | None, *, force_refresh: bool = False
) -> dict[str, str] | None:
    """Resolve a synchronous token provider off-loop, immediately before dispatch."""
    if callable(headers):
        if force_refresh:
            return await asyncio.to_thread(headers, force_refresh=True)
        return await asyncio.to_thread(headers)
    return headers


class RetryCooldowns:
    """In-process server cooldowns shared by legacy requests to one API origin."""

    def __init__(self):
        self._deadlines = {}

    @staticmethod
    def _origin(url):
        parsed = urlsplit(url)
        return parsed.scheme.lower(), parsed.netloc.lower()

    def reserve(self, url, seconds):
        origin = self._origin(url)
        self._deadlines[origin] = max(
            self._deadlines.get(origin, 0), monotonic() + seconds
        )

    def remaining(self, url):
        return max(0.0, self._deadlines.get(self._origin(url), 0) - monotonic())

    async def wait(self, url):
        while (delay := self.remaining(url)) > 0:
            await asyncio.sleep(delay)
