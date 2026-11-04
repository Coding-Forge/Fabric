"""Preserve observations of recent Fabric item job instances."""

from env.context import Context
from env.utility.fabric_collection import (
    JOB_ITEM_TYPES,
    FabricCollection,
    identified_records,
    item_scope,
    select_fields,
)

_JOB_FIELDS = (
    "id",
    "itemId",
    "jobType",
    "invokeType",
    "status",
    "rootActivityId",
    "startTimeUtc",
    "endTimeUtc",
    "failureReason",
)


async def main(context: Context | None = None) -> bool:
    """Poll explicitly configured supported items and retain immutable observations.

    ``FABRIC_ITEM_JOB_SCOPE`` requires 1–100 workspaceId/itemId/type objects.
    Supported types are Notebook, DataPipeline and SparkJobDefinition. Other
    types fail configuration, never masquerading as empty history. Returned
    job item IDs must match the requested parent.

    Most items expose only 100 recent completed jobs plus active jobs. Polling
    cannot recover runs already aged out between polls. Each run retains raw
    selected job fields, including failureReason, and UTC observation context.
    Deduplicate across observations by workspaceId/itemId/job id, selecting
    the latest observedAt for status, not by overwriting daily history.

    :param context: Configured runtime; caller needs actual resource permissions.
    :return: True only if every scoped item was read and persisted completely.
    :raises RuntimeError: If context or storage is unavailable.
    :raises ValueError: If scope or item type is invalid.
    :raises TypeError: If a scope entry is not an object.
    """
    if context is None:
        raise RuntimeError("Context is None")
    scope = item_scope("FABRIC_ITEM_JOB_SCOPE", 100)
    if any(item["type"] not in JOB_ITEM_TYPES for item in scope):
        raise ValueError(
            "FABRIC_ITEM_JOB_SCOPE supports Notebook, DataPipeline and SparkJobDefinition"
        )
    collection = FabricCollection(
        context,
        "fabricitemjobhistory",
        "Explicit configured supported items; resource access required. Most items "
        "expose only 100 recent completed jobs plus active jobs; polling gaps "
        "cannot be recovered. Admin discovery does not grant resource access.",
    )
    await collection.start()
    complete = True
    for item in scope:
        endpoint = (
            f"workspaces/{item['workspaceId']}/items/{item['itemId']}/jobs/instances"
        )
        records = identified_records(
            await collection.pages(endpoint),
            ("id", "itemId", "jobType", "invokeType", "status"),
        )
        if records is not None:
            if any(
                record["itemId"] != item["itemId"]
                or any(
                    field in record
                    and record[field] is not None
                    and not isinstance(record[field], str)
                    for field in ("startTimeUtc", "endTimeUtc", "rootActivityId")
                )
                or (
                    record.get("failureReason") is not None
                    and not isinstance(record["failureReason"], dict)
                )
                for record in records
            ):
                records = None
            else:
                records = [select_fields(record, _JOB_FIELDS) for record in records]
        success = await collection.snapshot(
            f"{item['workspaceId']}_{item['itemId']}", endpoint, dict(item), records
        )
        complete = success and complete
    return await collection.finish(complete)
