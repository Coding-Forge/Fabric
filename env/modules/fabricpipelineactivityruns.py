"""Discover pipeline activity evidence without executing workloads."""

import asyncio
from urllib.parse import quote

import aiohttp

from env import context as runtime
from env.context import _safe_http_status, safe_fabric_error_code
from env.utility.fabric_collection import (
    FABRIC_ROOT,
    FabricCollection,
    _RequestDeferred,
)
from env.utility.pipeline_activity import (
    activity_configuration,
    activity_query_body,
    activity_records,
    discovery_progress,
    discovery_window,
    pipeline_inventory,
    pipeline_runs,
)

MODULE = "fabricpipelineactivityruns"
_INVALID_DATA = (ValueError, TypeError, KeyError, AttributeError, OverflowError)


class _ActivityRuns(FabricCollection):
    async def query(self, parent):
        endpoint = (
            f"workspaces/{parent['workspaceId']}/datapipelines/pipelineruns/"
            f"{parent['pipelineRunId']}/queryactivityruns"
        )
        self._resource_deferred = False
        try:
            self._request_delay()
            result = await self.context.invokeAPI(
                f"{FABRIC_ROOT}/{endpoint}",
                headers=self.context.clients["tenant"].get_headers,
                request_gate=self._gate,
                response_gate=self._observe_response,
                activity_query=activity_query_body(parent),
            )
        except _RequestDeferred as exc:
            self.record_deferral(str(exc))
            return endpoint, None
        except (aiohttp.ClientError, asyncio.TimeoutError):
            self.errors.append("Activity query transport failure")
            return endpoint, None
        if not isinstance(result, dict) or "ERROR" in result or "error" in result:
            self.errors.append(
                {
                    "error": "Activity query incomplete",
                    "status": _safe_http_status(
                        result.get("status") if isinstance(result, dict) else None
                    ),
                    "errorCode": safe_fabric_error_code(result),
                }
            )
            return endpoint, None
        try:
            records = activity_records(result.get("value"), parent["pipelineRunId"])
        except _INVALID_DATA:
            self.errors.append("Malformed or conflicting activity results")
            return endpoint, None
        return endpoint, records


async def _discover(collection, progress):
    async def persist():
        await collection.context.fm.save_snapshot(
            MODULE + "/", "progress.json", progress
        )

    async def finish(done):
        collection.execution.update(
            {
                "window": progress["window"],
                "sweepComplete": done,
                "sweepHealthy": progress["healthy"],
                "evidence": progress["evidence"],
            }
        )
        collection.failed = collection.failed or not progress["healthy"]
        result = await collection.finish(done and progress["healthy"])
        # Commit cursors after the manifest; crashes replay uncommitted observations.
        if done:
            await collection.context.fm.save_snapshot(
                MODULE + "/", "progress.json", {"finished": True}
            )
        else:
            await persist()
        return result

    def next_pipeline():
        progress.update(
            {
                "phase": "jobs",
                "nextPipeline": progress["nextPipeline"] + 1,
                "runs": [],
                "nextRun": 0,
                "tokens": [],
                "continuationToken": None,
            }
        )

    progress["evidence"].append(collection.path + "manifest.json")
    await persist()
    while True:
        phase = progress["phase"]
        if phase != "inventory" and progress["nextPipeline"] == len(
            progress["pipelines"]
        ):
            return await finish(True)
        if phase == "activities":
            pipeline = progress["pipelines"][progress["nextPipeline"]]
            while progress["nextRun"] < len(progress["runs"]):
                parent = {
                    **pipeline,
                    **progress["runs"][progress["nextRun"]],
                    **progress["window"],
                }
                endpoint, records = await collection.query(parent)
                success = await collection.snapshot(
                    f"{parent['workspaceId']}_{parent['pipelineRunId']}",
                    endpoint,
                    parent,
                    records,
                )
                if collection.resume_later or collection.pending or collection.blocked:
                    return await finish(False)
                progress["healthy"] = success and progress["healthy"]
                progress["nextRun"] += 1
            next_pipeline()
            continue

        inventory = phase == "inventory"
        pipeline = {} if inventory else progress["pipelines"][progress["nextPipeline"]]
        root = (
            "admin/items?type=DataPipeline"
            if inventory
            else f"workspaces/{pipeline['workspaceId']}/items/{pipeline['itemId']}/jobs/instances"
        )
        name = (
            "inventory"
            if inventory
            else f"jobs_{pipeline['workspaceId']}_{pipeline['itemId']}"
        )
        token = progress["continuationToken"]
        endpoint = root + (
            f"{'&' if '?' in root else '?'}continuationToken={quote(token, safe='')}"
            if token
            else ""
        )
        # Admin inventory allows 200 requests/hour, shared across the tenant.
        collection.interval = 18.0 if inventory else 1.0
        response = await collection.page(
            endpoint, "itemEntities" if inventory else "value"
        )
        records = None
        if "ERROR" not in response:
            try:
                token = response.get("continuationToken")
                if token and (
                    token in progress["tokens"] or len(progress["tokens"]) >= 10000
                ):
                    raise ValueError("Repeated or excessive discovery pagination")
                if inventory:
                    records = pipeline_inventory(
                        [
                            {"id": item["itemId"], **item}
                            for item in progress["pipelines"]
                        ]
                        + response["itemEntities"],
                        progress["settings"]["excludeWorkspaceIds"],
                    )
                else:
                    records = pipeline_runs(
                        [
                            {"id": run["pipelineRunId"], "itemId": pipeline["itemId"]}
                            for run in progress["runs"]
                        ]
                        + response["value"],
                        pipeline["itemId"],
                    )
            except _INVALID_DATA:
                collection.errors.append(
                    "Invalid pipeline discovery identities or pagination"
                )
        if records is None:
            await collection.snapshot(
                name, root, {**pipeline, **progress["window"]}, None
            )
            if collection.resume_later or collection.pending or collection.blocked:
                return await finish(False)
            progress["healthy"] = False
            if inventory:
                return await finish(False)
            next_pipeline()
            continue

        progress["pipelines" if inventory else "runs"] = records
        progress["continuationToken"] = token
        if token:
            progress["tokens"].append(token)
        else:
            await collection.snapshot(
                name, root, {**pipeline, **progress["window"]}, records
            )
            progress.update(
                {
                    "phase": "jobs" if inventory else "activities",
                    "tokens": [],
                    "continuationToken": None,
                }
            )


async def main(context=None):
    """Discover pipelines by default; retain explicit-run mode for investigations."""
    if context is None:
        raise RuntimeError("Context is None")
    settings, scope = activity_configuration()
    collection = _ActivityRuns(
        context,
        MODULE,
        "Admin active pipeline discovery (unless explicit runs are configured), "
        "then non-Admin job/activity queries; resource access required. Workspace "
        "opt-outs apply before resource calls. Returned recent jobs and activities "
        "only, not unlimited history. No execution or child-run traversal.",
    )
    collection.durable_gate = True
    collection.execution = {
        "mode": "discovery" if scope is None else "explicit",
        "excludeWorkspaceIds": settings["excludeWorkspaceIds"],
    }
    if scope is None:
        collection.request_deadline = asyncio.get_running_loop().time() + 85
        window = discovery_window(runtime.utc_now(), settings["lookbackHours"])
        progress = discovery_progress(
            await context.fm.read_snapshot(MODULE + "/", "progress.json"),
            settings,
            window,
        )
        collection.execution["lookbackHours"] = settings["lookbackHours"]
    await collection.start()
    if scope is None:
        return await _discover(collection, progress)
    complete = True
    for parent in scope:
        endpoint, records = await collection.query(parent)
        success = await collection.snapshot(
            f"{parent['workspaceId']}_{parent['pipelineRunId']}",
            endpoint,
            parent,
            records,
        )
        complete = success and complete
    return await collection.finish(complete)
