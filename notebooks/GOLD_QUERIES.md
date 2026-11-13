# Explore Gold in a Fabric notebook

These examples use **Spark SQL**, not the Lakehouse SQL analytics endpoint's
T-SQL dialect. Attach `lh_monitor` as the default Lakehouse to a PySpark notebook,
or add cells to notebook 25. They do not write Lakehouse tables.

**Importable option:** upload
[26_monitor_gold_investigation.ipynb](26_monitor_gold_investigation.ipynb) into
your workspace's **Gold** folder. It embeds its own validated setup and selected
event loop, so no pasted setup or helper upload is needed. Attach `lh_monitor`,
edit `EVENTS_SQL`, and run all cells after Gold publication.

## Before querying

Gold tables must have been published. A preview alone does not create them:

1. Publish notebook 24 to Silver after reviewing its preview.
2. Run notebook 25 in preview, then explicitly publish Gold if appropriate.
3. Keep Bronze/Silver/Gold writers idle while opening the investigation.

With the execution inputs you previously shared, event/artifact queries can
return information, but execution/activity queries should be empty. That is an
evidence gap, not proof that no pipelines ran.

If you do not want to publish yet, leave `WRITE_TABLES=False` in notebook 25 and
set `EVENT_ID` to a provider event ID. Its existing preview displays that case
and trace, provided a ready Silver build has already been published.

## Setup: open one consistent published Gold build

Run this **Python cell once** before the SQL cells below. It pins Delta versions,
requires one ready build, checks every table's build IDs, and creates temporary
session views. It makes no persisted writes or permission changes.

If your Lakehouse has a different name, replace `lh_monitor` in `gold_name`.
The views are local to this Spark session; rerun setup to see a newer publication.

```python
from pyspark.sql import functions as F

def gold_name(table):
    return f"`lh_monitor`.`gold`.`{table}`"

def gold_version(table):
    return int(spark.sql(
        f"DESCRIBE HISTORY {gold_name(table)} LIMIT 1"
    ).first()["version"])

versions = {"build": gold_version("build")}
gate = spark.sql(
    f"SELECT * FROM {gold_name('build')} "
    f"VERSION AS OF {versions['build']}"
).collect()
if len(gate) != 1 or gate[0]["state"] != "ready":
    raise ValueError("Gold is not ready. Complete publication before querying.")

build_id = gate[0]["build_id"]
source_build_id = gate[0]["source_build_id"]
if not build_id or not source_build_id:
    raise ValueError("Gold gate is missing its build identifiers.")

frames = {}
for table in (
    "event_case", "event_trace_edge", "execution_fact",
    "pipeline_activity_fact", "event_execution_bridge",
    "reported_location", "evidence_coverage",
):
    versions[table] = gold_version(table)
    frame = spark.sql(
        f"SELECT * FROM {gold_name(table)} VERSION AS OF {versions[table]}"
    )
    matching_build = (
        F.col("build_id").eqNullSafe(F.lit(build_id))
        & F.col("source_build_id").eqNullSafe(F.lit(source_build_id))
    )
    if frame.filter(~matching_build).limit(1).count():
        raise ValueError(f"Mixed or incomplete Gold build in {table}.")
    frames[table] = frame

if any(gold_version(table) != version for table, version in versions.items()):
    raise ValueError("Gold changed during setup. Rerun after writers finish.")

for table, frame in frames.items():
    frame.createOrReplaceTempView(f"fm_gold_{table}")

print("Opened Gold build:", build_id)
print("Source Silver build:", source_build_id)
print("Temporary views ready; no Lakehouse tables were changed.")
```

A ready build is an internally consistent publication, not a guarantee of
complete collection coverage. This setup cannot manufacture missing evidence.

## 1. What evidence does this build contain?

Run each SQL block in its own notebook cell. `%%sql` selects Spark SQL.

```sql
%%sql
SELECT dataset, availability, row_count, interpretation
FROM fm_gold_evidence_coverage
ORDER BY dataset;
```

These are input coverage counts carried from Silver, not Gold event/fact counts.
Get the actual output counts separately:

```sql
%%sql
SELECT 'event cases' AS dataset, COUNT(*) AS row_count
FROM fm_gold_event_case
UNION ALL
SELECT 'trace edges', COUNT(*) FROM fm_gold_event_trace_edge
UNION ALL
SELECT 'execution facts', COUNT(*) FROM fm_gold_execution_fact
UNION ALL
SELECT 'activity facts', COUNT(*) FROM fm_gold_pipeline_activity_fact
UNION ALL
SELECT 'accepted event/run links', COUNT(*) FROM fm_gold_event_execution_bridge;
```

## 2. What operations were reported?

```sql
%%sql
SELECT
    operation,
    correlation_state,
    COUNT(*) AS event_count,
    SUM(CASE WHEN reported_event_success = true THEN 1 ELSE 0 END)
        AS reported_success,
    SUM(CASE WHEN reported_event_success = false THEN 1 ELSE 0 END)
        AS reported_failure,
    SUM(CASE WHEN reported_event_success IS NULL THEN 1 ELSE 0 END)
        AS outcome_not_reported
FROM fm_gold_event_case
GROUP BY operation, correlation_state
ORDER BY event_count DESC, operation;
```

Reported event success is not the same as pipeline-run success. Null outcomes
remain unknown.

## 3. Show recent events and choose one to investigate

```sql
%%sql
SELECT
    event_key,
    event_id,
    event_time_utc,
    operation,
    validity,
    correlation_state,
    referenced_artifact_count,
    unresolved_reference_count,
    reported_location_count,
    linked_execution_count,
    traced_execution_count,
    trace_capped
FROM fm_gold_event_case
ORDER BY event_time_utc DESC NULLS LAST, event_key
LIMIT 50;
```

Copy an `event_key` for queries 5-7. Use the key rather than assuming every event
has a provider `event_id`. This is an audit-event timeline, not a live run monitor.
To avoid copying keys individually, use [the event loop below](#loop-over-the-events-returned-by-your-query).

## 4. Which artifacts were referenced, and how reliable are their labels?

```sql
%%sql
WITH labels AS (
    SELECT
        event_key,
        event_time_utc,
        operation,
        explode(from_json(
            artifact_labels_json,
            'array<struct<artifact_key:string,name:string,label_timing:string>>'
        )) AS label
    FROM fm_gold_event_case
)
SELECT
    event_key,
    event_time_utc,
    operation,
    label.artifact_key AS artifact_key,
    label.name AS observed_name,
    label.label_timing AS label_timing
FROM labels
ORDER BY event_time_utc DESC NULLS LAST, event_key, artifact_key
LIMIT 100;
```

An event can have multiple labels, so these are reference rows, not distinct
event counts. `LATER_OBSERVED_HINT` is not proof of the name at event time.
Events without label entries are not shown by this exploded-label query; they
remain in `event_case`.

## 5. Follow one event's evidence trace

Replace `PASTE_EVENT_KEY_HERE` with a key returned by query 3.

```sql
%%sql
SELECT
    depth,
    source_type,
    source_key,
    relation_type,
    target_type,
    target_key,
    resolution,
    evidence_fields_json,
    source_path,
    observed_at_utc
FROM fm_gold_event_trace_edge
WHERE event_key = 'PASTE_EVENT_KEY_HERE'
ORDER BY depth, relation_type, edge_key
LIMIT 200;
```

`REPORTED_REFERENCE` is an audit reference. `EXACT_CORRELATION` is an accepted
identifier/scope match. `EVIDENCE_GAP` with a null target is deliberately missing
evidence, not a hidden destination. Depth is traversal depth, not chronological
order or a causal guarantee.

The display limit can omit edges. Check `trace_capped` in the case separately:
that flag describes the transformation's depth limit, not this query's limit.

## 6. Show activities on the executions traced from that event

```sql
%%sql
SELECT
    a.execution_id,
    a.activity_run_id,
    a.activity_name,
    a.activity_type,
    a.status,
    a.start_time_utc,
    a.end_time_utc,
    a.rows_read,
    a.rows_copied,
    a.data_read,
    a.data_written,
    a.poll_state,
    a.physical_source,
    a.physical_destination,
    a.destination_state
FROM fm_gold_pipeline_activity_fact a
WHERE EXISTS (
    SELECT 1
    FROM fm_gold_event_trace_edge t
    WHERE t.event_key = 'PASTE_EVENT_KEY_HERE'
      AND t.target_type = 'execution'
      AND t.target_key = a.execution_key
)
ORDER BY a.start_time_utc NULLS LAST, a.activity_key
LIMIT 100;
```

`EXISTS` avoids duplicating an activity when several trace edges reference the
same execution. This includes resolved child executions reached by the trace,
not just directly correlated root runs. It can correctly return no rows.

Metrics are retained per activity, not verified distinct business-row movement
across a whole chain. Physical source/destination remain unknown under the
current collection contract, even when metrics are populated.

## 7. What locations did the audit record report?

```sql
%%sql
SELECT source_field, reported_location, interpretation, source_path
FROM fm_gold_reported_location
WHERE event_key = 'PASTE_EVENT_KEY_HERE'
ORDER BY source_field, location_key;
```

These redacted audit references are **not proven pipeline sources or sinks**.
They can still contain sensitive operational detail.

## 8. Which cases deserve closer inspection?

```sql
%%sql
SELECT
    event_key,
    event_time_utc,
    operation,
    validity,
    reported_event_success,
    correlation_state,
    unresolved_reference_count,
    trace_capped
FROM fm_gold_event_case
WHERE validity <> 'VALID'
   OR reported_event_success = false
   OR unresolved_reference_count > 0
   OR trace_capped = true
   OR correlation_state IN ('AMBIGUOUS', 'UNRESOLVED_OR_SCOPE_MISMATCH')
ORDER BY event_time_utc DESC NULLS LAST, event_key
LIMIT 100;
```

This is an investigation shortlist, not a security finding or proof of impact.
`NO_RETAINED_EXACT_LINK` alone is not flagged here: many audit operations need
not correspond to a collected job, and your shared execution inputs are empty.

## 9. Group audit events by reported actor/IP keys

```sql
%%sql
SELECT
    actor_key,
    ip_key,
    COUNT(*) AS event_count,
    MIN(event_time_utc) AS first_retained_event_utc,
    MAX(event_time_utc) AS last_retained_event_utc
FROM fm_gold_event_case
WHERE actor_key IS NOT NULL OR ip_key IS NOT NULL
GROUP BY actor_key, ip_key
ORDER BY event_count DESC
LIMIT 50;
```

This groups audit events, not pipeline activities or distinct people. Gold
contains keys, not raw identity/IP values. Enabling those values in Silver does
not automatically copy them into Gold. Do not treat a reported IP as a verified
person/device/location or use these counts as proof of causality.

## Loop over the events returned by your query

The recommended option is **notebook 26** above. Its parameter cell controls
`LAKEHOUSE_NAME`, `EVENTS_SQL`, `PRINT_QUERIES` and `EXECUTE_QUERIES`. It opens the
published Gold snapshot, displays the selected events, then separately displays
trace/activity/location results for each unique returned key. It is read-only,
not a third medallion transformation.

For an existing notebook where you prefer to paste the implementation:

Use [explore_gold_events.py](explore_gold_events.py) to generate and execute
queries 5-7 separately for every unique event key returned by your selected
query.

1. Run this guide's Python setup cell to create the pinned `fm_gold_*` views.
2. Copy the entire script into a new **Python** cell in the same notebook.
   Do not run it as a local command-line script or a `%%sql` cell.
3. Edit `EVENTS_SQL` at the top to your chosen read-only `SELECT` event query. It must return an
   `event_key` column. The initial example selects the latest 50 events, like
   query 3; it does not silently select every event in Gold.
4. Run the cell. For each unique key, it prints the three generated SQL queries
   and displays separate trace, activity and reported-location result tables.
   Empty activity/location results are legitimate; processing continues.

The loop streams keys instead of collecting the entire event DataFrame on the
driver. Repeated keys in your query results are investigated once, in their
first-returned order. Invalid/null keys fail rather than generating unsafe SQL.
The final summary reports unique events processed and investigation queries
generated/executed.

The loop processes **all unique keys returned by `EVENTS_SQL`**. The selection's
filters and `LIMIT` determine the scope. Per-event investigation queries have no
SQL row limit, although Fabric's display UI can still page or limit rendered
rows. Large selections produce three queries and three result displays per
event; start with a small selection before expanding.

| Control | Behavior |
|---|---|
| `PRINT_QUERIES=True`, `EXECUTE_QUERIES=True` | Print SQL and display its results; default |
| `PRINT_QUERIES=False`, `EXECUTE_QUERIES=True` | Display results without SQL text |
| `PRINT_QUERIES=True`, `EXECUTE_QUERIES=False` | Print investigation SQL only; the event-selection query still runs |

If you already have a Python DataFrame from your selected query, copy just the
script's imports/functions and call:

```python
summary = run_gold_event_queries(spark, display, events_df)
print(summary)
```

No Lakehouse tables or files are written. Output contains operational detail;
review access and clear notebook outputs before sharing. The script uses the
existing pinned views, not automatically refreshed data. It stops on query or
display errors rather than claiming a complete investigation after a failure.

## If you prefer Python cells

After running setup, omit `%%sql` and use:

```python
display(spark.sql("""
SELECT operation, correlation_state, COUNT(*) AS event_count
FROM fm_gold_event_case
GROUP BY operation, correlation_state
ORDER BY event_count DESC
"""))
```

The queries are based on the implemented Gold schema. These examples have not
been executed against your live Gold publication. Missing tables require
publication; SQL analytics endpoint metadata can also lag publication, but these
examples read Delta directly through Spark.

See [the medallion explanation](MEDALLION_EXPLAINED.md) for interpretation and
[the runbook](MEDALLION.md) for publication/access safeguards.
