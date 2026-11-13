"""Strict scope and field validation for read-only pipeline activity queries."""

import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from env.utility.workspace_filter import parse_workspace_ids

_GUID = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
_QUERY_ROUTE = re.compile(
    rf"https://api\.fabric\.microsoft\.com/v1/workspaces/{_GUID}"
    rf"/datapipelines/pipelineruns/{_GUID}/queryactivityruns"
)
_WINDOW_FIELDS = ("lastUpdatedAfter", "lastUpdatedBefore")
_SCOPE_FIELDS = {"workspaceId", "pipelineRunId", *_WINDOW_FIELDS}
_COUNTS = ("rowsRead", "rowsCopied", "dataRead", "dataWritten")


def _utc(value):
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("Activity queries require explicit UTC timestamps")
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.utcoffset() != timedelta(0):
        raise ValueError("Activity queries require explicit UTC timestamps")
    return (
        moment.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _window(value):
    window = {field: _utc(value[field]) for field in _WINDOW_FIELDS}
    if window["lastUpdatedAfter"] >= window["lastUpdatedBefore"]:
        raise ValueError("Activity query UTC window must increase")
    return window


def activity_scope():
    """Validate all configured runs before storage, authentication or HTTP."""
    try:
        values = json.loads(os.environ.get("FABRIC_PIPELINE_ACTIVITY_SCOPE", "null"))
        if not isinstance(values, list) or not 1 <= len(values) <= 100:
            raise ValueError
        result, seen = [], set()
        for value in values:
            if not isinstance(value, dict) or set(value) != _SCOPE_FIELDS:
                raise ValueError
            parent = {
                field: str(UUID(value[field]))
                for field in ("workspaceId", "pipelineRunId")
            }
            identity = parent["workspaceId"], parent["pipelineRunId"]
            if identity in seen:
                raise ValueError
            seen.add(identity)
            result.append({**parent, **_window(value)})
        return result
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError(
            "FABRIC_PIPELINE_ACTIVITY_SCOPE requires 1-100 unique workspace/run "
            "UUID pairs with increasing explicit UTC lastUpdatedAfter/lastUpdatedBefore"
        ) from None


def activity_configuration():
    """Default to discovery, but never turn an invalid explicit scope into discovery."""
    try:
        exclusions = sorted(
            parse_workspace_ids(
                os.environ.get("FABRIC_PIPELINE_ACTIVITY_EXCLUDE_WORKSPACE_IDS")
            )
        )
        hours = int(os.environ.get("FABRIC_PIPELINE_ACTIVITY_LOOKBACK_HOURS", "24"))
        if hours <= 0:
            raise ValueError
        timedelta(hours=hours)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(
            "Invalid pipeline activity lookback or workspace exclusions"
        ) from None
    settings = {"excludeWorkspaceIds": exclusions, "lookbackHours": hours}
    scope = activity_scope() if "FABRIC_PIPELINE_ACTIVITY_SCOPE" in os.environ else None
    if scope is not None:
        scope = [parent for parent in scope if parent["workspaceId"] not in exclusions]
    return settings, scope


def discovery_window(now, hours):
    """Freeze a rolling UTC window at the start of a discovery sweep."""
    try:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return _window(
            {
                "lastUpdatedAfter": (now - timedelta(hours=hours)).isoformat(),
                "lastUpdatedBefore": now.isoformat(),
            }
        )
    except (ValueError, OverflowError):
        raise ValueError(
            "Pipeline activity lookback exceeds supported UTC range"
        ) from None


def pipeline_inventory(records, exclusions):
    """Keep only validated pipeline identities outside opted-out workspaces."""
    selected = {}
    for record in records:
        if not isinstance(record.get("type"), str) or not record["type"]:
            raise ValueError("Invalid pipeline inventory type")
        if record["type"] != "DataPipeline":
            continue
        workspace = str(UUID(record["workspaceId"]))
        if workspace in exclusions:
            continue
        item = str(UUID(record["id"]))
        selected[workspace, item] = {
            "workspaceId": workspace,
            "itemId": item,
            "type": "DataPipeline",
        }
    return [selected[key] for key in sorted(selected)]


def pipeline_runs(records, item_id):
    """Use only job IDs proven to belong to the requested pipeline."""
    selected = {}
    for record in records:
        if str(UUID(record["itemId"])) != item_id:
            raise ValueError("Pipeline job parent identity mismatch")
        identity = str(UUID(record["id"]))
        selected[identity] = {"pipelineRunId": identity}
    return [selected[key] for key in sorted(selected)]


def discovery_progress(saved, settings, window):
    """Validate durable cursors before trusting them as request scope."""
    if saved is None or saved == {"finished": True}:
        return {
            "settings": settings,
            "window": window,
            "phase": "inventory",
            "pipelines": [],
            "nextPipeline": 0,
            "runs": [],
            "nextRun": 0,
            "continuationToken": None,
            "tokens": [],
            "healthy": True,
            "evidence": [],
        }
    try:
        if not isinstance(saved, dict):
            raise TypeError
        expected = {
            "settings",
            "window",
            "phase",
            "pipelines",
            "nextPipeline",
            "runs",
            "nextRun",
            "continuationToken",
            "tokens",
            "healthy",
            "evidence",
        }
        if set(saved) != expected:
            raise ValueError
        prior_settings = saved["settings"]
        if (
            not isinstance(prior_settings, dict)
            or set(prior_settings) != {"excludeWorkspaceIds", "lookbackHours"}
            or type(prior_settings["lookbackHours"]) is not int
            or prior_settings["lookbackHours"] <= 0
            or not isinstance(prior_settings["excludeWorkspaceIds"], list)
            or sorted(parse_workspace_ids(prior_settings["excludeWorkspaceIds"]))
            != prior_settings["excludeWorkspaceIds"]
            or _window(saved["window"]) != saved["window"]
        ):
            raise ValueError
        pipelines = saved["pipelines"]
        normalized = pipeline_inventory(
            [{"id": item["itemId"], **item} for item in pipelines],
            prior_settings["excludeWorkspaceIds"],
        )
        phase = saved["phase"]
        index, run_index = saved["nextPipeline"], saved["nextRun"]
        runs, tokens, token = saved["runs"], saved["tokens"], saved["continuationToken"]
        if (
            pipelines != normalized
            or phase not in ("inventory", "jobs", "activities")
            or type(index) is not int
            or not 0 <= index <= len(pipelines)
            or type(run_index) is not int
            or not 0 <= run_index <= len(runs)
            or type(saved["healthy"]) is not bool
            or not isinstance(runs, list)
            or runs
            != [
                {"pipelineRunId": identity}
                for identity in sorted(
                    {str(UUID(run["pipelineRunId"])) for run in runs}
                )
            ]
            or not isinstance(tokens, list)
            or len(tokens) > 10000
            or any(not isinstance(value, str) or not value for value in tokens)
            or len(tokens) != len(set(tokens))
            or (token is not None and (not tokens or token != tokens[-1]))
            or (phase == "activities" and token is not None)
            or (token is None and tokens)
            or (phase == "inventory" and (index != 0 or runs or run_index != 0))
            or (phase == "jobs" and run_index != 0)
            or (
                phase != "inventory" and index == len(pipelines) and (runs or run_index)
            )
            or not isinstance(saved["evidence"], list)
            or any(
                not isinstance(path, str)
                or re.fullmatch(
                    r"fabricpipelineactivityruns/\d{4}/\d{2}/\d{2}/[0-9a-f]{32}/manifest\.json",
                    path,
                )
                is None
                for path in saved["evidence"]
            )
        ):
            raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise ValueError(
            "Invalid pipeline activity progress; requests blocked"
        ) from None
    if prior_settings != settings:
        return discovery_progress(None, settings, window)
    return saved


def activity_query_body(parent):
    return {
        "filters": [],
        "orderBy": [{"orderBy": "ActivityRunStart", "order": "DESC"}],
        **_window(parent),
    }


def validate_activity_query(url, body):
    """Allow only the documented retrieval endpoint and fixed query structure."""
    if not isinstance(url, str) or _QUERY_ROUTE.fullmatch(url) is None:
        raise ValueError("Disallowed pipeline activity query URL")
    try:
        if (
            not isinstance(body, dict)
            or set(body) != {"filters", "orderBy", *_WINDOW_FIELDS}
            or body != activity_query_body(body)
        ):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise ValueError("Disallowed pipeline activity query body") from None


def activity_records(values, run_id):
    """Select metrics/identity fields; never retain input, error text or arbitrary output."""
    if not isinstance(values, list) or len(values) > 10000:
        raise ValueError("Invalid activity result list")
    indexed = {}
    for value in values:
        if not isinstance(value, dict) or str(UUID(value["pipelineRunId"])) != run_id:
            raise ValueError("Activity run identity mismatch")
        record = {
            "activityRunId": str(UUID(value["activityRunId"])),
            "pipelineRunId": run_id,
        }
        for field in ("activityName", "activityType", "status"):
            if not isinstance(value.get(field), str) or not value[field]:
                raise ValueError("Invalid activity identity/status")
            record[field] = value[field]
        for field in ("activityRunStart", "activityRunEnd"):
            record[field] = _utc(value[field]) if value.get(field) is not None else None
        duration = value.get("durationInMs")
        if duration is not None and (
            type(duration) not in (int, float)
            or not math.isfinite(duration)
            or duration < 0
        ):
            raise ValueError("Invalid activity duration")
        record["durationInMs"] = duration
        output = value.get("output")
        output = {} if output is None else output
        if not isinstance(output, dict):
            raise TypeError("Invalid activity output")
        metrics = {}
        for field in (*_COUNTS, "throughput"):
            metric = output.get(field)
            if metric is not None:
                if field in _COUNTS:
                    if type(metric) is not int or not 0 <= metric <= 2**63 - 1:
                        raise ValueError("Invalid activity count")
                elif (
                    type(metric) not in (int, float)
                    or not math.isfinite(metric)
                    or metric < 0
                ):
                    raise ValueError("Invalid activity throughput")
            metrics[field] = metric
        record["output"] = metrics
        if (
            record["activityType"] in {"ExecutePipeline", "InvokePipeline"}
            and output.get("pipelineRunId") is not None
        ):
            record["childPipelineRunId"] = str(UUID(output["pipelineRunId"]))
        identity = record["activityRunId"]
        if identity in indexed and indexed[identity] != record:
            raise ValueError("Conflicting activity run observations")
        indexed[identity] = record
    return list(indexed.values())
