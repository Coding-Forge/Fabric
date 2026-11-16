"""Question-driven analytics from existing collector files; no additional APIs."""

import json
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath

from notebooks.monitor_analytics import canonical, records, row, sha256, text, utc
from notebooks.monitor_fabric_runtime import plot_counts, to_frame

ESTATE_DOMAINS = {
    "activity": ("activity_events",),
    "catalog": (
        "catalog_workspaces",
        "catalog_items",
        "catalog_models",
        "model_tables",
        "model_columns",
        "model_measures",
        "model_relationships",
    ),
    "connections": ("connection_observations",),
    "gateways": ("gateway_observations", "gateway_datasources", "gateway_status"),
    "refresh": ("refresh_observations", "refreshable_observations"),
}
ESTATE_SOURCES = {
    "activity": ("activity",),
    "catalog": ("catalog", "items", "workspaces"),
    "connections": ("fabricconnections",),
    "gateways": ("gateways",),
    "refresh": ("datasetrefresh", "datasetrefreshable"),
}
SCANNER_KINDS = {
    "reports": "Report",
    "datasets": "SemanticModel",
    "dataflows": "Dataflow",
    "dashboards": "Dashboard",
    "datamarts": "Datamart",
}


def estate_optional(value, kind=str):
    if value is not None and type(value) is not kind:
        raise TypeError("Invalid optional metadata")
    return value


def estate_utc(value):
    if value is None:
        return None
    parsed = datetime.fromisoformat(text(value).replace("Z", "+00:00"))
    # Activity CreationTime and dataset refresh times are provider-defined UTC.
    return utc(parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).isoformat())


def estate_source_date(doc):
    parts = PurePosixPath(doc["path"]).parts
    offset = 2 if parts[:2] == ("catalog", "scans") else 1
    return datetime.strptime("/".join(parts[offset : offset + 3]), "%Y/%m/%d").strftime(
        "%Y-%m-%d"
    )


def estate_records(doc):
    if doc["issue"]:
        raise ValueError("Malformed raw JSON")
    value = doc["value"]
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, dict):
        value = value["value"]
    return records(value)


def estate_optional_records(value):
    return records(value) if value is not None else None


def estate_row(dataset, doc, key, **values):
    if "source_date" not in values:
        values["source_date"] = estate_source_date(doc)
    result = row(
        dataset,
        doc,
        key,
        coverage_status=values.pop("coverage_status", "legacy_unverified"),
        **values,
    )
    result["observed_at_utc"], result["run_id"] = None, None
    return result


def estate_activity(doc, pending):
    if not re.fullmatch(r"activity/\d{4}/\d{2}/\d{2}/\d{8}_\d+\.json", doc["path"]):
        raise ValueError("Unsupported activity file")
    for index, event in enumerate(estate_records(doc)):
        identity = estate_optional(event.get("Id"))
        if identity is not None:
            text(identity)
        actor = estate_optional(event.get("UserId") or event.get("UserKey"))
        actor_type = event.get("UserType")
        if actor_type is not None and type(actor_type) not in (int, str):
            raise TypeError("Invalid actor type")
        pending["activity_events"].append(
            estate_row(
                "activity_events",
                doc,
                identity or index,
                event_id=identity,
                event_time_utc=estate_utc(event.get("CreationTime")),
                operation=text(event["Operation"]),
                workload=estate_optional(event.get("Workload")),
                actor_key=sha256(actor.encode()) if actor else None,
                actor_type=str(actor_type) if actor_type is not None else None,
                is_success=estate_optional(event.get("IsSuccess"), bool),
                workspace_id=estate_optional(
                    event.get("WorkspaceId") or event.get("WorkSpaceId")
                ),
                item_id=estate_optional(
                    event.get("ArtifactId")
                    or event.get("DatasetId")
                    or event.get("ReportId")
                ),
                item_type=estate_optional(event.get("ItemType")),
            )
        )


def estate_catalog(doc, pending):
    if doc["issue"] or not re.fullmatch(
        r"catalog/scans/\d{4}/\d{2}/\d{2}/\d{8}_\d+\.scanResults(?:\.fullscan)?\.json",
        doc["path"],
    ):
        raise ValueError("Unsupported catalog file")
    for workspace in records(doc["value"]["workspaces"]):
        workspace_id = text(workspace["id"])
        returned = [name for name in SCANNER_KINDS if workspace.get(name) is not None]
        pending["catalog_workspaces"].append(
            estate_row(
                "catalog_workspaces",
                doc,
                workspace_id,
                workspace_id=workspace_id,
                workspace_name=estate_optional(workspace.get("name")),
                workspace_type=estate_optional(workspace.get("type")),
                state=estate_optional(workspace.get("state")),
                capacity_id=estate_optional(workspace.get("capacityId")),
                returned_collections_json=canonical(returned),
            )
        )
        for collection, kind in SCANNER_KINDS.items():
            for item in estate_optional_records(workspace.get(collection)) or []:
                fields = {
                    "workspace_id": workspace_id,
                    "item_id": text(item["id"]),
                    "item_type": kind,
                }
                identity = [workspace_id, kind, fields["item_id"]]
                pending["catalog_items"].append(
                    estate_row(
                        "catalog_items",
                        doc,
                        identity,
                        **fields,
                        item_name=estate_optional(item.get("name")),
                    )
                )
                if kind != "SemanticModel":
                    continue
                tables = estate_optional_records(item.get("tables"))
                relationships = estate_optional_records(item.get("relationships"))
                pending["catalog_models"].append(
                    estate_row(
                        "catalog_models",
                        doc,
                        identity,
                        **fields,
                        model_name=estate_optional(item.get("name")),
                        schema_coverage="returned"
                        if tables is not None
                        else "not_returned",
                        table_count=len(tables) if tables is not None else None,
                        relationship_count=len(relationships)
                        if relationships is not None
                        else None,
                    )
                )
                for table in tables or []:
                    table_name = text(table["name"])
                    columns = estate_optional_records(table.get("columns"))
                    measures = estate_optional_records(table.get("measures"))
                    pending["model_tables"].append(
                        estate_row(
                            "model_tables",
                            doc,
                            [*identity, table_name],
                            **fields,
                            table_name=table_name,
                            is_hidden=estate_optional(table.get("isHidden"), bool),
                            column_count=len(columns) if columns is not None else None,
                            measure_count=len(measures)
                            if measures is not None
                            else None,
                        )
                    )
                    for column in columns or []:
                        name = text(column["name"])
                        pending["model_columns"].append(
                            estate_row(
                                "model_columns",
                                doc,
                                [*identity, table_name, name],
                                **fields,
                                table_name=table_name,
                                column_name=name,
                                data_type=estate_optional(column.get("dataType")),
                                is_hidden=estate_optional(column.get("isHidden"), bool),
                            )
                        )
                    for measure in measures or []:
                        name = text(measure["name"])
                        expression = estate_optional(measure.get("expression"))
                        pending["model_measures"].append(
                            estate_row(
                                "model_measures",
                                doc,
                                [*identity, table_name, name],
                                **fields,
                                table_name=table_name,
                                measure_name=name,
                                data_type=estate_optional(measure.get("dataType")),
                                expression_returned=bool(expression)
                                if "expression" in measure
                                else None,
                            )
                        )
                for index, relationship in enumerate(relationships or []):
                    pending["model_relationships"].append(
                        estate_row(
                            "model_relationships",
                            doc,
                            [*identity, "relationship", index],
                            **fields,
                            from_table=text(relationship["fromTable"]),
                            from_column=text(relationship["fromColumn"]),
                            to_table=text(relationship["toTable"]),
                            to_column=text(relationship["toColumn"]),
                            from_cardinality=estate_optional(
                                relationship.get("fromCardinality")
                            ),
                            to_cardinality=estate_optional(
                                relationship.get("toCardinality")
                            ),
                            is_active=estate_optional(
                                relationship.get("isActive"), bool
                            ),
                        )
                    )


def estate_gateways(doc, pending):
    name = PurePosixPath(doc["path"]).name
    if not re.fullmatch(r"gateways/\d{4}/\d{2}/\d{2}/[^/]+\.json", doc["path"]):
        raise ValueError("Unsupported gateway file")
    for entry in estate_records(doc):
        if name == "gateways.json":
            pending["gateway_observations"].append(
                estate_row(
                    "gateway_observations",
                    doc,
                    text(entry["id"]),
                    gateway_id=entry["id"],
                    gateway_name=estate_optional(entry.get("name")),
                    gateway_type=estate_optional(entry.get("type")),
                )
            )
        elif name in {"datasources.json", "datasource_details.json"}:
            gateway, datasource = text(entry["gatewayId"]), text(entry["id"])
            pending["gateway_datasources"].append(
                estate_row(
                    "gateway_datasources",
                    doc,
                    [gateway, datasource],
                    gateway_id=gateway,
                    datasource_id=datasource,
                    datasource_name=estate_optional(entry.get("datasourceName")),
                    datasource_type=estate_optional(entry.get("datasourceType")),
                    detail_returned=name == "datasource_details.json",
                )
            )
        elif name == "status.json":
            gateway, datasource = text(entry["gatewayId"]), text(entry["datasourceId"])
            error = entry.get("error")
            if not isinstance(error, dict):
                raise TypeError("Invalid gateway status")
            code = estate_optional(error.get("code"))
            detail = error.get("pbi.error", {})
            if not isinstance(detail, dict):
                raise TypeError("Invalid gateway status details")
            http = next(
                (
                    value["detail"]
                    for value in records(detail.get("details", []))
                    if type(value.get("detail")) is int
                    and 100 <= value["detail"] <= 599
                ),
                None,
            )
            pending["gateway_status"].append(
                estate_row(
                    "gateway_status",
                    doc,
                    [gateway, datasource],
                    gateway_id=gateway,
                    datasource_id=datasource,
                    status_code=code,
                    http_status=http,
                    connectivity_observation="success_response"
                    if code == "success"
                    else "failed_or_unknown",
                )
            )
        else:
            raise ValueError("Unsupported gateway artifact")


def estate_count(value):
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError("Invalid optional count")
    return value


def estate_refresh(doc, pending):
    history = doc["path"].split("/")[0] == "datasetrefresh"
    expected = (
        "workspaces.datasets.refreshes.json"
        if history
        else "workspaces.datasets.refreshable.json"
    )
    if PurePosixPath(doc["path"]).name != expected:
        raise ValueError("Unsupported refresh file")
    for index, entry in enumerate(estate_records(doc)):
        if history:
            fields = {
                "workspace_id": text(entry["workspace_id"]),
                "item_id": text(entry["dataset_id"]),
                "item_type": "SemanticModel",
            }
            identity = entry.get("requestId", entry.get("id"))
            if identity is not None and type(identity) not in (int, str):
                raise TypeError("Invalid refresh identity")
            if isinstance(identity, str):
                text(identity)
            start, end = (
                estate_utc(entry.get("startTime")),
                estate_utc(entry.get("endTime")),
            )
            duration = None
            if start and end:
                delta = (
                    datetime.fromisoformat(end.replace("Z", "+00:00"))
                    - datetime.fromisoformat(start.replace("Z", "+00:00"))
                ).total_seconds()
                duration = delta if delta >= 0 else None
            failure_code = None
            failure = entry.get("serviceExceptionJson")
            if isinstance(failure, str):
                try:
                    parsed = json.loads(failure)
                    if isinstance(parsed, dict):
                        failure_code = estate_optional(
                            parsed.get("errorCode") or parsed.get("code")
                        )
                except (ValueError, TypeError):
                    failure_code = None
            pending["refresh_observations"].append(
                estate_row(
                    "refresh_observations",
                    doc,
                    [
                        fields["workspace_id"],
                        fields["item_id"],
                        identity if identity is not None else index,
                    ],
                    **fields,
                    dataset_name=estate_optional(entry.get("dataset_name")),
                    refresh_id=str(identity) if identity is not None else None,
                    refresh_type=estate_optional(entry.get("refreshType")),
                    status=estate_optional(entry.get("status")),
                    start_time_utc=start,
                    end_time_utc=end,
                    duration_seconds=duration,
                    failure_code=failure_code,
                )
            )
        else:
            group, capacity, schedule = (
                {} if entry.get(key) is None else entry[key]
                for key in ("group", "capacity", "refreshSchedule")
            )
            if not isinstance(group, dict) or not isinstance(capacity, dict):
                raise TypeError("Invalid refreshable parent")
            if not isinstance(schedule, dict):
                raise TypeError("Invalid refresh schedule")
            identity = text(entry["id"])
            kind = estate_optional(entry.get("kind"))
            pending["refreshable_observations"].append(
                estate_row(
                    "refreshable_observations",
                    doc,
                    identity,
                    workspace_id=estate_optional(group.get("id")),
                    item_id=identity,
                    item_type="SemanticModel"
                    if kind in {"Dataset", "SemanticModel"}
                    else kind or "Unknown",
                    dataset_name=estate_optional(entry.get("name")),
                    capacity_id=estate_optional(capacity.get("id")),
                    refresh_count=estate_count(entry.get("refreshCount")),
                    refresh_failures=estate_count(entry.get("refreshFailures")),
                    schedule_enabled=estate_optional(schedule.get("enabled"), bool),
                )
            )


def estate_connections(runs, output):
    for run in runs.values():
        if run["module"] != "fabricconnections":
            continue
        manifest = run["manifest"]
        status, issue, pending = "invalid", "invalid_connection_run", []
        if run["valid"] and not manifest["finished"]:
            status, issue = "unfinished", "unfinished_connection_run"
        elif run["valid"]:
            try:
                if len(run["resources"]) != 1:
                    raise ValueError("Invalid connection resource count")
                doc = run["resources"][0]
                resource = doc["value"]
                if (
                    PurePosixPath(doc["path"]).name != "connections.json"
                    or resource["requestPath"] != "connections"
                    or resource["parent"]
                ):
                    raise ValueError("Invalid connection resource identity")
                if resource["complete"]:
                    for entry in records(resource["records"]):
                        details = entry["connectionDetails"]
                        if not isinstance(details, dict):
                            raise TypeError("Invalid connection type")
                        pending.append(
                            row(
                                "connection_observations",
                                doc,
                                text(entry["id"]),
                                connection_id=entry["id"],
                                connection_name=estate_optional(entry["displayName"]),
                                gateway_id=estate_optional(entry.get("gatewayId")),
                                connectivity_type=text(entry["connectivityType"]),
                                privacy_level=estate_optional(
                                    entry.get("privacyLevel")
                                ),
                                connection_type=text(details["type"]),
                            )
                        )
                    status = "success" if manifest["complete"] else "partial"
                    issue = "caller_visible_only_endpoints_and_credentials_excluded"
                    unique = {}
                    for entry in pending:
                        key = entry["observation_id"]
                        if key in unique and unique[key] != entry:
                            raise ValueError("Conflicting connection identity")
                        unique[key] = entry
                else:
                    status, issue = "failed", "connection_resource_failed"
            except (ValueError, TypeError, KeyError, AttributeError):
                status, issue, pending = "invalid", "invalid_connection_metadata", []
        output["connection_observations"].extend(pending)
        output["estate_coverage"].append(
            row(
                "estate_coverage",
                run["doc"],
                "connections",
                analysis="connections",
                coverage_status=status,
                issue=issue,
                record_count=len(pending) if status in {"success", "partial"} else None,
            )
        )


def estate_inventory(documents, output):
    indexed = {doc["path"]: doc for doc in documents}
    for entry in output["inventory"]:
        source = entry["inventory_source"]
        if source not in {"legacy_items", "legacy_workspaces"}:
            continue
        doc = indexed[entry["source_path"]]
        if source == "legacy_items":
            output["catalog_items"].append(
                estate_row(
                    "catalog_items",
                    doc,
                    [entry["workspace_id"], entry["item_id"], entry["item_type"]],
                    workspace_id=entry["workspace_id"],
                    item_id=entry["item_id"],
                    item_type=entry["item_type"],
                    item_name=entry["item_name"],
                )
            )
        else:
            output["catalog_workspaces"].append(
                estate_row(
                    "catalog_workspaces",
                    doc,
                    entry["workspace_id"],
                    workspace_id=entry["workspace_id"],
                    workspace_name=entry["item_name"],
                )
            )
    for health in output["collection_health"]:
        if health["module"] not in {"items", "workspaces"}:
            continue
        doc = indexed.get(health["source_path"])
        if doc is None:
            continue
        output["estate_coverage"].append(
            estate_row(
                "estate_coverage",
                doc,
                "catalog_inventory",
                analysis="catalog",
                coverage_status=health["coverage_status"],
                source_date=estate_source_date(doc)
                if health["coverage_status"] != "invalid"
                else None,
                record_count=health["record_count"],
                issue="legacy_item_inventory_not_physical_schema",
            )
        )


def transform_estate(documents, runs, output):
    estate_connections(runs, output)
    estate_inventory(documents, output)
    for doc in documents:
        prefix = doc["path"].split("/")[0]
        domain = next(
            (
                name
                for name, sources in ESTATE_SOURCES.items()
                if prefix in sources and name != "connections"
            ),
            None,
        )
        if domain is None or (
            domain == "catalog" and not doc["path"].startswith("catalog/scans/")
        ):
            continue
        if domain == "gateways" and PurePosixPath(doc["path"]).name == "users.json":
            continue
        pending = {name: [] for name in ESTATE_DOMAINS[domain]}
        status, issue, count, source_date = (
            "legacy_unverified",
            "no_completion_manifest_or_exact_collection_time",
            None,
            None,
        )
        try:
            source_date = estate_source_date(doc)
            {
                "activity": estate_activity,
                "catalog": estate_catalog,
                "gateways": estate_gateways,
                "refresh": estate_refresh,
            }[domain](doc, pending)
            for entries in pending.values():
                unique = {}
                for entry in entries:
                    identity = entry["observation_id"]
                    if identity in unique and unique[identity] != entry:
                        raise ValueError("Conflicting raw identity")
                    unique[identity] = entry
            count = sum(len(entries) for entries in pending.values())
            if domain == "catalog":
                issue = "semantic_model_schema_only_physical_schemas_uncollected"
            for dataset, entries in pending.items():
                output[dataset].extend(entries)
        except (ValueError, TypeError, KeyError, AttributeError, IndexError):
            status, issue = "invalid", "invalid_or_unsupported_estate_artifact"
        output["estate_coverage"].append(
            estate_row(
                "estate_coverage",
                doc,
                domain,
                analysis=domain,
                coverage_status=status,
                source_date=source_date,
                record_count=count,
                issue=issue,
            )
        )


def preview_estate(spark_session, display_frame, tables, domain):
    from pyspark.sql import functions as F

    coverage = [
        entry for entry in tables["estate_coverage"] if entry["analysis"] == domain
    ]
    if not coverage:
        print(
            f"{domain}: no supported collected files. NOT COLLECTED, not successful zero."
        )
    else:
        display_frame(
            to_frame(spark_session, "estate_coverage", coverage)
            .groupBy("coverage_status", "issue")
            .count()
            .orderBy("coverage_status", "issue")
        )
    frames = {
        name: to_frame(spark_session, name, tables[name])
        for name in ESTATE_DOMAINS[domain]
    }
    print(
        "Charts use retained raw-file observations, not proof of current or complete estate coverage."
    )
    if domain == "activity":
        frame = frames["activity_events"]
        plot_counts(frame, "operation", "Retained activity observations by operation")
        display_frame(
            frame.groupBy("workload", "operation").agg(
                F.count("*").alias("observations"),
                F.countDistinct("event_id").alias("known_event_ids"),
                F.countDistinct("actor_key").alias("pseudonymous_actors"),
            )
        )
        display_frame(
            frame.groupBy(
                F.substring("event_time_utc", 1, 10).alias("event_date_utc")
            ).count()
        )
        print(
            "Actor keys are unsalted pseudonyms, not anonymous identities. UPNs, IPs and event payloads are excluded."
        )
    elif domain == "catalog":
        plot_counts(
            frames["catalog_items"], "item_type", "Scanner-returned item observations"
        )
        plot_counts(
            frames["catalog_models"],
            "schema_coverage",
            "Semantic-model schema availability",
        )
        plot_counts(frames["model_columns"], "data_type", "Returned model column types")
        display_frame(
            frames["catalog_models"]
            .select(
                "workspace_id",
                "item_id",
                "model_name",
                "schema_coverage",
                "table_count",
                "relationship_count",
                "source_date",
            )
            .limit(100)
        )
        display_frame(
            frames["model_columns"]
            .select(
                "workspace_id",
                "item_id",
                "table_name",
                "column_name",
                "data_type",
                "is_hidden",
            )
            .limit(100)
        )
        display_frame(
            frames["model_measures"]
            .select(
                "workspace_id",
                "item_id",
                "table_name",
                "measure_name",
                "expression_returned",
            )
            .limit(100)
        )
        display_frame(
            frames["model_relationships"]
            .select(
                "workspace_id",
                "item_id",
                "from_table",
                "from_column",
                "to_table",
                "to_column",
                "is_active",
            )
            .limit(100)
        )
        print(
            "Tables/columns/measures/relationships are available in managed model_* tables after publishing."
        )
        print(
            "Missing schema is not an empty model. Physical Lakehouse/Warehouse schemas and expression text are not exported."
        )
    elif domain == "connections":
        plot_counts(
            frames["connection_observations"],
            "connection_type",
            "Retained caller-visible connection types",
        )
        display_frame(
            frames["connection_observations"]
            .groupBy("connectivity_type", "privacy_level")
            .count()
        )
        display_frame(
            frames["connection_observations"]
            .filter(F.col("gateway_id").isNotNull())
            .groupBy("gateway_id")
            .agg(F.countDistinct("connection_id").alias("observed_connections"))
        )
        display_frame(
            frames["connection_observations"]
            .select(
                "connection_id",
                "connection_name",
                "connection_type",
                "connectivity_type",
                "gateway_id",
                "privacy_level",
                "observed_at_utc",
            )
            .limit(100)
        )
        print(
            "Caller-visible only. Failure/empty latest attempts do not prove older connections are current. Endpoints and credentials are excluded."
        )
    elif domain == "gateways":
        plot_counts(
            frames["gateway_datasources"],
            "datasource_type",
            "Retained datasource type observations",
        )
        plot_counts(
            frames["gateway_status"],
            "connectivity_observation",
            "Retained gateway connectivity observations",
        )
        display_frame(
            frames["gateway_status"]
            .groupBy("source_date", "status_code", "http_status")
            .count()
        )
        display_frame(
            frames["gateway_observations"]
            .select(
                "gateway_id",
                "gateway_name",
                "gateway_type",
                "source_date",
            )
            .limit(100)
        )
        display_frame(
            frames["gateway_datasources"]
            .select(
                "gateway_id",
                "datasource_id",
                "datasource_name",
                "datasource_type",
                "detail_returned",
                "source_date",
            )
            .limit(100)
        )
        paths = [entry["source_path"] for entry in coverage]
        for name in (
            "gateways.json",
            "datasources.json",
            "datasource_details.json",
            "status.json",
        ):
            if not any(path.endswith("/" + name) for path in paths):
                print(f"{name}: NOT COLLECTED; missing is not healthy/empty.")
        print(
            "Gateway API visibility is not tenant completeness or guaranteed VNet coverage. Status lacks exact observation time; users and connection details are excluded."
        )
    elif domain == "refresh":
        frame = frames["refresh_observations"]
        plot_counts(frame, "status", "Retained dataset refresh status observations")
        display_frame(
            frame.groupBy("status", "refresh_type").agg(
                F.count("*").alias("observations"),
                F.countDistinct("workspace_id", "item_id", "refresh_id").alias(
                    "known_refresh_keys"
                ),
                F.avg("duration_seconds").alias("mean_known_duration_seconds"),
            )
        )
        display_frame(
            frames["refreshable_observations"]
            .groupBy("schedule_enabled")
            .agg(
                F.count("*").alias("observations"),
                F.sum("refresh_failures").alias("reported_failure_observations"),
            )
        )
        display_frame(
            frame.filter(F.col("failure_code").isNotNull())
            .groupBy(
                "workspace_id",
                "item_id",
                "failure_code",
            )
            .count()
            .orderBy(F.desc("count"))
            .limit(100)
        )
        for source in ESTATE_SOURCES["refresh"]:
            if not any(entry["module"] == source for entry in coverage):
                print(f"{source}: NOT COLLECTED, not zero refreshes.")
        print(
            "Power BI semantic-model refresh only, not all Fabric jobs. Repeated history windows are retained observations; averages are not deduplicated run-level KPIs. Error messages are excluded."
        )
