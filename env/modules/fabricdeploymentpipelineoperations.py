"""Preserve read-only observations of Fabric deployment pipeline operations."""

from uuid import UUID

from env.context import Context
from env.utility.fabric_collection import (
    FabricCollection,
    identified_records,
    select_fields,
)

_OPERATION_FIELDS = (
    "id",
    "type",
    "status",
    "lastUpdatedTime",
    "executionStartTime",
    "executionEndTime",
    "sourceStageId",
    "targetStageId",
)


async def main(context: Context | None = None) -> bool:
    """Discover authorized pipelines and collect their recent deployment operations.

    Discovery is caller-visible, not tenant-wide; operation history requires
    pipeline Admin. Up to 20 recent deployments are exposed per pipeline.
    Immutable polling observations preserve earlier runs and refresh ongoing
    status; consumers deduplicate by pipeline ID/operation ID and observedAt.
    Deployments aged out between polls cannot be recovered. No deployment or
    other mutation is issued.

    :param context: Configured runtime with actual pipeline resource permissions.
    :return: True only when discovery and every pipeline history/write succeeded.
    :raises RuntimeError: If context or storage is unavailable.
    """
    if context is None:
        raise RuntimeError("Context is None")
    collection = FabricCollection(
        context,
        "fabricdeploymentpipelineoperations",
        "Caller-visible pipelines, not tenant-wide; operation history requires "
        "pipeline Admin. Up to 20 recent deployments per pipeline; polling gaps "
        "cannot be recovered.",
    )
    await collection.start()
    pipelines = identified_records(
        await collection.pages("deploymentPipelines"), ("id", "displayName")
    )
    if pipelines is not None:
        pipelines = [
            select_fields(pipeline, ("id", "displayName")) for pipeline in pipelines
        ]
    complete = await collection.snapshot(
        "pipelines", "deploymentPipelines", {}, pipelines
    )
    if pipelines is None:
        return await collection.finish(False)
    for pipeline in pipelines:
        # API resource IDs must never become unvalidated path or URL components.
        try:
            pipeline_id = str(UUID(pipeline["id"]))
        except (ValueError, TypeError, AttributeError):
            context.logger.warning("Pipeline discovery returned an invalid UUID")
            return await collection.finish(False)
        endpoint = f"deploymentPipelines/{pipeline_id}/operations"
        records = identified_records(
            await collection.pages(endpoint), ("id", "type", "status")
        )
        if records is not None:
            if any(
                field in record
                and record[field] is not None
                and not isinstance(record[field], str)
                for record in records
                for field in _OPERATION_FIELDS
            ):
                records = None
            else:
                records = [
                    select_fields(record, _OPERATION_FIELDS) for record in records
                ]
        success = await collection.snapshot(
            pipeline_id, endpoint, {"deploymentPipeline": pipeline}, records
        )
        complete = success and complete
    return await collection.finish(complete)
