"""Bounded, evidence-preserving Silver/Gold event investigation transformations."""

import hashlib
import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

MEDALLION_VERSION = "1"
BRONZE_DATASETS = (
    "inventory",
    "catalog_items",
    "collection_health",
    "job_resources",
    "job_observations",
    "pipeline_activity_resources",
    "pipeline_activity_observations",
)
MD_COMMON = {
    "build_id": "string",
    "source_path": "string",
    "source_sha256": "string",
    "source_observation_id": "string",
    "observed_at_utc": "timestamp",
    "coverage_status": "string",
    "collection_module": "string",
    "collection_mode": "string",
    "collection_run_id": "string",
    "record_sha256": "string",
}
SILVER_SCHEMAS = {
    "audit_event": {
        "event_key": "string",
        "event_id": "string",
        "event_time_utc": "timestamp",
        "operation": "string",
        "workload": "string",
        "actor_key": "string",
        "ip_key": "string",
        "is_success": "boolean",
        "activity_id": "string",
        "request_id": "string",
        "validity": "string",
        "identity_basis": "string",
    },
    "event_source": {"event_key": "string"},
    "actor_identity": {
        "actor_key": "string",
        "identity_field": "string",
        "reported_identity": "string",
        "value_suppressed": "boolean",
    },
    "client_ip": {
        "ip_key": "string",
        "reported_ip": "string",
        "value_suppressed": "boolean",
    },
    "artifact_observation": {
        "artifact_key": "string",
        "workspace_id": "string",
        "item_id": "string",
        "item_name": "string",
        "item_type": "string",
    },
    "event_artifact": {
        "event_key": "string",
        "artifact_key": "string",
        "workspace_id": "string",
        "item_id": "string",
        "reference_field": "string",
        "resolution": "string",
    },
    "execution_observation": {
        "execution_key": "string",
        "artifact_key": "string",
        "workspace_id": "string",
        "item_id": "string",
        "execution_id": "string",
        "job_type": "string",
        "status": "string",
        "start_time_utc": "timestamp",
        "end_time_utc": "timestamp",
        "root_activity_id": "string",
    },
    "execution_latest": {
        "execution_key": "string",
        "artifact_key": "string",
        "workspace_id": "string",
        "item_id": "string",
        "execution_id": "string",
        "job_type": "string",
        "status": "string",
        "start_time_utc": "timestamp",
        "end_time_utc": "timestamp",
        "root_activity_id": "string",
        "observation_count": "long",
        "poll_state": "string",
    },
    "pipeline_activity": {
        "activity_key": "string",
        "execution_key": "string",
        "artifact_key": "string",
        "workspace_id": "string",
        "item_id": "string",
        "execution_id": "string",
        "activity_run_id": "string",
        "activity_name": "string",
        "activity_type": "string",
        "status": "string",
        "start_time_utc": "timestamp",
        "end_time_utc": "timestamp",
        "rows_read": "long",
        "rows_copied": "long",
        "data_read": "long",
        "data_written": "long",
        "child_execution_id": "string",
        "observation_count": "long",
        "poll_state": "string",
        "physical_source": "string",
        "physical_destination": "string",
        "destination_state": "string",
    },
    "event_correlation_id": {
        "event_key": "string",
        "correlation_field": "string",
        "correlation_id": "string",
    },
    "correlation_candidate": {
        "event_key": "string",
        "execution_key": "string",
        "matched_fields_json": "string",
        "match_state": "string",
    },
    "event_execution_link": {
        "event_key": "string",
        "execution_key": "string",
        "matched_fields_json": "string",
        "link_state": "string",
    },
    "child_run_link": {
        "activity_key": "string",
        "execution_key": "string",
        "child_execution_id": "string",
        "child_execution_key": "string",
        "resolution": "string",
    },
    "reported_location": {
        "event_key": "string",
        "location_key": "string",
        "source_field": "string",
        "reported_location": "string",
        "interpretation": "string",
    },
    "quarantine": {"entity_key": "string", "reason": "string"},
    "evidence_coverage": {
        "dataset": "string",
        "availability": "string",
        "row_count": "long",
        "source_version": "long",
        "interpretation": "string",
    },
    "build": {
        "state": "string",
        "built_at_utc": "timestamp",
        "source_signature": "string",
        "transformation_version": "string",
        "sensitive_values_enabled": "boolean",
    },
}
GOLD_SCHEMAS = {
    "event_case": {
        "event_key": "string",
        "event_id": "string",
        "event_time_utc": "timestamp",
        "operation": "string",
        "actor_key": "string",
        "ip_key": "string",
        "reported_event_success": "boolean",
        "validity": "string",
        "referenced_artifact_count": "long",
        "unresolved_reference_count": "long",
        "reported_location_count": "long",
        "artifact_labels_json": "string",
        "linked_execution_count": "long",
        "traced_execution_count": "long",
        "correlation_state": "string",
        "trace_capped": "boolean",
        "interpretation": "string",
    },
    "event_trace_edge": {
        "edge_key": "string",
        "event_key": "string",
        "source_type": "string",
        "source_key": "string",
        "target_type": "string",
        "target_key": "string",
        "relation_type": "string",
        "resolution": "string",
        "depth": "long",
        "evidence_fields_json": "string",
    },
    "execution_fact": dict(SILVER_SCHEMAS["execution_latest"]),
    "pipeline_activity_fact": dict(SILVER_SCHEMAS["pipeline_activity"]),
    "event_execution_bridge": dict(SILVER_SCHEMAS["event_execution_link"]),
    "reported_location": dict(SILVER_SCHEMAS["reported_location"]),
    "evidence_coverage": dict(SILVER_SCHEMAS["evidence_coverage"]),
    "build": dict(SILVER_SCHEMAS["build"]),
}
SILVER_SCHEMAS = {
    name: {**MD_COMMON, **schema} for name, schema in SILVER_SCHEMAS.items()
}
GOLD_SCHEMAS = {
    name: {**MD_COMMON, "source_build_id": "string", **schema}
    for name, schema in GOLD_SCHEMAS.items()
}


def md_json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=lambda item: (
            item.isoformat() if isinstance(item, datetime) else str(item)
        ),
    )


def md_key(*values):
    return hashlib.sha256(md_json(values).encode()).hexdigest()


def md_uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def md_time(value, *, provider_utc=False):
    if value is None:
        return None
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        if not provider_utc and not isinstance(value, datetime):
            raise ValueError("Naive evidence timestamp")
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def md_location(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if "://" in value:
        parts = urlsplit(value)
        return urlunsplit(
            (parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", "")
        )
    return value.split("?", 1)[0].split("#", 1)[0]


def md_row(build_id, source=None, **values):
    source = source or {}
    result = {
        "build_id": build_id,
        "source_path": source.get("source_path"),
        "source_sha256": source.get("source_sha256"),
        "source_observation_id": source.get(
            "observation_id", source.get("source_observation_id")
        ),
        "observed_at_utc": md_time(source.get("observed_at_utc")),
        "coverage_status": source.get("coverage_status", "derived"),
        "collection_module": source.get("module", source.get("collection_module")),
        "collection_mode": source.get("mode", source.get("collection_mode")),
        "collection_run_id": source.get("run_id", source.get("collection_run_id")),
        **values,
    }
    result["record_sha256"] = md_key(result)
    return result


def md_latest(rows, fields):
    groups = defaultdict(list)
    for row in {md_json(row): row for row in rows}.values():
        groups[tuple(row[field] for field in fields)].append(row)
    selected, conflicts = [], []
    for group in groups.values():
        known = [
            row["observed_at_utc"]
            for row in group
            if row["observed_at_utc"] is not None
        ]
        latest = max(known) if known else None
        choices = [row for row in group if row["observed_at_utc"] in {latest, None}]
        payloads = {
            md_json(
                {name: value for name, value in row.items() if name not in MD_COMMON}
            )
            for row in choices
        }
        if len(payloads) != 1:
            conflicts.extend(choices)
            continue
        preferred = [row for row in choices if row["observed_at_utc"] == latest]
        selected.append(
            (min(preferred, key=lambda row: row["record_sha256"]), len(group))
        )
    return selected, conflicts


def md_poll_state(resources, workspace, item, execution_id=None):
    matches = [
        row
        for row in resources
        if md_uuid(row.get("workspace_id")) == workspace
        and md_uuid(row.get("item_id")) == item
        and (
            execution_id is None or md_uuid(row.get("pipeline_run_id")) == execution_id
        )
    ]
    if not matches:
        return "NO_RETAINED_POLL_COVERAGE"
    normalized = [
        {
            "observed_at_utc": md_time(row.get("observed_at_utc")),
            "coverage": row.get("coverage_status"),
            "record_count": row.get("record_count"),
        }
        for row in matches
    ]
    known = [
        row["observed_at_utc"]
        for row in normalized
        if row["observed_at_utc"] is not None
    ]
    if any(row["observed_at_utc"] is None for row in normalized):
        return "UNKNOWN_POLL_ORDER"
    time = max(known) if known else None
    latest = [row for row in normalized if row["observed_at_utc"] == time]
    states = {(row["coverage"], row["record_count"]) for row in latest}
    if len(states) != 1:
        return "AMBIGUOUS_LATEST_POLL"
    coverage, count = next(iter(states))
    if coverage != "success":
        return "LATEST_POLL_" + str(coverage or "UNKNOWN").upper()
    if count is None:
        return "LATEST_POLL_COUNT_UNKNOWN"
    return "LATEST_POLL_EMPTY" if count == 0 else "LATEST_POLL_REPORTED_ROWS"


def build_silver(
    sources,
    documents,
    *,
    tenant_id,
    source_signature,
    source_versions=None,
    source_presence=None,
    activity_scope_present=True,
    include_sensitive=False,
):
    tenant = md_uuid(tenant_id)
    if tenant is None or type(include_sensitive) is not bool:
        raise ValueError(
            "Explicit tenant UUID and boolean sensitive-value setting required"
        )
    source_versions = source_versions or {}
    source_presence = set(sources) if source_presence is None else set(source_presence)
    build_id = md_key(
        "silver", MEDALLION_VERSION, tenant, source_signature, include_sensitive
    )
    result = {name: [] for name in SILVER_SCHEMAS}

    def quarantine(source, key, reason):
        result["quarantine"].append(
            md_row(build_id, source, entity_key=key, reason=reason)
        )

    artifacts = set()
    for dataset in ("inventory", "catalog_items"):
        for row in sources.get(dataset, []):
            workspace, item = (
                md_uuid(row.get("workspace_id")),
                md_uuid(row.get("item_id")),
            )
            if (
                not workspace
                or not item
                or str(row.get("item_type", "")).lower() == "workspace"
            ):
                continue
            artifact = md_key("artifact", tenant, workspace, item)
            if row.get("coverage_status") in {
                "invalid",
                "failed",
                "unfinished",
                "missing",
            }:
                quarantine(row, artifact, "UNUSABLE_ARTIFACT_OBSERVATION")
                continue
            artifacts.add(artifact)
            result["artifact_observation"].append(
                md_row(
                    build_id,
                    row,
                    artifact_key=artifact,
                    workspace_id=workspace,
                    item_id=item,
                    item_name=row.get("item_name"),
                    item_type=row.get("item_type"),
                )
            )
    grouped_events = defaultdict(list)
    for document in documents:
        source = {
            "source_path": document["path"],
            "source_sha256": document["sha256"],
            "coverage_status": "legacy_unverified",
            "module": "activity",
        }
        for raw in document["records"]:
            provider_id = raw.get("Id")
            if provider_id is not None and (
                not isinstance(provider_id, str) or not provider_id.strip()
            ):
                raise ValueError("Malformed provider event ID")
            event_key = (
                md_key("event", tenant, provider_id)
                if provider_id
                else md_key("event_hash", tenant, raw)
            )
            grouped_events[event_key].append((raw, source))
    actors, ips = {}, {}
    for event_key, observations in sorted(grouped_events.items()):
        for source in {md_json(source): source for _, source in observations}.values():
            result["event_source"].append(md_row(build_id, source, event_key=event_key))
        unique = {md_key(raw) for raw, _ in observations}
        raw, source = min(
            observations, key=lambda value: (value[1]["source_path"], md_key(value[0]))
        )
        if len(unique) != 1:
            quarantine(source, event_key, "CONFLICTING_PROVIDER_EVENT")
            result["audit_event"].append(
                md_row(
                    build_id,
                    source,
                    event_key=event_key,
                    event_id=raw.get("Id"),
                    validity="CONFLICT",
                    identity_basis="Conflicting provider ID",
                )
            )
            continue
        actor_field = "UserId" if raw.get("UserId") else "UserKey"
        actor = raw.get(actor_field)
        ip = raw.get("ClientIP") or raw.get("ClientIp")
        if any(
            value is not None and not isinstance(value, str) for value in (actor, ip)
        ):
            raise ValueError("Malformed reported actor/IP")
        actor_key = md_key("actor", tenant, actor_field, actor) if actor else None
        ip_key = md_key("ip", tenant, ip) if ip else None
        if actor_key:
            actors[actor_key] = md_row(
                build_id,
                source,
                actor_key=actor_key,
                identity_field=actor_field,
                reported_identity=actor if include_sensitive else None,
                value_suppressed=not include_sensitive,
            )
        if ip_key:
            ips[ip_key] = md_row(
                build_id,
                source,
                ip_key=ip_key,
                reported_ip=ip if include_sensitive else None,
                value_suppressed=not include_sensitive,
            )
        success = raw.get("IsSuccess")
        if success is not None and type(success) is not bool:
            raise ValueError("Malformed reported event outcome")
        event = md_row(
            build_id,
            source,
            event_key=event_key,
            event_id=raw.get("Id"),
            event_time_utc=md_time(raw.get("CreationTime"), provider_utc=True),
            operation=raw.get("Operation"),
            workload=raw.get("Workload"),
            actor_key=actor_key,
            ip_key=ip_key,
            is_success=success,
            activity_id=md_uuid(raw.get("ActivityId")),
            request_id=md_uuid(raw.get("RequestId")),
            validity="VALID",
            identity_basis="Provider ID"
            if raw.get("Id")
            else "Canonical full-record hash",
        )
        result["audit_event"].append(event)
        workspace = md_uuid(raw.get("WorkspaceId") or raw.get("WorkSpaceId"))
        references = [
            (name, md_uuid(raw.get(name)))
            for name in ("ItemId", "ArtifactId", "ReportId", "DatasetId", "ObjectId")
            if raw.get(name) is not None
        ]
        references = [(name, item) for name, item in references if item]
        if not references:
            references = [("No explicit artifact ID", None)]
        for name, item in references:
            artifact = (
                md_key("artifact", tenant, workspace, item)
                if workspace and item
                else None
            )
            resolution = (
                "SCOPED_IDENTIFIER"
                if artifact in artifacts
                else "IDENTIFIER_REPORTED_NOT_IN_INVENTORY"
                if artifact
                else "UNRESOLVED_SCOPE"
            )
            result["event_artifact"].append(
                md_row(
                    build_id,
                    source,
                    event_key=event_key,
                    artifact_key=artifact,
                    workspace_id=workspace,
                    item_id=item,
                    reference_field=name,
                    resolution=resolution,
                )
            )
        for name in ("activity_id", "request_id"):
            if event[name]:
                result["event_correlation_id"].append(
                    md_row(
                        build_id,
                        source,
                        event_key=event_key,
                        correlation_field=name,
                        correlation_id=event[name],
                    )
                )
        for name in ("ObjectId", "ImportSource"):
            location = md_location(raw.get(name))
            if location and not md_uuid(location):
                result["reported_location"].append(
                    md_row(
                        build_id,
                        source,
                        event_key=event_key,
                        location_key=md_key("location", tenant, location),
                        source_field=name,
                        reported_location=location,
                        interpretation="Reported audit reference, not resolved physical source/sink",
                    )
                )
    result["actor_identity"], result["client_ip"] = (
        list(actors.values()),
        list(ips.values()),
    )
    for row in sources.get("job_observations", []):
        workspace, item, execution = (
            md_uuid(row.get(name)) for name in ("workspace_id", "item_id", "job_id")
        )
        if not all((workspace, item, execution)):
            quarantine(
                row,
                md_key("invalid_execution", row.get("observation_id")),
                "INVALID_EXECUTION_SCOPE",
            )
            continue
        if row.get("coverage_status") in {"invalid", "failed", "unfinished", "missing"}:
            quarantine(row, execution, "UNUSABLE_EXECUTION_OBSERVATION")
            continue
        artifact = md_key("artifact", tenant, workspace, item)
        result["execution_observation"].append(
            md_row(
                build_id,
                row,
                execution_key=md_key("execution", artifact, execution),
                artifact_key=artifact,
                workspace_id=workspace,
                item_id=item,
                execution_id=execution,
                job_type=row.get("job_type"),
                status=row.get("status"),
                start_time_utc=md_time(row.get("start_time_utc")),
                end_time_utc=md_time(row.get("end_time_utc")),
                root_activity_id=md_uuid(row.get("root_activity_id")),
            )
        )
    latest, conflicts = md_latest(result["execution_observation"], ("execution_key",))
    for row in conflicts:
        quarantine(row, row["execution_key"], "CONFLICTING_LATEST_EXECUTION")
    job_polls, activity_polls = defaultdict(list), defaultdict(list)
    for resource in sources.get("job_resources", []):
        job_polls[
            (md_uuid(resource.get("workspace_id")), md_uuid(resource.get("item_id")))
        ].append(resource)
    for resource in sources.get("pipeline_activity_resources", []):
        activity_polls[
            (
                md_uuid(resource.get("workspace_id")),
                md_uuid(resource.get("item_id")),
                md_uuid(resource.get("pipeline_run_id")),
            )
        ].append(resource)
    for row, count in latest:
        result["execution_latest"].append(
            {
                **row,
                "observation_count": count,
                "poll_state": md_poll_state(
                    job_polls[(row["workspace_id"], row["item_id"])],
                    row["workspace_id"],
                    row["item_id"],
                ),
            }
        )
    activities = []
    for row in sources.get("pipeline_activity_observations", []):
        workspace, item, execution, activity = (
            md_uuid(row.get(name))
            for name in (
                "workspace_id",
                "item_id",
                "pipeline_run_id",
                "activity_run_id",
            )
        )
        if not all((workspace, item, execution, activity)):
            quarantine(
                row,
                md_key("invalid_activity", row.get("observation_id")),
                "INVALID_ACTIVITY_SCOPE",
            )
            continue
        if row.get("coverage_status") in {"invalid", "failed", "unfinished", "missing"}:
            quarantine(row, activity, "UNUSABLE_ACTIVITY_OBSERVATION")
            continue
        metrics = {
            name: row.get(name)
            for name in ("rows_read", "rows_copied", "data_read", "data_written")
        }
        if any(
            value is not None
            and (type(value) is not int or not 0 <= value <= 2**63 - 1)
            for value in metrics.values()
        ):
            raise ValueError("Invalid reported activity count")
        artifact = md_key("artifact", tenant, workspace, item)
        execution_key = md_key("execution", artifact, execution)
        activities.append(
            md_row(
                build_id,
                row,
                activity_key=md_key("activity", execution_key, activity),
                execution_key=execution_key,
                artifact_key=artifact,
                workspace_id=workspace,
                item_id=item,
                execution_id=execution,
                activity_run_id=activity,
                activity_name=row.get("activity_name"),
                activity_type=row.get("activity_type"),
                status=row.get("status"),
                start_time_utc=md_time(row.get("start_time_utc")),
                end_time_utc=md_time(row.get("end_time_utc")),
                **metrics,
                child_execution_id=md_uuid(row.get("child_pipeline_run_id")),
                physical_source=None,
                physical_destination=None,
                destination_state="NOT_RETAINED_BY_CURRENT_CONTRACT",
            )
        )
    latest, conflicts = md_latest(activities, ("activity_key",))
    for row in conflicts:
        quarantine(row, row["activity_key"], "CONFLICTING_LATEST_ACTIVITY")
    for row, count in latest:
        result["pipeline_activity"].append(
            {
                **row,
                "observation_count": count,
                "poll_state": md_poll_state(
                    activity_polls[
                        (row["workspace_id"], row["item_id"], row["execution_id"])
                    ],
                    row["workspace_id"],
                    row["item_id"],
                    row["execution_id"],
                ),
            }
        )
    executions = {row["execution_key"]: row for row in result["execution_latest"]}
    # An activity's explicit parent survives even when no job observation was retained.
    for row in result["pipeline_activity"]:
        if row["execution_key"] not in executions:
            parent = md_row(
                build_id,
                row,
                execution_key=row["execution_key"],
                artifact_key=row["artifact_key"],
                workspace_id=row["workspace_id"],
                item_id=row["item_id"],
                execution_id=row["execution_id"],
                job_type="Activity-referenced parent",
                status=None,
                start_time_utc=None,
                end_time_utc=None,
                root_activity_id=None,
                observation_count=0,
                poll_state="NO_RETAINED_JOB_OBSERVATION",
            )
            executions[parent["execution_key"]] = parent
            result["execution_latest"].append(parent)
    by_root, by_id, event_artifacts = (
        defaultdict(list),
        defaultdict(list),
        defaultdict(set),
    )
    for row in executions.values():
        if row["root_activity_id"]:
            by_root[row["root_activity_id"]].append(row)
        by_id[row["execution_id"]].append(row)
    for row in result["event_artifact"]:
        if row["artifact_key"]:
            event_artifacts[row["event_key"]].add(row["artifact_key"])
    candidates = defaultdict(lambda: defaultdict(set))
    candidate_rows = 0
    for row in result["event_correlation_id"]:
        for execution in by_root[row["correlation_id"]]:
            candidate_rows += 1
            if candidate_rows > 500000:
                raise ValueError(
                    "Correlation candidate limit exceeded; no truncated build"
                )
            candidates[row["event_key"]][execution["execution_key"]].add(
                row["correlation_field"]
            )
    event_index = {row["event_key"]: row for row in result["audit_event"]}
    for event_key, matches in candidates.items():
        compatible = {
            key
            for key in matches
            if executions[key]["artifact_key"] in event_artifacts[event_key]
        }
        for execution_key, matched_fields in matches.items():
            state = (
                "UNRESOLVED_SCOPE"
                if not event_artifacts[event_key]
                else "SCOPE_MISMATCH"
                if execution_key not in compatible
                else "AMBIGUOUS"
                if len(compatible) > 1
                else "EXACT_SCOPED_MATCH"
            )
            event = event_index[event_key]
            candidate = md_row(
                build_id,
                {
                    "source_path": event["source_path"],
                    "source_sha256": event["source_sha256"],
                    "coverage_status": event["coverage_status"],
                },
                event_key=event_key,
                execution_key=execution_key,
                matched_fields_json=md_json(sorted(matched_fields)),
                match_state=state,
            )
            result["correlation_candidate"].append(candidate)
            if state == "EXACT_SCOPED_MATCH":
                result["event_execution_link"].append(
                    {
                        **{name: candidate.get(name) for name in MD_COMMON},
                        "event_key": event_key,
                        "execution_key": execution_key,
                        "matched_fields_json": candidate["matched_fields_json"],
                        "link_state": state,
                    }
                )
    for row in result["pipeline_activity"]:
        if row["child_execution_id"]:
            matches = by_id[row["child_execution_id"]]
            result["child_run_link"].append(
                {
                    **{name: row.get(name) for name in MD_COMMON},
                    "activity_key": row["activity_key"],
                    "execution_key": row["execution_key"],
                    "child_execution_id": row["child_execution_id"],
                    "child_execution_key": matches[0]["execution_key"]
                    if len(matches) == 1
                    else None,
                    "resolution": "EXPLICIT_ID_UNIQUE_OBSERVED_SCOPE"
                    if len(matches) == 1
                    else "AMBIGUOUS"
                    if matches
                    else "UNRESOLVED_CHILD_RUN",
                }
            )
    for dataset in BRONZE_DATASETS:
        result["evidence_coverage"].append(
            md_row(
                build_id,
                dataset=dataset,
                availability="PRESENT" if dataset in source_presence else "MISSING",
                row_count=len(sources.get(dataset, []))
                if dataset in source_presence
                else None,
                source_version=source_versions.get(dataset),
                interpretation="Retained historical evidence; zero rows do not establish absence. Resource outcomes retain failed/partial polling scope.",
            )
        )
    result["evidence_coverage"].extend(
        [
            md_row(
                build_id,
                dataset="raw_activity",
                availability="PRESENT" if activity_scope_present else "MISSING",
                row_count=sum(len(doc["records"]) for doc in documents)
                if activity_scope_present
                else None,
                source_version=None,
                interpretation="Raw Admin audit evidence; provider retention/coverage applies. Folder dates are not collection times.",
            ),
            md_row(
                build_id,
                dataset="actor_ip_values",
                availability="ENABLED" if include_sensitive else "SUPPRESSED",
                row_count=len(actors) + len(ips),
                source_version=None,
                interpretation="Keys are not an access-control boundary. Raw identity/IP values require explicit opt-in and access review.",
            ),
        ]
    )
    result["build"] = [
        md_row(
            build_id,
            state="ready",
            built_at_utc=datetime.now(timezone.utc).replace(tzinfo=None),
            source_signature=source_signature,
            transformation_version=MEDALLION_VERSION,
            sensitive_values_enabled=include_sensitive,
        )
    ]
    return md_validate(result, SILVER_SCHEMAS)


def md_validate(tables, schemas):
    if set(tables) != set(schemas):
        raise ValueError("Unexpected medallion table contract")
    gate = tables["build"]
    if len(gate) != 1 or gate[0]["state"] != "ready":
        raise ValueError("Expected one ready source build")
    build_id = gate[0]["build_id"]
    for dataset, rows in tables.items():
        for row in rows:
            if set(row) - set(schemas[dataset]) or row["build_id"] != build_id:
                raise ValueError("Mixed build IDs or unexpected columns")
            for name in schemas[dataset]:
                row.setdefault(name, None)
            row["record_sha256"] = md_key(
                {name: value for name, value in row.items() if name != "record_sha256"}
            )
    for dataset, key in (
        ("audit_event", "event_key"),
        ("execution_latest", "execution_key"),
        ("pipeline_activity", "activity_key"),
        ("event_case", "event_key"),
        ("execution_fact", "execution_key"),
        ("pipeline_activity_fact", "activity_key"),
        ("event_trace_edge", "edge_key"),
    ):
        if dataset in tables:
            keys = [row[key] for row in tables[dataset]]
            if len(set(keys)) != len(keys) or None in keys:
                raise ValueError("Duplicate or missing medallion fact identity")
    return tables


def build_gold(silver, *, source_signature, max_trace_depth=32):
    md_validate(silver, SILVER_SCHEMAS)
    if type(max_trace_depth) is not int or not 1 <= max_trace_depth <= 32:
        raise ValueError("Trace depth must be 1-32")
    source_build = silver["build"][0]["build_id"]
    build_id = md_key(
        "gold", MEDALLION_VERSION, source_build, source_signature, max_trace_depth
    )
    output = {name: [] for name in GOLD_SCHEMAS}

    def gold_row(source, **values):
        row = {
            **source,
            **values,
            "source_build_id": source_build,
            "build_id": build_id,
        }
        row["record_sha256"] = md_key(row)
        return row

    for target, source in (
        ("execution_fact", "execution_latest"),
        ("pipeline_activity_fact", "pipeline_activity"),
        ("event_execution_bridge", "event_execution_link"),
        ("reported_location", "reported_location"),
        ("evidence_coverage", "evidence_coverage"),
    ):
        output[target] = [gold_row(row) for row in silver[source]]
    refs, links, activities, children, candidates, labels, locations = (
        defaultdict(list) for _ in range(7)
    )
    for row in silver["event_artifact"]:
        refs[row["event_key"]].append(row)
    for row in silver["event_execution_link"]:
        links[row["event_key"]].append(row)
    for row in silver["pipeline_activity"]:
        activities[row["execution_key"]].append(row)
    for row in silver["child_run_link"]:
        children[row["activity_key"]].append(row)
    for row in silver["correlation_candidate"]:
        candidates[row["event_key"]].append(row)
    for row in silver["artifact_observation"]:
        labels[row["artifact_key"]].append(row)
    for row in silver["reported_location"]:
        locations[row["event_key"]].append(row)
    for event in silver["audit_event"]:
        event_key = event["event_key"]
        common = {name: event.get(name) for name in MD_COMMON}
        event_labels, queue, visited, capped = [], deque(), set(), False

        def edge(
            source_type,
            source_key,
            target_type,
            target_key,
            relation,
            resolution,
            depth,
            evidence,
            *,
            case_key=event_key,
            case_common=common,
        ):
            if len(output["event_trace_edge"]) >= 500000:
                raise ValueError("Trace edge limit exceeded; no truncated build")
            provenance = {
                **case_common,
                **{
                    name: evidence.get(name)
                    for name in MD_COMMON
                    if name not in {"build_id", "record_sha256"}
                },
            }
            evidence_fields = md_json(
                {
                    "reference_field": evidence.get("reference_field"),
                    "source_field": evidence.get("source_field"),
                    "matched_fields_json": evidence.get("matched_fields_json"),
                }
            )
            output["event_trace_edge"].append(
                gold_row(
                    provenance,
                    edge_key=md_key(
                        case_key,
                        source_type,
                        source_key,
                        target_type,
                        target_key,
                        relation,
                        resolution,
                        evidence_fields,
                    ),
                    event_key=case_key,
                    source_type=source_type,
                    source_key=source_key,
                    target_type=target_type,
                    target_key=target_key,
                    relation_type=relation,
                    resolution=resolution,
                    depth=depth,
                    evidence_fields_json=evidence_fields,
                )
            )

        for ref in refs[event_key]:
            edge(
                "event",
                event_key,
                "artifact",
                ref["artifact_key"],
                "REPORTED_REFERENCE",
                ref["resolution"],
                0,
                ref,
            )
        for location in locations[event_key]:
            edge(
                "event",
                event_key,
                "reported_location",
                location["location_key"],
                "REPORTED_AUDIT_LOCATION",
                "NOT_RESOLVED_PHYSICAL_ENDPOINT",
                0,
                location,
            )
        for artifact in sorted(
            {ref["artifact_key"] for ref in refs[event_key] if ref["artifact_key"]}
        ):
            observations = labels[artifact]
            event_time = event["event_time_utc"]
            before = [
                row
                for row in observations
                if event_time
                and row["observed_at_utc"]
                and row["observed_at_utc"] <= event_time
            ]
            known = [row for row in observations if row["observed_at_utc"]]
            choices = before or known or observations
            if choices:
                target_time = (
                    max(row["observed_at_utc"] for row in before)
                    if before
                    else min(row["observed_at_utc"] for row in known)
                    if known
                    else None
                )
                names = {
                    row["item_name"]
                    for row in choices
                    if row["observed_at_utc"] == target_time
                }
                name = next(iter(names)) if len(names) == 1 else None
                timing = (
                    "LAST_OBSERVED_BEFORE_EVENT"
                    if before
                    else "LATER_OBSERVED_HINT"
                    if known
                    else "UNDATED_HINT"
                )
                if event_time is None and known:
                    timing = "EVENT_TIME_UNKNOWN_HINT"
                if len(names) > 1:
                    timing = "CONFLICTING_LABEL_HINT"
            else:
                name, timing = None, "NO_RETAINED_LABEL"
            event_labels.append(
                {"artifact_key": artifact, "name": name, "label_timing": timing}
            )
        for link in links[event_key]:
            edge(
                "event",
                event_key,
                "execution",
                link["execution_key"],
                "EXACT_CORRELATION",
                link["link_state"],
                0,
                link,
            )
            queue.append((link["execution_key"], 0))
        while queue:
            execution, depth = queue.popleft()
            if execution in visited:
                continue
            visited.add(execution)
            for activity in activities[execution]:
                edge(
                    "execution",
                    execution,
                    "activity",
                    activity["activity_key"],
                    "EXPLICIT_PARENT_RUN",
                    "SCOPED_IDENTIFIER",
                    depth,
                    activity,
                )
                edge(
                    "activity",
                    activity["activity_key"],
                    "physical_source",
                    None,
                    "EVIDENCE_GAP",
                    activity["destination_state"],
                    depth,
                    activity,
                )
                edge(
                    "activity",
                    activity["activity_key"],
                    "physical_destination",
                    None,
                    "EVIDENCE_GAP",
                    activity["destination_state"],
                    depth,
                    activity,
                )
                for child in children[activity["activity_key"]]:
                    child_key = child["child_execution_key"]
                    edge(
                        "activity",
                        activity["activity_key"],
                        "execution",
                        child_key,
                        "EXPLICIT_CHILD_RUN",
                        child["resolution"],
                        depth,
                        child,
                    )
                    if child_key and child_key not in visited:
                        if depth < max_trace_depth:
                            queue.append((child_key, depth + 1))
                        else:
                            capped = True
        if not links[event_key]:
            edge(
                "event",
                event_key,
                "execution",
                None,
                "EVIDENCE_GAP",
                "NO_RETAINED_EXACT_SCOPED_LINK",
                0,
                event,
            )
        states = {row["match_state"] for row in candidates[event_key]}
        state = (
            "CONFLICT"
            if event["validity"] != "VALID"
            else "EXACT_SCOPED_MATCH"
            if links[event_key]
            else (
                "AMBIGUOUS"
                if "AMBIGUOUS" in states
                else "UNRESOLVED_OR_SCOPE_MISMATCH"
                if states
                else "NO_RETAINED_EXACT_LINK"
            )
        )
        output["event_case"].append(
            gold_row(
                common,
                event_key=event_key,
                event_id=event["event_id"],
                event_time_utc=event["event_time_utc"],
                operation=event["operation"],
                actor_key=event["actor_key"],
                ip_key=event["ip_key"],
                reported_event_success=event["is_success"],
                validity=event["validity"],
                referenced_artifact_count=len(
                    {
                        ref["artifact_key"]
                        for ref in refs[event_key]
                        if ref["artifact_key"]
                    }
                ),
                unresolved_reference_count=sum(
                    ref["artifact_key"] is None for ref in refs[event_key]
                ),
                reported_location_count=len(
                    {row["location_key"] for row in locations[event_key]}
                ),
                artifact_labels_json=md_json(event_labels),
                linked_execution_count=len(links[event_key]),
                traced_execution_count=len(visited),
                correlation_state=state,
                trace_capped=capped,
                interpretation="Exact links are correlation, not proof of the initiating actor or causality. No links/metrics do not prove no runs. Physical movement destinations are not retained.",
            )
        )
    output["build"] = [
        gold_row(
            silver["build"][0],
            built_at_utc=datetime.now(timezone.utc).replace(tzinfo=None),
            source_signature=source_signature,
        )
    ]
    return md_validate(output, GOLD_SCHEMAS)
