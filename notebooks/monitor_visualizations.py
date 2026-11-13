"""Read-only, bounded visualizations of curated Monitor observations."""

import json
import math

from notebooks.monitor_analytics import sha256
from notebooks.monitor_fabric_runtime import latest_frame, plot_counts, read_curated


def graph_lineage(frame, max_edges):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    if type(max_edges) is not int or not 1 <= max_edges <= 200:
        raise ValueError("Select 1-200 graph edges")
    values = frame.orderBy("observation_id").limit(max_edges + 1).collect()
    if not values:
        print("No selected lineage edges. Check resource coverage and diagnostics.")
        return
    truncated = len(values) > max_edges
    values = values[:max_edges]
    nodes, edges = {}, []
    for entry in values:
        query = "item:" + entry["item_id"]
        nodes[query] = (entry["item_type"] or "Item") + ":" + entry["item_id"][:8]
        if entry["evidence_type"] == "eventstream_configuration":
            reference = json.loads(entry["reference"])
            scope = "topology:" + entry["workspace_id"] + ":" + entry["item_id"] + ":"
            relation = entry["relation_type"]
            if relation == "topology_input":
                source, destination = (
                    scope + reference["fromNode"],
                    scope + reference["toNode"],
                )
                nodes[source] = reference["fromType"] + ":" + reference["fromNode"][:8]
                nodes[destination] = reference["toType"] + ":" + reference["toNode"][:8]
            else:
                node = scope + reference["nodeId"]
                nodes[node] = reference["type"] + ":" + reference["nodeId"][:8]
                if relation == "topology_node":
                    source, destination = query, node
                else:
                    target = (
                        entry["related_item_id"] or reference["connectionReference"]
                    )
                    destination = (
                        "item:" + target
                        if entry["related_item_id"]
                        else "connection:" + target
                    )
                    nodes.setdefault(
                        destination,
                        (entry["related_type"] or "Reference") + ":" + target[:8],
                    )
                    source = node
            edges.append((source, destination, relation))
            continue
        reference = entry["related_item_id"] or entry["reference"] or "unresolved"
        related = (
            "item:" + entry["related_item_id"]
            if entry["related_item_id"]
            else "reference:" + (entry["related_type"] or "") + ":" + reference
        )
        nodes.setdefault(
            related,
            (entry["related_type"] or "Unresolved")
            + ":"
            + sha256(reference.encode())[:8],
        )
        source, destination = (
            (related, query) if entry["direction"] == "upstream" else (query, related)
        )
        edges.append((source, destination, entry["evidence_type"]))
    ordered = sorted(nodes)
    positions = {
        node: (
            math.cos(2 * math.pi * index / len(ordered)),
            math.sin(2 * math.pi * index / len(ordered)),
        )
        for index, node in enumerate(ordered)
    }
    _, axis = plt.subplots(figsize=(13, 10))
    for source, destination, evidence in edges:
        configured = evidence in {
            "configuration_metadata",
            "shortcut_configuration",
            "topology_node",
            "topology_input",
            "topology_target",
        }
        axis.annotate(
            "",
            xy=positions[destination],
            xytext=positions[source],
            arrowprops={
                "arrowstyle": "->"
                if evidence == "topology_input" or not configured
                else "-",
                "alpha": 0.6,
                "color": "tab:purple"
                if evidence == "topology_input"
                else "tab:gray"
                if evidence == "topology_node"
                else "tab:green"
                if configured
                else "tab:orange"
                if evidence == "static_inference"
                else "tab:blue",
                "linestyle": "--" if configured else "-",
            },
        )
    for node, (x, y) in positions.items():
        axis.scatter([x], [y], s=80)
        axis.text(x * 1.1, y * 1.1, nodes[node], ha="center", fontsize=8)
    axis.legend(
        handles=[
            Line2D([0], [0], color="tab:blue", label="Scanner relationship"),
            Line2D([0], [0], color="tab:orange", label="Potential static reference"),
            Line2D(
                [0],
                [0],
                color="tab:green",
                linestyle="--",
                label="Configured Lakehouse/shortcut association (not I/O)",
            ),
            Line2D(
                [0],
                [0],
                color="tab:purple",
                linestyle="--",
                label="Declared Eventstream input (not runtime)",
            ),
            Line2D(
                [0],
                [0],
                color="tab:gray",
                linestyle="--",
                label="Eventstream node membership",
            ),
        ]
    )
    axis.set_title(
        "Selected relationships (not runtime I/O)"
        + ("; truncated" if truncated else "")
    )
    axis.set_xlim(-1.5, 1.5)
    axis.set_ylim(-1.5, 1.5)
    axis.axis("off")
    plt.show()


def render(
    spark_session,
    display_frame,
    *,
    prefix,
    permission_mode,
    permission_cycle_id="",
    stale_after_hours=24,
    lineage_source_path="",
    max_graph_edges=40,
):
    from pyspark.sql import functions as F

    if permission_mode not in {"Scoped", "Tenant"}:
        raise ValueError("Choose Scoped or Tenant explicitly")
    if isinstance(stale_after_hours, bool) or stale_after_hours <= 0:
        raise ValueError("Choose a positive staleness threshold")
    spark_session.conf.set("spark.sql.session.timeZone", "UTC")
    health = read_curated(spark_session, prefix, "collection_health")
    latest_health = latest_frame(health, ["module"]).withColumn(
        "freshness",
        F.when(F.col("observed_at_utc").isNull(), "unknown")
        .when(
            F.unix_timestamp(F.current_timestamp())
            - F.unix_timestamp(F.to_timestamp("observed_at_utc"))
            > stale_after_hours * 3600,
            "stale",
        )
        .otherwise("within_threshold"),
    )
    display_frame(
        latest_health.select(
            "module", "coverage_status", "freshness", "observed_at_utc", "issue"
        )
    )
    plot_counts(
        health, "coverage_status", "Retained collection observations by coverage"
    )
    print(
        "Historical invalid/unknown observations remain visible, even after later success."
    )
    display_frame(
        health.filter(F.col("coverage_status").isin("invalid", "unfinished", "missing"))
        .groupBy("module", "coverage_status")
        .count()
    )

    inventory = read_curated(spark_session, prefix, "inventory")
    plot_counts(
        inventory, "item_type", "Inventory observations (not current unique items)"
    )

    cycles = read_curated(spark_session, prefix, "permission_cycles").filter(
        F.col("mode") == permission_mode
    )
    if permission_cycle_id:
        cycles = cycles.filter(F.col("cycle_id") == permission_cycle_id)
    unknown_cycle = (
        not permission_cycle_id
        and cycles.filter(F.col("observed_at_utc").isNull()).limit(1).count()
    )
    selected = (
        []
        if unknown_cycle
        else (
            cycles.orderBy(
                F.col("observed_at_utc").desc_nulls_last(), F.col("source_path").desc()
            )
            .limit(1)
            .collect()
        )
    )
    if not selected:
        print(
            "No safely selected permission cycle (missing/unknown evidence). "
            "Inspect health or select an explicit historical cycle; this is not zero grants."
        )
    else:
        selected = selected[0]
        print(
            {
                key: selected[key]
                for key in (
                    "mode",
                    "cycle_id",
                    "coverage_status",
                    "chain_valid",
                    "cycle_finished",
                    "cycle_healthy",
                )
            }
        )
        resources = read_curated(spark_session, prefix, "permission_resources").filter(
            (F.col("mode") == permission_mode)
            & (F.col("cycle_id") == selected["cycle_id"])
            & (F.col("observation_unit") == "item_access")
        )
        resources = latest_frame(resources, ["workspace_id", "item_id"])
        plot_counts(resources, "coverage_status", "Selected-cycle item access coverage")
        display_frame(
            resources.groupBy("coverage_status").agg(
                F.count("*").alias("items"),
                F.sum("record_count").alias("successful_access_records"),
            )
        )
        if not selected["chain_valid"]:
            print("Invalid selected cycle: no grant view is admitted.")
        else:
            grant_keys = ["mode", "cycle_id", "workspace_id", "item_id", "source_path"]
            grants = read_curated(spark_session, prefix, "permission_grants")
            grants = grants.join(
                resources.filter(F.col("coverage_status") == "success")
                .select(*grant_keys)
                .distinct(),
                grant_keys,
                "inner",
            )
            permissions = grants.select(
                F.explode(F.from_json("permissions_json", "array<string>")).alias(
                    "permission"
                )
            )
            plot_counts(
                permissions,
                "permission",
                "Selected-cycle observed permission assignments",
            )

    jobs = read_curated(spark_session, prefix, "job_observations")
    jobs = latest_frame(jobs, ["workspace_id", "item_id", "job_id"])
    plot_counts(
        jobs, "status", "Latest retained status per job (not current polling health)"
    )
    display_frame(
        jobs.groupBy("item_type", "status").agg(
            F.count("*").alias("jobs"),
            F.avg("duration_seconds").alias("mean_known_duration_seconds"),
        )
    )
    job_resources = read_curated(spark_session, prefix, "job_resources")
    job_resources = latest_frame(job_resources, ["workspace_id", "item_id"])
    plot_counts(
        job_resources, "coverage_status", "Latest per-item job collection coverage"
    )

    resources = read_curated(spark_session, prefix, "lineage_resources")
    edges = read_curated(spark_session, prefix, "lineage_edges")
    if lineage_source_path:
        resources = resources.filter(F.col("source_path") == lineage_source_path)
        edges = edges.filter(F.col("source_path") == lineage_source_path)
        print("Explicit historical source selected; this is not a current graph.")
        eligible = resources.filter(
            F.col("coverage_status").isin(
                "success", "legacy_unverified", "partial_batch"
            )
        )
    else:
        resources = latest_frame(
            resources.filter(F.col("observed_at_utc").isNotNull()),
            ["workspace_id", "item_id", "evidence_type"],
        )
        # Select the latest attempt before filtering success; never fall back to old edges.
        eligible = resources.filter(
            F.col("coverage_status").isin("success", "partial_batch")
        )
        for configuration_module in ("fabricshortcuts", "fabriceventstreamtopology"):
            attempt = (
                latest_health.filter(F.col("module") == configuration_module)
                .select("mode", "coverage_status")
                .limit(1)
                .collect()
            )
            if attempt:
                selected = attempt[0]
                eligible = eligible.filter(
                    (F.col("module") != configuration_module)
                    | (
                        (F.col("mode") == selected["mode"])
                        & F.lit(selected["coverage_status"] == "success")
                    )
                )
            else:
                eligible = eligible.filter(F.col("module") != configuration_module)
        uncertain = health.filter(
            F.col("module").isin(
                "fabricitemdefinitions",
                "lineage_edges",
                "fabricshortcuts",
                "fabriceventstreamtopology",
            )
            & F.col("coverage_status").isin("invalid", "unfinished")
        )
        if uncertain.limit(1).count():
            print(
                "Invalid/unfinished lineage evidence prevents automatic graph selection. "
                "Inspect health, then select an explicit historical LINEAGE_SOURCE_PATH."
            )
            eligible = eligible.limit(0)
    plot_counts(resources, "coverage_status", "Selected lineage resource coverage")
    keys = ["source_path", "workspace_id", "item_id", "evidence_type"]
    edges = edges.join(eligible.select(*keys).distinct(), keys, "inner")
    plot_counts(
        edges, "evidence_type", "Selected lineage evidence, never runtime proof"
    )
    diagnostics = read_curated(spark_session, prefix, "lineage_diagnostics")
    plot_counts(diagnostics, "reason", "Retained static-analysis diagnostics")
    graph_lineage(edges, max_graph_edges)
