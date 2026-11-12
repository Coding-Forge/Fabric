"""Pure transformations embedded into the uploadable Monitor notebooks."""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import UUID

from env.utility.eventstream_topology import (
    EVENTSTREAM_MODULE,
    eventstream_hash,
    eventstream_inventory,
    eventstream_scope,
    validate_eventstream_topology,
)
from env.utility.notebook_relationships import notebook_lakehouse_relationships
from env.utility.shortcut_relationships import (
    SHORTCUT_MODULE,
    shortcut_fingerprint,
    shortcut_inventory,
    shortcut_scope,
    validate_shortcut_records,
)

SCHEMA_VERSION = 1
LAKEHOUSE_FILES = "/lakehouse/default/Files"
PERMISSIONS = {
    "fabricitemaccesspermissions": "Scoped",
    "fabricitemaccesspermissions_tenant": "Tenant",
}
MODULES = (
    *PERMISSIONS,
    "fabricitemjobhistory",
    "fabricitemdefinitions",
    "fabricconnections",
    "fabricdeploymentpipelineoperations",
)
CORE_SOURCE_PREFIXES = {*MODULES, "items", "workspaces", "catalog", "lineage_edges"}
SHORTCUT_PREFIXES = {SHORTCUT_MODULE}
EVENTSTREAM_PREFIXES = {EVENTSTREAM_MODULE}
POWER_BI = {"Report", "Dashboard", "SemanticModel", "App", "Dataflow"}
COMMON = {
    "schema_version": "int",
    "observation_id": "string",
    "source_path": "string",
    "source_sha256": "string",
    "record_sha256": "string",
    "observed_at_utc": "string",
    "module": "string",
    "mode": "string",
    "run_id": "string",
    "cycle_id": "string",
    "coverage_status": "string",
}
TARGET_COLUMNS = {
    "workspace_id": "string",
    "item_id": "string",
    "item_type": "string",
}
SCHEMAS = {
    "collection_health": {
        "complete": "boolean",
        "finished": "boolean",
        "successful_resources": "long",
        "failed_resources": "long",
        "record_count": "long",
        "coverage": "string",
        "issue": "string",
    },
    "inventory": {
        **TARGET_COLUMNS,
        "item_name": "string",
        "inventory_source": "string",
    },
    "permission_cycles": {
        "chain_valid": "boolean",
        "cycle_finished": "boolean",
        "cycle_healthy": "boolean",
        "slice_count": "long",
        "selected_items": "long",
    },
    "permission_resources": {
        **TARGET_COLUMNS,
        "observation_unit": "string",
        "record_count": "long",
        "resource_outcome": "string",
    },
    "permission_grants": {
        **TARGET_COLUMNS,
        "principal_id": "string",
        "principal_type": "string",
        "permissions_json": "string",
        "additional_permissions_json": "string",
    },
    "job_resources": {**TARGET_COLUMNS, "record_count": "long"},
    "job_observations": {
        **TARGET_COLUMNS,
        "job_id": "string",
        "job_type": "string",
        "invoke_type": "string",
        "status": "string",
        "start_time_utc": "string",
        "end_time_utc": "string",
        "duration_seconds": "double",
        "root_activity_id": "string",
        "failure_code": "string",
    },
    "lineage_resources": {
        **TARGET_COLUMNS,
        "evidence_type": "string",
        "record_count": "long",
        "diagnostic_count": "long",
    },
    "lineage_edges": {
        **TARGET_COLUMNS,
        "related_workspace_id": "string",
        "related_item_id": "string",
        "related_type": "string",
        "direction": "string",
        "relation_type": "string",
        "reference": "string",
        "resolution": "string",
        "evidence_type": "string",
        "runtime_verified": "boolean",
    },
    "lineage_diagnostics": {
        **TARGET_COLUMNS,
        "reason": "string",
        "location": "string",
    },
}
CORE_DATASETS = tuple(SCHEMAS)
ESTATE_SCHEMAS = {
    "estate_coverage": {
        "analysis": "string",
        "source_date": "string",
        "record_count": "long",
        "issue": "string",
    },
    "activity_events": {
        **TARGET_COLUMNS,
        "event_id": "string",
        "event_time_utc": "string",
        "operation": "string",
        "workload": "string",
        "actor_key": "string",
        "actor_type": "string",
        "is_success": "boolean",
        "source_date": "string",
    },
    "catalog_workspaces": {
        "workspace_id": "string",
        "workspace_name": "string",
        "workspace_type": "string",
        "state": "string",
        "capacity_id": "string",
        "returned_collections_json": "string",
        "source_date": "string",
    },
    "catalog_items": {
        **TARGET_COLUMNS,
        "item_name": "string",
        "source_date": "string",
    },
    "catalog_models": {
        **TARGET_COLUMNS,
        "model_name": "string",
        "schema_coverage": "string",
        "table_count": "long",
        "relationship_count": "long",
        "source_date": "string",
    },
    "model_tables": {
        **TARGET_COLUMNS,
        "table_name": "string",
        "is_hidden": "boolean",
        "column_count": "long",
        "measure_count": "long",
        "source_date": "string",
    },
    "model_columns": {
        **TARGET_COLUMNS,
        "table_name": "string",
        "column_name": "string",
        "data_type": "string",
        "is_hidden": "boolean",
        "source_date": "string",
    },
    "model_measures": {
        **TARGET_COLUMNS,
        "table_name": "string",
        "measure_name": "string",
        "data_type": "string",
        "expression_returned": "boolean",
        "source_date": "string",
    },
    "model_relationships": {
        **TARGET_COLUMNS,
        "from_table": "string",
        "from_column": "string",
        "to_table": "string",
        "to_column": "string",
        "from_cardinality": "string",
        "to_cardinality": "string",
        "is_active": "boolean",
        "source_date": "string",
    },
    "connection_observations": {
        "connection_id": "string",
        "connection_name": "string",
        "gateway_id": "string",
        "connectivity_type": "string",
        "privacy_level": "string",
        "connection_type": "string",
    },
    "gateway_observations": {
        "gateway_id": "string",
        "gateway_name": "string",
        "gateway_type": "string",
        "source_date": "string",
    },
    "gateway_datasources": {
        "gateway_id": "string",
        "datasource_id": "string",
        "datasource_name": "string",
        "datasource_type": "string",
        "detail_returned": "boolean",
        "source_date": "string",
    },
    "gateway_status": {
        "gateway_id": "string",
        "datasource_id": "string",
        "status_code": "string",
        "http_status": "long",
        "connectivity_observation": "string",
        "source_date": "string",
    },
    "refresh_observations": {
        **TARGET_COLUMNS,
        "dataset_name": "string",
        "refresh_id": "string",
        "refresh_type": "string",
        "status": "string",
        "start_time_utc": "string",
        "end_time_utc": "string",
        "duration_seconds": "double",
        "failure_code": "string",
        "source_date": "string",
    },
    "refreshable_observations": {
        **TARGET_COLUMNS,
        "dataset_name": "string",
        "capacity_id": "string",
        "refresh_count": "long",
        "refresh_failures": "long",
        "schedule_enabled": "boolean",
        "source_date": "string",
    },
}
SCHEMAS.update(ESTATE_SCHEMAS)
ESTATE_DATASETS = tuple(SCHEMAS)
ESTATE_PREFIXES = {"activity", "gateways", "datasetrefresh", "datasetrefreshable"}
MODULE_PREFIXES = {
    "capacity",
    "capacity_metrics",
    "graph",
    "roles",
    "tenant",
    "delegatedsettings",
    "domains",
    "gitconnections",
    "tags",
    "widelysharedlinks",
}
MODULE_SCHEMAS = {
    "apps": {
        "app_id": "string",
        "app_name": "string",
        "workspace_id": "string",
        "last_update_utc": "string",
        "source_date": "string",
    },
    "capacities": {
        "capacity_id": "string",
        "capacity_name": "string",
        "sku": "string",
        "state": "string",
        "region": "string",
        "source_date": "string",
    },
    "capacity_metric_observations": {
        "capacity_id": "string",
        "sku": "string",
        "metric_group": "string",
        "metric_date": "string",
        "timepoint_raw": "string",
        "timepoint_utc": "string",
        "metric_name": "string",
        "metric_value": "double",
        "source_date": "string",
    },
    "directory_users": {
        "principal_id": "string",
        "account_enabled": "boolean",
        "user_type": "string",
        "assigned_license_count": "long",
        "source_date": "string",
    },
    "directory_groups": {
        "group_id": "string",
        "security_enabled": "boolean",
        "mail_enabled": "boolean",
        "group_types_json": "string",
        "is_audience_group": "boolean",
        "source_date": "string",
    },
    "group_memberships": {
        "group_id": "string",
        "principal_id": "string",
        "membership_kind": "string",
        "is_audience_group": "boolean",
        "source_date": "string",
    },
    "user_licenses": {
        "principal_id": "string",
        "sku_id": "string",
        "disabled_plans_json": "string",
        "source_date": "string",
    },
    "subscribed_skus": {
        "sku_id": "string",
        "sku_part_number": "string",
        "capability_status": "string",
        "consumed_units": "long",
        "enabled_units": "long",
        "suspended_units": "long",
        "warning_units": "long",
        "source_date": "string",
    },
    "workspace_role_scopes": {
        "workspace_id": "string",
        "roles_returned": "boolean",
        "assignment_count": "long",
        "source_date": "string",
    },
    "workspace_role_assignments": {
        "workspace_id": "string",
        "principal_id": "string",
        "principal_type": "string",
        "workspace_role": "string",
        "source_date": "string",
    },
    "tenant_settings": {
        "setting_name": "string",
        "title": "string",
        "setting_group": "string",
        "enabled": "boolean",
        "can_specify_groups": "boolean",
        "enabled_group_count": "long",
        "excluded_group_count": "long",
        "source_date": "string",
    },
    "delegated_setting_scopes": {
        "scope_type": "string",
        "entity_id": "string",
        "settings_returned": "boolean",
        "setting_count": "long",
        "source_date": "string",
    },
    "delegated_setting_overrides": {
        "scope_type": "string",
        "entity_id": "string",
        "setting_name": "string",
        "title": "string",
        "setting_group": "string",
        "enabled": "boolean",
        "delegated_from": "string",
        "enabled_group_count": "long",
        "excluded_group_count": "long",
        "source_date": "string",
    },
    "tenant_setting_groups": {
        "scope_type": "string",
        "entity_id": "string",
        "setting_name": "string",
        "group_id": "string",
        "group_rule": "string",
        "source_date": "string",
    },
    "domains": {
        "domain_id": "string",
        "domain_name": "string",
        "parent_domain_id": "string",
        "source_date": "string",
    },
    "domain_workspaces": {
        "domain_id": "string",
        "workspace_id": "string",
        "workspace_name": "string",
        "source_date": "string",
    },
    "workspace_git_connections": {
        "workspace_id": "string",
        "provider_type": "string",
        "owner_key": "string",
        "organization_name": "string",
        "project_name": "string",
        "repository_name": "string",
        "branch_name": "string",
        "directory_key": "string",
        "connection_state": "string",
        "last_sync_utc": "string",
        "source_date": "string",
    },
    "tags": {
        "tag_id": "string",
        "tag_name": "string",
        "scope_type": "string",
        "domain_id": "string",
        "source_date": "string",
    },
    "organization_shares": {
        "artifact_id": "string",
        "artifact_type": "string",
        "access_right": "string",
        "share_type": "string",
        "source_date": "string",
    },
    "publish_to_web_shares": {
        "artifact_id": "string",
        "artifact_type": "string",
        "access_right": "string",
        "share_type": "string",
        "source_date": "string",
    },
    "deployment_pipelines": {
        "pipeline_id": "string",
        "pipeline_name": "string",
        "source_date": "string",
    },
    "deployment_operation_resources": {
        "pipeline_id": "string",
        "record_count": "long",
        "resource_outcome": "string",
        "source_date": "string",
    },
    "deployment_operations": {
        "pipeline_id": "string",
        "operation_id": "string",
        "operation_type": "string",
        "status": "string",
        "last_updated_utc": "string",
        "execution_start_utc": "string",
        "execution_end_utc": "string",
        "duration_seconds": "double",
        "source_stage_id": "string",
        "target_stage_id": "string",
        "source_date": "string",
    },
}
SCHEMAS.update(MODULE_SCHEMAS)
MODULE_DATASETS = tuple(SCHEMAS)
PIPELINE_ACTIVITY_MODULE = "fabricpipelineactivityruns"
PIPELINE_ACTIVITY_PREFIXES = {PIPELINE_ACTIVITY_MODULE}
PIPELINE_ACTIVITY_SCHEMAS = {
    "pipeline_activity_resources": {
        **TARGET_COLUMNS,
        "scope_id": "string",
        "pipeline_run_id": "string",
        "observation_unit": "string",
        "last_updated_after_utc": "string",
        "last_updated_before_utc": "string",
        "record_count": "long",
        "issue": "string",
    },
    "pipeline_activity_observations": {
        **TARGET_COLUMNS,
        "scope_id": "string",
        "pipeline_run_id": "string",
        "activity_run_id": "string",
        "activity_name": "string",
        "activity_type": "string",
        "status": "string",
        "last_updated_after_utc": "string",
        "last_updated_before_utc": "string",
        "start_time_utc": "string",
        "end_time_utc": "string",
        "duration_ms": "double",
        "rows_read": "long",
        "rows_copied": "long",
        "data_read": "long",
        "data_written": "long",
        "throughput": "double",
        "child_pipeline_run_id": "string",
    },
}
SCHEMAS.update(PIPELINE_ACTIVITY_SCHEMAS)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def utc(value):
    if not isinstance(value, str):
        raise TypeError("Invalid UTC timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Naive timestamp")
    return (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing text")
    return value


def uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Invalid canonical identity")
    return value


def records(value):
    if not isinstance(value, list) or any(not isinstance(v, dict) for v in value):
        raise ValueError("Invalid record collection")
    return value


def target(parent):
    return uuid(parent["workspaceId"]), uuid(parent["itemId"]), text(parent["type"])


def target_fields(parent):
    return dict(zip(TARGET_COLUMNS, target(parent), strict=True))


def document(path, data):
    """Parse bytes without propagating source text into diagnostics."""
    relative = PurePosixPath(path)
    if relative.is_absolute() or ".." in relative.parts or "\\" in path:
        raise ValueError("Unsafe source path")
    try:
        value = json.loads(data)
        canonical(value)
        issue = None
    except (ValueError, UnicodeError, RecursionError):
        value, issue = None, "malformed_json"
    return {
        "path": path,
        "sha256": sha256(data),
        "value": value,
        "issue": issue,
    }


def load_documents(
    raw_root,
    *,
    max_files=50000,
    max_bytes=128 * 1024 * 1024,
    max_file_bytes=8 * 1024 * 1024,
    source_prefixes=None,
    allow_empty=False,
):
    """Bounded driver-side reads of the attached Lakehouse; never write raw files."""
    root = Path(raw_root)
    allowed = Path(LAKEHOUSE_FILES)
    if (
        not root.is_absolute()
        or ".." in root.parts
        or root.resolve() == allowed
        or allowed not in root.resolve().parents
        or not root.is_dir()
    ):
        raise ValueError(
            "Select an existing folder inside the attached Lakehouse Files"
        )
    result, total = [], 0
    prefixes = (
        CORE_SOURCE_PREFIXES
        | ESTATE_PREFIXES
        | MODULE_PREFIXES
        | PIPELINE_ACTIVITY_PREFIXES
        | SHORTCUT_PREFIXES
        | EVENTSTREAM_PREFIXES
    )
    if source_prefixes is not None:
        selected = set(source_prefixes)
        if not selected or not selected.issubset(prefixes):
            raise ValueError("Select known source folders")
        prefixes = selected
    for path in sorted(root.rglob("*.json")):
        relative = path.relative_to(root)
        if relative.parts[0] not in prefixes or path.name in {
            "request_gate.json",
            "progress.json",
            "tenant_progress.json",
        }:
            continue
        if relative.parts[0] == "gateways" and path.name == "users.json":
            continue
        if path.is_symlink() or root.resolve() not in path.resolve().parents:
            raise ValueError("Source path escaped the raw folder")
        size = path.stat().st_size
        total += size
        if len(result) >= max_files or total > max_bytes or size > max_file_bytes:
            raise ValueError("Raw evidence exceeds configured driver safety limits")
        data = path.read_bytes()
        if len(data) != size:
            raise ValueError("Source changed during reading")
        result.append(document(relative.as_posix(), data))
    if not result and not allow_empty:
        raise ValueError("No supported collection files; refusing an empty import")
    return result


def row(table, doc, key, *, observed=None, **values):
    path = doc["path"]
    parts = PurePosixPath(path).parts
    value = doc["value"] if isinstance(doc["value"], dict) else {}
    timestamp = observed if observed is not None else value.get("observedAt")
    try:
        timestamp = utc(timestamp)
    except (ValueError, TypeError):
        timestamp = None
    result = dict.fromkeys({**COMMON, **SCHEMAS[table]})
    result.update(
        schema_version=SCHEMA_VERSION,
        observation_id=sha256(canonical([table, path, key]).encode()),
        source_path=path,
        source_sha256=doc["sha256"],
        observed_at_utc=timestamp,
        module=parts[0],
        mode=PERMISSIONS.get(parts[0]),
        run_id=next(
            (
                value[key]
                for key in ("runId", "scanId")
                if isinstance(value.get(key), str)
            ),
            None,
        ),
        coverage_status="success",
    )
    if set(values) - set(result):
        raise ValueError("Unknown contract column")
    result.update(values)
    if parts[0] in {"items", "workspaces", "catalog"} or result["coverage_status"] in {
        "invalid",
        "unfinished",
        "legacy_unverified",
    }:
        result["observation_id"] = sha256(
            canonical([table, path, key, doc["sha256"]]).encode()
        )
    return result


def _validate_records(module, resource):
    parent = resource["parent"]
    inventory = parent.get("observationUnit") == "inventoryPage"
    if module in PERMISSIONS:
        if inventory:
            if not isinstance(parent.get("inventoryComplete"), bool):
                raise ValueError("Invalid inventory completion")
            if PERMISSIONS[module] == "Scoped":
                uuid(parent["workspaceId"])
        else:
            target(parent)
    elif module == "fabricitemjobhistory":
        if target(parent)[2] not in {"Notebook", "DataPipeline", "SparkJobDefinition"}:
            raise ValueError("Unsupported job item")
    elif (
        module == "fabricitemdefinitions"
        and parent
        and target(parent)[2] not in {"Notebook", "DataPipeline"}
    ):
        raise ValueError("Unsupported definition item")
    elif module == SHORTCUT_MODULE and parent and target(parent)[2] != "Lakehouse":
        raise ValueError("Unsupported shortcut parent")
    elif module == EVENTSTREAM_MODULE and parent and target(parent)[2] != "Eventstream":
        raise ValueError("Unsupported Eventstream parent")
    if not resource["complete"]:
        text(resource["error"])
        if "records" in resource or (inventory and parent["inventoryComplete"]):
            raise ValueError("Failed resource contains records or complete inventory")
        return
    if "error" in resource:
        raise ValueError("Successful resource contains an error")
    values = records(resource["records"])
    if module == SHORTCUT_MODULE:
        if parent:
            validate_shortcut_records(values)
        elif (
            shortcut_inventory(
                [{"id": value["itemId"], **value} for value in values], []
            )
            != values
        ):
            raise ValueError("Invalid shortcut inventory identities")
    elif module == EVENTSTREAM_MODULE:
        if parent:
            if len(values) != 1:
                raise ValueError("Missing or repeated Eventstream topology")
            validate_eventstream_topology(values[0])
        elif (
            eventstream_inventory(
                [{"id": value["itemId"], **value} for value in values], []
            )
            != values
        ):
            raise ValueError("Invalid Eventstream inventory identities")
    identities = []
    for value in values:
        if module in PERMISSIONS and inventory:
            identity = target(value)
            if PERMISSIONS[module] == "Scoped" and identity[0] != parent["workspaceId"]:
                raise ValueError("Inventory workspace mismatch")
            identities.append(
                identity[:2] if PERMISSIONS[module] == "Tenant" else identity
            )
        elif module in PERMISSIONS:
            principal, detail = value["principal"], value["itemAccessDetails"]
            text(principal["id"])
            if not isinstance(principal["type"], str):
                raise ValueError("Invalid principal type")
            if not (
                detail["type"] == parent["type"]
                or (parent["type"] in POWER_BI and detail["type"] is None)
            ):
                raise ValueError("Permission item type mismatch")
            for field in ("permissions", "additionalPermissions"):
                if field == "additionalPermissions" and (
                    field not in detail
                    or (detail[field] is None and parent["type"] in POWER_BI)
                ):
                    continue
                if not isinstance(detail[field], list) or any(
                    not isinstance(v, str) for v in detail[field]
                ):
                    raise ValueError("Invalid permission list")
        elif module == "fabricitemjobhistory":
            for field in ("id", "jobType", "invokeType", "status"):
                text(value[field])
            if value["itemId"] != parent["itemId"]:
                raise ValueError("Job parent mismatch")
            for field in ("startTimeUtc", "endTimeUtc"):
                if value.get(field) is not None:
                    utc(value[field])
            if value.get("failureReason") is not None and not isinstance(
                value["failureReason"], dict
            ):
                raise ValueError("Invalid job failure metadata")
            if value.get("rootActivityId") is not None and not isinstance(
                value["rootActivityId"], str
            ):
                raise ValueError("Invalid activity identity")
            identities.append(value["id"])
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate observation identity")


def _resource_name_endpoint(module, resource):
    parent = resource["parent"]
    if module in PERMISSIONS:
        if parent.get("observationUnit") == "inventoryPage":
            if PERMISSIONS[module] == "Tenant":
                return "inventory.json", "admin/items?state=active"
            workspace = parent["workspaceId"]
            return f"inventory_{workspace}.json", f"admin/items?workspaceId={workspace}"
        workspace, item, kind = target(parent)
        suffix = f"?type={kind}" if kind in POWER_BI else ""
        return (
            f"{workspace}_{item}.json",
            f"admin/workspaces/{workspace}/items/{item}/users{suffix}",
        )
    if module == "fabricitemjobhistory":
        workspace, item, _ = target(parent)
        return (
            f"{workspace}_{item}.json",
            f"workspaces/{workspace}/items/{item}/jobs/instances",
        )
    if module == "fabricitemdefinitions":
        if not parent:
            return "inventory.json", "admin/items"
        workspace, item, kind = target(parent)
        endpoint = (
            f"notebooks/{item}/getDefinition?format=ipynb"
            if kind == "Notebook"
            else f"dataPipelines/{item}/getDefinition"
        )
        return f"{workspace}_{item}.json", f"workspaces/{workspace}/{endpoint}"
    if module == SHORTCUT_MODULE:
        if not parent:
            return "inventory.json", "admin/items?type=Lakehouse"
        workspace, item, _ = target(parent)
        return (
            f"{workspace}_{item}.json",
            f"workspaces/{workspace}/items/{item}/shortcuts",
        )
    if module == EVENTSTREAM_MODULE:
        if not parent:
            return "inventory.json", "admin/items?type=Eventstream"
        workspace, item, _ = target(parent)
        return (
            f"{workspace}_{item}.json",
            f"workspaces/{workspace}/eventstreams/{item}/topology",
        )
    return None, None


def build_runs(
    documents, *, modules=MODULES, resource_validator=None, manifest_validator=None
):
    grouped = {}
    for doc in documents:
        path = PurePosixPath(doc["path"])
        if path.parts[0] in modules:
            grouped.setdefault(str(path.parent), {})[path.name] = doc
    result = {}
    for folder, files in sorted(grouped.items()):
        module = folder.split("/")[0]
        manifest_doc = files.get("manifest.json")
        representative = manifest_doc or files[min(files)]
        run = {
            "doc": representative,
            "module": module,
            "manifest": None,
            "resources": [],
            "valid": False,
            "issue": None,
            "chain": None,
        }
        result[folder + "/manifest.json"] = run
        try:
            parts = folder.split("/")
            if len(parts) != 5 or not re.fullmatch(r"[a-f0-9]{32}", parts[-1]):
                raise ValueError("Invalid immutable run path")
            datetime.strptime("/".join(parts[1:4]), "%Y/%m/%d")
            if manifest_doc is None or manifest_doc["issue"]:
                raise ValueError("Missing or malformed manifest")
            manifest = manifest_doc["value"]
            if not isinstance(manifest, dict):
                raise TypeError("Invalid manifest object")
            run["manifest"] = manifest
            if (
                manifest["runId"] != parts[-1]
                or not isinstance(manifest["complete"], bool)
                or not isinstance(manifest["finished"], bool)
                or not isinstance(manifest["errors"], list)
            ):
                raise ValueError("Invalid manifest fields")
            final_time = utc(manifest["observedAt"])
            entries = records(manifest["resources"])
            names = []
            if not manifest["finished"]:
                if manifest["complete"] or entries or manifest["errors"]:
                    raise ValueError("Invalid initial manifest")
                run["valid"] = True
                continue
            if manifest_validator is not None:
                manifest_validator(manifest)
            if module == SHORTCUT_MODULE:
                shortcut_scope(manifest["execution"])
            elif module == EVENTSTREAM_MODULE:
                eventstream_scope(manifest["execution"])
            for entry in entries:
                name = text(entry["file"])
                if (
                    PurePosixPath(name).name != name
                    or "\\" in name
                    or name == "manifest.json"
                    or not name.endswith(".json")
                    or name in names
                    or not isinstance(entry["complete"], bool)
                    or not isinstance(entry["parent"], dict)
                ):
                    raise ValueError("Invalid manifest entry")
                names.append(name)
                doc = files[name]
                resource = doc["value"]
                if (
                    doc["issue"]
                    or not isinstance(resource, dict)
                    or resource["runId"] != manifest["runId"]
                    or not isinstance(resource["complete"], bool)
                    or resource["parent"] != entry["parent"]
                    or resource["complete"] != entry["complete"]
                    or utc(resource["observedAt"]) > final_time
                ):
                    raise ValueError("Resource and manifest disagree")
                if resource_validator is not None:
                    expected_name, endpoint = resource_validator(resource, manifest)
                else:
                    _validate_records(module, resource)
                    expected_name, endpoint = _resource_name_endpoint(module, resource)
                if module in {SHORTCUT_MODULE, EVENTSTREAM_MODULE}:
                    excluded = manifest["execution"]["excludeWorkspaceIds"]
                    parents = (
                        [resource["parent"]]
                        if resource["parent"]
                        else resource.get("records", [])
                    )
                    if any(parent["workspaceId"] in excluded for parent in parents):
                        raise ValueError("Excluded configuration workspace captured")
                if endpoint is not None and (
                    name != expected_name or resource["requestPath"] != endpoint
                ):
                    raise ValueError("Resource identity or endpoint mismatch")
                run["resources"].append(doc)
            if set(files) != {"manifest.json", *names}:
                raise ValueError("Unlisted or missing run resources")
            if module in PERMISSIONS:
                if len(entries) != 1:
                    raise ValueError("Permission slice must contain one resource")
            elif module == "fabricitemjobhistory" and (
                not 1 <= len(entries) <= 100
                or len({target(entry["parent"]) for entry in entries}) != len(entries)
            ):
                raise ValueError("Invalid job resource scope")
            elif module in {SHORTCUT_MODULE, EVENTSTREAM_MODULE}:
                execution = manifest["execution"]
                if manifest["complete"] != (
                    execution["sweepComplete"]
                    and execution["sweepHealthy"]
                    and all(entry["complete"] for entry in entries)
                    and not manifest["errors"]
                ):
                    raise ValueError(
                        "Configuration sweep outcome disagrees with resources"
                    )
            elif module == PIPELINE_ACTIVITY_MODULE:
                execution = manifest.get("execution") or {}
                if execution.get("mode") not in {"discovery", "explicit"}:
                    raise ValueError("Invalid pipeline activity collection mode")
                if execution["mode"] == "discovery":
                    if (
                        type(execution.get("sweepComplete")) is not bool
                        or type(execution.get("sweepHealthy")) is not bool
                    ):
                        raise ValueError("Invalid pipeline discovery outcome")
                    expected_complete = (
                        execution["sweepComplete"] and execution["sweepHealthy"]
                    )
                    if manifest["complete"] != (
                        expected_complete
                        and all(entry["complete"] for entry in entries)
                        and not manifest["errors"]
                    ):
                        raise ValueError(
                            "Pipeline sweep outcome disagrees with resources"
                        )
                elif manifest["complete"] != (
                    all(entry["complete"] for entry in entries)
                    and not manifest["errors"]
                ):
                    raise ValueError(
                        "Pipeline explicit outcome disagrees with resources"
                    )
            elif manifest["complete"] != (
                all(entry["complete"] for entry in entries) and not manifest["errors"]
            ):
                raise ValueError("Manifest completeness disagrees with resources")
            run["valid"] = True
        except (ValueError, KeyError, TypeError, AttributeError, IndexError):
            run["issue"] = "invalid_run_artifacts"
    for path, run in result.items():
        if (
            run["module"] in PERMISSIONS
            and run["valid"]
            and run["manifest"]["finished"]
        ):
            try:
                run["chain"] = permission_chain(path, result)
            except (ValueError, KeyError, TypeError, AttributeError, IndexError):
                run["issue"] = "invalid_permission_chain"
                run["valid"] = False
    return result


def _integer(value):
    if type(value) is not int or value < 0:
        raise ValueError("Invalid nonnegative integer")
    return value


def permission_chain(path, runs):
    """Follow enumerated immutable manifests only, then validate cursor transitions."""
    module = runs[path]["module"]
    tenant = PERMISSIONS[module] == "Tenant"
    chain, seen = [], set()
    while True:
        if path in seen or len(seen) >= 10000 or path not in runs:
            raise ValueError("Missing, cyclic or excessive permission evidence")
        seen.add(path)
        run = runs[path]
        manifest = run["manifest"]
        if not run["valid"] or run["module"] != module or not manifest["finished"]:
            raise ValueError("Uncommitted permission evidence")
        chain.append(run)
        execution = manifest["execution"]
        links = execution["cycleEvidence"]
        if not isinstance(links, list) or len(links) > 1:
            raise ValueError("Invalid evidence links")
        if not links:
            break
        path = text(links[0])
    chain.reverse()
    selected, selected_keys, inventories, access = [], set(), set(), []
    before, healthy, prior, prior_parent, prior_task = 0, True, None, None, None
    task_keys, task_ids = set(), set()
    inventory_workspaces = set()
    for run in chain:
        manifest, resource = run["manifest"], run["resources"][0]["value"]
        e, parent = manifest["execution"], resource["parent"]
        inventory = parent.get("observationUnit") == "inventoryPage"
        for field in ("cycleFinished", "cycleHealthy", "deferred"):
            if not isinstance(e[field], bool):
                raise TypeError("Invalid cycle flag")
        attempts = _integer(e["attempts"])
        if attempts > 1:
            raise ValueError("Invalid slice attempt count")
        unattempted = e["deferred"] and attempts == 0
        if resource["complete"] and (attempts != 1 or e["deferred"]):
            raise ValueError("Successful deferred or unattempted resource")
        if prior is not None and (
            prior["execution"]["cycleFinished"]
            or utc(prior["observedAt"]) > utc(resource["observedAt"])
        ):
            raise ValueError("Invalid cycle transition")
        previous_healthy = healthy
        healthy = healthy and (resource["complete"] or unattempted)
        if e["cycleHealthy"] != healthy or (
            healthy and manifest["errors"] and not unattempted
        ):
            raise ValueError("Nonmonotonic cycle health")
        if tenant:
            if (
                e["scopeMode"] != "tenant"
                or e["phase"] != ("inventory" if inventory else "access")
                or not isinstance(e["inventoryComplete"], bool)
                or e["resourceOutcome"]
                not in {
                    "succeeded",
                    "failed",
                    "unsupported",
                    "denied",
                    "not_found",
                    "deferred",
                }
                or (e["resourceOutcome"] == "succeeded") != resource["complete"]
                or (e["resourceOutcome"] == "deferred") != e["deferred"]
                or (attempts == 0 and not e["deferred"])
            ):
                raise ValueError("Invalid tenant execution")
            if inventory:
                if before != 0 or (
                    prior is not None and prior["execution"]["inventoryComplete"]
                ):
                    raise ValueError("Inventory after tenant access")
                if resource["complete"]:
                    for item in resource["records"]:
                        key = target(item)[:2]
                        if key in selected_keys:
                            raise ValueError("Duplicate tenant inventory")
                        selected_keys.add(key)
                        selected.append(item)
                after = 0
                if e["inventoryComplete"] != parent["inventoryComplete"]:
                    raise ValueError("Inventory completion mismatch")
            else:
                if (
                    prior is None
                    or not prior["execution"]["inventoryComplete"]
                    or before >= len(selected)
                    or target(parent) != target(selected[before])
                    or not e["inventoryComplete"]
                ):
                    raise ValueError("Access outside tenant inventory order")
                after = before + (0 if unattempted else 1)
            if (
                _integer(e["discoveredItems"]) != len(selected)
                or _integer(e["nextItem"]) != after
                or e["cycleFinished"]
                != (e["inventoryComplete"] and after == len(selected))
            ):
                raise ValueError("Invalid tenant cursor")
        else:
            count = _integer(e["taskCount"])
            if not 2 <= count <= 100 or (
                prior is not None and count != prior["execution"]["taskCount"]
            ):
                raise ValueError("Invalid scoped task count")
            workspace = parent["workspaceId"]
            key = (workspace, "inventory") if inventory else target(parent)
            if prior is None:
                if not inventory:
                    raise ValueError("Cycle does not begin with inventory")
            elif before == prior_task:
                prior_key = (
                    (prior_parent["workspaceId"], "inventory")
                    if prior_parent.get("observationUnit") == "inventoryPage"
                    else target(prior_parent)
                )
                if key != prior_key:
                    raise ValueError("Deferred task changed identity")
            elif prior_parent.get("observationUnit") == "inventoryPage":
                if inventory or workspace != prior_parent["workspaceId"]:
                    raise ValueError("Invalid inventory to access transition")
            elif not inventory:
                if workspace != prior_parent["workspaceId"]:
                    raise ValueError("Access workspace changed without inventory")
            elif workspace in inventory_workspaces:
                raise ValueError("Repeated workspace inventory task")
            if inventory:
                inventory_workspaces.add(workspace)
                if resource["complete"]:
                    for item in resource["records"]:
                        identity = target(item)
                        if identity in selected_keys:
                            raise ValueError("Duplicate scoped inventory")
                        selected_keys.add(identity)
                        selected.append(item)
                    if parent["inventoryComplete"]:
                        inventories.add(workspace)
            elif resource["complete"]:
                if target(parent) not in selected_keys or workspace not in inventories:
                    raise ValueError("Access outside completed scoped inventory")
                access.append(target(parent))
            delta = (
                0
                if unattempted
                or (
                    inventory
                    and resource["complete"]
                    and not parent["inventoryComplete"]
                )
                else 1
            )
            after = before + delta
            if (
                _integer(e["nextTask"]) != after
                or after > count
                or e["cycleFinished"] != (after == count)
            ):
                raise ValueError("Invalid scoped cursor")
            task_keys.add((before, key))
            task_ids.add(before)
            if manifest["complete"] and (
                not 1 <= len(access) <= 50
                or len(access) != len(set(access))
                or set(access) != selected_keys
                or len(task_keys) != count
                or len(task_ids) != count
                or len({key[0] for key in access}) + len(access) != count
            ):
                raise ValueError("Incomplete scoped selection")
        if manifest["complete"] != (e["cycleFinished"] and healthy):
            raise ValueError("Invalid permission cycle completeness")
        # A failed slice cannot become healthy merely by following a newer link.
        if not previous_healthy and healthy:
            raise ValueError("Cycle health recovered without a new cycle")
        prior_task, before, prior, prior_parent = before, after, manifest, parent
    return {
        "nodes": chain,
        "cycle_id": chain[0]["manifest"]["runId"],
        "selected_items": len(selected),
    }


def _health(run):
    manifest = run["manifest"] or {}
    valid, finished = run["valid"], manifest.get("finished") is True
    resources = run["resources"]
    status = (
        "invalid"
        if not valid
        else "unfinished"
        if not finished
        else "success"
        if manifest["complete"]
        else "partial_or_failed"
    )
    return row(
        "collection_health",
        run["doc"],
        "run",
        coverage_status=status,
        complete=manifest.get("complete") if valid else None,
        finished=manifest.get("finished") if valid else None,
        successful_resources=sum(d["value"]["complete"] for d in resources)
        if valid and finished
        else None,
        failed_resources=sum(not d["value"]["complete"] for d in resources)
        if valid and finished
        else None,
        coverage=manifest.get("coverage")
        if isinstance(manifest.get("coverage"), str)
        else None,
        issue=run["issue"],
        cycle_id=run["chain"]["cycle_id"] if run["chain"] else None,
        mode=shortcut_scope(manifest["execution"])
        if run["module"] == SHORTCUT_MODULE and valid and finished
        else eventstream_scope(manifest["execution"])
        if run["module"] == EVENTSTREAM_MODULE and valid and finished
        else PERMISSIONS.get(run["module"]),
    )


def _permission_tables(runs, output):
    for run in runs.values():
        if run["module"] not in PERMISSIONS:
            continue
        manifest = run["manifest"] or {}
        chain = run["chain"]
        valid = run["valid"] and chain is not None
        cycle_id = (
            chain["cycle_id"]
            if valid
            else (
                manifest.get("runId")
                if isinstance(manifest.get("runId"), str)
                else None
            )
        )
        execution = manifest.get("execution") or {}
        output["permission_cycles"].append(
            row(
                "permission_cycles",
                run["doc"],
                "cycle_tip",
                cycle_id=cycle_id,
                chain_valid=valid,
                cycle_finished=execution.get("cycleFinished") if valid else None,
                cycle_healthy=execution.get("cycleHealthy") if valid else None,
                slice_count=len(chain["nodes"]) if valid else None,
                selected_items=chain["selected_items"] if valid else None,
                coverage_status="success"
                if valid and manifest["complete"]
                else "partial_or_failed"
                if valid
                else "invalid",
            )
        )
        if not valid:
            continue
        doc = run["resources"][0]
        resource, parent = doc["value"], doc["value"]["parent"]
        inventory = parent.get("observationUnit") == "inventoryPage"
        fields = (
            {"workspace_id": parent.get("workspaceId")}
            if inventory
            else target_fields(parent)
        )
        successful = resource["complete"]
        output["permission_resources"].append(
            row(
                "permission_resources",
                doc,
                "resource",
                **fields,
                cycle_id=cycle_id,
                observation_unit="inventory_page" if inventory else "item_access",
                record_count=len(resource["records"]) if successful else None,
                resource_outcome=execution.get("resourceOutcome")
                or (
                    "succeeded"
                    if successful
                    else "deferred"
                    if execution["deferred"]
                    else "failed"
                ),
                coverage_status="success"
                if successful
                else "deferred"
                if execution["deferred"]
                else "failed",
            )
        )
        if not successful:
            continue
        for record in resource["records"]:
            if inventory:
                output["inventory"].append(
                    row(
                        "inventory",
                        doc,
                        target(record),
                        **target_fields(record),
                        inventory_source="permission_inventory",
                        cycle_id=cycle_id,
                    )
                )
            else:
                principal, detail = record["principal"], record["itemAccessDetails"]
                permissions = sorted(set(detail["permissions"]))
                additional = detail.get("additionalPermissions")
                additional = sorted(set(additional)) if additional is not None else None
                output["permission_grants"].append(
                    row(
                        "permission_grants",
                        doc,
                        [principal["id"], principal["type"], permissions, additional],
                        **fields,
                        cycle_id=cycle_id,
                        principal_id=principal["id"],
                        principal_type=principal["type"],
                        permissions_json=canonical(permissions),
                        additional_permissions_json=canonical(additional),
                    )
                )


def _job_tables(runs, output):
    for run in runs.values():
        if run["module"] != "fabricitemjobhistory" or not run["valid"]:
            continue
        if not run["manifest"]["finished"]:
            continue
        for doc in run["resources"]:
            resource, parent = doc["value"], doc["value"]["parent"]
            fields = target_fields(parent)
            output["job_resources"].append(
                row(
                    "job_resources",
                    doc,
                    "resource",
                    **fields,
                    coverage_status="success" if resource["complete"] else "failed",
                    record_count=len(resource["records"])
                    if resource["complete"]
                    else None,
                )
            )
            if not resource["complete"]:
                continue
            for job in resource["records"]:
                start = utc(job["startTimeUtc"]) if job.get("startTimeUtc") else None
                end = utc(job["endTimeUtc"]) if job.get("endTimeUtc") else None
                duration = (
                    (
                        datetime.fromisoformat(end.replace("Z", "+00:00"))
                        - datetime.fromisoformat(start.replace("Z", "+00:00"))
                    ).total_seconds()
                    if start and end
                    else None
                )
                failure = job.get("failureReason") or {}
                output["job_observations"].append(
                    row(
                        "job_observations",
                        doc,
                        job["id"],
                        **fields,
                        job_id=job["id"],
                        job_type=job["jobType"],
                        invoke_type=job["invokeType"],
                        status=job["status"],
                        start_time_utc=start,
                        end_time_utc=end,
                        duration_seconds=duration
                        if duration is not None and duration >= 0
                        else None,
                        root_activity_id=job.get("rootActivityId"),
                        failure_code=failure.get("errorCode")
                        if isinstance(failure.get("errorCode"), str)
                        else None,
                    )
                )


def _legacy_inventory(doc, output):
    path = doc["path"]
    module = path.split("/")[0]
    try:
        if not re.fullmatch(r"(items|workspaces)/\d{4}/\d{2}/\d{2}/[^/]+\.json", path):
            raise ValueError("Invalid legacy inventory path")
        values = records(doc["value"])
        datetime.strptime("/".join(path.split("/")[1:4]), "%Y/%m/%d")
        pending = []
        for value in values:
            item = uuid(value["id"])
            workspace = item if module == "workspaces" else uuid(value["workspaceId"])
            kind = "Workspace" if module == "workspaces" else text(value["type"])
            name = value.get("displayName", value.get("name"))
            pending.append(
                row(
                    "inventory",
                    doc,
                    [workspace, item, kind],
                    workspace_id=workspace,
                    item_id=item,
                    item_type=kind,
                    item_name=name if isinstance(name, str) else None,
                    inventory_source="legacy_" + module,
                    coverage_status="legacy_unverified",
                )
            )
        output["inventory"].extend(pending)
        status, count = "legacy_unverified", len(values)
    except (ValueError, KeyError, TypeError, AttributeError):
        status, count = "invalid", None
    output["collection_health"].append(
        row(
            "collection_health",
            doc,
            "legacy_file",
            coverage_status=status,
            record_count=count,
            issue="no_manifest_or_exact_observation_time",
        )
    )


def _scanner_tables(doc, output, *, legacy_snapshot=None):
    try:
        legacy = legacy_snapshot is not None
        scan = legacy_snapshot if legacy else doc["value"]
        if (
            doc["issue"]
            or (
                not legacy
                and not re.fullmatch(
                    r"lineage_edges/\d{4}/\d{2}/\d{2}/[A-Za-z0-9][A-Za-z0-9_-]{0,127}\.lineage_edges\.json",
                    doc["path"],
                )
            )
            or type(scan["schemaVersion"]) is not int
            or scan["schemaVersion"] != 1
            or scan["source"] != "Scanner"
            or scan["complete"] is not True
            or (
                not legacy
                and PurePosixPath(doc["path"]).name
                != scan["scanId"] + ".lineage_edges.json"
            )
            or scan["scanMode"] not in {"full", "incremental"}
        ):
            raise ValueError("Invalid scanner envelope")
        observed = None if legacy else utc(scan["observedAtUtc"])
        status = "legacy_unverified" if legacy else "success"
        date_parts = (
            doc["path"].split("/")[2:5] if legacy else doc["path"].split("/")[1:4]
        )
        datetime.strptime("/".join(date_parts), "%Y/%m/%d")
        requested = {uuid(value) for value in scan["requestedWorkspaceIds"]}
        returned = {uuid(value) for value in scan["returnedWorkspaceIds"]}
        if not returned.issubset(requested):
            raise ValueError("Unexpected returned workspace")
        items = records(scan["items"])
        indexed = {}
        inventory = []
        for item in items:
            identity, workspace = uuid(item["id"]), uuid(item["workspaceId"])
            if identity in indexed or workspace not in returned:
                raise ValueError("Invalid scanner item inventory")
            indexed[identity] = item
            inventory.append(
                row(
                    "inventory",
                    doc,
                    identity,
                    observed=observed,
                    workspace_id=workspace,
                    item_id=identity,
                    item_type=text(item["type"]),
                    item_name=item.get("name")
                    if isinstance(item.get("name"), str)
                    else None,
                    inventory_source="legacy_scanner" if legacy else "scanner_batch",
                    coverage_status=status,
                )
            )
        edges = []
        for edge in records(scan["edges"]):
            item = indexed[edge["QueryItemId"]]
            if (
                edge["Source"] != "Scanner"
                or edge["Direction"] not in {"upstream", "downstream"}
                or edge["QueryWorkspaceId"] != item["workspaceId"]
                or edge["QueryItemType"] != item["type"]
            ):
                raise ValueError("Invalid scanner edge scope")
            related = text(edge["RelatedItemId"])
            if edge.get("RelatedItemType") is not None:
                text(edge["RelatedItemType"])
            if edge.get("RelatedWorkspaceId") is not None:
                uuid(edge["RelatedWorkspaceId"])
            key = [item["id"], edge["Direction"], related, text(edge["RelationType"])]
            edges.append(
                row(
                    "lineage_edges",
                    doc,
                    key,
                    observed=observed,
                    workspace_id=item["workspaceId"],
                    item_id=item["id"],
                    item_type=item["type"],
                    related_workspace_id=edge.get("RelatedWorkspaceId"),
                    related_item_id=related,
                    related_type=edge.get("RelatedItemType"),
                    direction=edge["Direction"],
                    relation_type=edge["RelationType"],
                    evidence_type="scanner_relationship",
                    runtime_verified=False,
                    coverage_status=status,
                    resolution="in_batch"
                    if related in indexed
                    else "external_or_unresolved",
                )
            )
        coverage = status if requested == returned else "partial_batch"
        resources = [
            row(
                "lineage_resources",
                doc,
                ["scanner_item", identity],
                observed=observed,
                workspace_id=item["workspaceId"],
                item_id=identity,
                item_type=item["type"],
                evidence_type="scanner_relationship",
                record_count=sum(edge["item_id"] == identity for edge in edges),
                diagnostic_count=0,
                coverage_status=coverage,
            )
            for identity, item in indexed.items()
        ]
        output["inventory"].extend(inventory)
        output["lineage_edges"].extend(edges)
        output["lineage_resources"].extend(resources)
        output["collection_health"].append(
            row(
                "collection_health",
                doc,
                "scanner_batch",
                observed=observed,
                complete=None if legacy else requested == returned,
                finished=None if legacy else True,
                record_count=len(items),
                coverage_status=coverage,
                coverage="Scanner batch only; not exhaustive tenant or runtime I/O coverage",
                issue="no_manifest_or_exact_observation_time" if legacy else None,
            )
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        output["collection_health"].append(
            row(
                "collection_health",
                doc,
                "scanner_batch",
                coverage_status="invalid",
                issue="invalid_scanner_envelope",
            )
        )


def _notebook_configuration_tables(runs, output):
    for run in runs.values():
        if (
            run["module"] != "fabricitemdefinitions"
            or not run["valid"]
            or not run["manifest"]["finished"]
        ):
            continue
        for doc in run["resources"]:
            resource, parent = doc["value"], doc["value"]["parent"]
            if parent.get("type") != "Notebook":
                continue
            fields = target_fields(parent)
            status, relationships, diagnostics = "failed", [], []
            if resource["complete"]:
                try:
                    values = records(resource["records"])
                    if len(values) != 1:
                        raise ValueError("Invalid definition record count")
                    decoded = values[0].get("decodedParts", {})
                    if not isinstance(decoded, dict):
                        raise TypeError("Invalid decoded definition")
                    if "notebook-content.ipynb" not in decoded:
                        status = "missing"
                        diagnostics = [
                            {
                                "fieldPath": "/decodedParts/notebook-content.ipynb",
                                "reason": "missing_notebook_configuration",
                            }
                        ]
                    else:
                        analysis = notebook_lakehouse_relationships(
                            decoded["notebook-content.ipynb"]
                        )
                        diagnostics = analysis["diagnostics"]
                        status = "success" if analysis["complete"] else "invalid"
                        if analysis["complete"]:
                            relationships = analysis["relationships"]
                except (ValueError, KeyError, TypeError, AttributeError):
                    status = "invalid"
                    diagnostics = [
                        {
                            "fieldPath": "/decodedParts",
                            "reason": "invalid_notebook_configuration",
                        }
                    ]
            for relationship in relationships:
                output["lineage_edges"].append(
                    row(
                        "lineage_edges",
                        doc,
                        relationship,
                        **fields,
                        direction="association",
                        related_workspace_id=relationship["workspaceId"],
                        related_item_id=relationship["itemId"],
                        related_type="Lakehouse",
                        relation_type=relationship["relation"],
                        reference=relationship["itemId"],
                        resolution="configured_id",
                        evidence_type="configuration_metadata",
                        runtime_verified=False,
                    )
                )
            for index, diagnostic in enumerate(diagnostics):
                output["lineage_diagnostics"].append(
                    row(
                        "lineage_diagnostics",
                        doc,
                        ["notebook_configuration", index],
                        **fields,
                        reason=diagnostic["reason"],
                        location=canonical({"fieldPath": diagnostic["fieldPath"]}),
                    )
                )
            output["lineage_resources"].append(
                row(
                    "lineage_resources",
                    doc,
                    "notebook_configuration",
                    **fields,
                    coverage_status=status,
                    evidence_type="configuration_metadata",
                    record_count=len(relationships) if status == "success" else None,
                    diagnostic_count=len(diagnostics),
                )
            )


def _definition_tables(runs, output):
    for run in runs.values():
        if (
            run["module"] != "fabricitemdefinitions"
            or not run["valid"]
            or not run["manifest"]["finished"]
        ):
            continue
        for doc in run["resources"]:
            resource, parent = doc["value"], doc["value"]["parent"]
            if not parent:
                continue
            fields = target_fields(parent)
            status, edges, diagnostics = "failed", [], []
            if resource["complete"]:
                try:
                    values = records(resource["records"])
                    if len(values) != 1:
                        raise ValueError("Invalid definition record count")
                    key = (
                        "notebookReferences"
                        if parent["type"] == "Notebook"
                        else "pipelineReferences"
                    )
                    refs = values[0][key]
                    if (
                        type(refs["schemaVersion"]) is not int
                        or refs["schemaVersion"] != 1
                        or refs["evidence"] != "static_inference"
                        or refs["runtimeVerified"] is not False
                    ):
                        raise ValueError("Invalid static evidence")
                    for ref in records(refs["references"]):
                        if ref["operation"] not in {"read", "write", "execute"}:
                            raise ValueError("Invalid static operation")
                        reference = text(ref["reference"])
                        kind = text(ref["kind"])
                        if ref.get("workspaceId") is not None:
                            uuid(ref["workspaceId"])
                        edges.append(
                            row(
                                "lineage_edges",
                                doc,
                                ref,
                                **fields,
                                direction="downstream"
                                if ref["operation"] == "write"
                                else "upstream",
                                related_workspace_id=ref.get("workspaceId"),
                                related_item_id=reference
                                if ref.get("referenceType") == "id"
                                else None,
                                related_type=kind,
                                relation_type=ref["operation"],
                                reference=reference,
                                resolution="unresolved",
                                evidence_type="static_inference",
                                runtime_verified=False,
                            )
                        )
                    for index, diagnostic in enumerate(records(refs["diagnostics"])):
                        diagnostics.append(
                            row(
                                "lineage_diagnostics",
                                doc,
                                index,
                                **fields,
                                reason=text(diagnostic["reason"]),
                                location=canonical(
                                    {
                                        key: diagnostic[key]
                                        for key in ("cell", "line", "fieldPath")
                                        if key in diagnostic
                                    }
                                ),
                            )
                        )
                    status = "success"
                except (ValueError, KeyError, TypeError, AttributeError):
                    status, edges, diagnostics = "invalid", [], []
            output["lineage_resources"].append(
                row(
                    "lineage_resources",
                    doc,
                    "definition",
                    **fields,
                    coverage_status=status,
                    evidence_type="static_inference",
                    record_count=len(edges) if status == "success" else None,
                    diagnostic_count=len(diagnostics) if status == "success" else None,
                )
            )
            output["lineage_edges"].extend(edges)
            output["lineage_diagnostics"].extend(diagnostics)


def _shortcut_tables(runs, output):
    for run in runs.values():
        if (
            run["module"] != SHORTCUT_MODULE
            or not run["valid"]
            or not run["manifest"]["finished"]
        ):
            continue
        mode = shortcut_scope(run["manifest"]["execution"])
        for doc in run["resources"]:
            resource, parent = doc["value"], doc["value"]["parent"]
            fields = target_fields(parent) if parent else {}
            values = (
                resource.get("records", []) if parent and resource["complete"] else []
            )
            diagnostics = 0
            for value in values:
                output["lineage_edges"].append(
                    row(
                        "lineage_edges",
                        doc,
                        value["shortcutId"],
                        **fields,
                        mode=mode,
                        direction="association",
                        related_workspace_id=value["targetWorkspaceId"],
                        related_item_id=value["targetItemId"],
                        related_type="FabricItem"
                        if value["targetType"] == "OneLake"
                        else value["targetType"],
                        relation_type="shortcut_transform_target"
                        if value["isShortcutTransform"]
                        else "shortcut_target",
                        reference=value["targetReference"]
                        or (
                            value["targetItemId"]
                            or "shortcut:"
                            + shortcut_fingerprint(
                                [
                                    parent["workspaceId"],
                                    parent["itemId"],
                                    value["shortcutId"],
                                ]
                            )
                        ),
                        resolution=value["targetStatus"],
                        evidence_type="shortcut_configuration",
                        runtime_verified=False,
                    )
                )
                if value["targetStatus"] in {"unavailable", "unsupported"}:
                    diagnostics += 1
                    output["lineage_diagnostics"].append(
                        row(
                            "lineage_diagnostics",
                            doc,
                            value["shortcutId"],
                            **fields,
                            mode=mode,
                            reason="shortcut_target_" + value["targetStatus"],
                            location=canonical({"shortcutId": value["shortcutId"]}),
                        )
                    )
            output["lineage_resources"].append(
                row(
                    "lineage_resources",
                    doc,
                    "shortcuts" if parent else "inventory",
                    **fields,
                    mode=mode,
                    evidence_type="shortcut_configuration",
                    coverage_status="success" if resource["complete"] else "failed",
                    record_count=len(values)
                    if parent and resource["complete"]
                    else None,
                    diagnostic_count=diagnostics
                    if parent and resource["complete"]
                    else None,
                )
            )


def _eventstream_tables(runs, output):
    for run in runs.values():
        if (
            run["module"] != EVENTSTREAM_MODULE
            or not run["valid"]
            or not run["manifest"]["finished"]
        ):
            continue
        mode = eventstream_scope(run["manifest"]["execution"])
        for doc in run["resources"]:
            resource, parent = doc["value"], doc["value"]["parent"]
            fields = target_fields(parent) if parent else {}
            graph = resource["records"][0] if parent and resource["complete"] else None
            edge_count = 0
            if graph is not None:
                nodes = {node["nodeId"]: node for node in graph["nodes"]}

                def edge(
                    key,
                    relation,
                    reference,
                    *,
                    doc=doc,
                    fields=fields,
                    mode=mode,
                    **related,
                ):
                    output["lineage_edges"].append(
                        row(
                            "lineage_edges",
                            doc,
                            key,
                            **fields,
                            mode=mode,
                            direction="configured_link"
                            if relation == "topology_input"
                            else "association",
                            relation_type=relation,
                            reference=canonical(reference),
                            evidence_type="eventstream_configuration",
                            runtime_verified=False,
                            **related,
                        )
                    )

                for node in nodes.values():
                    reference = {
                        key: node[key]
                        for key in (
                            "nodeId",
                            "role",
                            "type",
                            "reportedStatus",
                            "inputsKnown",
                        )
                    }
                    edge(
                        ["node", node["nodeId"]],
                        "topology_node",
                        reference,
                        related_type="EventstreamNode",
                        resolution="configured_node",
                    )
                    edge_count += 1
                    if node["targetStatus"] in {
                        "configured_item",
                        "connection_reference",
                    }:
                        edge(
                            ["target", node["nodeId"]],
                            "topology_target",
                            {
                                **reference,
                                "connectionReference": node["connectionReference"],
                            },
                            related_type="FabricItem"
                            if node["targetStatus"] == "configured_item"
                            else "ConnectionReference",
                            related_workspace_id=node["targetWorkspaceId"],
                            related_item_id=node["targetItemId"],
                            resolution=node["targetStatus"],
                        )
                        edge_count += 1
                for link in graph["links"]:
                    edge(
                        ["input", link["fromNode"], link["toNode"]],
                        "topology_input",
                        {
                            **link,
                            "fromType": nodes[link["fromNode"]]["type"]
                            if link["resolved"]
                            else "Unknown",
                            "toType": nodes[link["toNode"]]["type"],
                        },
                        related_type="EventstreamNode",
                        resolution="configured_link"
                        if link["resolved"]
                        else "unresolved_input",
                    )
                    edge_count += 1
                for diagnostic in graph["diagnostics"]:
                    output["lineage_diagnostics"].append(
                        row(
                            "lineage_diagnostics",
                            doc,
                            eventstream_hash(diagnostic),
                            **fields,
                            mode=mode,
                            reason=diagnostic["reason"],
                            location=canonical(
                                {
                                    key: value
                                    for key, value in diagnostic.items()
                                    if key != "reason"
                                }
                            ),
                        )
                    )
            output["lineage_resources"].append(
                row(
                    "lineage_resources",
                    doc,
                    "topology" if parent else "inventory",
                    **fields,
                    mode=mode,
                    evidence_type="eventstream_configuration",
                    coverage_status="success" if resource["complete"] else "failed",
                    record_count=edge_count if graph is not None else None,
                    diagnostic_count=len(graph["diagnostics"])
                    if graph is not None
                    else None,
                )
            )


def transform(
    documents,
    *,
    scanner_extractor=None,
    estate_extractor=None,
    module_extractor=None,
    pipeline_extractor=None,
    include_shortcuts=False,
    include_eventstream_topology=False,
):
    """Return historical observations and explicit coverage, never inferred deletions."""
    documents = list(documents)
    if len({doc["path"] for doc in documents}) != len(documents):
        raise ValueError("Duplicate source path")
    output = {table: [] for table in SCHEMAS}
    if (
        type(include_shortcuts) is not bool
        or type(include_eventstream_topology) is not bool
    ):
        raise TypeError("Choose boolean configuration inclusion flags")
    modules = MODULES
    if include_shortcuts:
        modules += (SHORTCUT_MODULE,)
    if include_eventstream_topology:
        modules += (EVENTSTREAM_MODULE,)
    runs = build_runs(documents, modules=modules)
    output["collection_health"].extend(_health(run) for run in runs.values())
    _permission_tables(runs, output)
    _job_tables(runs, output)
    _definition_tables(runs, output)
    _notebook_configuration_tables(runs, output)
    if include_shortcuts:
        _shortcut_tables(runs, output)
    if include_eventstream_topology:
        _eventstream_tables(runs, output)
    present = {doc["path"].split("/")[0] for doc in documents}
    for doc in documents:
        module = doc["path"].split("/")[0]
        if module in {"items", "workspaces"}:
            _legacy_inventory(doc, output)
        elif module == "lineage_edges":
            _scanner_tables(doc, output)
        elif module == "catalog" and doc["path"].startswith("catalog/scans/"):
            try:
                if scanner_extractor is None or not re.fullmatch(
                    r"catalog/scans/\d{4}/\d{2}/\d{2}/\d{8}_\d+\.scanResults(?:\.fullscan)?\.json",
                    doc["path"],
                ):
                    raise ValueError("Unsupported raw scanner artifact")
                scan = doc["value"]
                workspaces = [
                    workspace["id"] for workspace in records(scan["workspaces"])
                ]
                snapshot = scanner_extractor(
                    scan, "legacy_" + doc["sha256"][:32], workspaces, None
                )
                _scanner_tables(doc, output, legacy_snapshot=snapshot)
            except (ValueError, KeyError, TypeError, AttributeError):
                output["collection_health"].append(
                    row(
                        "collection_health",
                        doc,
                        "legacy_scanner",
                        coverage_status="invalid",
                        issue="invalid_raw_scanner",
                    )
                )
    expected_modules = (*MODULES, "lineage_edges", "items", "workspaces")
    if include_shortcuts:
        expected_modules += (SHORTCUT_MODULE,)
    if include_eventstream_topology:
        expected_modules += (EVENTSTREAM_MODULE,)
    for module in expected_modules:
        if module not in present:
            output["collection_health"].append(
                row(
                    "collection_health",
                    {"path": module + "/_missing", "sha256": "", "value": None},
                    "missing",
                    coverage_status="missing",
                    issue="no_collection_files",
                )
            )
    if estate_extractor is not None:
        estate_extractor(documents, runs, output)
    if module_extractor is not None:
        module_extractor(documents, runs, output)
    if pipeline_extractor is not None:
        pipeline_extractor(documents, output)
    for table, rows in output.items():
        unique = {}
        for entry in rows:
            entry["record_sha256"] = sha256(
                canonical(
                    {
                        key: value
                        for key, value in entry.items()
                        if key != "record_sha256"
                    }
                ).encode()
            )
            existing = unique.get(entry["observation_id"])
            if existing is not None and existing != entry:
                raise ValueError("Conflicting observation identity")
            unique[entry["observation_id"]] = entry
        output[table] = sorted(
            unique.values(), key=lambda entry: entry["observation_id"]
        )
    return output


def latest(rows, keys):
    """Select latest observations inside an explicitly chosen scope."""
    selected = {}
    for entry in rows:
        key = tuple(entry[field] for field in keys)
        order = (entry["observed_at_utc"] or "", entry["source_path"])
        if key not in selected or order > (
            selected[key]["observed_at_utc"] or "",
            selected[key]["source_path"],
        ):
            selected[key] = entry
    return list(selected.values())


def selected_permission_cycle(tables, mode):
    if mode not in {"Scoped", "Tenant"}:
        raise ValueError("Select Scoped or Tenant explicitly")
    candidates = [
        entry for entry in tables["permission_cycles"] if entry["mode"] == mode
    ]
    if not candidates:
        return None
    unknown = [entry for entry in candidates if entry["observed_at_utc"] is None]
    if unknown:
        return max(unknown, key=lambda entry: entry["source_path"])
    return max(
        candidates,
        key=lambda entry: (entry["observed_at_utc"] or "", entry["source_path"]),
    )
