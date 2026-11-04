"""Collect caller-visible Fabric connection metadata without credential material."""

from env.context import Context, log_validation_failure
from env.utility.fabric_collection import (
    FabricCollection,
    JsonObject,
    identified_records,
    select_fields,
)


async def main(context: Context | None = None) -> bool:
    """Inventory authorized connections using a deliberate metadata allowlist.

    Only id, displayName, gatewayId, connectivityType, privacyLevel and
    connectionDetails.type are saved. All paths, connection strings,
    credentialDetails, tokens and unknown fields are discarded before writing.
    No connection permissions or credential API is called.
    Validation failures log only schema paths, record ordinals and type labels.
    Display names must be present and either null or nonempty strings; explicit
    nulls are preserved in the snapshot without synthesizing a name.

    :param context: Configured runtime with a Fabric-audience client.
    :return: True only if all caller-visible pages were valid and persisted.
    :raises RuntimeError: If context or storage is unavailable.
    """
    if context is None:
        raise RuntimeError("Context is None")
    collection = FabricCollection(
        context,
        "fabricconnections",
        "Caller-visible connections only, not tenant-wide. Credential details "
        "and all connection paths are intentionally excluded.",
    )
    await collection.start()
    records = identified_records(
        await collection.pages("connections"),
        ("id", "connectivityType"),
        logger=context.logger,
    )
    safe_records: list[JsonObject] | None = None
    if records is not None:
        safe_records = []
        for ordinal, record in enumerate(records, 1):
            display_name = record.get("displayName")
            if "displayName" not in record or (
                display_name is not None
                and (not isinstance(display_name, str) or not display_name)
            ):
                log_validation_failure(
                    context.logger,
                    "fabricconnections",
                    "displayName",
                    "nonempty string or null",
                    display_name,
                    missing="displayName" not in record,
                    ordinal=ordinal,
                )
                safe_records = None
                break
            safe = select_fields(
                record,
                ("id", "displayName", "gatewayId", "connectivityType", "privacyLevel"),
            )
            details = record.get("connectionDetails")
            invalid_field = next(
                (
                    field
                    for field, value in safe.items()
                    if value is not None and not isinstance(value, str)
                ),
                None,
            )
            if invalid_field is not None:
                log_validation_failure(
                    context.logger,
                    "fabricconnections",
                    invalid_field,
                    "string or null",
                    safe[invalid_field],
                    ordinal=ordinal,
                )
                safe_records = None
                break
            if not isinstance(details, dict):
                log_validation_failure(
                    context.logger,
                    "fabricconnections",
                    "connectionDetails",
                    "object",
                    details,
                    missing="connectionDetails" not in record,
                    ordinal=ordinal,
                )
                safe_records = None
                break
            if not isinstance(details.get("type"), str) or not details["type"]:
                log_validation_failure(
                    context.logger,
                    "fabricconnections",
                    "connectionDetails.type",
                    "nonempty string",
                    details.get("type"),
                    missing="type" not in details,
                    ordinal=ordinal,
                )
                safe_records = None
                break
            safe["connectionDetails"] = {"type": details["type"]}
            safe_records.append(safe)
    complete = await collection.snapshot("connections", "connections", {}, safe_records)
    return await collection.finish(complete)
