"""Shared helper for admin REST endpoints that page with ``continuationToken``."""

from typing import Any
from urllib.parse import quote

# Statuses returned by preview/admin endpoints that are not available to the caller
_UNAVAILABLE_STATUSES = (403, 404)


async def fetch_all_pages(
    context: Any,
    url: str,
    headers: dict[str, str],
    list_key: str,
    label: str,
) -> list[Any] | None:
    """Fetch every page of a ``continuationToken`` paged endpoint.

    The first request uses ``url`` unchanged; later requests append the
    URL-quoted ``continuationToken`` returned by the previous page.

    :param context: Runtime context providing ``invokeAPI`` and ``logger``.
    :param url: Endpoint URL without a ``continuationToken`` parameter.
    :param headers: Request headers.
    :param list_key: Response property holding the page's items.
    :param label: Human-readable name used in log messages.
    :return: All items from all pages, or ``None`` if any request failed. HTTP
        403/404 (preview API unavailable or no permission) is logged as a
        warning rather than an error; no exception is raised for either.
    """
    items: list[Any] = []
    seen_tokens = set()
    request_url = url
    separator = "&" if "?" in url else "?"

    while True:
        response = await context.invokeAPI(request_url, headers=headers)

        if not isinstance(response, dict) or not response or "ERROR" in response:
            status = response.get("status") if isinstance(response, dict) else None
            if status in _UNAVAILABLE_STATUSES:
                context.logger.warning(
                    f"{label} unavailable (HTTP {status}); the API may be in preview "
                    f"or the caller lacks permission: {response}"
                )
            else:
                context.logger.error(f"{label} request failed: {response}")
            return None

        items.extend(response.get(list_key) or [])

        token = response.get("continuationToken")
        if not token:
            return items
        if token in seen_tokens:
            context.logger.error(
                f"{label} returned a repeated continuationToken; stopping"
            )
            return None
        seen_tokens.add(token)
        request_url = f"{url}{separator}continuationToken={quote(token, safe='')}"
