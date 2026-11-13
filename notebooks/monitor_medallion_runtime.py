"""Fabric-only bounded readers and owned snapshot publication for medallion notebooks."""

import base64
import hashlib
import json
import re
from pathlib import Path

from notebooks.monitor_analytics import SCHEMA_VERSION
from notebooks.monitor_medallion import (
    BRONZE_DATASETS,
    GOLD_SCHEMAS,
    MEDALLION_VERSION,
    SILVER_SCHEMAS,
    build_gold,
    build_silver,
    md_key,
    md_uuid,
    md_validate,
)


def md_resolve_tenant(tenant_id="", *, auto_discover=True):
    if type(auto_discover) is not bool:
        raise ValueError("AUTO_DISCOVER_TENANT must be boolean")
    if tenant_id not in ("", None):
        tenant = md_uuid(tenant_id)
        if tenant is None:
            raise ValueError("Manual TENANT_ID must be a tenant UUID")
        return tenant
    if not auto_discover:
        raise ValueError("Set TENANT_ID when AUTO_DISCOVER_TENANT=False")
    try:
        import notebookutils

        # Inspect only a token acquired directly from Fabric, never a supplied token.
        token = notebookutils.credentials.getToken("pbi")
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Unsupported token format")
        payload = base64.b64decode(
            parts[1] + "=" * (-len(parts[1]) % 4), altchars=b"-_", validate=True
        )
        tenant = md_uuid(json.loads(payload).get("tid"))
        if tenant is None:
            raise ValueError("Missing tenant claim")
        return tenant
    except Exception:  # noqa: BLE001 - Suppress token-bearing SDK error details.
        raise ValueError(
            "Automatic tenant discovery unavailable. Set AUTO_DISCOVER_TENANT=False "
            "and TENANT_ID to the tenant UUID that owns the collected evidence."
        ) from None


def md_name(lakehouse, schema, dataset):
    if any(
        not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value)
        for value in (lakehouse, schema, dataset)
    ):
        raise ValueError("Lakehouse/schema/table names must be simple identifiers")
    return ".".join(f"`{value}`" for value in (lakehouse, schema, dataset))


def md_properties(spark_session, name):
    return {
        row["key"]: row["value"]
        for row in spark_session.sql(f"SHOW TBLPROPERTIES {name}").collect()
    }


def md_version(spark_session, name):
    return int(spark_session.sql(f"DESCRIBE HISTORY {name} LIMIT 1").first()["version"])


def md_frame(spark_session, rows, schema):
    from pyspark.sql import types as T

    types = {
        "string": T.StringType,
        "long": T.LongType,
        "double": T.DoubleType,
        "boolean": T.BooleanType,
        "timestamp": T.TimestampType,
    }
    struct = T.StructType(
        [T.StructField(name, types[kind](), True) for name, kind in schema.items()]
    )
    return spark_session.createDataFrame(rows, schema=struct)


class MedallionReader:
    def __init__(
        self, spark_session, lakehouse, *, max_source_rows=250000, max_total_rows=500000
    ):
        md_name(lakehouse, "dbo", "monitor_inventory")
        if any(
            type(value) is not int or value <= 0
            for value in (max_source_rows, max_total_rows)
        ):
            raise ValueError("Positive integer evidence row limits required")
        self.spark, self.lakehouse = spark_session, lakehouse
        self.max_source_rows, self.max_total_rows = max_source_rows, max_total_rows
        self.total_rows, self.versions, self.missing, self.raw_hashes = 0, {}, set(), {}
        self.raw_root = None
        self.raw_scope_present = False

    def collect(self, frame):
        rows = frame.limit(self.max_source_rows + 1).collect()
        self.total_rows += len(rows)
        if len(rows) > self.max_source_rows or self.total_rows > self.max_total_rows:
            raise ValueError(
                "Evidence row limit exceeded; no truncated build is publishable"
            )
        return [row.asDict(recursive=True) for row in rows]

    def read(self, schema, dataset, *, bronze=False, layer=None):
        name = md_name(self.lakehouse, schema, dataset)
        if not self.spark.catalog.tableExists(name):
            self.missing.add(name)
            return None
        properties = md_properties(self.spark, name)
        if bronze:
            if properties.get("monitor.contract") != str(
                SCHEMA_VERSION
            ) or properties.get("monitor.dataset") != dataset.removeprefix("monitor_"):
                raise ValueError(
                    "Bronze input does not match the Monitor ownership contract"
                )
        elif (
            properties.get("monitor.medallion.layer") != layer
            or properties.get("monitor.medallion.dataset") != dataset
            or properties.get("monitor.medallion.version") != MEDALLION_VERSION
        ):
            raise ValueError(
                "Silver input does not match the medallion ownership contract"
            )
        version = md_version(self.spark, name)
        self.versions[name] = version
        return self.collect(
            self.spark.sql(f"SELECT * FROM {name} VERSION AS OF {version}")
        )

    def activity_documents(
        self,
        raw_root,
        *,
        max_files=10000,
        max_bytes=128 * 1024 * 1024,
        max_file_bytes=8 * 1024 * 1024,
    ):
        if any(
            type(value) is not int or value <= 0
            for value in (max_files, max_bytes, max_file_bytes)
        ):
            raise ValueError("Positive integer raw evidence limits required")
        self.raw_root = Path(raw_root) / "activity"
        self.raw_scope_present = self.raw_root.exists()
        if not self.raw_root.exists():
            return [], False
        paths = sorted(path for path in self.raw_root.rglob("*") if path.is_file())
        if len(paths) > max_files:
            raise ValueError("Raw activity file limit exceeded")
        documents, total = [], 0
        for path in paths:
            if path.is_symlink() or not path.resolve().is_relative_to(
                self.raw_root.resolve()
            ):
                raise ValueError("Unexpected raw evidence symlink")
            relative = path.relative_to(self.raw_root).as_posix()
            if not re.fullmatch(r"\d{4}/\d{2}/\d{2}/\d{8}_\d+\.json", relative):
                raise ValueError("Unexpected file in raw activity scope")
            with path.open("rb") as stream:
                content = stream.read(max_file_bytes + 1)
            total += len(content)
            if len(content) > max_file_bytes or total > max_bytes:
                raise ValueError("Raw activity byte limit exceeded")
            payload = json.loads(content)
            if not isinstance(payload, (list, dict)):
                raise TypeError("Malformed raw activity payload type")
            rows = (
                payload
                if isinstance(payload, list)
                else payload.get("activityEventEntities", payload.get("value"))
            )
            if not isinstance(rows, list) or any(
                not isinstance(row, dict) for row in rows
            ):
                raise ValueError("Malformed raw activity document")
            self.total_rows += len(rows)
            if (
                len(rows) > self.max_source_rows
                or self.total_rows > self.max_total_rows
            ):
                raise ValueError("Raw evidence row limit exceeded")
            signature = hashlib.sha256(content).hexdigest()
            self.raw_hashes[path] = signature
            documents.append(
                {"path": "activity/" + relative, "sha256": signature, "records": rows}
            )
        return documents, True

    def signature(self):
        return md_key(
            self.versions,
            sorted(self.missing),
            {str(path): value for path, value in self.raw_hashes.items()},
            self.raw_scope_present,
        )

    def unchanged(self):
        for name, version in self.versions.items():
            if md_version(self.spark, name) != version:
                raise ValueError("Input Delta version changed during medallion build")
        if any(self.spark.catalog.tableExists(name) for name in self.missing):
            raise ValueError("A missing input appeared during medallion build")
        if self.raw_root is not None:
            if self.raw_root.exists() != self.raw_scope_present:
                raise ValueError("Raw activity scope availability changed during build")
            paths = {path for path in self.raw_root.rglob("*") if path.is_file()}
            if paths != set(self.raw_hashes):
                raise ValueError(
                    "Raw activity file scope changed during medallion build"
                )
            for path, expected in self.raw_hashes.items():
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                if digest.hexdigest() != expected:
                    raise ValueError(
                        "Raw activity content changed during medallion build"
                    )


def md_publish(spark_session, tables, schemas, *, lakehouse, layer, write, unchanged):
    if type(write) is not bool or layer not in {"silver", "gold"}:
        raise ValueError(
            "Explicit preview/publication setting and medallion layer required"
        )
    md_validate(tables, schemas)
    md_name(lakehouse, layer, "build")
    spark_session.conf.set("spark.sql.session.timeZone", "UTC")
    # Validate the user-created namespace, without creating schemas or changing grants.
    spark_session.sql(f"SHOW TABLES IN `{lakehouse}`.`{layer}`").collect()
    prepared = {}
    for dataset, schema in schemas.items():
        name = md_name(lakehouse, layer, dataset)
        frame = md_frame(spark_session, tables[dataset], schema)
        if spark_session.catalog.tableExists(name):
            properties = md_properties(spark_session, name)
            expected = {
                "monitor.medallion.layer": layer,
                "monitor.medallion.dataset": dataset,
                "monitor.medallion.version": MEDALLION_VERSION,
            }
            if any(properties.get(key) != value for key, value in expected.items()):
                raise ValueError("Refusing to overwrite an unowned medallion table")
            if spark_session.table(name).schema != frame.schema:
                raise ValueError(
                    "Medallion schema changed; explicit migration required"
                )
        prepared[dataset] = (name, frame)
    unchanged()
    if not write:
        print("PREVIEW ONLY: no schemas, tables, permissions or Fabric items changed.")
        return

    def save(dataset, frame):
        name = prepared[dataset][0]
        frame.write.format("delta").mode("overwrite").saveAsTable(name)
        spark_session.sql(
            f"ALTER TABLE {name} SET TBLPROPERTIES ("
            f"'monitor.medallion.layer'='{layer}', "
            f"'monitor.medallion.dataset'='{dataset}', "
            f"'monitor.medallion.version'='{MEDALLION_VERSION}')"
        )
        persisted = spark_session.table(name).select(*schemas[dataset])
        expected = frame.select(*schemas[dataset])
        if (
            persisted.exceptAll(expected).limit(1).count()
            or expected.exceptAll(persisted).limit(1).count()
        ):
            raise ValueError("Persisted medallion snapshot differs from prepared rows")

    save(
        "build",
        md_frame(
            spark_session,
            [dict(tables["build"][0], state="building")],
            schemas["build"],
        ),
    )
    for dataset, (_, frame) in prepared.items():
        if dataset != "build":
            save(dataset, frame)
    unchanged()
    save("build", prepared["build"][1])
    print(
        f"Published owned {layer} snapshots. No cross-table transaction or writer lock is provided."
    )


def run_silver(
    spark_session,
    display_frame,
    *,
    lakehouse,
    tenant_id="",
    raw_root,
    auto_discover_tenant=True,
    write=False,
    include_sensitive=False,
    max_source_rows=250000,
    max_total_rows=500000,
    max_raw_files=10000,
    max_raw_bytes=128 * 1024 * 1024,
    max_file_bytes=8 * 1024 * 1024,
):
    tenant_id = md_resolve_tenant(tenant_id, auto_discover=auto_discover_tenant)
    spark_session.conf.set("spark.sql.session.timeZone", "UTC")
    reader = MedallionReader(
        spark_session,
        lakehouse,
        max_source_rows=max_source_rows,
        max_total_rows=max_total_rows,
    )
    sources, presence, versions = {}, set(), {}
    for dataset in BRONZE_DATASETS:
        rows = reader.read("dbo", "monitor_" + dataset, bronze=True)
        sources[dataset] = rows or []
        if rows is not None:
            presence.add(dataset)
            versions[dataset] = reader.versions[
                md_name(lakehouse, "dbo", "monitor_" + dataset)
            ]
    documents, present = reader.activity_documents(
        raw_root,
        max_files=max_raw_files,
        max_bytes=max_raw_bytes,
        max_file_bytes=max_file_bytes,
    )
    tables = build_silver(
        sources,
        documents,
        tenant_id=tenant_id,
        source_signature=reader.signature(),
        source_versions=versions,
        source_presence=presence,
        activity_scope_present=present,
        include_sensitive=include_sensitive,
    )
    md_publish(
        spark_session,
        tables,
        SILVER_SCHEMAS,
        lakehouse=lakehouse,
        layer="silver",
        write=write,
        unchanged=reader.unchanged,
    )
    print({dataset: len(rows) for dataset, rows in tables.items()})
    display_frame(
        md_frame(
            spark_session,
            tables["evidence_coverage"],
            SILVER_SCHEMAS["evidence_coverage"],
        ).select("dataset", "availability", "row_count", "interpretation")
    )


def run_gold(
    spark_session,
    display_frame,
    *,
    lakehouse,
    write=False,
    event_id="",
    max_preview_rows=50,
    max_source_rows=250000,
    max_total_rows=1000000,
    max_trace_depth=32,
):
    if (
        not isinstance(event_id, str)
        or type(max_preview_rows) is not int
        or not 1 <= max_preview_rows <= 1000
    ):
        raise ValueError("Explicit event ID text and 1-1000 preview rows required")
    spark_session.conf.set("spark.sql.session.timeZone", "UTC")
    reader = MedallionReader(
        spark_session,
        lakehouse,
        max_source_rows=max_source_rows,
        max_total_rows=max_total_rows,
    )
    silver = {}
    # Pin the gate before data, then recheck it with all other source versions.
    for dataset in ("build", *[name for name in SILVER_SCHEMAS if name != "build"]):
        rows = reader.read("silver", dataset, layer="silver")
        if rows is None:
            raise ValueError("Publish notebook 24 to Silver before running Gold")
        silver[dataset] = rows
        if dataset == "build" and (len(rows) != 1 or rows[0]["state"] != "ready"):
            raise ValueError("Silver build is incomplete; Gold cannot consume it")
    tables = build_gold(
        silver, source_signature=reader.signature(), max_trace_depth=max_trace_depth
    )
    md_publish(
        spark_session,
        tables,
        GOLD_SCHEMAS,
        lakehouse=lakehouse,
        layer="gold",
        write=write,
        unchanged=reader.unchanged,
    )
    print({dataset: len(rows) for dataset, rows in tables.items()})
    cases = md_frame(spark_session, tables["event_case"], GOLD_SCHEMAS["event_case"])
    display_frame(cases.groupBy("operation", "correlation_state").count())
    if event_id:
        selected = [row for row in tables["event_case"] if row["event_id"] == event_id]
        keys = {row["event_key"] for row in selected}
        trace = [row for row in tables["event_trace_edge"] if row["event_key"] in keys]
        display_frame(
            md_frame(
                spark_session, selected[:max_preview_rows], GOLD_SCHEMAS["event_case"]
            )
        )
        display_frame(
            md_frame(
                spark_session,
                trace[:max_preview_rows],
                GOLD_SCHEMAS["event_trace_edge"],
            )
        )
        print(
            "Explicit event preview: rows are bounded; keys/names/paths may be sensitive. Clear outputs before sharing."
        )
