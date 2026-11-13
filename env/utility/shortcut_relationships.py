"""Minimized shortcut configuration evidence, never runtime or access proof."""

import hashlib
import json
import re
from urllib.parse import urlsplit
from uuid import UUID

SHORTCUT_MODULE = "fabricshortcuts"
_SHORTCUT_TYPES = {
    "AdlsGen2": "adlsGen2",
    "AmazonS3": "amazonS3",
    "AzureBlobStorage": "azureBlobStorage",
    "Dataverse": "dataverse",
    "ExternalDataShare": "externalDataShare",
    "GoogleCloudStorage": "googleCloudStorage",
    "OneDriveSharePoint": "oneDriveSharePoint",
    "S3Compatible": "s3Compatible",
}
_SHORTCUT_FIELDS = {
    "shortcutId",
    "targetType",
    "targetStatus",
    "targetWorkspaceId",
    "targetItemId",
    "targetReference",
    "isShortcutTransform",
}


def shortcut_fingerprint(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def shortcut_exclusions(value):
    if not isinstance(value, str):
        raise TypeError(
            "Shortcut workspace exclusions must be a comma-separated string"
        )
    try:
        return sorted(
            {str(UUID(part.strip())) for part in value.split(",") if part.strip()}
        )
    except (ValueError, AttributeError):
        raise ValueError("Shortcut workspace exclusions require UUIDs") from None


def shortcut_inventory(values, excluded):
    if not isinstance(values, list):
        raise TypeError("Invalid shortcut inventory")
    selected = {}
    for value in values:
        if not isinstance(value, dict) or value.get("type") != "Lakehouse":
            raise ValueError("Invalid shortcut inventory type")
        parent = {
            "workspaceId": str(UUID(value["workspaceId"])),
            "itemId": str(UUID(value["id"])),
            "type": "Lakehouse",
        }
        if parent["workspaceId"] not in excluded:
            selected[parent["workspaceId"], parent["itemId"]] = parent
    return [selected[key] for key in sorted(selected)]


def validate_shortcut_records(values):
    if not isinstance(values, list):
        raise TypeError("Invalid shortcut records")
    seen = set()
    for value in values:
        if not isinstance(value, dict) or set(value) != _SHORTCUT_FIELDS:
            raise ValueError("Invalid shortcut record fields")
        identity = value["shortcutId"]
        if (
            not isinstance(identity, str)
            or re.fullmatch(r"[a-f0-9]{64}", identity) is None
            or identity in seen
            or not isinstance(value["targetType"], str)
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,63}", value["targetType"]) is None
            or value["targetStatus"]
            not in {
                "configured_item",
                "external_reference",
                "unavailable",
                "unsupported",
            }
            or (
                value["isShortcutTransform"] is not None
                and type(value["isShortcutTransform"]) is not bool
            )
        ):
            raise ValueError("Invalid shortcut identity or status")
        seen.add(identity)
        configured = value["targetStatus"] == "configured_item"
        for field in ("targetWorkspaceId", "targetItemId"):
            target_id = value[field]
            if configured:
                if str(UUID(target_id)) != target_id:
                    raise ValueError("Invalid shortcut target identity")
            elif target_id is not None:
                raise ValueError("Unresolved shortcut has an item identity")
        reference = value["targetReference"]
        if reference is not None and (
            not isinstance(reference, str)
            or re.fullmatch(r"[a-f0-9]{64}", reference) is None
        ):
            raise ValueError("Invalid shortcut target fingerprint")
        if (
            configured
            and value["targetType"] != "OneLake"
            or value["targetStatus"] == "external_reference"
            and (value["targetType"] not in _SHORTCUT_TYPES or reference is None)
            or value["targetStatus"] in {"unavailable", "unsupported"}
            and reference is not None
        ):
            raise ValueError("Shortcut target type and resolution disagree")
    return values


def shortcut_records(values):
    """Drop names, paths, URLs, credentials and arbitrary response properties."""
    if not isinstance(values, list):
        raise TypeError("Invalid shortcut list")
    selected = {}
    for value in values:
        if not isinstance(value, dict):
            raise TypeError("Invalid shortcut")
        path, name, target = value.get("path"), value.get("name"), value.get("target")
        if (
            not isinstance(path, str)
            or not path
            or not isinstance(name, str)
            or not name
            or not isinstance(target, dict)
        ):
            raise ValueError("Missing shortcut identity or target")
        kind = target.get("type")
        if (
            not isinstance(kind, str)
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,63}", kind) is None
        ):
            raise ValueError("Invalid shortcut target type")
        record = {
            "shortcutId": shortcut_fingerprint([path, name]),
            "targetType": kind,
            "targetStatus": "unavailable",
            "targetWorkspaceId": None,
            "targetItemId": None,
            "targetReference": None,
            "isShortcutTransform": value.get("isShortcutTransform"),
        }
        detail_key = "oneLake" if kind == "OneLake" else _SHORTCUT_TYPES.get(kind)
        if detail_key is None:
            record["targetStatus"] = "unsupported"
        elif detail_key in target:
            detail = target[detail_key]
            if not isinstance(detail, dict):
                raise TypeError("Invalid shortcut target details")
            if kind == "OneLake":
                for field in ("workspaceId", "itemId"):
                    if field in detail:
                        str(UUID(detail[field]))
                if "workspaceId" in detail and "itemId" in detail:
                    record.update(
                        targetWorkspaceId=str(UUID(detail["workspaceId"])),
                        targetItemId=str(UUID(detail["itemId"])),
                        targetStatus="configured_item",
                    )
            else:
                location = {}
                for field in ("location", "subpath", "path", "bucket", "connectionId"):
                    if field not in detail:
                        continue
                    content = detail[field]
                    if not isinstance(content, str) or not content:
                        raise ValueError("Invalid shortcut external reference")
                    if field == "connectionId":
                        content = str(UUID(content))
                    elif field == "location":
                        parsed = urlsplit(content)
                        if (
                            parsed.scheme != "https"
                            or not parsed.netloc
                            or parsed.username is not None
                            or parsed.password is not None
                        ):
                            raise ValueError("Invalid shortcut external location")
                        content = parsed._replace(query="", fragment="").geturl()
                    location[field] = content
                if "location" in location:
                    record.update(
                        targetReference=shortcut_fingerprint([kind, location]),
                        targetStatus="external_reference",
                    )
        identity = record["shortcutId"]
        if identity in selected and selected[identity] != record:
            raise ValueError("Conflicting shortcut identity")
        selected[identity] = record
    return validate_shortcut_records([selected[key] for key in sorted(selected)])


def shortcut_progress(saved, excluded):
    settings = {"excludeWorkspaceIds": excluded}
    if saved is not None and saved != {"finished": True}:
        try:
            previous = saved["settings"]["excludeWorkspaceIds"]
            if not isinstance(previous, list) or previous != shortcut_exclusions(
                ",".join(previous)
            ):
                raise ValueError("Invalid shortcut progress settings")
        except (KeyError, ValueError, TypeError, AttributeError):
            raise ValueError("Invalid shortcut progress; requests blocked") from None
    if saved is None or saved == {"finished": True} or saved["settings"] != settings:
        return {
            "settings": settings,
            "phase": "inventory",
            "items": [],
            "nextItem": 0,
            "records": [],
            "continuationToken": None,
            "tokens": [],
            "healthy": True,
        }
    try:
        items = shortcut_inventory(
            [{"id": item["itemId"], **item} for item in saved["items"]], excluded
        )
        token, tokens = saved["continuationToken"], saved["tokens"]
        if (
            items != saved["items"]
            or saved["phase"] not in {"inventory", "shortcuts"}
            or type(saved["nextItem"]) is not int
            or not 0 <= saved["nextItem"] <= len(items)
            or type(saved["healthy"]) is not bool
            or not isinstance(tokens, list)
            or len(tokens) != len(set(tokens))
            or len(tokens) > 10000
            or any(not isinstance(value, str) or not value for value in tokens)
            or (
                token is not None
                and (not isinstance(token, str) or not token or tokens[-1:] != [token])
            )
            or (token is None and tokens)
            or (
                saved["phase"] == "inventory"
                and (saved["nextItem"] != 0 or saved["records"])
            )
        ):
            raise ValueError("Invalid shortcut progress")
        validate_shortcut_records(saved["records"])
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ValueError("Invalid shortcut progress; requests blocked") from None
    return saved


def shortcut_scope(execution):
    excluded = execution["excludeWorkspaceIds"]
    if (
        not isinstance(excluded, list)
        or excluded != shortcut_exclusions(",".join(excluded))
        or type(execution["sweepComplete"]) is not bool
        or type(execution["sweepHealthy"]) is not bool
    ):
        raise ValueError("Invalid shortcut execution scope")
    return "shortcut:" + shortcut_fingerprint(excluded)
