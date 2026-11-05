import asyncio
import base64
import json
from datetime import datetime
from unittest import mock

from env.modules import itemjobs
from test_workspace_filter import FakeContext, WORKSPACE_ID, OTHER_WORKSPACE_ID

LAKEHOUSE_ID = "4bea5ffc-62d9-4ff5-9022-a8b43e7e3548"
EXTRA_LAKEHOUSE_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
NOTEBOOK_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
WAREHOUSE_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
CODE_MARKER = "SECRET_NOTEBOOK_CODE"

DEPENDENCIES = {
    "lakehouse": {
        "default_lakehouse": LAKEHOUSE_ID,
        "default_lakehouse_name": "fabricauditlh",
        "default_lakehouse_workspace_id": WORKSPACE_ID,
        "known_lakehouses": [{"id": LAKEHOUSE_ID}, {"id": EXTRA_LAKEHOUSE_ID}],
    }
}

NOTEBOOK_PY = f"""# Fabric notebook source

# METADATA ********************

# META {{
# META   "kernel_info": {{
# META     "name": "synapse_pyspark"
# META   }},
# META   "dependencies": {{
# META     "lakehouse": {json.dumps(DEPENDENCIES["lakehouse"])}
# META   }}
# META }}

# CELL ********************

print("{CODE_MARKER}")

# METADATA ********************

# META {{
# META   "language": "python"
# META }}
"""

NOTEBOOK_IPYNB = json.dumps({
    "cells": [{"cell_type": "code", "source": [CODE_MARKER]}],
    "metadata": {"kernel_info": {"name": "synapse_pyspark"}, "dependencies": DEPENDENCIES},
})


def test_notebook_dependencies_parse_py_and_ipynb():
    assert itemjobs._notebook_dependencies("notebook-content.py", NOTEBOOK_PY) == DEPENDENCIES
    assert itemjobs._notebook_dependencies("notebook-content.ipynb", NOTEBOOK_IPYNB) == DEPENDENCIES
    assert itemjobs._notebook_dependencies("notebook-content.py", "print('no metadata')") == {}


def test_flatten_notebook_emits_attached_and_known_lakehouses():
    item_index = {EXTRA_LAKEHOUSE_ID: {"workspaceId": OTHER_WORKSPACE_ID, "name": "otherlh"}}
    rows = itemjobs._flatten_notebook({"notebook-dependencies": DEPENDENCIES}, {}, item_index)

    assert [(r["Role"], r["TargetItemId"]) for r in rows] == [
        ("AttachedLakehouse", LAKEHOUSE_ID),
        ("KnownLakehouse", EXTRA_LAKEHOUSE_ID),
    ]
    assert rows[0]["TargetWorkspaceId"] == WORKSPACE_ID and rows[0]["TargetItemName"] == "fabricauditlh"
    assert rows[1]["TargetWorkspaceId"] == OTHER_WORKSPACE_ID and rows[1]["TargetItemName"] == "otherlh"


def test_flatten_shortcuts_covers_onelake_and_external_targets():
    rows = itemjobs._flatten_shortcuts([
        {"name": "a", "path": "Files/a", "target": {"type": "OneLake", "oneLake": {
            "workspaceId": OTHER_WORKSPACE_ID, "itemId": EXTRA_LAKEHOUSE_ID, "path": "Tables/t"}}},
        {"name": "b", "path": "Files/b", "target": {"type": "AdlsGen2", "adlsGen2": {
            "location": "https://acct.dfs.core.windows.net", "subpath": "/c/d", "connectionId": "conn-1"}}},
        {"name": "c", "path": "Files/c", "target": {"type": "AmazonS3"}},
    ], {EXTRA_LAKEHOUSE_ID: "otherlh"})

    assert all(r["Role"] == "ShortcutSource" for r in rows)
    one, adls, s3 = rows
    assert (one["TargetType"], one["TargetWorkspaceId"], one["TargetItemId"], one["TargetItemName"]) == (
        "OneLake", OTHER_WORKSPACE_ID, EXTRA_LAKEHOUSE_ID, "otherlh")
    assert (adls["TargetType"], adls["TargetLocation"], adls["TargetPath"], adls["ConnectionId"]) == (
        "AdlsGen2", "https://acct.dfs.core.windows.net", "/c/d", "conn-1")
    assert s3["TargetType"] == "AmazonS3" and s3["ConnectionId"] is None


SCAN = {
    "workspaces": [
        {"id": WORKSPACE_ID, "name": "poc", "warehouses": [
            {"id": WAREHOUSE_ID, "name": "wh", "datasourceUsages": [{"datasourceInstanceId": "DS-1"}]}]},
        {"id": OTHER_WORKSPACE_ID, "name": "other", "datasets": [
            {"id": "ffffffff-ffff-4fff-8fff-ffffffffffff", "name": "m",
             "datasourceUsages": [{"datasourceInstanceId": "DS-1"}]}]},
    ],
    "datasourceInstances": [{
        "datasourceId": "ds-1", "datasourceType": "Sql", "gatewayId": "gw",
        "connectionDetails": {"server": "srv.database.windows.net", "database": "db"},
    }],
}


def test_flatten_scanner_scopes_to_included_workspaces():
    rows = itemjobs._flatten_scanner([SCAN, SCAN], {}, frozenset({WORKSPACE_ID}), frozenset())

    assert len(rows) == 1
    row = rows[0]
    assert (row["Collector"], row["Role"], row["ItemType"], row["WorkspaceId"]) == (
        "Scanner", "DataSource", "Warehouse", WORKSPACE_ID)
    assert row["EndpointType"] == "Sql" and row["TargetLocation"] == "srv.database.windows.net / db"


def _definition_response(path, text):
    payload = base64.b64encode(text.encode()).decode()
    return {"definition": {"parts": [{"path": path, "payload": payload}]}}


class Response:
    def __init__(self, body, status=200):
        self._body, self.status_code, self.headers, self.text = body, status, {}, ""

    def json(self):
        return self._body


class SourceContext(FakeContext):
    async def invokeAPI(self, rest_api, headers=None, json=None):
        return {"itemEntities": [
            {"id": NOTEBOOK_ID, "workspaceId": WORKSPACE_ID, "name": "nb", "type": "Notebook"},
            {"id": LAKEHOUSE_ID, "workspaceId": WORKSPACE_ID, "name": "fabricauditlh", "type": "Lakehouse"},
            {"id": "99999999-9999-4999-8999-999999999999", "workspaceId": OTHER_WORKSPACE_ID,
             "name": "elsewhere", "type": "Lakehouse"},
        ]}


def test_main_emits_definition_shortcut_and_scanner_rows_without_notebook_code():
    context = SourceContext(include_ids={WORKSPACE_ID})
    day = datetime.now()
    scan_path = f"catalog/scans/{day:%Y}/{day:%m}/{day:%d}/"
    context.fm.files[f"{scan_path}{day:%Y%m%d}_00001.scanResults.json"] = json.dumps(SCAN)
    urls = []

    def fake_request(method, url, **kwargs):
        urls.append(url)
        if url.endswith("/getDefinition"):
            return Response(_definition_response("notebook-content.py", NOTEBOOK_PY))
        if url.endswith("/jobs/instances"):
            return Response({"value": []})
        if "/shortcuts" in url and "page=2" not in url:
            return Response({"value": [{"name": "s1", "path": "Files/s1", "target": {
                "type": "AmazonS3", "amazonS3": {"location": "https://b.s3.amazonaws.com",
                                                 "connectionId": "conn-9"}}}],
                             "continuationUri": url + "?page=2"})
        return Response({"value": []})

    with mock.patch("requests.request", side_effect=fake_request):
        asyncio.run(itemjobs.main(context))

    saved = {path.split("/")[0]: content for path, _, content in context.fm.saved}
    rows = saved["itemdefinitions"]
    by_collector = {}
    for row in rows:
        by_collector.setdefault(row["Collector"], []).append(row)

    assert {r["Role"] for r in by_collector["Definition"]} == {"AttachedLakehouse", "KnownLakehouse"}
    assert [(r["Role"], r["TargetType"], r["ConnectionId"]) for r in by_collector["Shortcuts"]] == [
        ("ShortcutSource", "AmazonS3", "conn-9")]
    assert [(r["ItemType"], r["Role"]) for r in by_collector["Scanner"]] == [("Warehouse", "DataSource")]
    assert all(r["WorkspaceId"] == WORKSPACE_ID for r in rows)
    assert all(f"/workspaces/{WORKSPACE_ID}/" in u for u in urls)
    assert CODE_MARKER not in json.dumps(context.fm.saved)
