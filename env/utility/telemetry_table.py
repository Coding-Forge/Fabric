"""Flatten ControlPlane / lineage graph rows into readable, Delta-safe tables.

Pure Python with no imports from the app, so the notebook notebooks/controlplane_delta.ipynb embeds this file as is.
"""
import json

COUNT_COLUMNS = ("RunsCollected", "FailedRunsCollected", "UpstreamCount", "DownstreamCount", "ActivityCount",
                 "OperationCount", "RowsRead", "RowsCopied", "DataReadBytes", "DataWrittenBytes", "RowsWritten",
                 "BytesWritten")


def is_empty(value):
    return value is None or value == "" or value == [] or value == {}


def _names(items):
    parts = []
    for item in items or []:
        name = item.get("ItemName") or item.get("ItemId")
        kind = item.get("ItemType")
        parts.append(f"{name} ({kind})" if kind else str(name))
    return "; ".join(parts) or None


def _access(entries):
    parts = []
    for entry in entries or []:
        what = entry.get("Role") or "/".join(entry.get("Permissions") or []) or entry.get("PrincipalType")
        who = entry.get("Principal") or entry.get("PrincipalId")
        parts.append(f"{who} ({what})" if what else str(who))
    return "; ".join(parts) or None


def _json_text(value):
    return None if is_empty(value) else json.dumps(value, default=str, sort_keys=True)


def flatten_controlplane_row(row):
    """Readable text for list/dict columns. Existing columns keep their names; *Names / *Summary columns are added."""
    out = dict(row)
    out["UpstreamItemNames"] = _names(row.get("UpstreamItems"))
    out["DownstreamItemNames"] = _names(row.get("DownstreamItems"))
    out["ItemAccessSummary"] = _access(row.get("ItemAccess"))
    out["WorkspaceAccessSummary"] = _access(row.get("WorkspaceAccess"))
    out["ActivityUsers"] = "; ".join(row.get("ActivityUsers") or []) or None
    out["ActivityUserUpns"] = "; ".join(row.get("ActivityUserUpns") or []) or None
    for column in ("UpstreamItems", "DownstreamItems", "ItemAccess", "WorkspaceAccess", "ItemProperties"):
        out[column] = _json_text(row.get(column))
    return out


def flatten_lineage_row(row):
    out = dict(row)
    out["Sources"] = "; ".join(row.get("Sources") or []) or None
    return out


def drop_empty_columns(rows):
    """Remove columns that are empty in every row. Returns (rows, dropped column names)."""
    columns = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    kept = [c for c in columns if any(not is_empty(r.get(c)) for r in rows)]
    dropped = [c for c in columns if c not in kept]
    return [{c: r.get(c) for c in kept} for r in rows], dropped


def prepare_controlplane(rows):
    return drop_empty_columns([flatten_controlplane_row(r) for r in rows])


def prepare_lineage(rows):
    return drop_empty_columns([flatten_lineage_row(r) for r in rows])


def prepare_operations(rows):
    return drop_empty_columns([dict(r) for r in rows])


def prepare_consolidated(rows):
    return drop_empty_columns([dict(r) for r in rows])
