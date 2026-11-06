"""Data-led semantic model registry and pure lookup construction."""

import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from notebooks.monitor_analytics import COMMON, SCHEMAS

PREFIX = "monitor_report_"
WORKSPACE = "1f681810-ec02-411f-ac4b-9b5544272273"
LAKEHOUSE = "f1d6b7d9-f02b-4a44-9828-8dd5da8d6822"
PROJECT = Path(__file__).resolve().parents[1]
FACTS = {
    "collection_health": ("Collection Health", "Confidence"),
    "inventory": ("Item Inventory", "Inventory"),
    "permission_cycles": ("Permission Cycles", "Access"),
    "permission_resources": ("Permission Polls", "Access"),
    "permission_grants": ("Permission Grants", "Access"),
    "job_resources": ("Job Polls", "Reliability"),
    "job_observations": ("Job History", "Reliability"),
    "lineage_resources": ("Lineage Coverage", "Lineage"),
    "lineage_edges": ("Lineage Edges", "Lineage"),
    "lineage_diagnostics": ("Lineage Diagnostics", "Lineage"),
    "estate_coverage": ("Domain Coverage", "Confidence"),
    "activity_events": ("Activity Events", "Activity"),
    "catalog_workspaces": ("Workspace Catalog", "Inventory"),
    "catalog_items": ("Item Catalog", "Inventory"),
    "catalog_models": ("Semantic Model Catalog", "Schema"),
    "model_tables": ("Model Tables", "Schema"),
    "model_columns": ("Model Columns", "Schema"),
    "model_measures": ("Model Measures", "Schema"),
    "model_relationships": ("Model Relationships", "Schema"),
    "connection_observations": ("Connection Inventory", "Connectivity"),
    "gateway_observations": ("Gateway Inventory", "Connectivity"),
    "gateway_datasources": ("Gateway Datasources", "Connectivity"),
    "gateway_status": ("Gateway Status", "Connectivity"),
    "refresh_observations": ("Refresh History", "Reliability"),
    "refreshable_observations": ("Refreshables", "Reliability"),
    "apps": ("App Inventory", "Organization"),
    "capacities": ("Capacity Inventory", "Capacity"),
    "capacity_metric_observations": ("Capacity Metrics", "Capacity"),
    "directory_users": ("Directory Users", "Directory"),
    "directory_groups": ("Directory Groups", "Directory"),
    "group_memberships": ("Group Memberships", "Directory"),
    "user_licenses": ("User Licenses", "Directory"),
    "subscribed_skus": ("Subscribed SKUs", "Directory"),
    "workspace_role_scopes": ("Workspace Role Coverage", "Access"),
    "workspace_role_assignments": ("Workspace Role Assignments", "Access"),
    "tenant_settings": ("Tenant Settings", "Governance"),
    "delegated_setting_scopes": ("Delegated Setting Scopes", "Governance"),
    "delegated_setting_overrides": ("Delegated Overrides", "Governance"),
    "tenant_setting_groups": ("Setting Group Rules", "Governance"),
    "domains": ("Domain Inventory", "Organization"),
    "domain_workspaces": ("Domain Workspaces", "Organization"),
    "workspace_git_connections": ("Git Connections", "Change"),
    "tags": ("Tag Inventory", "Organization"),
    "organization_shares": ("Organization Sharing", "Access"),
    "publish_to_web_shares": ("Public Sharing", "Access"),
    "deployment_pipelines": ("Deployment Pipelines", "Change"),
    "deployment_operation_resources": ("Deployment Polls", "Change"),
    "deployment_operations": ("Deployment Operations", "Change"),
}
assert set(FACTS) == set(SCHEMAS)

# Keys are contextual identities, never a relationship between repeated snapshots.
ENTITIES = {
    "workspace": ("Workspace", ("workspace_id",), ("workspace_name",)),
    "item": (
        "Item",
        ("workspace_id", "item_id"),
        ("item_name", "model_name", "dataset_name"),
    ),
    "capacity": ("Capacity", ("capacity_id",), ("capacity_name",)),
    "gateway": ("Gateway", ("gateway_id",), ("gateway_name",)),
    "connection": ("Connection", ("connection_id",), ("connection_name",)),
    "principal": ("Principal", ("principal_id",), ()),
    "group": ("Directory Group", ("group_id",), ()),
    "sku": ("License SKU", ("sku_id",), ("sku_part_number",)),
    "domain": ("Domain", ("domain_id",), ("domain_name",)),
    "pipeline": ("Deployment Pipeline", ("pipeline_id",), ("pipeline_name",)),
    "datasource": ("Datasource", ("gateway_id", "datasource_id"), ("datasource_name",)),
    "setting": ("Setting", ("setting_name",), ("title", "setting_name")),
    "app": ("Application", ("app_id",), ("app_name",)),
    "tag": ("Tag", ("tag_id",), ("tag_name",)),
}
LOOKUP_TYPES = {
    "entity_key": "string",
    "entity_id": "string",
    "workspace_id": "string",
    "label": "string",
    "item_type": "string",
    "label_basis": "string",
}
CONTEXT_TYPES = {
    "observation_id": "string",
    "dataset": "string",
    "source_key": "string",
    **{f"{name}_key": "string" for name in ENTITIES},
    "related_workspace_key": "string",
    "related_item_key": "string",
    "observed_date_key": "long",
    "source_date_key": "long",
    "event_date_key": "long",
    "metric_date_key": "long",
    "observed_at": "timestamp",
    "coverage_status": "string",
    "module": "string",
    "run_id": "string",
    "cycle_id": "string",
    "mode": "string",
}
DATE_TYPES = {
    "date_key": "long",
    "date": "date",
    "year": "long",
    "month_number": "long",
    "year_month": "string",
    "day_of_week": "string",
}
DATASET_TYPES = {
    "dataset": "string",
    "label": "string",
    "domain": "string",
    "profiled_rows": "long",
    "delta_version": "long",
    "availability": "string",
    "latest_exact_observation": "timestamp",
    "latest_source_date": "date",
    "profiled_at": "timestamp",
}
BUILD_TYPES = {
    "state": "string",
    "built_at": "timestamp",
    "source_rows": "long",
    "source_datasets": "long",
    "nonempty_datasets": "long",
    "source_signature": "string",
    "contract_version": "long",
}
SOURCE_TYPES = {
    "source_key": "string",
    "module": "string",
    "source_path": "string",
    "source_sha256": "string",
}
DERIVED_SCHEMAS = {
    **{name: LOOKUP_TYPES for name in ENTITIES},
    "context": CONTEXT_TYPES,
    "date": DATE_TYPES,
    "dataset": DATASET_TYPES,
    "build": BUILD_TYPES,
    "source": SOURCE_TYPES,
    "permission_mode": {"mode": "string"},
}
SPECIAL_MODELS = {
    "context": "Observation Context",
    "dataset": "Dataset",
    "build": "Estate Measures",
    "source": "Evidence Source",
    "permission_mode": "Permission Mode",
}
DATE_ROLES = {
    "Collection Date": "observed_date_key",
    "Source Folder Date": "source_date_key",
    "Event Date": "event_date_key",
    "Metric Query Date": "metric_date_key",
}


def key(kind, values):
    normalized = [
        value.lower() if isinstance(value, str) and len(value) == 36 else value
        for value in values
    ]
    return hashlib.sha256(
        json.dumps(
            [kind, *normalized], separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()


def utc(value):
    if not value:
        return None
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("An exact observation timestamp must include its timezone")
    return result.astimezone(timezone.utc)


def day(value):
    return date.fromisoformat(value[:10]) if value else None


def date_key(value):
    parsed = day(value)
    return int(parsed.strftime("%Y%m%d")) if parsed else None


def frame(rows, types):
    arrow_types = {
        "string": pa.string(),
        "long": pa.int64(),
        "int": pa.int32(),
        "double": pa.float64(),
        "boolean": pa.bool_(),
        "timestamp": pa.timestamp("us", tz="UTC"),
        "date": pa.date32(),
    }
    return pa.Table.from_pylist(
        rows,
        schema=pa.schema([(name, arrow_types[kind]) for name, kind in types.items()]),
    )


def build_dimensions(sources, profile):
    if set(sources) != set(SCHEMAS):
        raise ValueError("All 48 contracted sources are required; missing is not empty")
    entities = {name: {} for name in ENTITIES}
    sources_index = {}
    context = []
    seen = set()
    dates = set()

    def retain(kind, row, rank):
        label, columns, label_columns = ENTITIES[kind]
        values = [row.get(column) for column in columns]
        if not values[-1] or (kind == "item" and row.get("item_type") == "Workspace"):
            return None
        identity = key(kind, values)
        name = next(
            (row.get(column) for column in label_columns if row.get(column)), None
        )
        if kind == "workspace" and row.get("item_type") == "Workspace":
            name = row.get("item_name") or name
        record = {
            "entity_key": identity,
            "entity_id": str(values[-1]),
            "workspace_id": row.get("workspace_id")
            if kind in ("workspace", "item")
            else None,
            "label": name or f"{label} {str(values[-1])[:8]}",
            "item_type": row.get("item_type") if kind == "item" else None,
            "label_basis": "Latest retained descriptive label; not historical/current-state authority"
            if name
            else "Identifier only; descriptive metadata not returned",
        }
        previous = entities[kind].get(identity)
        # A newer missing label must not erase a useful returned name.
        score = (bool(name), rank, record["label"])
        if previous is None or score > previous[0]:
            entities[kind][identity] = (score, record)
        return identity

    for dataset, table in sources.items():
        expected = set(COMMON | SCHEMAS[dataset])
        if not expected.issubset(table.column_names):
            raise ValueError(f"Schema mismatch in {dataset}")
        for row in table.to_pylist():
            observation = row["observation_id"]
            if not observation or observation in seen:
                raise ValueError(
                    "Observation identities must be nonnull and globally unique"
                )
            seen.add(observation)
            rank = (
                row.get("observed_at_utc") or row.get("source_date") or "",
                row["source_sha256"] or "",
            )
            context_row = {name: None for name in CONTEXT_TYPES}
            context_row.update(
                {
                    "observation_id": observation,
                    "dataset": dataset,
                    "observed_at": utc(row.get("observed_at_utc")),
                    **{
                        name: row.get(name)
                        for name in (
                            "coverage_status",
                            "module",
                            "run_id",
                            "cycle_id",
                            "mode",
                        )
                    },
                }
            )
            for kind in ENTITIES:
                context_row[f"{kind}_key"] = retain(kind, row, rank)
            for kind in ("workspace", "item"):
                related = {
                    "workspace_id": row.get("related_workspace_id"),
                    "item_id": row.get("related_item_id"),
                    "item_type": row.get("related_type"),
                }
                context_row[f"related_{kind}_key"] = retain(kind, related, rank)
            source_key = key(
                "source", (row["module"], row["source_path"], row["source_sha256"])
            )
            sources_index[source_key] = {
                "source_key": source_key,
                **{
                    name: row[name]
                    for name in ("module", "source_path", "source_sha256")
                },
            }
            context_row["source_key"] = source_key
            date_values = {
                "observed_date_key": row.get("observed_at_utc"),
                "source_date_key": row.get("source_date"),
                "event_date_key": row.get("event_time_utc")
                or row.get("start_time_utc")
                or row.get("execution_start_utc"),
                "metric_date_key": row.get("metric_date"),
            }
            for column, value in date_values.items():
                context_row[column] = date_key(value)
                if value:
                    dates.add(day(value))
            context.append(context_row)
    if dates:
        cursor, end = min(dates), max(dates)
        date_rows = []
        while cursor <= end:
            date_rows.append(
                {
                    "date_key": int(cursor.strftime("%Y%m%d")),
                    "date": cursor,
                    "year": cursor.year,
                    "month_number": cursor.month,
                    "year_month": cursor.strftime("%Y-%m"),
                    "day_of_week": cursor.strftime("%A"),
                }
            )
            cursor += timedelta(days=1)
    else:
        date_rows = []
    built_at = utc(profile["profiled_at_utc"])
    dataset_rows = []
    for dataset, info in profile["datasets"].items():
        dataset_rows.append(
            {
                "dataset": dataset,
                "label": FACTS[dataset][0],
                "domain": FACTS[dataset][1],
                "profiled_rows": info["row_count"],
                "delta_version": info["delta_version"],
                "availability": "Retained observations"
                if info["row_count"]
                else "No curated rows; inspect coverage before inferring absence",
                "latest_exact_observation": utc(
                    info["time_ranges"]["observed_at_utc"]["max"]
                ),
                "latest_source_date": day(
                    info["time_ranges"].get("source_date", {}).get("max")
                ),
                "profiled_at": built_at,
            }
        )
    output = {
        name: frame([value[1] for _, value in sorted(index.items())], LOOKUP_TYPES)
        for name, index in entities.items()
    }
    signature = key(
        "source-versions",
        [
            (name, info["delta_version"], info["cache_sha256"])
            for name, info in sorted(profile["datasets"].items())
        ],
    )
    output.update(
        {
            "context": frame(context, CONTEXT_TYPES),
            "source": frame(list(sources_index.values()), SOURCE_TYPES),
            "date": frame(date_rows, DATE_TYPES),
            "dataset": frame(dataset_rows, DATASET_TYPES),
            "permission_mode": frame(
                [{"mode": "Scoped"}, {"mode": "Tenant"}], {"mode": "string"}
            ),
            "build": frame(
                [
                    {
                        "state": "ready",
                        "built_at": built_at,
                        "source_rows": len(context),
                        "source_datasets": len(SCHEMAS),
                        "nonempty_datasets": sum(
                            info["row_count"] > 0
                            for info in profile["datasets"].values()
                        ),
                        "source_signature": signature,
                        "contract_version": 1,
                    }
                ],
                BUILD_TYPES,
            ),
        }
    )
    validate_dimensions(output, sources)
    return output


def validate_dimensions(dimensions, sources):
    context = dimensions["context"].to_pylist()
    expected_ids = {
        row
        for table in sources.values()
        for row in table.column("observation_id").to_pylist()
    }
    if (
        len(context) != len(expected_ids)
        or {row["observation_id"] for row in context} != expected_ids
    ):
        raise ValueError("Observation context must cover every source row exactly once")
    for kind in ENTITIES:
        ids = dimensions[kind].column("entity_key").to_pylist()
        if len(set(ids)) != len(ids) or any(value is None for value in ids):
            raise ValueError(f"Nonunique dimension key: {kind}")
        valid = set(ids)
        fields = [f"{kind}_key"]
        if kind in ("workspace", "item"):
            fields.append(f"related_{kind}_key")
        if any(
            row[field] is not None and row[field] not in valid
            for row in context
            for field in fields
        ):
            raise ValueError(f"Unmatched dimension key: {kind}")
    for field in DATE_ROLES.values():
        valid = set(dimensions["date"].column("date_key").to_pylist())
        if any(row[field] is not None and row[field] not in valid for row in context):
            raise ValueError("Unmatched date role")


def title(name):
    acronyms = {
        "id": "ID",
        "ids": "IDs",
        "utc": "UTC",
        "json": "JSON",
        "sku": "SKU",
        "skus": "SKUs",
        "http": "HTTP",
        "git": "Git",
    }
    return " ".join(acronyms.get(word, word.title()) for word in name.split("_"))
