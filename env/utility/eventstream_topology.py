"""Minimized Eventstream configuration graphs; no runtime or target-access proof."""

import hashlib
import json
import re
from uuid import UUID, uuid4

EVENTSTREAM_MODULE = "fabriceventstreamtopology"
_EVENTSTREAM_GROUPS = {
    "sources": "source",
    "streams": "stream",
    "operators": "operator",
    "destinations": "destination",
}
_EVENTSTREAM_ITEM_TYPES = {
    "source": frozenset(
        {
            "CustomStreamConnector",
            "LakehouseChangeFeed",
            "MirroredDatabaseChangeFeed",
            "BusinessEvents",
            "FabricAnomalyDetectionEvents",
            "FabricJobEvents",
            "FabricOneLakeEvents",
            "FabricWorkspaceItemEvents",
        }
    ),
    "destination": frozenset(
        {"Lakehouse", "Eventhouse", "Notebook", "BusinessEvents", "Activator"}
    ),
}
_EVENTSTREAM_STATUSES = frozenset(
    {
        "Running",
        "Stopped",
        "Failed",
        "Starting",
        "Stopping",
        "Updating",
        "Created",
        "Disabled",
        "Enabled",
        "External",
        "Unknown",
        "Other",
    }
)
_EVENTSTREAM_NODE_FIELDS = {
    "nodeId",
    "role",
    "type",
    "reportedStatus",
    "inputsKnown",
    "targetWorkspaceId",
    "targetItemId",
    "connectionReference",
    "targetStatus",
}


def eventstream_hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def eventstream_exclusions(value):
    if not isinstance(value, str):
        raise TypeError("Eventstream workspace exclusions must be a string")
    try:
        return sorted(
            {str(UUID(part.strip())) for part in value.split(",") if part.strip()}
        )
    except (ValueError, AttributeError):
        raise ValueError("Eventstream workspace exclusions require UUIDs") from None


def eventstream_inventory(values, excluded):
    if not isinstance(values, list):
        raise TypeError("Invalid Eventstream inventory")
    selected = {}
    for value in values:
        if not isinstance(value, dict) or value.get("type") != "Eventstream":
            raise ValueError("Invalid Eventstream inventory type")
        parent = {
            "workspaceId": str(UUID(value["workspaceId"])),
            "itemId": str(UUID(value["id"])),
            "type": "Eventstream",
        }
        if parent["workspaceId"] not in excluded:
            selected[parent["workspaceId"], parent["itemId"]] = parent
    return [selected[key] for key in sorted(selected)]


def eventstream_scope(execution):
    excluded = execution["excludeWorkspaceIds"]
    if (
        not isinstance(excluded, list)
        or excluded != eventstream_exclusions(",".join(excluded))
        or type(execution["sweepComplete"]) is not bool
        or type(execution["sweepHealthy"]) is not bool
        or not isinstance(execution["sweepId"], str)
        or re.fullmatch(r"[a-f0-9]{32}", execution["sweepId"]) is None
    ):
        raise ValueError("Invalid Eventstream execution scope")
    return "eventstream:" + eventstream_hash([excluded, execution["sweepId"]])


def validate_eventstream_topology(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"schemaVersion", "nodes", "links", "diagnostics"}
        or type(value["schemaVersion"]) is not int
        or value["schemaVersion"] != 1
        or any(
            not isinstance(value[key], list)
            for key in ("nodes", "links", "diagnostics")
        )
    ):
        raise ValueError("Invalid minimized Eventstream topology")
    nodes = {}
    for node in value["nodes"]:
        if (
            not isinstance(node, dict)
            or set(node) != _EVENTSTREAM_NODE_FIELDS
            or not isinstance(node["nodeId"], str)
            or re.fullmatch(r"[a-f0-9]{64}", node["nodeId"]) is None
            or node["nodeId"] in nodes
            or node["role"] not in _EVENTSTREAM_GROUPS.values()
            or not isinstance(node["type"], str)
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,95}", node["type"]) is None
            or node["reportedStatus"] is not None
            and node["reportedStatus"] not in _EVENTSTREAM_STATUSES
            or type(node["inputsKnown"]) is not bool
            or node["targetStatus"]
            not in {
                "configured_item",
                "connection_reference",
                "unresolved",
                "unsupported",
                "not_applicable",
            }
        ):
            raise ValueError("Invalid topology node")
        nodes[node["nodeId"]] = node
        configured = node["targetStatus"] == "configured_item"
        for field in ("targetWorkspaceId", "targetItemId"):
            identity = node[field]
            if configured:
                if not isinstance(identity, str) or str(UUID(identity)) != identity:
                    raise ValueError("Invalid configured topology target")
            elif identity is not None:
                raise ValueError("Unresolved topology has an item identity")
        reference = node["connectionReference"]
        if reference is not None and (
            not isinstance(reference, str)
            or re.fullmatch(r"[a-f0-9]{64}", reference) is None
        ):
            raise ValueError("Invalid topology connection fingerprint")
        if (
            configured
            and node["type"] not in _EVENTSTREAM_ITEM_TYPES.get(node["role"], ())
            or node["targetStatus"] == "connection_reference"
            and reference is None
            or node["role"] in {"stream", "operator"}
            and (node["targetStatus"] != "not_applicable" or reference is not None)
            or node["role"] in {"source", "destination"}
            and node["targetStatus"] == "not_applicable"
        ):
            raise ValueError("Topology node and target disagree")
    seen = set()
    for link in value["links"]:
        if (
            not isinstance(link, dict)
            or set(link) != {"fromNode", "toNode", "resolved"}
            or any(
                not isinstance(link[key], str)
                or re.fullmatch(r"[a-f0-9]{64}", link[key]) is None
                for key in ("fromNode", "toNode")
            )
            or type(link["resolved"]) is not bool
            or link["toNode"] not in nodes
            or not nodes[link["toNode"]]["inputsKnown"]
            or link["resolved"] != (link["fromNode"] in nodes)
            or (link["fromNode"], link["toNode"]) in seen
        ):
            raise ValueError("Invalid topology link")
        seen.add((link["fromNode"], link["toNode"]))
    expected = []
    for node in nodes.values():
        if not node["inputsKnown"] and node["role"] != "source":
            expected.append(
                {"nodeId": node["nodeId"], "reason": "missing_topology_inputs"}
            )
        if node["targetStatus"] in {"unresolved", "unsupported"}:
            expected.append(
                {
                    "nodeId": node["nodeId"],
                    "reason": "unresolved_topology_target"
                    if node["targetStatus"] == "unresolved"
                    else "unsupported_topology_target",
                }
            )
    for link in value["links"]:
        if not link["resolved"]:
            expected.append(
                {
                    "nodeId": link["toNode"],
                    "reason": "unresolved_topology_input",
                    "inputNodeId": link["fromNode"],
                }
            )
    if sorted(value["diagnostics"], key=eventstream_hash) != sorted(
        expected, key=eventstream_hash
    ):
        raise ValueError("Topology diagnostics disagree with evidence")
    return value


def eventstream_topology(body):
    """Keep structural nodes/inputs and selected UUIDs; never keep node payloads."""
    if (
        not isinstance(body, dict)
        or body.get("continuationToken") is not None
        or body.get("continuationUri") is not None
    ):
        raise ValueError("Invalid or unexpectedly paginated topology")
    nodes, names, ids, inputs = [], set(), set(), []
    for group, role in _EVENTSTREAM_GROUPS.items():
        values = body.get(group)
        if not isinstance(values, list):
            raise TypeError("Missing or malformed topology node collection")
        for value in values:
            if not isinstance(value, dict):
                raise TypeError("Invalid topology node")
            name, kind = value.get("name"), value.get("type")
            if (
                not isinstance(name, str)
                or not name
                or name in names
                or not isinstance(kind, str)
                or re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,95}", kind) is None
            ):
                raise ValueError("Invalid or ambiguous topology node identity")
            names.add(name)
            if "id" in value:
                identity = str(UUID(value["id"]))
                if identity in ids:
                    raise ValueError("Duplicate topology node UUID")
                ids.add(identity)
            properties = value.get("properties", {})
            if not isinstance(properties, dict):
                raise TypeError("Invalid topology node properties")
            status = value.get("status")
            if status is not None and not isinstance(status, str):
                raise TypeError("Invalid topology node status")
            node = {
                "nodeId": eventstream_hash(name),
                "role": role,
                "type": kind,
                "reportedStatus": status
                if status in _EVENTSTREAM_STATUSES or status is None
                else "Other",
                "inputsKnown": "inputNodes" in value,
                "targetWorkspaceId": None,
                "targetItemId": None,
                "connectionReference": None,
                "targetStatus": "not_applicable"
                if role in {"stream", "operator"}
                else "unresolved",
            }
            if role in {"source", "destination"}:
                if "dataConnectionId" in properties:
                    node["connectionReference"] = eventstream_hash(
                        str(UUID(properties["dataConnectionId"]))
                    )
                    node["targetStatus"] = "connection_reference"
                if kind in _EVENTSTREAM_ITEM_TYPES[role]:
                    for field in ("workspaceId", "itemId"):
                        if field in properties:
                            str(UUID(properties[field]))
                    if "workspaceId" in properties and "itemId" in properties:
                        node.update(
                            targetWorkspaceId=str(UUID(properties["workspaceId"])),
                            targetItemId=str(UUID(properties["itemId"])),
                            targetStatus="configured_item",
                        )
                elif "workspaceId" in properties or "itemId" in properties:
                    node["targetStatus"] = "unsupported"
            if "inputNodes" in value:
                if not isinstance(value["inputNodes"], list):
                    raise TypeError("Invalid topology inputs")
                for entry in value["inputNodes"]:
                    if (
                        not isinstance(entry, dict)
                        or not isinstance(entry.get("name"), str)
                        or not entry["name"]
                    ):
                        raise ValueError("Invalid topology input")
                    inputs.append((eventstream_hash(entry["name"]), node["nodeId"]))
            nodes.append(node)
    identities = {node["nodeId"] for node in nodes}
    links = [
        {"fromNode": source, "toNode": destination, "resolved": source in identities}
        for source, destination in sorted(set(inputs))
    ]
    diagnostics = []
    for node in nodes:
        if not node["inputsKnown"] and node["role"] != "source":
            diagnostics.append(
                {"nodeId": node["nodeId"], "reason": "missing_topology_inputs"}
            )
        if node["targetStatus"] in {"unresolved", "unsupported"}:
            diagnostics.append(
                {
                    "nodeId": node["nodeId"],
                    "reason": "unresolved_topology_target"
                    if node["targetStatus"] == "unresolved"
                    else "unsupported_topology_target",
                }
            )
    diagnostics.extend(
        {
            "nodeId": link["toNode"],
            "inputNodeId": link["fromNode"],
            "reason": "unresolved_topology_input",
        }
        for link in links
        if not link["resolved"]
    )
    return validate_eventstream_topology(
        {
            "schemaVersion": 1,
            "nodes": sorted(nodes, key=lambda node: node["nodeId"]),
            "links": links,
            "diagnostics": sorted(diagnostics, key=eventstream_hash),
        }
    )


def eventstream_progress(saved, excluded):
    if saved is not None and saved != {"finished": True}:
        try:
            execution = {
                **saved["settings"],
                "sweepComplete": False,
                "sweepHealthy": True,
                "sweepId": saved["sweepId"],
            }
            eventstream_scope(execution)
        except (KeyError, ValueError, TypeError, AttributeError):
            raise ValueError("Invalid Eventstream progress; requests blocked") from None
    settings = {"excludeWorkspaceIds": excluded}
    if saved is None or saved == {"finished": True} or saved["settings"] != settings:
        return {
            "settings": settings,
            "phase": "inventory",
            "items": [],
            "nextItem": 0,
            "continuationToken": None,
            "tokens": [],
            "healthy": True,
            "sweepId": uuid4().hex,
        }
    try:
        items = eventstream_inventory(
            [{"id": item["itemId"], **item} for item in saved["items"]], excluded
        )
        token, tokens = saved["continuationToken"], saved["tokens"]
        if (
            items != saved["items"]
            or saved["phase"] not in {"inventory", "topology"}
            or type(saved["nextItem"]) is not int
            or not 0 <= saved["nextItem"] <= len(items)
            or type(saved["healthy"]) is not bool
            or not isinstance(tokens, list)
            or len(tokens) != len(set(tokens))
            or len(tokens) > 10000
            or any(not isinstance(value, str) or not value for value in tokens)
            or token is not None
            and (not isinstance(token, str) or not token or tokens[-1:] != [token])
            or token is None
            and tokens
            or saved["phase"] == "inventory"
            and saved["nextItem"] != 0
            or saved["phase"] == "topology"
            and (token is not None or tokens)
        ):
            raise ValueError("Invalid Eventstream progress")
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ValueError("Invalid Eventstream progress; requests blocked") from None
    return saved
