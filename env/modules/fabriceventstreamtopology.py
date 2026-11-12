"""Discover Eventstream configuration without reading events or changing workloads."""

import asyncio
import os
from urllib.parse import quote

from env.utility.eventstream_topology import (
    EVENTSTREAM_MODULE,
    eventstream_exclusions,
    eventstream_inventory,
    eventstream_progress,
    eventstream_topology,
)
from env.utility.fabric_collection import FabricCollection

_EVENTSTREAM_INVALID = (KeyError, TypeError, ValueError, AttributeError)


async def main(context=None):
    """Opt-in Admin discovery followed by non-Admin Eventstream-Read topology GETs."""
    if context is None:
        raise RuntimeError("Context is None")
    excluded = eventstream_exclusions(
        os.environ.get("FABRIC_EVENTSTREAM_EXCLUDE_WORKSPACE_IDS", "")
    )
    progress = eventstream_progress(
        await context.fm.read_snapshot(EVENTSTREAM_MODULE + "/", "progress.json"),
        excluded,
    )
    collection = FabricCollection(
        context,
        EVENTSTREAM_MODULE,
        "Admin active Eventstream discovery, then non-Admin topology GETs; item "
        "Read required. Owner workspace exclusions precede resource calls. "
        "Configured nodes/inputs and selected explicit target IDs only, not "
        "runtime I/O, effective access, event data or complete impact analysis.",
        request_deadline=asyncio.get_running_loop().time() + 85,
    )
    collection.durable_gate = True
    await collection.start()

    async def persist():
        await context.fm.save_snapshot(
            EVENTSTREAM_MODULE + "/", "progress.json", progress
        )

    async def finish(done):
        collection.execution = {
            "excludeWorkspaceIds": excluded,
            "sweepId": progress["sweepId"],
            "sweepComplete": done,
            "sweepHealthy": progress["healthy"],
        }
        collection.failed = collection.failed or not progress["healthy"]
        result = await collection.finish(done and progress["healthy"])
        # A crash replays this invocation rather than skipping uncommitted evidence.
        if done:
            await context.fm.save_snapshot(
                EVENTSTREAM_MODULE + "/", "progress.json", {"finished": True}
            )
        else:
            await persist()
        return result

    await persist()
    while progress["phase"] == "inventory":
        root = "admin/items?type=Eventstream"
        token = progress["continuationToken"]
        endpoint = root + (
            f"&continuationToken={quote(token, safe='')}" if token else ""
        )
        collection.interval = 18.0
        response = await collection.page(endpoint, "itemEntities")
        selected = None
        if "ERROR" not in response:
            try:
                token = response.get("continuationToken")
                if token and (
                    token in progress["tokens"] or len(progress["tokens"]) >= 10000
                ):
                    raise ValueError("Invalid Eventstream pagination")
                selected = eventstream_inventory(
                    [{"id": item["itemId"], **item} for item in progress["items"]]
                    + response["itemEntities"],
                    excluded,
                )
            except _EVENTSTREAM_INVALID:
                collection.errors.append("Invalid Eventstream inventory or pagination")
        if selected is None:
            await collection.snapshot("inventory", root, {}, None)
            if not collection.resume_later:
                progress["healthy"] = False
            return await finish(False)
        progress["items"], progress["continuationToken"] = selected, token
        if token:
            progress["tokens"].append(token)
        else:
            await collection.snapshot("inventory", root, {}, selected)
            progress.update(phase="topology", continuationToken=None, tokens=[])
    collection.interval = 1.0
    while progress["nextItem"] < len(progress["items"]):
        parent = progress["items"][progress["nextItem"]]
        endpoint = f"workspaces/{parent['workspaceId']}/eventstreams/{parent['itemId']}/topology"
        response = await collection.object_response(endpoint)
        records = None
        if "ERROR" not in response:
            try:
                records = [eventstream_topology(response)]
            except _EVENTSTREAM_INVALID:
                collection.errors.append("Invalid Eventstream topology structure")
        success = await collection.snapshot(
            f"{parent['workspaceId']}_{parent['itemId']}",
            endpoint,
            parent,
            records,
        )
        if collection.resume_later or collection.pending or collection.blocked:
            return await finish(False)
        progress["healthy"] = success and progress["healthy"]
        progress["nextItem"] += 1
    return await finish(True)
