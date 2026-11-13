"""Read-only, resource-scoped investigation of retained curated evidence."""

from notebooks.monitor_analytics import uuid
from notebooks.monitor_fabric_runtime import read_curated, table_name

DISCOVERY_SCHEMA = (
    "resource_number int, workspace_id string, workspace_name_hint string, "
    "item_id string, item_name_hint string, item_type_hint string"
)


def investigation_settings(permission_mode, max_rows):
    if permission_mode not in {"Scoped", "Tenant"}:
        raise ValueError("Choose Scoped or Tenant explicitly")
    if type(max_rows) is not int or not 1 <= max_rows <= 1000:
        raise ValueError("Select 1-1000 rows per evidence section")


def investigation_scope(workspace_id, item_id, permission_mode, max_rows):
    try:
        workspace, item = uuid(workspace_id), uuid(item_id)
    except ValueError as exc:
        raise ValueError(
            "Select an explicit canonical workspace UUID and item UUID"
        ) from exc
    investigation_settings(permission_mode, max_rows)
    return workspace, item


def run_investigation(
    spark_session,
    display_frame,
    *,
    prefix,
    permission_mode,
    auto_discover=True,
    workspace_id="",
    item_id="",
    workspace_search="",
    item_search="",
    item_type="",
    resource_number=0,
    permission_cycle_id="",
    max_rows=200,
):
    from pyspark.sql import functions as F

    investigation_settings(permission_mode, max_rows)
    if type(auto_discover) is not bool:
        raise TypeError("AUTO_DISCOVER must be True or False")
    for value in (
        workspace_id,
        item_id,
        workspace_search,
        item_search,
        item_type,
        permission_cycle_id,
    ):
        if not isinstance(value, str):
            raise TypeError("Discovery filters, IDs and permission cycle must be text")
    if type(resource_number) is not int or not 0 <= resource_number <= max_rows:
        raise ValueError("RESOURCE_NUMBER must be 0 or a displayed resource number")
    table_name(prefix, "inventory")
    if not auto_discover:
        workspace, item = investigation_scope(
            workspace_id, item_id, permission_mode, max_rows
        )
    else:
        for value in (workspace_id, item_id):
            if value:
                uuid(value)
        if not spark_session.catalog.tableExists(table_name(prefix, "inventory")):
            print(
                "Discovery NOT PUBLISHED / UNKNOWN: publish notebook 01 inventory "
                "first, or disable AUTO_DISCOVER and provide known IDs. "
                "No API discovery or collection is performed."
            )
            return
        inventory = read_curated(spark_session, prefix, "inventory")
        print(
            "Discovering from retained inventory across sources/modes, NOT current "
            "or complete estate. Name/type hints are historical labels, not current "
            "metadata. Missing names stay unknown; access mode is selected separately."
        )
        workspaces = inventory.filter(F.lower(F.col("item_type")) == "workspace")
        if workspace_search:
            workspaces = workspaces.filter(
                F.lower(F.col("item_name")).contains(workspace_search.lower())
            )
        workspaces = workspaces.groupBy("workspace_id").agg(
            F.min("item_name").alias("workspace_name_hint")
        )
        candidates = inventory.filter(
            F.col("workspace_id").isNotNull()
            & F.col("item_id").isNotNull()
            & (F.lower(F.col("item_type")) != "workspace")
        )
        if workspace_id:
            candidates = candidates.filter(F.col("workspace_id") == workspace_id)
        if item_id:
            candidates = candidates.filter(F.col("item_id") == item_id)
        if item_search:
            candidates = candidates.filter(
                F.lower(F.col("item_name")).contains(item_search.lower())
            )
        if item_type:
            candidates = candidates.filter(
                F.lower(F.col("item_type")) == item_type.lower()
            )
        candidates = (
            candidates.groupBy("workspace_id", "item_id")
            .agg(
                F.min("item_name").alias("item_name_hint"),
                F.min("item_type").alias("item_type_hint"),
            )
            .join(
                workspaces,
                "workspace_id",
                "inner" if workspace_search else "left",
            )
            .orderBy(F.col("workspace_id").asc(), F.col("item_id").asc())
        )
        values = candidates.limit(max_rows + 1).collect()
        if not values:
            print(
                "No matching retained items. This is NOT proof of an empty estate. "
                "Clear or broaden filters and inspect notebook 01 coverage. Name searches "
                "require retained names; ID filters do not."
            )
            return
        visible = values[:max_rows]
        display_frame(
            spark_session.createDataFrame(
                [
                    {
                        "resource_number": number,
                        **{
                            key: entry[key]
                            for key in (
                                "workspace_id",
                                "workspace_name_hint",
                                "item_id",
                                "item_name_hint",
                                "item_type_hint",
                            )
                        },
                    }
                    for number, entry in enumerate(visible, start=1)
                ],
                schema=DISCOVERY_SCHEMA,
            )
        )
        if len(values) > max_rows:
            print(
                f"Discovery TRUNCATED to {max_rows} distinct workspace/item pairs. "
                "Filter by workspace/item name or type to narrow the list."
            )
        if resource_number > len(visible):
            raise ValueError("RESOURCE_NUMBER is not in the displayed discovery list")
        if resource_number:
            selected = visible[resource_number - 1]
            print(
                "Using RESOURCE_NUMBER from this run's displayed list. Numbering "
                "can change as inventory/filters change; use IDs for a stable rerun."
            )
        elif len(values) == 1:
            selected = values[0]
            print("One distinct matching resource; investigating automatically.")
        else:
            print(
                "Multiple resources: no item was selected automatically. Set "
                "WORKSPACE_SEARCH, ITEM_SEARCH or ITEM_TYPE to narrow the list, "
                "or set RESOURCE_NUMBER to a displayed number and rerun. "
                "WORKSPACE_ID/ITEM_ID are optional exact filters."
            )
            return
        workspace, item = selected["workspace_id"], selected["item_id"]
    render_investigation(
        spark_session,
        display_frame,
        prefix=prefix,
        workspace_id=workspace,
        item_id=item,
        permission_mode=permission_mode,
        permission_cycle_id=permission_cycle_id,
        max_rows=max_rows,
    )


def render_investigation(
    spark_session,
    display_frame,
    *,
    prefix,
    workspace_id,
    item_id,
    permission_mode,
    permission_cycle_id="",
    max_rows=200,
):
    from pyspark.sql import functions as F

    workspace, item = investigation_scope(
        workspace_id, item_id, permission_mode, max_rows
    )
    if not isinstance(permission_cycle_id, str):
        raise TypeError("PERMISSION_CYCLE_ID must be text")
    table_name(prefix, "inventory")
    spark_session.conf.set("spark.sql.session.timeZone", "UTC")
    print(
        f"Retained evidence for workspace {workspace}, item {item}. "
        "Each section is independent historical observations, NOT current state, "
        "a common snapshot, tenant completeness or effective access."
    )
    print(
        "Compare source_path, source_sha256, observed_at_utc, mode and cycle_id "
        "before correlating rows. Repeated polls/events/grants are not additive. "
        "Null observation times and legacy_unverified coverage remain unknown."
    )

    def show(dataset, description, predicate=None):
        print(f"\n{dataset}: {description}")
        if not spark_session.catalog.tableExists(table_name(prefix, dataset)):
            print(
                "NOT PUBLISHED / UNKNOWN: run the owning transformation with "
                "WRITE_TABLES=True if this evidence is required."
            )
            return
        frame = read_curated(spark_session, prefix, dataset)
        if predicate is not None:
            frame = frame.filter(predicate)
        values = (
            frame.orderBy(
                F.col("observed_at_utc").desc_nulls_first(),
                F.col("observation_id").asc(),
            )
            .limit(max_rows + 1)
            .collect()
        )
        if not values:
            print(
                "No matching retained observations. This is NOT proof of zero "
                "activity, jobs, grants or dependencies; inspect coverage."
            )
            return
        if len(values) > max_rows:
            print(
                f"TRUNCATED to {max_rows} rows; not a total or complete history. "
                "Unknown-time rows sort first, then newest known observations."
            )
        display_frame(
            spark_session.createDataFrame(values[:max_rows], schema=frame.schema)
        )

    owner = (F.lower(F.col("workspace_id")) == workspace) & (
        F.lower(F.col("item_id")) == item
    )
    incoming = (F.lower(F.col("related_workspace_id")) == workspace) & (
        F.lower(F.col("related_item_id")) == item
    )
    access = owner & (F.col("mode") == permission_mode)
    cycles = F.col("mode") == permission_mode
    if permission_cycle_id:
        cycles = cycles & (F.col("cycle_id") == permission_cycle_id)
        access = access & (F.col("cycle_id") == permission_cycle_id)
    print(
        f"Permission mode: {permission_mode}. "
        + (
            f"Explicit historical cycle: {permission_cycle_id}."
            if permission_cycle_id
            else "All retained cycles in this mode, NOT a merged access list."
        )
    )

    show(
        "collection_health",
        "collection-wide historical context, NOT coverage of this item",
    )
    show("inventory", "matching inventory observations, not current existence", owner)
    show("permission_cycles", "mode/cycle-wide outcomes, not item grants", cycles)
    show(
        "permission_resources",
        "item collection attempts; failed/absent outcomes are unknown access",
        access,
    )
    show(
        "permission_grants",
        "historically observed assignments, not effective or current access; "
        "no group expansion or workspace-role inheritance",
        access,
    )
    show("job_resources", "item polling outcomes, including failed/empty polls", owner)
    show(
        "job_observations",
        "retained job statuses; later failures do not refresh older statuses",
        owner,
    )
    show(
        "lineage_resources",
        "owned relationship collection/analysis outcomes, including zero edges",
        owner,
    )
    show(
        "lineage_edges",
        "historical owned references AND incoming references with explicit matching "
        "workspace/item IDs; evidence_type/direction distinguish Scanner, static "
        "and configured associations; none proves runtime I/O or removal impact",
        owner | incoming,
    )
    print(
        "Unresolved target IDs/workspaces cannot be matched as incoming links. "
        "Incoming links carry the other item's provenance; this is not transitive lineage."
    )
    show("lineage_diagnostics", "owned unresolved/unsupported analysis evidence", owner)
    show(
        "estate_coverage",
        "activity-analysis collection context, NOT item-level coverage",
        F.col("analysis") == "activity",
    )
    show(
        "activity_events",
        "events carrying explicit matching workspace/item IDs; event time is "
        "not collection time; events without these IDs cannot be attributed",
        owner,
    )
