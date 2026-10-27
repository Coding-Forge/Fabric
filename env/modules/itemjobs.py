import asyncio
import base64
import json
import time

from datetime import datetime, timedelta
import requests

JOB_ITEM_TYPES = {"CopyJob", "DataPipeline", "Notebook", "SynapseNotebook", "Dataflow", "SparkJobDefinition"}
DEFINITION_ITEM_TYPES = {"CopyJob", "DataPipeline"}
CONCURRENCY = 5


def _call(method, url, headers, **kwargs):
    r = None
    for _ in range(6):
        r = requests.request(method, url, headers=headers, timeout=120, **kwargs)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", "5")))
            continue
        break
    return r


def _find(node, key):
    """First value for `key` anywhere in a nested dict/list."""
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for v in node.values():
            found = _find(v, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _find(v, key)
            if found is not None:
                return found
    return None


def _list_jobs(item, headers, base):
    url = f"{base}/v1/workspaces/{item['workspaceId']}/items/{item['id']}/jobs/instances"
    runs = []
    while url:
        r = _call("GET", url, headers)
        if r.status_code != 200:
            return None, r
        body = r.json()
        runs.extend(body.get("value", []))
        url = body.get("continuationUri")
    return runs, None


def _get_definition(item, headers, base):
    url = f"{base}/v1/workspaces/{item['workspaceId']}/items/{item['id']}/getDefinition"
    r = _call("POST", url, headers)
    if r.status_code == 202:
        location = r.headers.get("Location")
        for _ in range(30):
            time.sleep(int(r.headers.get("Retry-After", "2")))
            s = _call("GET", location, headers)
            if s.status_code == 200 and s.json().get("status") == "Succeeded":
                r = _call("GET", location.rstrip("/") + "/result", headers)
                break
            if s.status_code == 200 and s.json().get("status") == "Failed":
                return None, s
        else:
            return None, r
    if r.status_code != 200:
        return None, r
    parts = {}
    for p in r.json().get("definition", {}).get("parts", []):
        try:
            parts[p["path"]] = json.loads(base64.b64decode(p["payload"]).decode("utf-8-sig"))
        except Exception:
            continue
    return parts, None


def _endpoint(role, kind, node, names, activity_name=None, **extra):
    settings = (node or {}).get("connectionSettings") or {}
    target_id = _find(settings, "artifactId")
    return {
        "Role": role,
        "ActivityName": activity_name,
        "EndpointType": (node or {}).get("type") or kind,
        "ConnectionType": settings.get("type"),
        "TargetWorkspaceId": _find(settings, "workspaceId"),
        "TargetItemId": target_id,
        "TargetItemName": names.get(target_id),
        **extra,
    }


def _query_activity_runs(job, headers, base, note, run_id=None, parent_run_id=None, depth=0,
                         window=None, names=None):
    """Per-activity volume (rows/bytes) for a pipeline run, following ExecutePipeline into child runs."""
    run_id = run_id or job["JobInstanceId"]
    if window is None:
        start = datetime.fromisoformat(job["StartTimeUtc"][:26])
        end = datetime.fromisoformat((job["EndTimeUtc"] or job["StartTimeUtc"])[:26])
        window = (start, end)
    body = {
        "filters": [],
        "orderBy": [{"orderBy": "ActivityRunStart", "order": "DESC"}],
        "lastUpdatedAfter": (window[0] - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lastUpdatedBefore": (window[1] + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    url = f"{base}/v1/workspaces/{job['WorkspaceId']}/datapipelines/pipelineruns/{run_id}/queryactivityruns"
    r = _call("POST", url, headers, json=body)
    if r.status_code != 200:
        note({"type": job["ItemType"]}, "activityruns", r)
        return []
    rows = []
    for a in r.json().get("value", []):
        out = a.get("output") or {}
        rows.append({
            "ItemId": job["ItemId"],
            "ItemName": job["ItemName"],
            "ItemType": job["ItemType"],
            "WorkspaceId": job["WorkspaceId"],
            "JobInstanceId": job["JobInstanceId"],
            "PipelineRunId": run_id,
            "ParentPipelineRunId": parent_run_id,
            "NestingLevel": depth,
            "ChildPipelineName": (names or {}).get(out.get("pipelineName"), out.get("pipelineName"))
            if a.get("activityType") == "ExecutePipeline" else None,
            "ActivityName": a.get("activityName"),
            "ActivityType": a.get("activityType"),
            "ActivityStatus": a.get("status"),
            "ActivityStart": a.get("activityRunStart"),
            "ActivityEnd": a.get("activityRunEnd"),
            "DurationMs": a.get("durationInMs"),
            "RowsRead": out.get("rowsRead"),
            "RowsCopied": out.get("rowsCopied"),
            "DataReadBytes": out.get("dataRead"),
            "DataWrittenBytes": out.get("dataWritten"),
            "ThroughputKBps": out.get("throughput"),
            "Error": json.dumps(a.get("error")) if a.get("error") and a["error"].get("message") else None,
        })
        child_run = out.get("pipelineRunId")
        if a.get("activityType") == "ExecutePipeline" and child_run and depth < 4:
            try:
                a_start = datetime.fromisoformat(a["activityRunStart"][:26])
                a_end = datetime.fromisoformat((a.get("activityRunEnd") or a["activityRunStart"])[:26])
            except (KeyError, TypeError, ValueError):
                a_start, a_end = window
            rows.extend(_query_activity_runs(job, headers, base, note, run_id=child_run, parent_run_id=run_id,
                                             depth=depth + 1, window=(a_start, a_end), names=names))
    return rows


def _flatten_copyjob(content, names):
    props = content.get("properties", {})
    rows = []
    activities = content.get("activities") or [{}]
    for act in activities:
        a = act.get("properties", {})
        src_ds = (a.get("source") or {}).get("datasetSettings") or {}
        dst = a.get("destination") or {}
        dst_ds = dst.get("datasetSettings") or {}
        rows.append(_endpoint("Source", "Source", props.get("source"), names,
                              Schema=src_ds.get("schema"), Table=src_ds.get("table"), JobMode=props.get("jobMode")))
        rows.append(_endpoint("Destination", "Destination", props.get("destination"), names,
                              Schema=dst_ds.get("schema"), Table=dst_ds.get("table"),
                              WriteBehavior=dst.get("writeBehavior"), JobMode=props.get("jobMode")))
    return rows


def _flatten_pipeline(content, names):
    rows = []

    def walk(activities):
        for act in activities or []:
            tp = act.get("typeProperties") or {}
            if act.get("type") == "Copy":
                for role, key in (("Source", "source"), ("Destination", "sink")):
                    node = tp.get(key) or {}
                    ds = node.get("datasetSettings") or {}
                    ds_props = ds.get("typeProperties") or {}
                    target_id = _find(ds, "artifactId")
                    rows.append({
                        "Role": role,
                        "ActivityName": act.get("name"),
                        "EndpointType": node.get("type") or ds.get("type"),
                        "ConnectionType": ds.get("type"),
                        "TargetWorkspaceId": _find(ds, "workspaceId"),
                        "TargetItemId": target_id,
                        "TargetItemName": names.get(target_id),
                        "Schema": ds_props.get("schema"),
                        "Table": ds_props.get("table"),
                        "WriteBehavior": node.get("writeBehavior"),
                    })
            else:
                rows.append({"Role": "Activity", "ActivityName": act.get("name"), "EndpointType": act.get("type")})
            for child in ("activities", "ifTrueActivities", "ifFalseActivities", "defaultActivities"):
                walk(tp.get(child))
            for case in tp.get("cases") or []:
                walk(case.get("activities"))

    walk(content.get("properties", {}).get("activities"))
    return rows


async def main(context=None):
    """
    Item Jobs
    """
    if context is None:
        raise RuntimeError("Context is None")

    headers = context.clients['tenant'].get_headers()
    base = context.get_fabric_url("").rstrip("/")
    today = datetime.now()

    items = []
    url = context.get_fabric_url("v1/admin/items")
    while url:
        for attempt in range(6):
            response = await context.invokeAPI(url, headers=headers)
            if "ERROR" not in response:
                break
            await asyncio.sleep(10 * (attempt + 1))
        else:
            break
        items.extend(response.get("itemEntities") or [])
        url = response.get("continuationUri")

    names = {i["id"]: i.get("name") or i.get("displayName") for i in items if i.get("id")}
    targets = [i for i in items if i.get("id") and i.get("workspaceId") and i.get("type") in JOB_ITEM_TYPES]
    sem = asyncio.Semaphore(CONCURRENCY)
    errors = {}

    def note(item, kind, r):
        key = f"{kind}:{item.get('type')}:{r.status_code}"
        errors.setdefault(key, [0, r.text[:200]])[0] += 1

    async def job_rows(item):
        async with sem:
            runs, err = await asyncio.to_thread(_list_jobs, item, headers, base)
        if err is not None:
            note(item, "jobs", err)
            return []
        rows = []
        for run in runs:
            start, end = run.get("startTimeUtc"), run.get("endTimeUtc")
            duration = None
            if start and end:
                try:
                    duration = (datetime.fromisoformat(end[:26]) - datetime.fromisoformat(start[:26])).total_seconds()
                except ValueError:
                    pass
            rows.append({
                "ItemId": item["id"],
                "ItemName": names.get(item["id"]),
                "ItemType": item.get("type"),
                "WorkspaceId": item["workspaceId"],
                "JobInstanceId": run.get("id"),
                "JobType": run.get("jobType"),
                "InvokeType": run.get("invokeType"),
                "Status": run.get("status"),
                "FailureReason": json.dumps(run.get("failureReason")) if run.get("failureReason") else None,
                "RootActivityId": run.get("rootActivityId"),
                "StartTimeUtc": start,
                "EndTimeUtc": end,
                "DurationSeconds": duration,
            })
        return rows

    async def definition_rows(item):
        async with sem:
            parts, err = await asyncio.to_thread(_get_definition, item, headers, base)
        if err is not None:
            note(item, "definition", err)
            return []
        if item["type"] == "CopyJob":
            flat = _flatten_copyjob(parts.get("copyjob-content.json", {}), names)
        else:
            flat = _flatten_pipeline(parts.get("pipeline-content.json", {}), names)
        return [{
            "ItemId": item["id"],
            "ItemName": names.get(item["id"]),
            "ItemType": item.get("type"),
            "WorkspaceId": item["workspaceId"],
            **row,
        } for row in flat]

    job_results = await asyncio.gather(*[job_rows(i) for i in targets])
    def_results = await asyncio.gather(*[definition_rows(i) for i in targets if i["type"] in DEFINITION_ITEM_TYPES])
    jobs = [r for rows in job_results for r in rows]
    definitions = [r for rows in def_results for r in rows]

    async def activity_rows(job):
        async with sem:
            return await asyncio.to_thread(_query_activity_runs, job, headers, base, note, names=names)

    volume_jobs = [j for j in jobs if j["ItemType"] == "DataPipeline" and j["StartTimeUtc"]]
    vol_results = await asyncio.gather(*[activity_rows(j) for j in volume_jobs])
    volumes = [r for rows in vol_results for r in rows]

    path = f"jobs/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"
    await context.fm.save(path=path, file_name="jobs_00001.json", content=jobs)
    path = f"itemdefinitions/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"
    await context.fm.save(path=path, file_name="itemdefinitions_00001.json", content=definitions)
    path = f"jobactivityruns/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"
    await context.fm.save(path=path, file_name="jobactivityruns_00001.json", content=volumes)

    print(f"ItemJobs: {len(jobs)} job runs, {len(definitions)} source/destination rows, "
          f"{len(volumes)} activity runs from {len(targets)} items")
    for key, (count, message) in errors.items():
        print(f"  {key} x{count}: {message}")


if __name__ == "__main__":
    asyncio.run(main())
