"""Extract declared Lakehouse associations without inferring notebook I/O."""

from uuid import UUID


def notebook_lakehouse_relationships(notebook):
    """Return configured identifiers only; never resolve names or check access."""
    relationships, diagnostics = [], []

    def diagnostic(path, reason):
        diagnostics.append({"fieldPath": path, "reason": reason})

    def identifier(value, path, *, optional=False):
        if optional and value in (None, ""):
            return None
        try:
            if not isinstance(value, str):
                raise TypeError
            return str(UUID(value))
        except (TypeError, ValueError):
            diagnostic(path, "invalid_configured_identifier")
            return None

    path = "/metadata"
    value = notebook
    for key in ("metadata", "dependencies", "lakehouse"):
        if not isinstance(value, dict):
            diagnostic(path, "invalid_notebook_configuration")
            break
        value = value.get(key, {})
        if key != "metadata" and value is None:
            value = {}
        path = "/metadata" if key == "metadata" else path + "/" + key
    else:
        if not isinstance(value, dict):
            diagnostic(path, "invalid_notebook_configuration")
        else:
            default_id = identifier(
                value.get("default_lakehouse"),
                path + "/default_lakehouse",
                optional=True,
            )
            default_workspace = identifier(
                value.get("default_lakehouse_workspace_id"),
                path + "/default_lakehouse_workspace_id",
                optional=True,
            )
            if default_workspace and not default_id:
                diagnostic(path + "/default_lakehouse", "missing_configured_lakehouse")
            if default_id:
                relationships.append(
                    {
                        "relation": "default_lakehouse",
                        "itemId": default_id,
                        "workspaceId": default_workspace,
                    }
                )
            known = value.get("known_lakehouses", [])
            if not isinstance(known, list):
                diagnostic(path + "/known_lakehouses", "invalid_notebook_configuration")
            else:
                seen = {default_id: default_workspace} if default_id else {}
                for index, entry in enumerate(known):
                    location = f"{path}/known_lakehouses/{index}"
                    if not isinstance(entry, dict):
                        diagnostic(location, "invalid_notebook_configuration")
                        continue
                    item_id = identifier(entry.get("id"), location + "/id")
                    workspace = identifier(
                        entry.get("workspaceId"),
                        location + "/workspaceId",
                        optional=True,
                    )
                    if item_id is None:
                        continue
                    if item_id in seen:
                        if seen[item_id] and workspace and seen[item_id] != workspace:
                            diagnostic(location, "conflicting_configured_workspace")
                        elif workspace and not seen[item_id]:
                            seen[item_id] = workspace
                            for relationship in relationships:
                                if relationship["itemId"] == item_id:
                                    relationship["workspaceId"] = workspace
                        continue
                    seen[item_id] = workspace
                    relationships.append(
                        {
                            "relation": "known_lakehouse",
                            "itemId": item_id,
                            "workspaceId": workspace,
                        }
                    )
    return {
        "schemaVersion": 1,
        "evidence": "configuration_metadata",
        "runtimeVerified": False,
        "complete": not diagnostics,
        "relationships": relationships,
        "diagnostics": diagnostics,
    }
