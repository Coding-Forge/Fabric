"""Fabric-only persistence helpers embedded in every generated notebook."""

import re

from notebooks.monitor_analytics import (
    COMMON,
    SCHEMA_VERSION,
    SCHEMAS,
    latest,
    selected_permission_cycle,
)


def table_name(prefix, dataset):
    if not re.fullmatch(r"monitor_[A-Za-z0-9_]*", prefix) or dataset not in SCHEMAS:
        raise ValueError("Use a monitor_ table prefix and a known dataset")
    return prefix + dataset


def to_frame(spark_session, dataset, rows):
    from pyspark.sql import types as T

    types = {
        "int": T.IntegerType,
        "long": T.LongType,
        "double": T.DoubleType,
        "boolean": T.BooleanType,
        "string": T.StringType,
    }
    schema = T.StructType(
        [
            T.StructField(name, types[kind](), True)
            for name, kind in {**COMMON, **SCHEMAS[dataset]}.items()
        ]
    )
    return spark_session.createDataFrame(rows, schema=schema)


def publish(spark_session, tables, datasets, prefix, *, write=False):
    """Insert immutable observations only; never overwrite, delete or run VACUUM."""
    from delta.tables import DeltaTable
    from pyspark.sql import functions as F

    spark_session.conf.set("spark.sql.session.timeZone", "UTC")
    prepared = {}
    for dataset in datasets:
        name = table_name(prefix, dataset)
        frame = to_frame(spark_session, dataset, tables[dataset])
        exists = spark_session.catalog.tableExists(name)
        if exists:
            properties = {
                entry["key"]: entry["value"]
                for entry in spark_session.sql(f"SHOW TBLPROPERTIES {name}").collect()
            }
            if (
                properties.get("monitor.contract") != str(SCHEMA_VERSION)
                or properties.get("monitor.dataset") != dataset
            ):
                raise ValueError("Existing table is not owned by this Monitor contract")
            existing = DeltaTable.forName(spark_session, name).toDF()
            expected_types = {
                field.name: field.dataType for field in frame.schema.fields
            }
            if {
                field.name: field.dataType for field in existing.schema.fields
            } != expected_types:
                raise ValueError("Existing table schema differs; select a new prefix")
            conflict = (
                existing.alias("old")
                .join(frame.alias("new"), "observation_id")
                .filter(
                    ~F.col("old.record_sha256").eqNullSafe(F.col("new.record_sha256"))
                )
            )
            if conflict.limit(1).count():
                raise ValueError(
                    "Immutable observation changed; no overwrite permitted"
                )
            changed_source = (
                existing.alias("old")
                .join(frame.alias("new"), "source_path")
                .filter(
                    ~F.col("old.source_sha256").eqNullSafe(F.col("new.source_sha256"))
                    & ~F.col("old.coverage_status").isin(
                        "invalid", "unfinished", "missing", "legacy_unverified"
                    )
                )
            )
            if changed_source.limit(1).count():
                raise ValueError("Committed source changed; no new version permitted")
        prepared[dataset] = (name, frame, exists)
    if not write:
        print(
            "PREVIEW ONLY: no Delta tables written. Set WRITE_TABLES=True to persist."
        )
        return {dataset: len(tables[dataset]) for dataset in datasets}
    for dataset, (name, frame, exists) in prepared.items():
        if not exists:
            columns = ", ".join(
                f"{column} {kind}"
                for column, kind in {**COMMON, **SCHEMAS[dataset]}.items()
            )
            spark_session.sql(
                f"CREATE TABLE {name} ({columns}) USING DELTA "
                f"TBLPROPERTIES ('monitor.contract'='{SCHEMA_VERSION}', "
                f"'monitor.dataset'='{dataset}')"
            )
        if tables[dataset]:
            DeltaTable.forName(spark_session, name).alias("old").merge(
                frame.alias("new"), "old.observation_id = new.observation_id"
            ).whenNotMatchedInsertAll().execute()
    print("Published immutable observations; no cross-table transaction is promised.")
    return {dataset: len(tables[dataset]) for dataset in datasets}


def read_curated(spark_session, prefix, dataset):
    name = table_name(prefix, dataset)
    if not spark_session.catalog.tableExists(name):
        raise ValueError(
            f"Missing {name}; run its transformation with WRITE_TABLES=True"
        )
    properties = {
        entry["key"]: entry["value"]
        for entry in spark_session.sql(f"SHOW TBLPROPERTIES {name}").collect()
    }
    if (
        properties.get("monitor.contract") != str(SCHEMA_VERSION)
        or properties.get("monitor.dataset") != dataset
    ):
        raise ValueError("Selected table does not match the Monitor contract")
    return spark_session.table(name)


def latest_frame(frame, keys):
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    order = Window.partitionBy(*keys).orderBy(
        F.col("observed_at_utc").desc_nulls_last(), F.col("source_path").desc()
    )
    return (
        frame.withColumn("_rank", F.row_number().over(order))
        .filter(F.col("_rank") == 1)
        .drop("_rank")
    )


def plot_counts(frame, category, title, *, limit=20):
    """Collect only a bounded aggregate, never arbitrary raw principal/job rows."""
    import matplotlib.pyplot as plt
    from pyspark.sql import functions as F

    values = (
        frame.groupBy(category)
        .count()
        .orderBy(F.desc("count"), F.asc(category))
        .limit(limit)
        .toPandas()
    )
    if values.empty:
        print(title + ": no matching observations; inspect the coverage tables.")
        return
    values[category] = values[category].fillna("unknown")
    axis = values.plot.bar(x=category, y="count", legend=False, title=title)
    axis.set_ylabel("Observations")
    plt.tight_layout()
    plt.show()


def preview_inventory(spark_session, display_frame, tables):
    display_frame(
        to_frame(spark_session, "collection_health", tables["collection_health"])
        .groupBy("module", "coverage_status")
        .count()
        .orderBy("module", "coverage_status")
    )
    display_frame(
        to_frame(spark_session, "inventory", tables["inventory"])
        .groupBy("inventory_source", "item_type", "coverage_status")
        .count()
    )


def preview_permissions(spark_session, display_frame, tables, mode):
    selected = selected_permission_cycle(tables, mode)
    if selected is None:
        print("No selected-mode cycle. Missing evidence is not a zero-grant success.")
        return
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
                "selected_items",
            )
        }
    )
    resources = [
        entry
        for entry in tables["permission_resources"]
        if entry["mode"] == mode and entry["cycle_id"] == selected["cycle_id"]
    ]
    display_frame(
        to_frame(spark_session, "permission_resources", resources)
        .groupBy("observation_unit", "coverage_status")
        .count()
    )


def preview_jobs(spark_session, display_frame, tables):
    current_jobs = latest(
        tables["job_observations"], ["workspace_id", "item_id", "job_id"]
    )
    display_frame(
        to_frame(spark_session, "job_resources", tables["job_resources"])
        .groupBy("coverage_status")
        .count()
    )
    display_frame(
        to_frame(spark_session, "job_observations", current_jobs)
        .groupBy("item_type", "status")
        .count()
    )


def preview_lineage(spark_session, display_frame, tables):
    for dataset, keys in (
        ("lineage_resources", ["evidence_type", "coverage_status"]),
        ("lineage_edges", ["evidence_type", "direction", "related_type"]),
        ("lineage_diagnostics", ["reason"]),
    ):
        display_frame(
            to_frame(spark_session, dataset, tables[dataset]).groupBy(*keys).count()
        )
