"""Collect scoped or opt-in tenant Fabric permissions in durable request slices."""

import asyncio
import os
import re
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

_POWER_BI_ITEM_TYPES = frozenset(
    {"Report", "Dashboard", "SemanticModel", "App", "Dataflow"}
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
            or (
                details.get("type") != item_type
                and not (
                    item_type in _POWER_BI_ITEM_TYPES
                    and "type" in details
                    and details["type"] is None
                )
            )
            or not isinstance(details.get("permissions"), list)
            or any(not isinstance(value, str) for value in details["permissions"])
            or (
                "additionalPermissions" in details
                and not (
                    item_type in _POWER_BI_ITEM_TYPES
                    and details["additionalPermissions"] is None
                )
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


def _access_endpoint(item: dict[str, str]) -> str:
    endpoint = f"admin/workspaces/{item['workspaceId']}/items/{item['itemId']}/users"
    if item["type"] in _POWER_BI_ITEM_TYPES:
        endpoint += f"?type={item['type']}"
    return endpoint


@dataclass
class _TenantProgress:
    phase: str = "inventory"
    items: list[dict[str, str]] = field(default_factory=list)
    cursor: int = 0
    token: str | None = None
    tokens: list[str] = field(default_factory=list)
    healthy: bool = True
    evidence: list[str] = field(default_factory=list)

    def encode(self) -> JsonObject:
        return {
            "schemaVersion": 1,
            "scopeMode": "tenant",
            "phase": self.phase,
            "items": cast(list[JsonValue], self.items),
            "cursor": self.cursor,
            "token": self.token,
            "tokens": list(self.tokens),
            "healthy": self.healthy,
            "evidence": list(self.evidence),
        }


def _tenant_items(
    records: list[JsonObject], previous: list[dict[str, str]]
) -> list[dict[str, str]]:
    selected = {(item["workspaceId"], item["itemId"]): item for item in previous}
    for record in records:
        try:
            target = {
                "workspaceId": str(UUID(record["workspaceId"])),
                "itemId": str(UUID(record["id"])),
                "type": record["type"],
            }
        except (KeyError, ValueError, TypeError, AttributeError):
            raise ValueError("Invalid tenant inventory identity") from None
        if (
            not isinstance(target["type"], str)
            or not target["type"].isascii()
            or not target["type"].isalnum()
            or record.get("state", "Active") != "Active"
        ):
            raise ValueError("Invalid active tenant inventory item")
        key = target["workspaceId"], target["itemId"]
        if key in selected and selected[key] != target:
            raise ValueError("Conflicting tenant inventory identity")
        selected[key] = target
    return list(selected.values())


def _load_tenant_progress(saved: JsonObject | None) -> _TenantProgress:
    if saved is None:
        return _TenantProgress()
    if (
        type(saved.get("schemaVersion")) is not int
        or saved["schemaVersion"] != 1
        or saved.get("scopeMode") != "tenant"
        or saved.get("phase") not in ("inventory", "access")
        or type(saved.get("cursor")) is not int
        or not isinstance(saved.get("healthy"), bool)
        or not isinstance(saved.get("items"), list)
        or not isinstance(saved.get("tokens"), list)
        or not isinstance(saved.get("evidence"), list)
        or "token" not in saved
    ):
        raise RuntimeError("Invalid tenant permission progress; requests blocked")
    try:
        items = _tenant_items(
            [
                {
                    "id": item["itemId"],
                    "workspaceId": item["workspaceId"],
                    "type": item["type"],
                }
                for item in saved["items"]
            ],
            [],
        )
    except (ValueError, KeyError, TypeError):
        raise RuntimeError(
            "Invalid tenant permission inventory; requests blocked"
        ) from None
    token, tokens, evidence = saved["token"], saved["tokens"], saved["evidence"]
    if (
        items != saved["items"]
        or not 0 <= saved["cursor"] <= len(items)
        or (saved["phase"] == "inventory" and saved["cursor"] != 0)
        or (saved["phase"] == "access" and saved["cursor"] == len(items))
        or (token is not None and (not isinstance(token, str) or not token))
        or any(not isinstance(value, str) or not value for value in tokens)
        or len(tokens) != len(set(tokens))
        or len(tokens) > 10000
        or (token is not None and tokens[-1:] != [token])
        or (saved["phase"] == "inventory" and token is None and (items or tokens))
        or (saved["phase"] == "access" and token is not None)
        or len(evidence) > 1
        or any(
            not isinstance(link, str)
            or re.fullmatch(
                r"fabricitemaccesspermissions_tenant/\d{4}/\d{2}/\d{2}/"
                r"[0-9a-f]{32}/manifest\.json",
                link,
            )
            is None
            for link in evidence
        )
        or ((items or tokens or saved["cursor"]) and not evidence)
    ):
        raise RuntimeError("Inconsistent tenant permission progress; requests blocked")
    return _TenantProgress(
        phase=saved["phase"],
        items=items,
        cursor=saved["cursor"],
        token=token,
        tokens=tokens,
        healthy=saved["healthy"],
        evidence=evidence,
    )


async def _collect_tenant_slice(
    context: Context, request_deadline: float
) -> tuple[bool, bool]:
    collection = FabricCollection(
        context,
        "fabricitemaccesspermissions",
        "Opt-in tenant active-item discovery and preview Admin accessDetails; "
        "not expanded groups or complete effective permissions. All returned "
        "types are attempted; unsupported/denied items fail cycle coverage. "
        "One HTTP attempt per slice, at most six slices per invocation within "
        "150 seconds. Discovery and access span time, not an atomic snapshot.",
        interval=19.0,
        single_attempt=True,
        request_deadline=request_deadline,
    )
    # Separate tenant evidence from scoped PBIP inputs, but share the quota gate.
    collection.path = collection.path.replace(
        "fabricitemaccesspermissions/", "fabricitemaccesspermissions_tenant/", 1
    )
    await collection.start()
    progress = _load_tenant_progress(
        await context.fm.read_snapshot(collection.module + "/", "tenant_progress.json")
    )
    if progress.evidence:
        folder, name = progress.evidence[0].rsplit("/", 1)
        previous = await context.fm.read_snapshot(folder + "/", name)
        if not isinstance(previous, dict) or previous.get("finished") is not True:
            raise RuntimeError(
                "Uncommitted tenant permission evidence; requests blocked"
            )
    phase = progress.phase
    parent: JsonObject = {"observationUnit": "inventoryPage"}
    records = None
    invalid_inventory = False
    if phase == "inventory":
        endpoint = "admin/items?state=active"
        request_endpoint = endpoint
        if progress.token is not None:
            request_endpoint += f"&continuationToken={quote(progress.token, safe='')}"
        response = await collection.page(request_endpoint, "itemEntities")
        if "ERROR" not in response:
            try:
                token = response.get("continuationToken")
                if token is not None and (
                    token in progress.tokens or len(progress.tokens) >= 10000
                ):
                    raise ValueError("Repeated token or tenant inventory page limit")
                merged = _tenant_items(response["itemEntities"], progress.items)
                records = merged[len(progress.items) :]
                progress.items = merged
                progress.token = token
                if token is not None:
                    progress.tokens.append(token)
                else:
                    progress.phase = "access"
            except ValueError:
                invalid_inventory = True
                collection.errors.append("Invalid or conflicting tenant inventory page")
        parent["inventoryComplete"] = progress.phase == "access"
        name = "inventory"
    else:
        item = progress.items[progress.cursor]
        parent = dict(item)
        endpoint = _access_endpoint(item)
        response = await collection.page(endpoint, "accessDetails", paged=False)
        if "ERROR" not in response and _valid_access(
            response["accessDetails"], item["type"]
        ):
            records = response["accessDetails"]
        if not response.get("deferred") or response.get("attempted"):
            progress.cursor += 1
        name = f"{item['workspaceId']}_{item['itemId']}"
    success = await collection.snapshot(name, endpoint, parent, records)
    if not response.get("deferred") or response.get("attempted"):
        progress.healthy = progress.healthy and success
    outcome = "succeeded" if success else "failed"
    if response.get("deferred"):
        outcome = "deferred"
    elif (
        response.get("errorCode") == "InvalidItemType" or response.get("status") == 501
    ):
        outcome = "unsupported"
    elif response.get("status") in (401, 403):
        outcome = "denied"
    elif response.get("errorCode") == "ItemNotFound":
        outcome = "not_found"
    cycle_finished = progress.phase == "access" and progress.cursor == len(
        progress.items
    )
    collection.execution = {
        "scopeMode": "tenant",
        "phase": phase,
        "inventoryComplete": progress.phase == "access",
        "discoveredItems": len(progress.items),
        "nextItem": progress.cursor,
        "cycleFinished": cycle_finished,
        "cycleHealthy": progress.healthy,
        "cycleEvidence": list(progress.evidence),
        "resourceOutcome": outcome,
        "deferred": bool(response.get("deferred")),
        "attempts": collection.attempts,
    }
    complete = cycle_finished and progress.healthy
    collection.failed = collection.failed or not progress.healthy
    collection.resume_later = not cycle_finished
    await collection.finish(complete)
    progress.evidence = [collection.path + "manifest.json"]
    await context.fm.save_snapshot(
        collection.module + "/",
        "tenant_progress.json",
        (_TenantProgress() if cycle_finished else progress).encode(),
    )
    return complete, (
        not cycle_finished
        and not response.get("deferred")
        and not invalid_inventory
        and not (phase == "inventory" and not success)
    )


async def main(context: Context | None = None) -> bool:
    """Resume bounded slices of scoped inventory and access observations.

    Default mode requires 1–50 ``FABRIC_ITEM_ACCESS_SCOPE`` identities.
    ``FABRIC_ITEM_ACCESS_MODE=tenant`` instead discovers all active Admin items
    before collecting their access. Tenant evidence/progress is separate, with
    the same durable quota ledger and invocation limits as scoped mode.
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
    mode = os.environ.get("FABRIC_ITEM_ACCESS_MODE", "scoped").strip().lower()
    if mode not in ("scoped", "tenant"):
        raise ValueError("FABRIC_ITEM_ACCESS_MODE must be scoped or tenant")
    scope = item_scope("FABRIC_ITEM_ACCESS_SCOPE", 50) if mode == "scoped" else []
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
        if mode == "tenant":
            complete, more = await _collect_tenant_slice(context, deadline - 35)
        else:
            complete, more = await _collect_slice(context, scope, tasks, deadline - 35)
        if complete or not more:
            return complete
    context.logger.info(
        "Permission invocation budget reached; saved cycle will resume next run"
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
            if records is not None:
                records = [
                    record
                    for record in records
                    if record["itemId"] not in progress.discovered
                ]
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
        endpoint = _access_endpoint(item)
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
    if not progress.healthy and response.get("deferred"):
        context.logger.warning(
            "Permission cycle contains failed observations; a request pause "
            "does not restore complete coverage"
        )
    collection.failed = collection.failed or not progress.healthy
    collection.resume_later = not cycle_finished
    await collection.finish(complete)
    progress.evidence = [f"{collection.path}manifest.json"]
    # Commit the cursor only after its immutable evidence has been persisted.
    await context.fm.save_snapshot(
        f"{collection.module}/",
        "progress.json",
        (_Progress() if cycle_finished else progress).encode(scope),
    )
    return complete, not cycle_finished and not bool(response.get("deferred"))
