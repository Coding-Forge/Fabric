"""Collect scoped Fabric permissions in bounded, durable request slices."""

import asyncio
from dataclasses import dataclass, field
from typing import cast
from urllib.parse import quote
from uuid import UUID

from env.context import Context
from env.utility.fabric_collection import (
    FabricCollection,
    JsonObject,
    JsonValue,
    identified_records,
    item_scope,
)


@dataclass
class _Progress:
    task: int = 0
    token: str | None = None
    tokens: list[str] = field(default_factory=list)
    discovered: list[str] = field(default_factory=list)
    inventory_complete: bool = False
    healthy: bool = True
    evidence: list[str] = field(default_factory=list)

    def encode(self, scope: list[dict[str, str]]) -> JsonObject:
        return {
            "scope": cast(list[JsonValue], scope),
            "task": self.task,
            "token": self.token,
            "tokens": list(self.tokens),
            "discovered": list(self.discovered),
            "inventoryComplete": self.inventory_complete,
            "healthy": self.healthy,
            "evidence": list(self.evidence),
        }


def _load_progress(
    saved: JsonObject | None,
    scope: list[dict[str, str]],
    tasks: list[tuple[str, dict[str, str]]],
) -> _Progress:
    if saved is None:
        return _Progress()
    if saved.get("scope") != scope:
        raise ValueError(
            "Permission scope changed; archive progress.json before "
            "explicitly starting a new scope"
        )
    task = saved.get("task")
    token = saved.get("token")
    if (
        type(task) is not int
        or not 0 <= task < len(tasks)
        or "token" not in saved
        or (token is not None and (not isinstance(token, str) or not token))
        or not isinstance(saved.get("inventoryComplete"), bool)
        or not isinstance(saved.get("healthy"), bool)
    ):
        raise RuntimeError("Invalid permission progress; requests blocked")
    lists: dict[str, list[str]] = {}
    for key in ("tokens", "discovered", "evidence"):
        value = saved.get(key)
        if not isinstance(value, list) or any(
            not isinstance(entry, str) or not entry for entry in value
        ):
            raise RuntimeError("Invalid permission progress list; requests blocked")
        lists[key] = cast(list[str], value)
    kind, item = tasks[task]
    if (
        len(lists["tokens"]) != len(set(lists["tokens"]))
        or (token is not None and lists["tokens"][-1:] != [token])
        or (token is None and lists["tokens"])
        or (kind == "access" and token is not None)
        or (kind == "inventory" and saved["inventoryComplete"])
        or len(lists["discovered"]) != len(set(lists["discovered"]))
        or not set(lists["discovered"]).issubset(
            target["itemId"]
            for target in scope
            if target["workspaceId"] == item["workspaceId"]
        )
        or len(lists["evidence"]) > 1
    ):
        raise RuntimeError("Inconsistent permission progress; requests blocked")
    return _Progress(
        task=task,
        token=token,
        tokens=lists["tokens"],
        discovered=lists["discovered"],
        inventory_complete=cast(bool, saved["inventoryComplete"]),
        healthy=cast(bool, saved["healthy"]),
        evidence=lists["evidence"],
    )


def _inventory_selection(
    response: JsonObject, workspace: str, scope: list[dict[str, str]]
) -> list[JsonObject] | None:
    records = identified_records(
        cast(list[JsonObject] | None, response.get("itemEntities")),
        ("id", "workspaceId", "type"),
    )
    if records is None:
        return None
    selected: list[JsonObject] = []
    configured = {
        (item["itemId"], item["type"])
        for item in scope
        if item["workspaceId"] == workspace
    }
    for record in records:
        try:
            item_id = str(UUID(record["id"]))
            returned_workspace = str(UUID(record["workspaceId"]))
        except (ValueError, TypeError, AttributeError):
            return None
        if returned_workspace != workspace:
            return None
        if (
            any(identity[0] == item_id for identity in configured)
            and (item_id, record["type"]) not in configured
        ):
            return None
        if (item_id, record["type"]) in configured:
            selected.append(
                {"workspaceId": workspace, "itemId": item_id, "type": record["type"]}
            )
    return selected


def _valid_access(records: list[JsonObject], item_type: str) -> bool:
    for record in records:
        principal = record.get("principal")
        details = record.get("itemAccessDetails")
        if (
            not isinstance(principal, dict)
            or not isinstance(principal.get("id"), str)
            or not principal["id"]
            or not isinstance(principal.get("type"), str)
            or not isinstance(details, dict)
            or details.get("type") != item_type
            or not isinstance(details.get("permissions"), list)
            or any(not isinstance(value, str) for value in details["permissions"])
            or (
                "additionalPermissions" in details
                and (
                    not isinstance(details["additionalPermissions"], list)
                    or any(
                        not isinstance(value, str)
                        for value in details["additionalPermissions"]
                    )
                )
            )
        ):
            return False
    return True


async def main(context: Context | None = None) -> bool:
    """Resume bounded slices of scoped inventory and access observations.

    ``FABRIC_ITEM_ACCESS_SCOPE`` requires 1–50 workspaceId/itemId/type objects.
    A cycle visits every workspace inventory (with durable continuation tokens)
    and its selected items in configured order. Each invocation admits at most
    six single-attempt slices within 150 seconds, reserving 35 seconds before
    starting another slice. Each HTTP request times out after 30 seconds.
    Each slice rechecks the durable UTC gate after waiting, admitting a wait
    only if the invocation still has its 35-second reserve. Cooldowns that
    exceed that budget defer to a later run. The 19-second spacing plus
    five-second reservation margin, server cooldowns, and invalid-header
    blocks survive restarts in request_gate.json.

    progress.json preserves the cycle cursor, selected identities and manifest
    references as a linked evidence chain. Intermediate manifests remain
    incomplete. Only a wholly successful cycle advances lastRun; denied or
    malformed resources are recorded and revisited next cycle, without starving
    later targets.
    Scope changes require explicitly archiving progress.json; an unfinished
    prior scope must not be mistaken for a completed cycle.
    Invalid headers and unacknowledged attempts (including transport timeouts)
    block further requests until an operator investigates the ledger.
    One scheduler per output root is required; external quota use is untracked.

    :param context: Runtime with Fabric tenant authentication and strict storage.
    :return: True only on the final slice of an entirely successful scope cycle.
    :raises RuntimeError: If context, storage, or persisted controls are unusable.
    :raises ValueError: If the configured scope is invalid or differs from progress.
    :raises TypeError: If a scope entry is not an object.
    """
    if context is None:
        raise RuntimeError("Context is None")
    scope = item_scope("FABRIC_ITEM_ACCESS_SCOPE", 50)
    tasks: list[tuple[str, dict[str, str]]] = []
    for workspace in dict.fromkeys(item["workspaceId"] for item in scope):
        tasks.append(("inventory", {"workspaceId": workspace}))
        tasks.extend(
            ("access", item) for item in scope if item["workspaceId"] == workspace
        )
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 150
    for _ in range(6):
        if loop.time() + 35 > deadline:
            break
        complete, more = await _collect_slice(context, scope, tasks, deadline - 35)
        if complete or not more:
            return complete
    context.logger.warning(
        "Permission invocation budget exhausted; persisted cycle remains incomplete"
    )
    return False


async def _collect_slice(
    context: Context,
    scope: list[dict[str, str]],
    tasks: list[tuple[str, dict[str, str]]],
    request_deadline: float,
) -> tuple[bool, bool]:
    """Collect one slice before the monotonic reservation-admission deadline.

    :param request_deadline: Absolute event-loop time, excluding the invocation's
        35-second network/storage reserve, passed unchanged to the request gate.
    :return: Whether the cycle completed healthily and whether it can continue.
    """
    collection = FabricCollection(
        context,
        "fabricitemaccesspermissions",
        "Explicit configured items only; preview admin accessDetails, not expanded "
        "groups or complete effective permissions. Maximum 50 items per cycle; "
        "one HTTP attempt per slice, at most six slices per invocation with a "
        "150-second admission budget. Inventory and access observations may "
        "span runs; cycle evidence is not a point-in-time tenant snapshot.",
        interval=19.0,
        single_attempt=True,
        request_deadline=request_deadline,
    )
    await collection.start()
    progress = _load_progress(
        await context.fm.read_snapshot(f"{collection.module}/", "progress.json"),
        scope,
        tasks,
    )
    kind, item = tasks[progress.task]
    workspace = item["workspaceId"]
    parent: JsonObject = dict(item)
    records: list[JsonObject] | None = None
    response: JsonObject = {}
    if kind == "inventory":
        endpoint = f"admin/items?workspaceId={workspace}"
        request_endpoint = endpoint
        if progress.token is not None:
            request_endpoint += f"&continuationToken={quote(progress.token, safe='')}"
        response = await collection.page(request_endpoint, "itemEntities")
        if "ERROR" not in response:
            records = _inventory_selection(response, workspace, scope)
            if records is not None and any(
                record["itemId"] in progress.discovered for record in records
            ):
                records = None
                collection.errors.append("Configured identity repeated across pages")
        token = cast(str | None, response.get("continuationToken"))
        if token is not None and (
            token in progress.tokens or len(progress.tokens) >= 10000
        ):
            records = None
            collection.errors.append("Repeated token or inventory page safety limit")
        parent["observationUnit"] = "inventoryPage"
        parent["inventoryComplete"] = records is not None and token is None
        if not response.get("deferred") or response.get("attempted"):
            if records is not None:
                progress.discovered.extend(
                    cast(str, record["itemId"]) for record in records
                )
            if records is not None and token:
                progress.tokens.append(token)
                progress.token = token
            else:
                progress.inventory_complete = records is not None
                progress.task += 1
                progress.token = None
                progress.tokens = []
        name = f"inventory_{workspace}"
    else:
        endpoint = f"admin/workspaces/{workspace}/items/{item['itemId']}/users"
        if item["type"] in {"Report", "Dashboard", "SemanticModel", "App", "Dataflow"}:
            endpoint += f"?type={item['type']}"
        if progress.inventory_complete and item["itemId"] in progress.discovered:
            response = await collection.page(endpoint, "accessDetails", paged=False)
            if "ERROR" not in response:
                records = cast(list[JsonObject], response["accessDetails"])
                if not _valid_access(records, item["type"]):
                    records = None
        if not response.get("deferred") or response.get("attempted"):
            progress.task += 1
        name = f"{workspace}_{item['itemId']}"
    success = await collection.snapshot(name, endpoint, parent, records)
    if not response.get("deferred") or response.get("attempted"):
        progress.healthy = progress.healthy and success
    cycle_finished = progress.task == len(tasks)
    if (
        not cycle_finished
        and tasks[progress.task][0] == "inventory"
        and not progress.token
    ):
        progress.discovered = []
        progress.inventory_complete = False
    collection.execution = {
        "cycleFinished": cycle_finished,
        "nextTask": progress.task,
        "taskCount": len(tasks),
        "cycleEvidence": list(progress.evidence),
        "deferred": bool(response.get("deferred")),
        "attempts": collection.attempts,
        "cycleHealthy": progress.healthy,
    }
    complete = cycle_finished and progress.healthy
    await collection.finish(complete)
    progress.evidence = [f"{collection.path}manifest.json"]
    # Commit the cursor only after its immutable evidence has been persisted.
    await context.fm.save_snapshot(
        f"{collection.module}/",
        "progress.json",
        (_Progress() if cycle_finished else progress).encode(scope),
    )
    return complete, not cycle_finished and not bool(response.get("deferred"))
