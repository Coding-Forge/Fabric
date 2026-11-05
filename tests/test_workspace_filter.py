import asyncio
import base64
import json
import logging
from datetime import datetime

import pytest

from env.config import build_audit
from env.modules import catalog, fabricitems, itemjobs
from env.utility.workspace_filter import filter_workspace_records, parse_workspace_ids


WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
OTHER_WORKSPACE_ID = "22222222-2222-4222-8222-222222222222"
ITEM_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_ITEM_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


class FakeFileManagement:
    def __init__(self):
        self.saved = []
        self.files = {}

    async def save(self, *, path, file_name, content):
        self.saved.append((path, file_name, content))

    async def read(self, path="", file_name=""):
        return self.files.get(f"{path}{file_name}")


def test_workspace_filter_normalizes_ids_and_exclusions_take_precedence():
    included = parse_workspace_ids(f" {WORKSPACE_ID.upper()}, {WORKSPACE_ID} ")
    records = [
        {"workspaceId": WORKSPACE_ID, "id": ITEM_ID},
        {"workspaceId": OTHER_WORKSPACE_ID, "id": OTHER_ITEM_ID},
        {"id": "missing-workspace"},
    ]

    filtered, counts = filter_workspace_records(
        records,
        included,
        WORKSPACE_ID.upper(),
        get_workspace_id=lambda item: item.get("workspaceId"),
    )

    assert filtered == []
    assert (counts.found, counts.included, counts.excluded) == (3, 0, 3)


def test_invalid_workspace_id_is_rejected():
    with pytest.raises(ValueError, match="Invalid workspace ID"):
        parse_workspace_ids("not-a-guid")


def test_workspace_filter_settings_are_wired_to_context():
    audit = build_audit({
        "TENANT_ID": "tenant",
        "CLIENT_ID": "client",
        "CLIENT_SECRET": "not-used-by-test",
        "INCLUDE_WORKSPACE_IDS": f" {WORKSPACE_ID}, {OTHER_WORKSPACE_ID} ",
        "EXCLUDE_WORKSPACE_IDS": OTHER_WORKSPACE_ID,
    })

    assert audit.context.include_workspace_ids == frozenset({WORKSPACE_ID, OTHER_WORKSPACE_ID})
    assert audit.context.exclude_workspace_ids == frozenset({OTHER_WORKSPACE_ID})


class FakeClient:
    def get_headers(self):
        return {"Authorization": "Bearer mocked"}


class FakeContext:
    def __init__(self, include_ids=(), exclude_ids=()):
        self.include_workspace_ids = frozenset(include_ids)
        self.exclude_workspace_ids = frozenset(exclude_ids)
        self.clients = {"pbi": FakeClient(), "tenant": FakeClient()}
        self.logger = logging.getLogger("test.workspace_filter")
        self.fm = FakeFileManagement()
        self.all_workspaces = False
        self.exclude_personal_workspaces = False
        self.exclude_inactive_workspaces = False
        self.CatalogGetInfoParameters = "lineage=true"
        self.current_state = {}
        self.api_calls = []
        self.http_max_retries = 6
        self.scan_status_poll_seconds = 20
        self.itemjobs_concurrency = 3

    def get_fabric_url(self, path):
        return f"https://api.fabric.microsoft.com/{path}"

    def convert_dt_str(self, value):
        if isinstance(value, datetime):
            return value
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")

    async def invokeAPI(self, rest_api, headers=None, json=None):
        self.api_calls.append((rest_api, json))
        if "scanStatus" in rest_api:
            return {"status": "Succeeded"}
        if "getInfo" in rest_api:
            return {"id": "scan-id", "status": "Running"}
        if "scanResult" in rest_api:
            return {
                "workspaces": [
                    {"id": WORKSPACE_ID, "name": "Included", "reports": []},
                ]
            }
        return {
            "itemEntities": [
                {"id": ITEM_ID, "workspaceId": WORKSPACE_ID, "name": "Included", "type": "DataPipeline"},
                {"id": OTHER_ITEM_ID, "workspaceId": OTHER_WORKSPACE_ID, "name": "Excluded", "type": "DataPipeline"},
            ],
            "continuationUri": None,
        }


def test_catalog_inclusion_overrides_modified_since_and_scans_only_included_workspace(monkeypatch, caplog):
    async def no_sleep(_):
        return None

    caplog.set_level(logging.INFO, logger="test.workspace_filter")
    monkeypatch.setattr(catalog.asyncio, "sleep", no_sleep)
    context = FakeContext(include_ids={WORKSPACE_ID})

    asyncio.run(catalog.main(context))

    get_info_calls = [(url, body) for url, body in context.api_calls if "getInfo" in url]
    assert [body["workspaces"] for _, body in get_info_calls] == [[WORKSPACE_ID]]
    assert not any("workspaces/modified" in url for url, _ in context.api_calls)
    scan_files = [saved for saved in context.fm.saved if saved[0].startswith("catalog/scans/")]
    assert len(scan_files) == 1
    assert [workspace["id"] for workspace in scan_files[0][2]["workspaces"]] == [WORKSPACE_ID]
    assert "Catalog workspace filter: found=1, included=1, excluded=0, processed=1" in caplog.text


def test_itemjobs_filters_before_per_item_http_calls(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="test.workspace_filter")
    context = FakeContext(include_ids={WORKSPACE_ID})
    context.api_calls.clear()
    request_urls = []

    class MockResponse:
        def __init__(self, url):
            self.url = url
        status_code = 200
        headers = {}
        text = ""

        def json(self):
            if self.url.endswith("/jobs/instances"):
                return {
                    "value": [{
                        "id": "job-run",
                        "status": "Succeeded",
                        "startTimeUtc": None,
                        "endTimeUtc": None,
                    }]
                }
            definition = {
                "properties": {
                    "activities": [{
                        "name": "copy",
                        "type": "Copy",
                        "typeProperties": {"source": {}, "sink": {}},
                    }]
                }
            }
            payload = base64.b64encode(json.dumps(definition).encode()).decode()
            return {"definition": {"parts": [{"path": "pipeline-content.json", "payload": payload}]}}

    def mock_request(method, url, **kwargs):
        request_urls.append(url)
        return MockResponse(url)

    monkeypatch.setattr("requests.request", mock_request)
    asyncio.run(itemjobs.main(context))

    assert request_urls
    assert all(f"/workspaces/{WORKSPACE_ID}/" in url for url in request_urls)
    saved_by_path = {path.split("/")[0]: content for path, _, content in context.fm.saved}
    assert saved_by_path["jobs"][0]["WorkspaceId"] == WORKSPACE_ID
    assert saved_by_path["itemdefinitions"]
    assert all(row["WorkspaceId"] == WORKSPACE_ID for row in saved_by_path["itemdefinitions"])
    assert "ItemJobs workspace filter: found=2, included=1, excluded=1, processed=1" in caplog.text


def test_fabricitems_filters_saved_items_and_lineage_api_calls(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="test.workspace_filter")
    context = FakeContext(include_ids={WORKSPACE_ID})
    relation_urls = []

    class MockResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"items": [], "workspaces": [], "relations": []}

    def mock_get(method, url, **kwargs):
        relation_urls.append(url)
        return MockResponse()

    monkeypatch.setattr("requests.request", mock_get)
    asyncio.run(fabricitems.main(context))

    item_outputs = [saved for saved in context.fm.saved if saved[0].startswith("items/")]
    assert len(item_outputs) == 1
    assert [item["workspaceId"] for item in item_outputs[0][2]] == [WORKSPACE_ID]
    assert len(relation_urls) == 2
    assert all(f"/workspaces/{WORKSPACE_ID}/" in url for url in relation_urls)
    assert "FabricItems workspace filter: found=2, included=1, excluded=1, processed=1" in caplog.text
    assert "FabricItems lineage workspace filter: found=2, included=1, excluded=1, processed=1" in caplog.text
