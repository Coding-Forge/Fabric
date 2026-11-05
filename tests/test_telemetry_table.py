import json
from pathlib import Path

from env.utility import telemetry_table as tt

ROOT = Path(__file__).resolve().parent.parent


def test_flatten_controlplane_row_makes_readable_text_and_keeps_columns():
    row = {
        "ItemId": "i1", "RowsRead": None, "ActivityCount": 2, "ActivityUsers": ["a@x.com", "b@x.com"],
        "UpstreamItems": [{"ItemId": "u", "ItemName": "lh", "ItemType": "Lakehouse"}],
        "DownstreamItems": [],
        "ItemAccess": [{"Principal": "Group One", "PrincipalType": "Group", "Permissions": ["Read", "Write"]}],
        "WorkspaceAccess": [{"Principal": "u1@contoso.com", "PrincipalType": "User", "Role": "Admin"}],
        "ItemProperties": {"sqlEndpoint": {"id": "e"}},
    }
    out = tt.flatten_controlplane_row(row)
    assert out["UpstreamItemNames"] == "lh (Lakehouse)" and out["DownstreamItemNames"] is None
    assert out["ItemAccessSummary"] == "Group One (Read/Write)"
    assert out["WorkspaceAccessSummary"] == "u1@contoso.com (Admin)"
    assert out["ActivityUsers"] == "a@x.com; b@x.com"
    assert out["DownstreamItems"] is None
    assert json.loads(out["UpstreamItems"])[0]["ItemId"] == "u"
    assert json.loads(out["ItemProperties"]) == {"sqlEndpoint": {"id": "e"}}
    assert out["ItemId"] == "i1" and out["ActivityCount"] == 2


def test_drop_empty_columns_keeps_zero_and_reports_dropped():
    rows, dropped = tt.drop_empty_columns([
        {"a": 1, "b": None, "c": [], "d": 0, "e": ""},
        {"a": None, "b": None, "c": [], "d": 0, "e": ""},
    ])
    assert dropped == ["b", "c", "e"]
    assert rows == [{"a": 1, "d": 0}, {"a": None, "d": 0}]


def test_prepare_lineage_joins_sources_and_drops_empty():
    rows, dropped = tt.prepare_lineage([
        {"UpstreamItemId": "u", "DownstreamItemId": "d", "Sources": ["Scanner", "FabricRelations"],
         "UpstreamLastActivity": None},
    ])
    assert rows[0]["Sources"] == "Scanner; FabricRelations"
    assert dropped == ["UpstreamLastActivity"]


def test_prepare_controlplane_drops_unfilled_volume_columns():
    rows, dropped = tt.prepare_controlplane([
        {"ItemId": "i", "RowsRead": None, "ThroughputKBps": None, "UpstreamItems": None, "ItemAccess": None},
    ])
    assert "RowsRead" in dropped and "ThroughputKBps" in dropped
    assert list(rows[0]) == ["ItemId"]


def test_notebook_embeds_current_helper_source():
    nb = json.loads((ROOT / "notebooks" / "controlplane_delta.ipynb").read_text(encoding="utf-8"))
    code = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    helpers = (ROOT / "env" / "utility" / "telemetry_table.py").read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")
    assert code[0] == helpers
    compile(code[1], "controlplane_delta", "exec")
