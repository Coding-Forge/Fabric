"""Flatten a Scanner API result into one row per lineage edge (both directions)."""

ITEM_TYPE_KEYS = {
    "reports": "Report",
    "dashboards": "Dashboard",
    "datasets": "SemanticModel",
    "dataflows": "Dataflow",
    "datamarts": "Datamart",
}
NON_ITEM_KEYS = {"id", "name", "type", "state", "isOnDedicatedCapacity", "capacityId",
                 "defaultDatasetStorageFormat", "domainId"}


def _lc(value):
    return value.lower() if isinstance(value, str) else None


def _datasource_label(instance):
    details = instance.get("connectionDetails") or {}
    parts = [details.get(k) for k in ("server", "database", "url", "path", "extensionDataSourcePath") if details.get(k)]
    return f"{instance.get('datasourceType')}: {' / '.join(parts)}" if parts else str(instance.get("datasourceType"))


def flatten_scan(scan):
    workspaces = scan.get("workspaces") or []
    instances = {_lc(i.get("datasourceId")): i for i in scan.get("datasourceInstances") or []}

    items = {}
    for ws in workspaces:
        for key, value in ws.items():
            if key in NON_ITEM_KEYS or not isinstance(value, list):
                continue
            item_type = ITEM_TYPE_KEYS.get(key, key)
            for it in value:
                if isinstance(it, dict) and it.get("id"):
                    items[_lc(it["id"])] = {
                        "id": it["id"], "name": it.get("name") or it.get("displayName"),
                        "type": item_type, "workspaceId": ws.get("id"), "workspaceName": ws.get("name"),
                        "raw": it, "key": key,
                    }

    upstream = set()
    datasources = {}

    def add(item_id, related_id, relation, related_override=None):
        if item_id and (related_id or related_override):
            upstream.add((_lc(item_id), _lc(related_id) if related_id else None, relation))
            if related_override:
                datasources[_lc(related_id)] = related_override

    for it in items.values():
        raw = it["raw"]
        for rel in raw.get("relations") or []:
            add(it["id"], rel.get("dependentOnArtifactId"), rel.get("relationType") or "Relation")
        if it["key"] == "reports" and raw.get("datasetId"):
            add(it["id"], raw["datasetId"], "ReportModel")
        for up in raw.get("upstreamDatasets") or []:
            add(it["id"], up.get("targetDatasetId"), "UpstreamDataset")
        for up in raw.get("upstreamDataflows") or []:
            add(it["id"], up.get("targetDataflowId"), "UpstreamDataflow")
        for use in raw.get("datasourceUsages") or []:
            ds_id = use.get("datasourceInstanceId")
            inst = instances.get(_lc(ds_id))
            if inst:
                add(it["id"], ds_id, "DataSource", {"name": _datasource_label(inst), "type": "DataSource"})

    def describe(item_id):
        if item_id in items:
            i = items[item_id]
            return i["name"], i["type"], i["workspaceId"], i["workspaceName"]
        d = datasources.get(item_id)
        return (d["name"], d["type"], None, None) if d else (None, None, None, None)

    rows = []
    for item_id, related_id, relation in upstream:
        if not related_id:
            continue
        for query_id, other_id, direction in ((item_id, related_id, "upstream"), (related_id, item_id, "downstream")):
            if query_id not in items:
                continue
            q = items[query_id]
            name, kind, ws_id, ws_name = describe(other_id)
            rows.append({
                "QueryItemId": q["id"],
                "QueryItemName": q["name"],
                "QueryItemType": q["type"],
                "QueryWorkspaceId": q["workspaceId"],
                "Direction": direction,
                "RelatedItemId": items[other_id]["id"] if other_id in items else other_id,
                "RelatedItemName": name,
                "RelatedItemType": kind,
                "RelatedWorkspaceId": ws_id,
                "RelatedWorkspaceName": ws_name,
                "RelationType": relation,
                "Source": "Scanner",
            })
    return rows
