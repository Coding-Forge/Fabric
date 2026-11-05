"""Conservative, nonexecuting analysis of configured pipeline dependencies."""

from uuid import UUID

_TABLES = frozenset(
    {
        "LakehouseTable",
        "SqlServerTable",
        "AzureSqlTable",
        "AzureSqlDWTable",
        "DataWarehouseTable",
    }
)
_FILES = frozenset(
    {"Avro", "Binary", "DelimitedText", "Excel", "Json", "Orc", "Parquet", "Xml"}
)
_LOCATIONS = frozenset(
    {
        "LakehouseLocation",
        "LakeHouseLocation",
        "AzureBlobFSLocation",
        "AzureBlobStorageLocation",
    }
)
_QUERIES = (
    "sqlReaderQuery",
    "query",
    "sqlReaderStoredProcedureName",
    "storedProcedureName",
)
_FILE_SELECTORS = ("wildcardFolderPath", "wildcardFileName", "fileListPath", "prefix")
_NO_IO = frozenset({"Wait", "Fail", "Filter", "SetVariable", "AppendVariable"})
_MAX_ACTIVITIES = 10000
_MAX_DEPTH = 64


def pipeline_references(pipeline: dict) -> dict:
    """Extract potential calls and Copy reads/writes, never execution evidence.

    Only documented field paths and supported literal targets are inspected.
    Unsupported/dynamic targets are diagnostics; malformed activity containers
    and safety-limit violations fail rather than become successful empties.
    """
    if not isinstance(pipeline, dict) or not isinstance(
        pipeline.get("properties"), dict
    ):
        raise TypeError("Invalid pipeline properties")
    references = []
    diagnostics = []
    diagnostic_keys = set()
    activity_count = 0

    def diagnostic(path, reason):
        key = path, reason
        if key not in diagnostic_keys:
            diagnostic_keys.add(key)
            diagnostics.append({"fieldPath": path, "reason": reason})

    def literal(value, path, *, identifier=False):
        if (
            not isinstance(value, str)
            or not value.strip()
            or value.startswith("@")
            or "@{" in value
        ):
            diagnostic(path, "dynamic_or_missing_target")
            return None
        if identifier:
            try:
                return str(UUID(value))
            except ValueError:
                diagnostic(path, "invalid_identifier")
                return None
        return value

    def object_value(value):
        if not isinstance(value, dict):
            raise TypeError("Invalid pipeline activity properties")
        return value

    def emit(activity, field, operation, kind, value, context=None, **extra):
        if value is not None:
            references.append(
                {
                    "activityPath": activity,
                    "fieldPath": field,
                    "operation": operation,
                    "kind": kind,
                    "reference": value,
                    "resolution": "unresolved",
                    **(context or {}),
                    **extra,
                }
            )

    def workspace(properties, path):
        if "workspaceId" not in properties:
            diagnostic(path + "/workspaceId", "dynamic_or_missing_target")
            return {}
        value = literal(
            properties["workspaceId"], path + "/workspaceId", identifier=True
        )
        return {"workspaceId": value} if value is not None else {}

    def copy_endpoint(endpoint, path, activity, operation):
        endpoint = object_value(endpoint)
        dataset = endpoint.get("datasetSettings")
        dataset_path = path + "/datasetSettings"
        if dataset is None:
            diagnostic(dataset_path, "unsupported_or_missing_dataset")
            return
        dataset = object_value(dataset)
        context = {}
        external = object_value(dataset.get("externalReferences", {}))
        if "connection" in external:
            field = dataset_path + "/externalReferences/connection"
            connection = literal(external["connection"], field, identifier=True)
            if connection is not None:
                context["connectionId"] = connection
                emit(
                    activity,
                    field,
                    operation,
                    "connection",
                    connection,
                    referenceType="id",
                )
        linked = object_value(dataset.get("linkedService", {}))
        service = object_value(linked.get("properties", {}))
        if service.get("type") in ("Lakehouse", "DataWarehouse"):
            service_path = dataset_path + "/linkedService/properties/typeProperties"
            properties = object_value(service.get("typeProperties", {}))
            context.update(workspace(properties, service_path))
            if "rootFolder" in properties:
                root = properties["rootFolder"]
                if root in ("Files", "Tables"):
                    context["rootFolder"] = root
                else:
                    diagnostic(
                        service_path + "/rootFolder", "unsupported_or_dynamic_root"
                    )
            artifact = literal(
                properties.get("artifactId"),
                service_path + "/artifactId",
                identifier=True,
            )
            emit(
                activity,
                service_path + "/artifactId",
                operation,
                "lakehouse" if service["type"] == "Lakehouse" else "warehouse",
                artifact,
                context,
                referenceType="id",
            )
            if artifact is not None:
                context["artifactId"] = artifact
        properties = object_value(dataset.get("typeProperties", {}))
        properties_path = dataset_path + "/typeProperties"
        for field in _QUERIES:
            if field in endpoint:
                diagnostic(path + "/" + field, "unsupported_query_or_procedure")
                return
        kind = dataset.get("type")
        if not isinstance(kind, str):
            raise TypeError("Invalid pipeline dataset type")
        if kind in _TABLES:
            table = literal(properties.get("table"), properties_path + "/table")
            for field in ("schema", "database"):
                if field in properties:
                    value = literal(properties[field], properties_path + "/" + field)
                    if value is not None:
                        context[field] = value
            emit(
                activity, properties_path + "/table", operation, "table", table, context
            )
        elif kind in _FILES:
            location = object_value(properties.get("location", {}))
            location_path = properties_path + "/location"
            if location.get("type") not in _LOCATIONS:
                diagnostic(location_path, "unsupported_copy_location")
                return
            settings = object_value(endpoint.get("storeSettings", {}))
            for field in _FILE_SELECTORS:
                if field in settings:
                    diagnostic(
                        path + "/storeSettings/" + field, "unsupported_file_selection"
                    )
                    return
            pieces = []
            for field in ("folderPath", "fileName"):
                value = location.get(field, "")
                value = (
                    "" if value == "" else literal(value, location_path + "/" + field)
                )
                if value is None:
                    return
                if "*" in value or "?" in value:
                    diagnostic(
                        location_path + "/" + field, "unsupported_file_selection"
                    )
                    return
                pieces.append(value)
            folder, name = pieces
            target = (
                folder
                + ("/" if folder and name and not folder.endswith("/") else "")
                + name
            )
            target = literal(target, location_path)
            for field in ("fileSystem", "container"):
                if field in location:
                    value = literal(location[field], location_path + "/" + field)
                    if value is not None:
                        context[field] = value
            emit(activity, location_path, operation, "path", target, context)
        else:
            diagnostic(dataset_path + "/type", "unsupported_copy_dataset")

    def walk(activities, path, depth=0):
        nonlocal activity_count
        if not isinstance(activities, list):
            raise TypeError("Invalid pipeline activity list")
        if depth > _MAX_DEPTH:
            raise ValueError("Pipeline activity safety limit exceeded")
        for index, activity in enumerate(activities):
            activity_count += 1
            if activity_count > _MAX_ACTIVITIES:
                raise ValueError("Pipeline activity safety limit exceeded")
            activity = object_value(activity)
            activity_path = f"{path}/{index}"
            kind = activity.get("type")
            if not isinstance(kind, str) or not kind:
                raise TypeError("Invalid pipeline activity type")
            properties = object_value(activity.get("typeProperties", {}))
            prop_path = activity_path + "/typeProperties"
            if kind == "TridentNotebook":
                target = literal(
                    properties.get("notebookId"),
                    prop_path + "/notebookId",
                    identifier=True,
                )
                emit(
                    activity_path,
                    prop_path + "/notebookId",
                    "execute",
                    "notebook",
                    target,
                    workspace(properties, prop_path),
                    referenceType="id",
                )
            elif kind == "InvokePipeline":
                if properties.get("operationType") != "InvokeFabricPipeline":
                    diagnostic(
                        prop_path + "/operationType", "unsupported_pipeline_operation"
                    )
                    continue
                target = literal(
                    properties.get("pipelineId"),
                    prop_path + "/pipelineId",
                    identifier=True,
                )
                emit(
                    activity_path,
                    prop_path + "/pipelineId",
                    "execute",
                    "pipeline",
                    target,
                    workspace(properties, prop_path),
                    referenceType="id",
                )
            elif kind == "ExecutePipeline":
                target = object_value(properties.get("pipeline", {}))
                field = prop_path + "/pipeline/referenceName"
                if target.get("type") != "PipelineReference":
                    diagnostic(
                        prop_path + "/pipeline", "unsupported_pipeline_reference"
                    )
                    continue
                emit(
                    activity_path,
                    field,
                    "execute",
                    "pipeline",
                    literal(target.get("referenceName"), field),
                    referenceType="name",
                )
            elif kind == "Copy":
                copy_endpoint(
                    properties.get("source", {}),
                    prop_path + "/source",
                    activity_path,
                    "read",
                )
                for field in ("sink", "destination"):
                    if field in properties:
                        copy_endpoint(
                            properties[field],
                            prop_path + "/" + field,
                            activity_path,
                            "write",
                        )
                if "sink" not in properties and "destination" not in properties:
                    diagnostic(prop_path + "/sink", "dynamic_or_missing_target")
            elif kind in ("ForEach", "Until"):
                if "activities" not in properties:
                    raise ValueError("Missing pipeline container activities")
                walk(properties["activities"], prop_path + "/activities", depth + 1)
            elif kind == "IfCondition":
                for field in ("ifTrueActivities", "ifFalseActivities"):
                    walk(properties.get(field, []), prop_path + "/" + field, depth + 1)
            elif kind == "Switch":
                cases = properties.get("cases", [])
                if not isinstance(cases, list):
                    raise TypeError("Invalid pipeline switch cases")
                activity_count += len(cases)
                if activity_count > _MAX_ACTIVITIES:
                    raise ValueError("Pipeline activity safety limit exceeded")
                for case_index, case in enumerate(cases):
                    case = object_value(case)
                    if "activities" not in case:
                        raise ValueError("Missing pipeline case activities")
                    walk(
                        case["activities"],
                        f"{prop_path}/cases/{case_index}/activities",
                        depth + 1,
                    )
                walk(
                    properties.get("defaultActivities", []),
                    prop_path + "/defaultActivities",
                    depth + 1,
                )
            elif kind not in _NO_IO:
                diagnostic(activity_path + "/type", "unsupported_activity_type")

    walk(pipeline["properties"].get("activities", []), "/properties/activities")
    return {
        "schemaVersion": 1,
        "evidence": "static_inference",
        "runtimeVerified": False,
        "coverage": "supported_static_references_only",
        "complete": not diagnostics,
        "references": references,
        "diagnostics": diagnostics,
    }
