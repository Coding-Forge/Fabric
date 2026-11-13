"""Paste into a Fabric PySpark cell after the GOLD_QUERIES.md setup."""

import re

EVENTS_SQL = """
SELECT event_key, event_id, event_time_utc, operation
FROM fm_gold_event_case
ORDER BY event_time_utc DESC NULLS LAST, event_key
LIMIT 50
"""
PRINT_QUERIES = True
EXECUTE_QUERIES = True


def open_gold_query_views(spark_session, *, lakehouse="lh_monitor"):
    if not isinstance(lakehouse, str) or not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*", lakehouse
    ):
        raise ValueError("Lakehouse name must be a simple identifier")
    from pyspark.sql import functions as F

    spark_session.conf.set("spark.sql.session.timeZone", "UTC")

    def name(table):
        return f"`{lakehouse}`.`gold`.`{table}`"

    def version(table):
        return int(
            spark_session.sql(f"DESCRIBE HISTORY {name(table)} LIMIT 1").first()[
                "version"
            ]
        )

    versions = {"build": version("build")}
    gate = spark_session.sql(
        f"SELECT * FROM {name('build')} VERSION AS OF {versions['build']}"
    ).collect()
    if len(gate) != 1 or gate[0]["state"] != "ready":
        raise ValueError("Gold is not ready. Complete notebook 25 publication first.")
    build_id, source_build_id = gate[0]["build_id"], gate[0]["source_build_id"]
    if not build_id or not source_build_id:
        raise ValueError("Gold gate is missing its build identifiers")
    frames = {}
    for table in (
        "event_case",
        "event_trace_edge",
        "execution_fact",
        "pipeline_activity_fact",
        "event_execution_bridge",
        "reported_location",
        "evidence_coverage",
    ):
        versions[table] = version(table)
        frame = spark_session.sql(
            f"SELECT * FROM {name(table)} VERSION AS OF {versions[table]}"
        )
        matching_build = F.col("build_id").eqNullSafe(F.lit(build_id)) & F.col(
            "source_build_id"
        ).eqNullSafe(F.lit(source_build_id))
        if frame.filter(~matching_build).limit(1).count():
            raise ValueError(f"Mixed or incomplete Gold build in {table}")
        frames[table] = frame
    if any(version(table) != prior for table, prior in versions.items()):
        raise ValueError("Gold changed during setup. Rerun after writers finish.")
    for table, frame in frames.items():
        frame.createOrReplaceTempView(f"fm_gold_{table}")
    return {
        "build_id": build_id,
        "source_build_id": source_build_id,
        "source_versions": versions,
    }


def gold_event_queries(event_key):
    if not isinstance(event_key, str) or not re.fullmatch(r"[0-9a-f]{64}", event_key):
        raise ValueError(
            "Expected a Gold event_key: 64 lowercase hexadecimal characters"
        )
    return (
        (
            "Evidence trace",
            f"""SELECT
    depth, source_type, source_key, relation_type,
    target_type, target_key, resolution, evidence_fields_json,
    source_path, observed_at_utc
FROM fm_gold_event_trace_edge
WHERE event_key = '{event_key}'
ORDER BY depth, relation_type, edge_key""",
        ),
        (
            "Traced activities",
            f"""SELECT
    a.execution_id, a.activity_run_id, a.activity_name, a.activity_type,
    a.status, a.start_time_utc, a.end_time_utc,
    a.rows_read, a.rows_copied, a.data_read, a.data_written,
    a.poll_state, a.physical_source, a.physical_destination,
    a.destination_state
FROM fm_gold_pipeline_activity_fact a
WHERE EXISTS (
    SELECT 1
    FROM fm_gold_event_trace_edge t
    WHERE t.event_key = '{event_key}'
      AND t.target_type = 'execution'
      AND t.target_key = a.execution_key
)
ORDER BY a.start_time_utc NULLS LAST, a.activity_key""",
        ),
        (
            "Reported audit locations",
            f"""SELECT source_field, reported_location, interpretation, source_path
FROM fm_gold_reported_location
WHERE event_key = '{event_key}'
ORDER BY source_field, location_key""",
        ),
    )


def run_gold_event_queries(
    spark_session,
    display_frame,
    events_df,
    *,
    print_queries=True,
    execute_queries=True,
):
    if any(type(value) is not bool for value in (print_queries, execute_queries)):
        raise ValueError("Query output controls must be boolean")
    if not print_queries and not execute_queries:
        raise ValueError("Enable SQL printing, query execution, or both")
    if "event_key" not in events_df.columns:
        raise ValueError("The selected event query must return an event_key column")

    seen = set()
    executed = 0
    for row in events_df.select("event_key").toLocalIterator():
        event_key = row["event_key"]
        queries = gold_event_queries(event_key)
        if event_key in seen:
            continue
        seen.add(event_key)
        print(f"\nEvent {len(seen)}: {event_key}")
        for title, sql in queries:
            print(f"\n{title}")
            if print_queries:
                print(sql + ";")
            if execute_queries:
                display_frame(spark_session.sql(sql))
                executed += 1

    if not seen:
        print("No event keys returned by the selected query.")
    return {
        "events_processed": len(seen),
        "queries_generated": len(seen) * 3,
        "queries_executed": executed,
    }


if __name__ == "__main__":
    notebook_spark = globals().get("spark")
    notebook_display = globals().get("display")
    if notebook_spark is None or notebook_display is None:
        raise RuntimeError(
            "Paste this script into a Fabric PySpark notebook after the Gold query setup."
        )
    events_df = notebook_spark.sql(EVENTS_SQL)
    summary = run_gold_event_queries(
        notebook_spark,
        notebook_display,
        events_df,
        print_queries=PRINT_QUERIES,
        execute_queries=EXECUTE_QUERIES,
    )
    print("\nCompleted:", summary)
