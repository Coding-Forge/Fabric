"""Microsoft Graph extraction (users, licenses, SKUs, groups and group members).

Settings (environment variables):

* ``GRAPH_EXTRACT_GROUPS`` - truthy enables groups.json and groupmembers.json (read by ``Context``).
* ``GRAPH_AUDIENCE_GROUP_PREFIXES`` - comma separated, case-insensitive display name prefixes that
  mark a group as a Power BI audience group (default ``PowerBI,Power BI``).
* ``GRAPH_MAX_GROUPS_FOR_MEMBERS`` - maximum number of groups whose members are fetched (default 200).

Required Graph permissions: User.Read.All, Group.Read.All, GroupMember.Read.All.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from env.context import utc_now

DEFAULT_AUDIENCE_PREFIXES = "PowerBI,Power BI"
DEFAULT_MAX_GROUPS_FOR_MEMBERS = 200
MEMBER_CONCURRENCY = 4
PAGE_SIZE = 999
USER_SELECT = (
    "id,displayName,userPrincipalName,mail,accountEnabled,userType,assignedLicenses"
)
SKU_SELECT = "id,skuId,skuPartNumber,capabilityStatus,consumedUnits,prepaidUnits"
GROUP_SELECT = "id,displayName,mail,mailEnabled,securityEnabled,groupTypes"
MEMBER_SELECT = "id,displayName,userPrincipalName,mail,accountEnabled,userType"


def audience_prefixes() -> list[str]:
    """Return the lower-cased audience group name prefixes from ``GRAPH_AUDIENCE_GROUP_PREFIXES``."""
    raw = os.environ.get("GRAPH_AUDIENCE_GROUP_PREFIXES", DEFAULT_AUDIENCE_PREFIXES)
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def max_groups_for_members() -> int:
    """Return the group cap from ``GRAPH_MAX_GROUPS_FOR_MEMBERS`` (default 200, minimum 0)."""
    try:
        return max(
            0,
            int(
                os.environ.get(
                    "GRAPH_MAX_GROUPS_FOR_MEMBERS", DEFAULT_MAX_GROUPS_FOR_MEMBERS
                )
            ),
        )
    except ValueError:
        return DEFAULT_MAX_GROUPS_FOR_MEMBERS


def is_audience_group(display_name: str | None, prefixes: list[str]) -> bool:
    """Return True when ``display_name`` starts with one of the (lower-cased) prefixes."""
    return bool(display_name) and any(
        display_name.lower().startswith(p) for p in prefixes
    )


def _failed(result: Any) -> bool:
    """Return True for empty responses and error dictionaries."""
    return not result or "ERROR" in result


async def fetch_all(
    context, url: str, headers: dict[str, str]
) -> tuple[list[Any] | None, Any]:
    """Fetch every page of a Graph collection by following ``@odata.nextLink``.

    :param context: Application context providing ``invokeAPI``.
    :param url: First page URL.
    :param headers: Request headers.
    :return: ``(items, None)`` on success, or ``(None, failed_response)`` if any page fails.
    """
    items: list[Any] = []
    next_url: str | None = url
    while next_url:
        try:
            result = await context.invokeAPI(rest_api=next_url, headers=headers)
        except Exception as exc:  # noqa: BLE001 - one failed call must not abort others
            context.logger.error(f"Graph request failed: {type(exc).__name__}: {exc}")
            return None, {"ERROR": f"{type(exc).__name__}: {exc}"}
        if _failed(result):
            return None, result
        items.extend(result.get("value") or [])
        next_url = result.get("@odata.nextLink")
    return items, None


def build_user_licenses(users: list[Any]) -> list[dict[str, Any]]:
    """Flatten ``assignedLicenses`` into one row per user per license."""
    rows = []
    for user in users:
        if not isinstance(user, dict):
            continue
        for lic in user.get("assignedLicenses") or []:
            rows.append(
                {
                    "userId": user.get("id"),
                    "userPrincipalName": user.get("userPrincipalName"),
                    "skuId": lic.get("skuId"),
                    "disabledPlans": lic.get("disabledPlans") or [],
                }
            )
    return rows


async def _group_members(
    context,
    graph_url: str,
    headers: dict[str, str],
    group: dict[str, Any],
    semaphore: asyncio.Semaphore,
) -> tuple[dict[str, Any], list[Any] | None]:
    """Fetch the user members of one group; the member list is None when the call failed."""
    url = f"{graph_url}/groups/{group['id']}/members/microsoft.graph.user?$select={MEMBER_SELECT}&$top={PAGE_SIZE}"
    async with semaphore:
        members, error = await fetch_all(context, url, headers)
    if members is None:
        context.logger.warning(f"Graph members for group {group['id']} failed: {error}")
    return group, members


def _member_rows(group: dict[str, Any], members: list[Any]) -> list[dict[str, Any]]:
    """Build flat groupmembers.json rows for a group."""
    return [
        {
            "groupId": group["id"],
            "groupDisplayName": group.get("displayName"),
            "isPowerBIAudienceGroup": group.get("isPowerBIAudienceGroup", False),
            "memberId": m.get("id"),
            "displayName": m.get("displayName"),
            "userPrincipalName": m.get("userPrincipalName"),
            "mail": m.get("mail"),
            "accountEnabled": m.get("accountEnabled"),
            "userType": m.get("userType"),
        }
        for m in members
        if isinstance(m, dict)
    ]


async def main(context=None):
    """
    Graph

    Saves users.json, userlicenses.json, subscribedskus.json and, when
    ``context.GraphExtractGroups`` is set, groups.json and groupmembers.json.

    :return: False if a required call or any group member call failed, otherwise True.
    """
    if context is None:
        raise RuntimeError("Context is None")

    headers = context.clients["graph"].get_headers()
    headers["Content-Type"] = "application/json"

    today = utc_now()
    lakehouse_catalog = (
        f"graph/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"
    )
    extract_groups = bool(context.GraphExtractGroups)
    graph_url = context.clients["graph"].get_api_root()

    graph_calls = [
        (
            "users",
            f"{graph_url}/users?$select={USER_SELECT}&$top={PAGE_SIZE}",
            "users.json",
        ),
        (
            "subscribedSkus",
            f"{graph_url}/subscribedSkus?$select={SKU_SELECT}",
            "subscribedskus.json",
        ),
    ]
    if extract_groups:
        graph_calls.append(
            (
                "groups",
                f"{graph_url}/groups?$filter=securityEnabled eq true&$select={GROUP_SELECT}&$top={PAGE_SIZE}",
                "groups.json",
            )
        )

    failures = 0
    results: dict[str, list[Any]] = {}
    for key, url, file_name in graph_calls:
        info, error = await fetch_all(context, url, headers)
        if info is None:
            failures += 1
            context.logger.error(f"Graph call {key} failed: {error}")
            continue

        if key == "groups":
            prefixes = audience_prefixes()
            info = [
                {
                    **g,
                    "isPowerBIAudienceGroup": is_audience_group(
                        g.get("displayName"), prefixes
                    ),
                }
                if isinstance(g, dict)
                else g
                for g in info
            ]
        results[key] = info
        await context.fm.save(path=lakehouse_catalog, file_name=file_name, content=info)

    if "users" in results:
        await context.fm.save(
            path=lakehouse_catalog,
            file_name="userlicenses.json",
            content=build_user_licenses(results["users"]),
        )

    if "groups" in results:
        groups = [g for g in results["groups"] if isinstance(g, dict) and g.get("id")]
        limit = max_groups_for_members()
        if len(groups) > limit:
            context.logger.warning(
                f"{len(groups)} groups found; fetching members for {limit} "
                "audience-first (GRAPH_MAX_GROUPS_FOR_MEMBERS); result is partial"
            )
            # Stable sort: audience groups first, original order otherwise
            groups = sorted(
                groups, key=lambda g: not g.get("isPowerBIAudienceGroup", False)
            )[:limit]

        semaphore = asyncio.Semaphore(MEMBER_CONCURRENCY)
        fetched = await asyncio.gather(
            *(_group_members(context, graph_url, headers, g, semaphore) for g in groups)
        )
        rows: list[dict[str, Any]] = []
        for group, members in fetched:
            if members is None:
                failures += 1
                continue
            rows.extend(_member_rows(group, members))
        await context.fm.save(
            path=lakehouse_catalog, file_name="groupmembers.json", content=rows
        )

    return failures == 0


if __name__ == "__main__":
    asyncio.run(main())
