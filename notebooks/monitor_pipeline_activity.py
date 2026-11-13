"""Coverage-first pipeline activity facts from retained files; no API calls."""

import math

from notebooks.monitor_analytics import (
    PIPELINE_ACTIVITY_MODULE,
    build_runs,
    canonical,
    latest,
    records,
    row,
    sha256,
    text,
    utc,
    uuid,
)
from notebooks.monitor_fabric_runtime import plot_counts, to_frame

PIPELINE_METRICS = {
    "rowsRead": "rows_read",
    "rowsCopied": "rows_copied",
    "dataRead": "data_read",
    "dataWritten": "data_written",
    "throughput": "throughput",
}


def pipeline_window(value):
    after, before = (
        utc(value[key]) for key in ("lastUpdatedAfter", "lastUpdatedBefore")
    )
    if after >= before:
        raise ValueError("Invalid pipeline activity query window")
    return {"last_updated_after_utc": after, "last_updated_before_utc": before}


def pipeline_parent(parent):
    fields = pipeline_window(parent)
    window_keys = {"lastUpdatedAfter", "lastUpdatedBefore"}
    if "pipelineRunId" in parent:
        unit = "activity_query"
        allowed = window_keys | {"workspaceId", "pipelineRunId"}
        fields.update(
            workspace_id=uuid(parent["workspaceId"]),
            pipeline_run_id=uuid(parent["pipelineRunId"]),
            item_type="DataPipeline",
        )
        if "itemId" in parent:
            allowed |= {"itemId", "type"}
            fields["item_id"] = uuid(parent["itemId"])
            if parent["type"] != "DataPipeline":
                raise ValueError("Invalid pipeline activity item type")
    elif "itemId" in parent:
        unit = "pipeline_jobs"
        allowed = window_keys | {"workspaceId", "itemId", "type"}
        if parent["type"] != "DataPipeline":
            raise ValueError("Invalid pipeline job item type")
        fields.update(
            workspace_id=uuid(parent["workspaceId"]),
            item_id=uuid(parent["itemId"]),
            item_type="DataPipeline",
        )
    else:
        unit, allowed = "inventory", window_keys
    if set(parent) != allowed:
        raise ValueError("Invalid pipeline activity parent fields")
    return {"observation_unit": unit, **fields}


def pipeline_number(value, *, count=False):
    if value is None:
        return None
    if count:
        if type(value) is not int or not 0 <= value <= 2**63 - 1:
            raise ValueError("Invalid pipeline activity count")
        return value
    if type(value) not in (int, float) or value < 0:
        raise ValueError("Invalid pipeline activity measurement")
    try:
        number = float(value)
    except OverflowError:
        raise ValueError(
            "Pipeline activity measurement exceeds supported range"
        ) from None
    if not math.isfinite(number):
        raise ValueError("Invalid pipeline activity measurement")
    return number


def pipeline_activity_fields(value, parent):
    if uuid(value["pipelineRunId"]) != uuid(parent["pipelineRunId"]):
        raise ValueError("Pipeline activity run mismatch")
    output = value.get("output")
    output = {} if output is None else output
    if not isinstance(output, dict):
        raise TypeError("Invalid pipeline activity output")
    fields = {
        "activity_run_id": uuid(value["activityRunId"]),
        "activity_name": text(value["activityName"]),
        "activity_type": text(value["activityType"]),
        "status": text(value["status"]),
        "start_time_utc": utc(value["activityRunStart"])
        if value.get("activityRunStart") is not None
        else None,
        "end_time_utc": utc(value["activityRunEnd"])
        if value.get("activityRunEnd") is not None
        else None,
        "duration_ms": pipeline_number(value.get("durationInMs")),
        **{
            target: pipeline_number(output.get(source), count=source != "throughput")
            for source, target in PIPELINE_METRICS.items()
        },
    }
    if value.get("childPipelineRunId") is not None:
        if fields["activity_type"] not in {"ExecutePipeline", "InvokePipeline"}:
            raise ValueError("Invalid child pipeline activity type")
        fields["child_pipeline_run_id"] = uuid(value["childPipelineRunId"])
    return fields


def pipeline_scope(manifest):
    execution = manifest.get("execution")
    if not isinstance(execution, dict) or execution.get("mode") not in {
        "explicit",
        "discovery",
    }:
        raise ValueError("Invalid pipeline activity collection mode")
    exclusions = execution.get("excludeWorkspaceIds", [])
    if not isinstance(exclusions, list) or exclusions != sorted(
        {uuid(value) for value in exclusions}
    ):
        raise ValueError("Invalid pipeline workspace exclusions")
    scope = {"mode": execution["mode"], "excludeWorkspaceIds": exclusions}
    if execution["mode"] == "discovery":
        hours = execution["lookbackHours"]
        if type(hours) is not int or hours <= 0:
            raise ValueError("Invalid pipeline query lookback")
        pipeline_window(execution["window"])
        scope["lookbackHours"] = hours
    else:
        scope["parents"] = sorted(
            canonical(entry["parent"]) for entry in manifest["resources"]
        )
    return sha256(canonical(scope).encode())


def validate_pipeline_resource(resource, manifest):
    parent = resource["parent"]
    fields = pipeline_parent(parent)
    unit = fields["observation_unit"]
    pipeline_scope(manifest)
    execution = manifest["execution"]
    exclusions = execution.get("excludeWorkspaceIds", [])
    if fields.get("workspace_id") in exclusions:
        raise ValueError("Pipeline resource violates workspace exclusions")
    if execution["mode"] == "discovery":
        if pipeline_window(execution["window"]) != pipeline_window(parent):
            raise ValueError("Pipeline resource disagrees with sweep window")
        if unit == "activity_query" and "item_id" not in fields:
            raise ValueError("Discovered pipeline identity missing")
    elif unit != "activity_query":
        raise ValueError("Explicit run scope contains discovery resources")
    if unit == "inventory":
        name, endpoint = "inventory.json", "admin/items?type=DataPipeline"
    elif unit == "pipeline_jobs":
        workspace, item = fields["workspace_id"], fields["item_id"]
        name = f"jobs_{workspace}_{item}.json"
        endpoint = f"workspaces/{workspace}/items/{item}/jobs/instances"
    else:
        workspace, run = fields["workspace_id"], fields["pipeline_run_id"]
        name = f"{workspace}_{run}.json"
        endpoint = (
            f"workspaces/{workspace}/datapipelines/pipelineruns/{run}/queryactivityruns"
        )
    if not resource["complete"]:
        text(resource["error"])
        if "records" in resource:
            raise ValueError("Failed pipeline resource contains records")
        return name, endpoint
    if "error" in resource:
        raise ValueError("Successful pipeline resource contains an error")
    identities = []
    for value in records(resource["records"]):
        if unit == "inventory":
            if value["type"] != "DataPipeline":
                raise ValueError("Invalid pipeline inventory type")
            if uuid(value["workspaceId"]) in exclusions:
                raise ValueError("Pipeline inventory violates workspace exclusions")
            identities.append((uuid(value["workspaceId"]), uuid(value["itemId"])))
        elif unit == "pipeline_jobs":
            identities.append(uuid(value["pipelineRunId"]))
        else:
            identities.append(
                pipeline_activity_fields(value, parent)["activity_run_id"]
            )
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate pipeline activity identity")
    return name, endpoint


def pipeline_activity_tables(documents, output):
    runs = build_runs(
        documents,
        modules=(PIPELINE_ACTIVITY_MODULE,),
        resource_validator=validate_pipeline_resource,
        manifest_validator=pipeline_scope,
    )
    if not runs:
        output["pipeline_activity_resources"].append(
            row(
                "pipeline_activity_resources",
                {
                    "path": PIPELINE_ACTIVITY_MODULE + "/_missing",
                    "sha256": "",
                    "value": None,
                },
                "collection",
                observation_unit="collection",
                coverage_status="missing",
                issue="no_pipeline_activity_files",
            )
        )
    for run in runs.values():
        manifest = run["manifest"] or {}
        execution = manifest.get("execution")
        execution = execution if isinstance(execution, dict) else {}
        mode = (
            execution.get("mode")
            if execution.get("mode") in {"explicit", "discovery"}
            else None
        )
        valid = run["valid"]
        finished = valid and manifest["finished"]
        status = (
            "invalid"
            if not valid
            else "unfinished"
            if not finished
            else "success"
            if manifest["complete"]
            else "partial_or_failed"
        )
        scope_id = pipeline_scope(manifest) if valid and finished else None
        output["pipeline_activity_resources"].append(
            row(
                "pipeline_activity_resources",
                run["doc"],
                "collection",
                mode=mode,
                scope_id=scope_id,
                observation_unit="collection",
                coverage_status=status,
                record_count=None,
                issue=run["issue"],
            )
        )
        if not finished:
            continue
        for doc in run["resources"]:
            resource = doc["value"]
            fields = pipeline_parent(resource["parent"])
            output["pipeline_activity_resources"].append(
                row(
                    "pipeline_activity_resources",
                    doc,
                    "resource",
                    **fields,
                    mode=mode,
                    scope_id=scope_id,
                    coverage_status="success" if resource["complete"] else "failed",
                    record_count=len(resource["records"])
                    if resource["complete"]
                    else None,
                )
            )
            if (
                not resource["complete"]
                or fields["observation_unit"] != "activity_query"
            ):
                continue
            activity_parent = {
                key: value for key, value in fields.items() if key != "observation_unit"
            }
            for activity in resource["records"]:
                facts = pipeline_activity_fields(activity, resource["parent"])
                output["pipeline_activity_observations"].append(
                    row(
                        "pipeline_activity_observations",
                        doc,
                        facts["activity_run_id"],
                        **activity_parent,
                        **facts,
                        mode=mode,
                        scope_id=scope_id,
                    )
                )


def selected_pipeline_activities(tables, source_path=""):
    """Choose one latest query attempt per mode/workspace/run before admitting metrics."""
    resources = tables["pipeline_activity_resources"]
    if source_path:
        selected = [
            entry
            for entry in resources
            if entry["observation_unit"] == "activity_query"
            and entry["source_path"] == source_path
        ]
    else:
        if any(
            entry["observation_unit"] == "collection"
            and entry["observed_at_utc"] is None
            for entry in resources
        ):
            return []
        collections = latest(
            [entry for entry in resources if entry["observation_unit"] == "collection"],
            ["mode"],
        )
        if any(
            entry["coverage_status"] in {"invalid", "unfinished", "missing"}
            for entry in collections
        ):
            return []
        scopes = {entry["scope_id"] for entry in collections}
        selected = latest(
            [
                entry
                for entry in resources
                if entry["observation_unit"] == "activity_query"
                and entry["scope_id"] in scopes
            ],
            ["mode", "workspace_id", "pipeline_run_id"],
        )
    admitted = {
        entry["source_path"]
        for entry in selected
        if entry["coverage_status"] == "success"
    }
    return [
        entry
        for entry in tables["pipeline_activity_observations"]
        if entry["source_path"] in admitted
    ]


def preview_pipeline_activity(spark_session, display_frame, tables, source_path=""):
    from pyspark.sql import functions as F

    display_frame(
        to_frame(
            spark_session,
            "pipeline_activity_resources",
            tables["pipeline_activity_resources"],
        )
        .groupBy("mode", "observation_unit", "coverage_status")
        .count()
    )
    selected = selected_pipeline_activities(tables, source_path)
    if not selected:
        print(
            "No safely selected activity observations. Inspect resource coverage: "
            "empty job history or absent activity queries are not zero activity metrics."
        )
        return
    frame = to_frame(spark_session, "pipeline_activity_observations", selected)
    plot_counts(frame, "status", "Latest retained activity status per queried run")
    display_frame(
        frame.groupBy("mode", "activity_type", "status").agg(
            F.count("*").alias("activities"),
            F.count("rows_read").alias("activities_with_rows_read"),
            F.count("throughput").alias("activities_with_reported_throughput"),
            F.avg("duration_ms").alias("mean_known_duration_ms"),
        )
    )
    display_frame(
        frame.select(
            "mode",
            "workspace_id",
            "item_id",
            "pipeline_run_id",
            "activity_run_id",
            "activity_type",
            "status",
            "rows_read",
            "rows_copied",
            "data_read",
            "data_written",
            "throughput",
            "duration_ms",
            "last_updated_after_utc",
            "last_updated_before_utc",
        )
        .orderBy("mode", "workspace_id", "pipeline_run_id", "activity_run_id")
        .limit(50)
    )
    print(
        "Reported metrics retain native units; unknown is null, not zero. "
        "Latest retained queries use the latest configured scope in each mode; "
        "their windows can differ and do not establish current polling health. "
        "Do not sum throughput or assume rows/bytes across chained activities are distinct. "
        "These observations are runtime metrics, not runtime lineage or tenant-complete history."
    )
