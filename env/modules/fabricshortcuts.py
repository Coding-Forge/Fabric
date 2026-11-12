"""Discover Lakehouse shortcuts without following targets or reading their data."""

import asyncio
import os
from urllib.parse import quote

from env.utility.fabric_collection import FabricCollection
from env.utility.shortcut_relationships import (
    SHORTCUT_MODULE,
    shortcut_exclusions,
    shortcut_inventory,
    shortcut_progress,
    shortcut_records,
    validate_shortcut_records,
)

_INVALID = (ValueError, TypeError, KeyError, AttributeError)


async def main(context=None):
    """Opt-in Admin discovery followed by non-Admin, item-Read shortcut listing."""
    if context is None:
        raise RuntimeError("Context is None")
    excluded = shortcut_exclusions(
        os.environ.get("FABRIC_SHORTCUT_EXCLUDE_WORKSPACE_IDS", "")
    )
    progress = shortcut_progress(
        await context.fm.read_snapshot(SHORTCUT_MODULE + "/", "progress.json"),
        excluded,
    )
    collection = FabricCollection(
        context,
        SHORTCUT_MODULE,
        "Admin active Lakehouse discovery, then non-Admin exhaustive shortcut "
        "listing; item Read required. Workspace exclusions precede resource calls. "
        "Configured references only: no target traversal, access test or data reads. "
        "Names/paths/locations are omitted or fingerprinted, not anonymous.",
        request_deadline=asyncio.get_running_loop().time() + 85,
    )
    collection.durable_gate = True
    await collection.start()

    async def persist():
        await context.fm.save_snapshot(SHORTCUT_MODULE + "/", "progress.json", progress)

    async def finish(done):
        collection.execution = {
            "excludeWorkspaceIds": excluded,
            "sweepComplete": done,
            "sweepHealthy": progress["healthy"],
        }
        collection.failed = collection.failed or not progress["healthy"]
        result = await collection.finish(done and progress["healthy"])
        # Advance only after immutable evidence commits; replay an interrupted slice.
        if done:
            await context.fm.save_snapshot(
                SHORTCUT_MODULE + "/", "progress.json", {"finished": True}
            )
        else:
            await persist()
        return result

    def next_item():
        progress.update(
            nextItem=progress["nextItem"] + 1,
            records=[],
            continuationToken=None,
            tokens=[],
        )

    await persist()
    while True:
        inventory = progress["phase"] == "inventory"
        if not inventory and progress["nextItem"] == len(progress["items"]):
            return await finish(True)
        parent = {} if inventory else progress["items"][progress["nextItem"]]
        root = (
            "admin/items?type=Lakehouse"
            if inventory
            else f"workspaces/{parent['workspaceId']}/items/{parent['itemId']}/shortcuts"
        )
        name = (
            "inventory" if inventory else f"{parent['workspaceId']}_{parent['itemId']}"
        )
        token = progress["continuationToken"]
        endpoint = root + (
            f"{'&' if inventory else '?'}continuationToken={quote(token, safe='')}"
            if token
            else ""
        )
        collection.interval = 18.0 if inventory else 1.0
        response = await collection.page(
            endpoint, "itemEntities" if inventory else "value"
        )
        values = None
        if "ERROR" not in response:
            try:
                token = response.get("continuationToken")
                if token and (
                    token in progress["tokens"] or len(progress["tokens"]) >= 10000
                ):
                    raise ValueError("Invalid shortcut pagination")
                if inventory:
                    values = shortcut_inventory(
                        [{"id": item["itemId"], **item} for item in progress["items"]]
                        + response["itemEntities"],
                        excluded,
                    )
                else:
                    incoming = shortcut_records(response["value"])
                    merged = {
                        record["shortcutId"]: record for record in progress["records"]
                    }
                    for record in incoming:
                        if (
                            record["shortcutId"] in merged
                            and merged[record["shortcutId"]] != record
                        ):
                            raise ValueError("Conflicting shortcut pages")
                        merged[record["shortcutId"]] = record
                    values = validate_shortcut_records(
                        [merged[key] for key in sorted(merged)]
                    )
            except _INVALID:
                collection.errors.append(
                    "Invalid shortcut identity, target or pagination"
                )
        if values is None:
            await collection.snapshot(name, root, parent, None)
            if collection.resume_later or collection.pending or collection.blocked:
                return await finish(False)
            progress["healthy"] = False
            if inventory:
                return await finish(False)
            next_item()
            continue
        progress["items" if inventory else "records"] = values
        progress["continuationToken"] = token
        if token:
            progress["tokens"].append(token)
            continue
        await collection.snapshot(name, root, parent, values)
        if inventory:
            progress.update(phase="shortcuts", continuationToken=None, tokens=[])
        else:
            next_item()
