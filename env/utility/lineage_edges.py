"""Normalize item-level dependencies from an existing Scanner API response."""

import re

ITEM_TYPES = {"reports": "Report", "datasets": "SemanticModel", "dataflows": "Dataflow"}


def _text(value, field, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid lineage field: {field}")
    return value.strip()


def _identifier(value, field, required=False):
    text = _text(value, field, required)
    return text.lower() if text else None


def _records(parent, field, required=False):
    value = parent.get(field)
    if value is None and not required:
        return []
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"Invalid lineage collection: {field}")
    return value


def scan_snapshot(
    scan, scan_id, requested_workspace_ids, observed_at_utc, full_scan=False
):
    """Build a batch observation, not an exhaustive or historical tenant graph.

    Unknown fields are ignored. Malformed recognized fields raise ``ValueError``
    rather than becoming successful empty observations. Missing optional
    metadata and references outside this batch remain unresolved.
    """
    if not isinstance(scan_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", scan_id
    ):
        raise ValueError("Invalid lineage scan ID")
    if not isinstance(scan, dict) or any(key in scan for key in ("ERROR", "error")):
        raise ValueError("Invalid lineage scan response")
    requested = sorted(
        {
            _identifier(value, "requestedWorkspaceId", required=True)
            for value in requested_workspace_ids
        }
    )
    workspaces = _records(scan, "workspaces", required=True)
    returned = set()
    items = {}
    raw_items = {}
    for workspace in workspaces:
        ws_id = _identifier(workspace.get("id"), "workspace.id", required=True)
        if ws_id in returned or ws_id not in requested:
            raise ValueError("Duplicate or unexpected lineage workspace")
        if any(key in workspace for key in ("ERROR", "error", "scanError")):
            raise ValueError("Failed lineage workspace")
        returned.add(ws_id)
        for key, kind in ITEM_TYPES.items():
            for raw in _records(workspace, key):
                item_id = _identifier(
                    raw.get("objectId") if key == "dataflows" else raw.get("id"),
                    f"{key}.id",
                    required=True,
                )
                if item_id in items:
                    raise ValueError("Duplicate lineage item")
                items[item_id] = {
                    "id": item_id,
                    "name": _text(raw.get("name"), f"{key}.name"),
                    "type": kind,
                    "workspaceId": ws_id,
                }
                raw_items[item_id] = raw

    datasources = {}
    for raw in _records(scan, "datasourceInstances"):
        source_id = _identifier(raw.get("datasourceId"), "datasourceId", required=True)
        if source_id in datasources:
            raise ValueError("Duplicate lineage datasource")
        kind = _text(raw.get("datasourceType"), "datasourceType")
        details = raw.get("connectionDetails")
        if details is not None and not isinstance(details, dict):
            raise ValueError("Invalid lineage connectionDetails")
        # Do not export arbitrary connection strings, URLs or expression payloads.
        labels = [
            _text((details or {}).get(key), f"connectionDetails.{key}")
            for key in ("server", "database")
        ]
        label = " / ".join(part for part in labels if part)
        datasources[source_id] = {
            "id": source_id,
            "name": f"{kind}: {label}" if kind and label else (kind or label or None),
            "type": "DataSource",
            "workspaceId": None,
        }

    edges = {}

    def add(query_id, related_id, relation, related_type=None, related_ws=None):
        query = items[query_id]
        related = (
            datasources.get(related_id)
            if related_type == "DataSource"
            else items.get(related_id)
        )
        if related is None:
            related = {
                "id": related_id,
                "name": None,
                "type": related_type,
                "workspaceId": related_ws,
            }

        def emit(source, target, direction):
            row = {
                "QueryItemId": source["id"],
                "QueryItemName": source["name"],
                "QueryItemType": source["type"],
                "QueryWorkspaceId": source["workspaceId"],
                "Direction": direction,
                "RelatedItemId": target["id"],
                "RelatedItemName": target["name"],
                "RelatedItemType": target["type"],
                "RelatedWorkspaceId": target["workspaceId"],
                "RelationType": relation,
                "Source": "Scanner",
            }
            key = (source["id"], direction, target["id"], relation)
            existing = edges.get(key)
            if existing is not None:
                for field, value in row.items():
                    if existing[field] is None:
                        existing[field] = value
                    elif value is not None and existing[field] != value:
                        raise ValueError("Conflicting lineage reference metadata")
            else:
                edges[key] = row

        emit(query, related, "upstream")
        if related_type != "DataSource" and related_id in items:
            emit(related, query, "downstream")

    for item_id, raw in raw_items.items():
        if items[item_id]["type"] == "Report" and raw.get("datasetId") is not None:
            add(
                item_id,
                _identifier(raw["datasetId"], "datasetId", True),
                "ReportModel",
                "SemanticModel",
            )
        for field, target, relation, kind in (
            ("upstreamDatasets", "targetDatasetId", "UpstreamDataset", "SemanticModel"),
            ("upstreamDataflows", "targetDataflowId", "UpstreamDataflow", "Dataflow"),
        ):
            for ref in _records(raw, field):
                add(
                    item_id,
                    _identifier(ref.get(target), target, True),
                    relation,
                    kind,
                    _identifier(ref.get("groupId"), "groupId"),
                )
        for ref in _records(raw, "relations"):
            add(
                item_id,
                _identifier(
                    ref.get("dependentOnArtifactId"), "dependentOnArtifactId", True
                ),
                _text(ref.get("relationType"), "relationType") or "Relation",
            )
        for ref in _records(raw, "datasourceUsages"):
            add(
                item_id,
                _identifier(
                    ref.get("datasourceInstanceId"), "datasourceInstanceId", True
                ),
                "DataSource",
                "DataSource",
            )

    return {
        "schemaVersion": 1,
        "source": "Scanner",
        "scanId": scan_id,
        "observedAtUtc": observed_at_utc,
        "scanMode": "full" if full_scan else "incremental",
        "requestedWorkspaceIds": requested,
        "returnedWorkspaceIds": sorted(returned),
        "items": [items[key] for key in sorted(items)],
        "complete": True,
        "edges": [edges[key] for key in sorted(edges)],
    }
