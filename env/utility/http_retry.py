"""Helpers for throttle-aware HTTP retries (``Retry-After`` and exponential backoff)."""

import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# Statuses that are transient and safe to retry
RETRYABLE_STATUSES = frozenset({429, 503, 504})

DEFAULT_MAX_RETRIES = 3
DEFAULT_MAX_CONCURRENCY = 16
BASE_BACKOFF_SECONDS = 2.0
MAX_DELAY_SECONDS = 120.0  # default; override with API_MAX_RETRY_DELAY


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
    """Return the retry delay cap in seconds (``API_MAX_RETRY_DELAY``, default 120)."""
    return float(_env_int("API_MAX_RETRY_DELAY", int(MAX_DELAY_SECONDS), 0))


def parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header value.

    :param value: Header value, either delay seconds or an HTTP date.
    :return: Seconds to wait, or ``None`` when absent or unparseable.
    """
    if not value:
        return None
    text = str(value).strip()
    if text.isdigit():
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
    :return: Seconds to sleep, capped at ``max_delay_seconds()``.
    """
    delay = parse_retry_after(retry_after)
    if delay is None:
        delay = BASE_BACKOFF_SECONDS * (2**attempt)
    return min(delay, max_delay_seconds())
