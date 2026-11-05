import asyncio
import base64
import json
from unittest import mock

from env.modules import itemjobs
from test_workspace_filter import FakeContext, WORKSPACE_ID, OTHER_WORKSPACE_ID
from test_item_sources import Response

MODEL_ID = "ee9d3aed-f341-4bba-a41c-f8be25e97b9e"
EVENTHOUSE_ID = "ad021d12-0721-4c22-acc8-f6f64469988f"
NOTEBOOK_ID = "cc6c4ecb-ed65-4de9-8fe2-e003491114d4"
REPORT_ID = "11111111-1111-4111-8111-111111111111"
STREAM_ID = "22222222-2222-4222-8222-222222222222"
SECRET = "sig=TOPSECRETSAS"

PBIR = {"datasetReference": {"byConnection": {"connectionString": (
    f"Data Source=powerbi://api.powerbi.com/v1.0/myorg/fabricauditpoc;initial catalog=m;"
    f"integrated security=ClaimsToken;semanticmodelid={MODEL_ID}")}}}

TMDL = f"""expression 'Sample File' =
    let
      Source = Folder.Files("C:\\Projects\\monitor-output\\activity"),
      Web = Web.Contents("https://acct.blob.core.windows.net/c/f.json?{SECRET}"),
      Db = Sql.Database("srv.database.windows.net", "db"),
      Other = Table.SelectColumns(Source, {{"Content"}})
    in Db
"""


def _b64(text):
    return base64.b64encode(text.encode()).decode()


def test_report_row_points_at_semantic_model():
    index = {MODEL_ID: {"workspaceId": WORKSPACE_ID, "name": "model"}}
    rows = itemjobs._flatten_report({"definition.pbir": PBIR}, {}, index)

    assert len(rows) == 1
    assert (rows[0]["Role"], rows[0]["EndpointType"], rows[0]["TargetItemId"]) == ("Source", "SemanticModel", MODEL_ID)
    assert rows[0]["TargetWorkspaceId"] == WORKSPACE_ID and rows[0]["TargetItemName"] == "model"
    assert itemjobs._flatten_report({}, {}, {}) == []


def test_model_sources_keep_only_source_functions_and_strip_query_strings():
    sources = itemjobs._model_sources(TMDL)

    assert ("Folder.Files", "C:\\Projects\\monitor-output\\activity") in sources
    assert ("Web.Contents", "https://acct.blob.core.windows.net/c/f.json") in sources
    assert ("Sql.Database", "srv.database.windows.net") in sources
    assert all(fn != "Table.SelectColumns" for fn, _ in sources)
    assert SECRET not in json.dumps(sources)


def test_semantic_model_rows_are_deduplicated_data_sources():
    parts = {"model-sources": itemjobs._model_sources(TMDL) * 2}
    rows = itemjobs._flatten_semantic_model(parts, {}, {})

    assert len(rows) == 3
    assert all(r["Role"] == "DataSource" for r in rows)


def test_monitoring_and_kqldatabase_rows():
    monitoring = {"MonitoringProperties.json": {"dataCollectionSettings": [
        {"sources": {"workspaceDiagnostics": {"mode": "All"}}, "destinations": {"eventhouse": {"mode": "Auto"}}}]}}
    rows = itemjobs._flatten_monitoring(monitoring, {}, {})
    assert [(r["Role"], r["EndpointType"], r["TargetLocation"]) for r in rows] == [
        ("Source", "workspaceDiagnostics", "All"), ("Destination", "eventhouse", "Auto")]

    index = {EVENTHOUSE_ID: {"workspaceId": WORKSPACE_ID, "name": "eh"}}
    kql = itemjobs._flatten_kqldatabase({"DatabaseProperties.json": {"parentEventhouseItemId": EVENTHOUSE_ID}}, {}, index)
    assert [(r["Role"], r["TargetItemName"]) for r in kql] == [("ParentEventhouse", "eh")]
    assert itemjobs._flatten_kqldatabase({}, {}, {}) == []


def test_eventstream_topology_rows():
    topology = {
        "sources": [{"name": "src", "type": "AzureEventHub", "properties": {"dataConnectionId": "conn-1"}}],
        "destinations": [{"name": "dest", "type": "Eventhouse", "properties": {
            "workspaceId": WORKSPACE_ID, "itemId": EVENTHOUSE_ID, "tableName": "RawLogs"}}],
    }
    rows = itemjobs._flatten_eventstream(topology, {EVENTHOUSE_ID: "eh"}, {})

    assert [(r["Role"], r["EndpointType"]) for r in rows] == [("Source", "AzureEventHub"), ("Destination", "Eventhouse")]
    assert rows[0]["ConnectionId"] == "conn-1"
    assert (rows[1]["TargetItemId"], rows[1]["TargetItemName"], rows[1]["Table"]) == (EVENTHOUSE_ID, "eh", "RawLogs")


def test_pipeline_notebook_activity_has_target():
    content = {"properties": {"activities": [{"name": "Notebook1", "type": "TridentNotebook", "typeProperties": {
        "notebookId": NOTEBOOK_ID, "workspaceId": WORKSPACE_ID}}]}}
    rows = itemjobs._flatten_pipeline(content, {NOTEBOOK_ID: "nb"})

    assert rows == [{"Role": "Activity", "ActivityName": "Notebook1", "EndpointType": "TridentNotebook",
                     "TargetWorkspaceId": WORKSPACE_ID, "TargetItemId": NOTEBOOK_ID, "TargetItemName": "nb"}]


class ItemsContext(FakeContext):
    async def invokeAPI(self, rest_api, headers=None, json=None):
        return {"itemEntities": [
            {"id": REPORT_ID, "workspaceId": WORKSPACE_ID, "name": "rep", "type": "Report"},
            {"id": MODEL_ID, "workspaceId": WORKSPACE_ID, "name": "model", "type": "SemanticModel"},
            {"id": STREAM_ID, "workspaceId": WORKSPACE_ID, "name": "stream", "type": "Eventstream"},
            {"id": "33333333-3333-4333-8333-333333333333", "workspaceId": OTHER_WORKSPACE_ID,
             "name": "elsewhere", "type": "Report"},
        ]}


def test_main_collects_report_model_and_eventstream_rows():
    context = ItemsContext(include_ids={WORKSPACE_ID})
    urls = []

    def fake_request(method, url, **kwargs):
        urls.append(url)
        if url.endswith(f"/items/{REPORT_ID}/getDefinition"):
            parts = [{"path": "definition.pbir", "payload": _b64(json.dumps(PBIR))},
                     {"path": "definition/pages/p/visuals/v/visual.json", "payload": _b64("{}")}]
            return Response({"definition": {"parts": parts}})
        if url.endswith(f"/items/{MODEL_ID}/getDefinition"):
            return Response({"definition": {"parts": [
                {"path": "definition/expressions.tmdl", "payload": _b64(TMDL)}]}})
        if url.endswith("/topology"):
            return Response({"sources": [], "destinations": [{"name": "d", "type": "Eventhouse", "properties": {
                "workspaceId": WORKSPACE_ID, "itemId": EVENTHOUSE_ID, "tableName": "RawLogs"}}]})
        return Response({"value": []})

    with mock.patch("requests.request", side_effect=fake_request):
        asyncio.run(itemjobs.main(context))

    rows = next(c for p, _, c in context.fm.saved if p.startswith("itemdefinitions"))
    by_type = {}
    for row in rows:
        by_type.setdefault(row["ItemType"], []).append(row)

    assert [(r["Collector"], r["Role"], r["TargetItemId"]) for r in by_type["Report"]] == [
        ("Definition", "Source", MODEL_ID)]
    assert {r["EndpointType"] for r in by_type["SemanticModel"]} == {"Folder.Files", "Web.Contents", "Sql.Database"}
    assert [(r["Role"], r["Table"]) for r in by_type["Eventstream"]] == [("Destination", "RawLogs")]
    assert all(r["WorkspaceId"] == WORKSPACE_ID for r in rows)
    assert all(f"/workspaces/{WORKSPACE_ID}/" in u for u in urls)
    assert SECRET not in json.dumps(context.fm.saved)
