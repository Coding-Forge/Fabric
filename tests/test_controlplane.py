import asyncio
import json
from datetime import datetime
from unittest import mock

from env.modules import controlplane
from env.context import utc_now
from tests.test_item_sources import Response
from tests.test_workspace_filter import FakeContext, WORKSPACE_ID, OTHER_WORKSPACE_ID, ITEM_ID, OTHER_ITEM_ID

PIPELINE_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"

SCAN = {"workspaces": [
    {"id": WORKSPACE_ID, "name": "poc", "datasets": [
        {"id": ITEM_ID, "name": "model", "createdBy": "owner@contoso.com", "modifiedBy": "mod@contoso.com"}]},
    {"id": OTHER_WORKSPACE_ID, "name": "other", "datasets": [{"id": OTHER_ITEM_ID, "name": "x"}]},
]}

WS_USERS = {"accessDetails": [{
    "principal": {"id": "u1", "displayName": "User One", "type": "User",
                  "userDetails": {"userPrincipalName": "u1@contoso.com"}},
    "workspaceAccessDetails": {"workspaceRole": "Admin"}}]}
ITEM_USERS = {"accessDetails": [{
    "principal": {"id": "g1", "displayName": "Group One", "type": "Group"},
    "itemAccessDetails": {"type": "SemanticModel", "permissions": ["Read"], "additionalPermissions": []}}]}


def _day():
    d = utc_now()
    return f"{d:%Y}/{d:%m}/{d:%d}/", d


def test_latest_run_and_volume_mapping():
    runs = controlplane._latest_runs([
        {"ItemId": "a", "Status": "Failed", "StartTimeUtc": "2026-01-01T00:00:00Z", "FailureReason": "x" * 900},
        {"ItemId": "a", "Status": "Completed", "StartTimeUtc": "2026-01-02T00:00:00Z"},
    ])
    assert controlplane._run_columns(runs["a"])["LastRunStatus"] == "Completed"
    assert controlplane._run_columns(runs["a"])["FailedRunsCollected"] == 1
    assert len(controlplane._run_columns({"run": {"FailureReason": "x" * 900}, "total": 1, "failed": 1})
               ["LastRunFailureReason"]) == controlplane.MAX_FAILURE_REASON_CHARS

    volumes = controlplane._latest_activity_volume([
        {"ItemId": "p", "ActivityName": "Copy", "ActivityStart": "1", "RowsCopied": 1},
        {"ItemId": "p", "ActivityName": "Copy", "ActivityStart": "2", "RowsCopied": 7, "DataWrittenBytes": 70},
        {"ItemId": "p", "ActivityName": "Nb", "ActivityStart": "2"},
    ])
    hit = controlplane._volume_columns({"ItemId": "p", "ActivityName": "Copy"}, volumes)
    assert (hit["RowsCopied"], hit["DataWrittenBytes"], hit["VolumeSource"]) == (7, 70, "PipelineActivityRun")
    miss = controlplane._volume_columns({"ItemId": "p", "ActivityName": "Nb"}, volumes)
    assert miss["RowsCopied"] is None and miss["VolumeSource"] == "NotAvailableFromApi"


def test_flatten_access_prefers_upn():
    ws = controlplane._flatten_access(WS_USERS["accessDetails"])
    item = controlplane._flatten_access(ITEM_USERS["accessDetails"])
    assert ws == [{"Principal": "u1@contoso.com", "PrincipalType": "User", "PrincipalId": "u1", "Role": "Admin"}]
    assert item[0]["Principal"] == "Group One" and item[0]["Permissions"] == ["Read"]


def test_lineage_falls_back_to_saved_scanner_results_without_beta_calls():
    context = FakeContext()
    day_path, day = _day()
    context.fm.files[f"catalog/scans/{day_path}{day:%Y%m%d}_00001.scanResults.json"] = json.dumps({
        "workspaces": [{
            "id": WORKSPACE_ID,
            "reports": [{"id": PIPELINE_ID, "datasetId": ITEM_ID}],
            "datasets": [{"id": ITEM_ID, "name": "model"}],
        }],
    })

    edges = asyncio.run(controlplane._load_lineage(context, day))

    assert len(edges) == 2
    upstream = next(edge for edge in edges if edge["Direction"] == "upstream")
    assert upstream["QueryItemId"] == PIPELINE_ID
    assert upstream["RelatedItemId"] == ITEM_ID
    assert upstream["Source"] == "Scanner"
    assert context.api_calls == []


def test_main_one_row_per_endpoint_and_item_row_for_items_without_endpoints():
    context = FakeContext(include_ids={WORKSPACE_ID})
    day_path, d = _day()
    files = context.fm.files
    files[f"itemdefinitions/{day_path}itemdefinitions_00001.json"] = json.dumps([
        {"ItemId": PIPELINE_ID, "ItemName": "p", "ItemType": "DataPipeline", "WorkspaceId": WORKSPACE_ID,
         "Collector": "Definition", "Role": "Activity", "ActivityName": "Copy"},
        {"ItemId": PIPELINE_ID, "ItemName": "p", "ItemType": "DataPipeline", "WorkspaceId": WORKSPACE_ID,
         "Collector": "Definition", "Role": "Destination", "ActivityName": "Copy"},
        {"ItemId": OTHER_ITEM_ID, "WorkspaceId": OTHER_WORKSPACE_ID, "Role": "Source"},
    ])
    files[f"jobs/{day_path}jobs_00001.json"] = json.dumps([
        {"ItemId": PIPELINE_ID, "Status": "Completed", "StartTimeUtc": "2026-01-02T00:00:00Z"}])
    files[f"jobactivityruns/{day_path}jobactivityruns_00001.json"] = json.dumps([
        {"ItemId": PIPELINE_ID, "ActivityName": "Copy", "ActivityStart": "1", "RowsCopied": 5}])
    files[f"catalog/scans/{day_path}{d:%Y%m%d}_00001.scanResults.json"] = json.dumps(SCAN)
    urls = []

    def fake_request(method, url, **kwargs):
        urls.append(url)
        if url.endswith(f"/admin/workspaces/{WORKSPACE_ID}/users"):
            return Response(WS_USERS)
        return Response(ITEM_USERS)

    with mock.patch("requests.request", side_effect=fake_request):
        asyncio.run(controlplane.main(context))

    path, name, rows = context.fm.saved[-1]
    assert path == f"controlplane/{day_path}" and name == "controlplane_00001.json"
    assert all(r["WorkspaceId"] == WORKSPACE_ID for r in rows)
    assert not any(OTHER_WORKSPACE_ID in u for u in urls)
    pipeline = [r for r in rows if r["ItemId"] == PIPELINE_ID]
    assert {r["Role"] for r in pipeline} == {"Activity", "Destination"}
    assert pipeline[0]["RowsCopied"] == 5 and pipeline[0]["LastRunStatus"] == "Completed"
    assert pipeline[0]["WorkspaceAccess"][0]["Principal"] == "u1@contoso.com"
    model = [r for r in rows if r["ItemId"] == ITEM_ID]
    assert len(model) == 1 and model[0]["Role"] == "Item" and model[0]["OwnerPrincipal"] == "owner@contoso.com"


def test_item_detail_rows_and_inventory_items_are_captured():
    context = FakeContext(include_ids={WORKSPACE_ID})
    urls = []

    def fake_request(method, url, **kwargs):
        urls.append(url)
        if "/dataPipelines/" in url:
            return Response({"id": ITEM_ID, "description": "nightly", "properties": {"k": "v"}})
        if "/admin/workspaces/" in url:
            return Response(WS_USERS if url.endswith(f"{WORKSPACE_ID}/users") else ITEM_USERS)
        return Response({}, 404)

    with mock.patch("requests.request", side_effect=fake_request):
        asyncio.run(controlplane.main(context))

    saved = {p.split("/")[0]: c for p, _, c in context.fm.saved}
    detail = saved["itemdetails"]
    assert [d["ItemId"] for d in detail] == [ITEM_ID]
    assert detail[0]["Description"] == "nightly" and detail[0]["ItemProperties"] == {"k": "v"}
    assert any("/dataPipelines/" in u for u in urls)
    assert saved["controlplane"][0]["Collector"] == "Inventory"
    assert saved["controlplane"][0]["Description"] == "nightly"


def test_delta_volume_matches_commits_inside_completed_run_window():
    from datetime import timezone
    ts = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    dest = {"ItemId": "cj", "ItemType": "CopyJob", "Role": "Destination", "TargetItemId": "lh",
            "Schema": "dbo", "Table": "t"}
    commits = {("lh", "dbo", "t"): [
        {"Timestamp": ts("2026-11-04T21:00:00"), "Operation": "Write", "Rows": 99, "Bytes": 999},
        {"Timestamp": ts("2026-11-04T21:21:20"), "Operation": "Update", "Rows": 5, "Bytes": 3890},
    ]}
    run = {"run": {"Status": "Completed", "StartTimeUtc": "2026-11-04T21:21:01.0952297",
                   "EndTimeUtc": "2026-11-04T21:21:34.1609015"}}
    cols = controlplane._delta_columns(dest, run, commits)
    assert (cols["RowsWritten"], cols["BytesWritten"], cols["VolumeSource"]) == (5, 3890, "DeltaLog")

    failed = {"run": {**run["run"], "Status": "Failed"}}
    assert controlplane._delta_columns(dest, failed, commits)["RowsWritten"] is None
    assert controlplane._delta_columns({**dest, "Role": "Source"}, run, commits)["RowsWritten"] is None


def test_read_delta_commits_sums_add_actions():
    class P:
        def __init__(self, name):
            self.name, self.last_modified = name, datetime(2026, 11, 4)

    logs = {
        "lh/Tables/dbo/t/_delta_log/00000000000000000000.json": '{"protocol": {}}\n{"commitInfo": {"operation": "Write"}}',
        "lh/Tables/dbo/t/_delta_log/00000000000000000001.json":
            '{"add": {"size": 3890, "stats": "{\\"numRecords\\":5}"}}\n{"commitInfo": {"operation": "Update"}}',
    }

    class Reader:
        def readall(self):
            return self.text.encode()

    class FileClient:
        def __init__(self, name):
            self.name = name

        def download_file(self):
            r = Reader()
            r.text = logs[self.name]
            return r

    class Fsc:
        def get_paths(self, path, recursive):
            return [P(n) for n in logs] + [P("lh/Tables/dbo/t/_delta_log/_commits")]

        def get_file_client(self, name):
            return FileClient(name)

    commits = controlplane._read_delta_commits(Fsc(), "lh", "dbo", "t")
    assert [(c["Operation"], c["Rows"], c["Bytes"]) for c in commits] == [("Write", 0, 0), ("Update", 5, 3890)]


def test_main_adds_delta_volume_for_lakehouse_destination(monkeypatch):
    from datetime import timezone
    context = FakeContext(include_ids={WORKSPACE_ID})
    day_path, d = _day()
    context.fm.files[f"itemdefinitions/{day_path}itemdefinitions_00001.json"] = json.dumps([
        {"ItemId": PIPELINE_ID, "ItemName": "cj", "ItemType": "CopyJob", "WorkspaceId": WORKSPACE_ID,
         "Role": "Destination", "EndpointType": "LakehouseTable", "TargetItemId": ITEM_ID,
         "TargetWorkspaceId": WORKSPACE_ID, "Schema": "dbo", "Table": "t"}])
    context.fm.files[f"jobs/{day_path}jobs_00001.json"] = json.dumps([
        {"ItemId": PIPELINE_ID, "Status": "Completed", "StartTimeUtc": "2026-11-04T21:21:01",
         "EndTimeUtc": "2026-11-04T21:21:34"}])
    monkeypatch.setattr(controlplane, "_open_onelake", lambda ctx, ws: object())
    monkeypatch.setattr(controlplane, "_read_delta_commits", lambda fsc, i, s, t: [
        {"Timestamp": datetime(2026, 11, 4, 21, 21, 20, tzinfo=timezone.utc), "Operation": "Update",
         "Rows": 5, "Bytes": 3890}])

    with mock.patch("requests.request", return_value=Response({}, 404)):
        asyncio.run(controlplane.main(context))

    row = [r for r in context.fm.saved[-1][2] if r["ItemId"] == PIPELINE_ID][0]
    assert (row["RowsWritten"], row["BytesWritten"], row["VolumeSource"]) == (5, 3890, "DeltaLog")


def test_get_access_tolerates_empty_200_body():
    details, err = controlplane._get_access("https://x", {}, lambda m, u, h: Response(None, 200))
    assert details == [] and err is None


def test_main_tolerates_missing_inputs_and_access_errors():
    context = FakeContext()
    with mock.patch("requests.request", return_value=Response({}, 403)):
        asyncio.run(controlplane.main(context))
    rows = context.fm.saved[-1][2]
    assert rows and all(r["State"] is None and r["ItemAccess"] is None for r in rows)


UP_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


def test_directed_edges_merge_sources_and_fill_names():
    raw = [
        {"QueryItemId": ITEM_ID, "QueryItemName": "model", "QueryItemType": "SemanticModel",
         "QueryWorkspaceId": WORKSPACE_ID, "Direction": "upstream", "RelatedItemId": UP_ID,
         "RelatedItemName": "lh", "RelatedItemType": "Lakehouse", "RelatedWorkspaceId": OTHER_WORKSPACE_ID,
         "RelationType": "Datasource", "Source": "Scanner"},
        {"QueryItemId": UP_ID, "QueryItemType": "Lakehouse", "QueryWorkspaceId": OTHER_WORKSPACE_ID,
         "Direction": "downstream", "RelatedItemId": ITEM_ID, "RelationType": "Datasource",
         "RelatedWorkspaceId": WORKSPACE_ID},
        {"QueryItemId": OTHER_ITEM_ID, "QueryWorkspaceId": "zzz", "Direction": "upstream",
         "RelatedItemId": PIPELINE_ID, "RelatedWorkspaceId": "zzz", "RelationType": "Datasource"},
        {"QueryItemId": ITEM_ID, "Direction": "upstream", "RelatedItemId": ITEM_ID},
    ]
    info = {UP_ID: {"ItemName": "lh2"}}
    edges = controlplane._directed_edges(raw, info, frozenset({WORKSPACE_ID}), frozenset())
    assert len(edges) == 1
    edge = edges[0]
    assert edge["From"]["ItemId"] == UP_ID and edge["To"]["ItemId"] == ITEM_ID
    assert edge["From"]["ItemName"] == "lh" and edge["Sources"] == ["Scanner", "Unknown"]


def test_activity_by_item_and_columns():
    events = [
        {"ObjectId": ITEM_ID.upper(), "Activity": "ViewReport", "CreationTime": "2026-01-01T00:00:00",
         "UserId": "a@x.com", "ClientIP": "1.1.1.1", "ResultStatus": "Succeeded"},
        {"ObjectId": ITEM_ID, "Activity": "EditReport", "CreationTime": "2026-01-02T00:00:00",
         "UserId": "b@x.com", "ClientIP": "2.2.2.2"},
        {"Activity": "GetArtifactsViaAdminApi", "CreationTime": "2026-01-03T00:00:00"},
    ]
    activity = controlplane._activity_by_item(events)
    cols = controlplane._activity_columns(ITEM_ID, activity)
    assert cols["LastActivity"] == "EditReport" and cols["LastActivityUser"] == "b@x.com"
    assert cols["ActivityCount"] == 2 and cols["ActivityUsers"] == ["a@x.com", "b@x.com"]
    assert controlplane._activity_columns(UP_ID, activity)["ActivityCount"] is None


def test_main_adds_lineage_activity_columns_and_lineagegraph():
    context = FakeContext(include_ids={WORKSPACE_ID})
    day_path, d = _day()
    files = context.fm.files
    files[f"itemdefinitions/{day_path}itemdefinitions_00001.json"] = json.dumps([
        {"ItemId": PIPELINE_ID, "ItemName": "p", "ItemType": "DataPipeline", "WorkspaceId": WORKSPACE_ID,
         "Collector": "Definition", "Role": "Activity"}])
    files[f"catalog/scans/{day_path}{d:%Y%m%d}_00001.scanResults.json"] = json.dumps(SCAN)
    files[f"lineage/{day_path}lineage_00001.json"] = json.dumps([
        {"QueryItemId": PIPELINE_ID, "QueryItemType": "DataPipeline", "QueryWorkspaceId": WORKSPACE_ID,
         "Direction": "downstream", "RelatedItemId": ITEM_ID, "RelatedItemName": "model",
         "RelatedItemType": "SemanticModel", "RelatedWorkspaceId": WORKSPACE_ID, "RelationType": "Datasource"}])
    files[f"lineage_edges/{day_path}{d:%Y%m%d}_00001.lineage_edges.json"] = json.dumps([
        {"QueryItemId": ITEM_ID, "QueryItemName": "model", "QueryItemType": "SemanticModel",
         "QueryWorkspaceId": WORKSPACE_ID, "Direction": "upstream", "RelatedItemId": PIPELINE_ID,
         "RelatedItemName": "p", "RelatedItemType": "DataPipeline", "RelatedWorkspaceId": WORKSPACE_ID,
         "RelationType": "Datasource", "Source": "Scanner"}])
    files[f"activity/{day_path}{d:%Y%m%d}_00001.json"] = json.dumps([
        {"ObjectId": PIPELINE_ID, "Activity": "RunArtifact", "CreationTime": "2026-01-02T00:00:00",
         "UserId": "runner@contoso.com", "ClientIP": "9.9.9.9"}])
    files[f"graph/{day_path}users.json"] = json.dumps([
        {"id": "u1", "displayName": "Runner Person", "userPrincipalName": "runner@contoso.com"}])

    def fake_request(method, url, **kwargs):
        return Response(WS_USERS if url.endswith("/users") and "/items/" not in url else ITEM_USERS)

    with mock.patch("requests.request", side_effect=fake_request):
        asyncio.run(controlplane.main(context))

    saved = {path: rows for path, _, rows in context.fm.saved}
    graph = saved[f"lineagegraph/{day_path}"]
    assert len(graph) == 1
    assert graph[0]["UpstreamItemId"] == PIPELINE_ID and graph[0]["DownstreamItemId"] == ITEM_ID
    assert graph[0]["UpstreamLastActivityUser"] == "runner@contoso.com"
    assert graph[0]["Sources"] == ["FabricRelations", "Scanner"]
    rows = saved[f"controlplane/{day_path}"]
    pipeline = [r for r in rows if r["ItemId"] == PIPELINE_ID][0]
    assert pipeline["DownstreamCount"] == 1 and pipeline["DownstreamItems"][0]["ItemId"] == ITEM_ID
    assert pipeline["LastActivityUser"] == "runner@contoso.com" and pipeline["ActivityCount"] == 1
    model = [r for r in rows if r["ItemId"] == ITEM_ID][0]
    assert model["UpstreamCount"] == 1 and model["ActivityCount"] is None
    operations = saved[f"controlplane_operations/{day_path}"]
    assert len(operations) == 1 and operations[0]["Operation"] == "RunArtifact"
    assert operations[0]["ItemId"] == PIPELINE_ID and operations[0]["DownstreamItemNames"] == "model"
    assert pipeline["LastOperation"] == "RunArtifact" and pipeline["LastOperationUpn"] == "runner@contoso.com"
    audit = saved[f"fabric_audit/{day_path}"]
    assert len(audit) == 1 and audit[0]["UserDisplayName"] == "Runner Person"
    assert audit[0]["OperationType"] == "Change" and audit[0]["DownstreamItemNames"] == "model (SemanticModel)"


def test_consolidated_reads_and_changes_with_item_context():
    info = {ITEM_ID: {"ItemName": "model", "ItemType": "SemanticModel", "WorkspaceId": WORKSPACE_ID}}
    rows = [
        {"ItemId": ITEM_ID, "OwnerPrincipal": "own@x.com", "State": "Active", "RunsCollected": 3,
         "FailedRunsCollected": 1, "LastRunStatus": "Failed", "DownstreamItems": [
             {"ItemName": "r", "ItemType": "Report"}, {"ItemName": "r", "ItemType": "Report"}],
         "Role": "Source", "EndpointType": "Lakehouse", "TargetItemName": "lh", "RowsCopied": 5},
        {"ItemId": ITEM_ID, "Role": "Destination", "EndpointType": "Warehouse", "TargetItemName": "wh", "RowsCopied": 7},
    ]
    context = controlplane.build_item_context(rows)[ITEM_ID.lower()]
    assert context["DownstreamItemNames"] == "r (Report)" and context["Sources"] == "lh (Lakehouse)"
    assert context["Destinations"] == "wh (Warehouse)" and context["RowsCopied"] == 12
    events = [
        {"Id": "1", "Activity": "ViewReport", "ObjectId": ITEM_ID, "UserId": "a@x.com", "UserType": 0,
         "CreationTime": "2026-01-01T10:00:00", "CapacityName": "cap"},
        {"Id": "1", "Activity": "ViewReport", "ObjectId": ITEM_ID, "UserId": "a@x.com"},
        {"Id": "2", "Activity": "DeleteArtifact", "ObjectId": "other", "WorkspaceId": OTHER_WORKSPACE_ID},
    ]
    out = controlplane.build_consolidated(events, info, {ITEM_ID.lower(): context}, {}, set(),
                                          {"a@x.com": "A User"}, {WORKSPACE_ID}, set(), "now")
    assert len(out) == 1
    assert out[0]["OperationType"] == "Read" and out[0]["UserDisplayName"] == "A User"
    assert out[0]["EventDate"] == "2026-01-01" and out[0]["CapacityName"] == "cap"
    assert out[0]["ItemOwner"] == "own@x.com" and out[0]["FailedRunsCollected"] == 1


COLLECTOR_APP = "9e0ea2b0-8a2f-49dd-acfe-b66a228ee30b"
COLLECTOR_OBJ = "6fbc11c0-43c3-4f63-917a-f06591c59a41"
USER_OBJ = "10032006459FC222"


def test_actor_resolution_collector_user_and_unresolved_guid():
    events = [
        {"UserId": COLLECTOR_APP, "UserKey": COLLECTOR_OBJ, "UserType": 6, "Activity": "GetArtifactsViaAdminApi"},
        {"UserId": "ann@contoso.com", "UserKey": USER_OBJ, "UserType": 0, "Activity": "ReadArtifact"},
        {"UserId": COLLECTOR_OBJ, "UserKey": COLLECTOR_OBJ, "UserType": 0, "Activity": "CreateFile"},
        {"UserId": USER_OBJ, "UserKey": USER_OBJ, "UserType": 0, "Activity": "DeleteArtifact"},
        {"UserId": "243171c9-b3eb-4c61-8e10-ead6377b8642", "UserType": 0, "Activity": "CreateFile"},
    ]
    collectors = controlplane.collector_ids(events, COLLECTOR_APP)
    assert collectors == {COLLECTOR_APP, COLLECTOR_OBJ.lower()}
    directory = controlplane.principal_directory(events, {"ws": [{"PrincipalId": "ABC", "Principal": "Grp"}]})
    assert directory[USER_OBJ.lower()] == "ann@contoso.com" and directory["abc"] == "Grp"
    assert controlplane.resolve_actor(events[0], directory, collectors) == (COLLECTOR_APP, COLLECTOR_APP, "Collector")
    assert controlplane.resolve_actor(events[2], directory, collectors)[2] == "Collector"
    assert controlplane.resolve_actor(events[3], directory, collectors) == ("ann@contoso.com", USER_OBJ, "User")
    assert controlplane.resolve_actor(events[4], directory, collectors)[2] == "ServicePrincipal"


def test_operations_scope_name_match_and_per_item_columns():
    info = {ITEM_ID: {"ItemName": "model", "ItemType": "SemanticModel", "WorkspaceId": WORKSPACE_ID,
                      "OwnerPrincipal": "own@x.com", "State": "Active"}}
    zero = "00000000-0000-0000-0000-000000000000"
    events = [
        {"Activity": "ReadArtifact", "ObjectId": ITEM_ID, "UserId": "a@x.com", "CreationTime": "2026-01-01T00:00:00"},
        {"Activity": "UpdateArtifact", "ObjectId": "model", "WorkspaceId": zero, "UserId": "a@x.com", "UserKey": "K1",
         "CreationTime": "2026-01-02T00:00:00", "ClientIP": "1.2.3.4", "ResultStatus": "Succeeded"},
        {"Activity": "DeleteArtifact", "ObjectId": OTHER_ITEM_ID, "WorkspaceId": OTHER_WORKSPACE_ID, "UserId": "b@x.com"},
        {"Activity": "CreateFile", "ObjectId": "unknown", "WorkspaceId": zero, "UserId": "c@x.com"},
    ]
    rows = controlplane.build_operations(events, info, [], {}, set(), {WORKSPACE_ID}, set(), "now")
    assert [r["Operation"] for r in rows] == ["UpdateArtifact"]
    assert rows[0]["ItemId"] == ITEM_ID.lower() and rows[0]["ActorUpn"] == "a@x.com"
    assert rows[0]["ItemOwner"] == "own@x.com" and rows[0]["WorkspaceId"] == WORKSPACE_ID
    activity = controlplane._activity_by_item(events[:2], {}, set(), info)[ITEM_ID.lower()]
    assert activity["OperationCount"] == 1 and activity["LastOperation"] == "UpdateArtifact"
    assert activity["LastUserActivityUpn"] == "a@x.com" and activity["ActivityCount"] == 2