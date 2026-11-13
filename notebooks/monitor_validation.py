"""Restart-safe rerun checks without changing raw evidence or curated tables."""

import json
import re
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path

from notebooks.monitor_analytics import (
    COMMON,
    CORE_DATASETS,
    CORE_SOURCE_PREFIXES,
    ESTATE_DATASETS,
    ESTATE_PREFIXES,
    EVENTSTREAM_PREFIXES,
    LAKEHOUSE_FILES,
    MODULE_DATASETS,
    MODULE_PREFIXES,
    PERMISSIONS,
    PIPELINE_ACTIVITY_PREFIXES,
    PIPELINE_ACTIVITY_SCHEMAS,
    SCHEMA_VERSION,
    SCHEMAS,
    SHORTCUT_PREFIXES,
    canonical,
    load_documents,
    sha256,
    utc,
    uuid,
)
from notebooks.monitor_fabric_runtime import read_curated, table_name, to_frame

VALIDATION_BASELINE_VERSION = 1
MAX_BASELINE_BYTES = 128 * 1024


def validation_baseline_path(name, raw_root):
    if not isinstance(name, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.json", name
    ):
        raise ValueError("Use a short JSON basename, not a path")
    allowed = Path(LAKEHOUSE_FILES)
    folder = allowed / "monitor_validation"
    path = folder / name
    if (
        folder.is_symlink()
        or path.is_symlink()
        or folder.resolve().parent != allowed.resolve()
        or path.resolve().parent != folder.resolve()
        or path.resolve().is_relative_to(Path(raw_root).resolve())
    ):
        raise ValueError("Baseline must stay outside raw evidence, without symlinks")
    return path


def validation_raw_digest(documents):
    entries = sorted((entry["path"], entry["sha256"]) for entry in documents)
    return {"files": len(entries), "sha256": sha256(canonical(entries).encode())}


def validation_freshness(observed, now, stale_after_hours):
    if (
        isinstance(stale_after_hours, bool)
        or not isinstance(stale_after_hours, (int, float))
        or not isfinite(stale_after_hours)
        or stale_after_hours <= 0
    ):
        raise ValueError("Choose a finite, positive staleness threshold")
    if observed is None:
        return "UNKNOWN"
    try:
        age = (
            datetime.fromisoformat(utc(now).replace("Z", "+00:00"))
            - datetime.fromisoformat(utc(observed).replace("Z", "+00:00"))
        ).total_seconds()
    except (ValueError, TypeError):
        return "INVALID_TIMESTAMP"
    if age < 0:
        return "CLOCK_AHEAD"
    return "STALE" if age > stale_after_hours * 3600 else "WITHIN_THRESHOLD"


def validation_save_baseline(path, snapshot):
    content = (json.dumps(snapshot, sort_keys=True, indent=2) + "\n").encode()
    if len(content) > MAX_BASELINE_BYTES:
        raise ValueError("Baseline exceeds metadata safety limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        raise ValueError(
            "Baseline already exists; choose compare or a new BASELINE_NAME"
        ) from None


def validation_load_baseline(path):
    try:
        with path.open("rb") as stream:
            content = stream.read(MAX_BASELINE_BYTES + 1)
    except FileNotFoundError:
        raise ValueError(
            "No baseline found; capture first or check BASELINE_NAME"
        ) from None
    if len(content) > MAX_BASELINE_BYTES:
        raise ValueError("Baseline exceeds metadata safety limit")
    try:
        snapshot = json.loads(content)
        if (
            not isinstance(snapshot, dict)
            or type(snapshot["baseline_version"]) is not int
            or snapshot["baseline_version"] != VALIDATION_BASELINE_VERSION
            or type(snapshot["contract_version"]) is not int
            or snapshot["contract_version"] != SCHEMA_VERSION
            or snapshot["permission_mode"] not in {"Scoped", "Tenant"}
            or not isinstance(snapshot["tables"], dict)
            or not snapshot["tables"]
            or not set(snapshot["tables"]).issubset(SCHEMAS)
            or type(snapshot.get("include_shortcuts", False)) is not bool
            or type(snapshot.get("include_eventstream_topology", False)) is not bool
        ):
            raise ValueError
        table_name(snapshot["prefix"], "inventory")
        utc(snapshot["captured_at_utc"])
        if not isinstance(snapshot["raw_root"], str):
            raise TypeError
        raw = snapshot["raw"]
        if type(raw["files"]) is not int or raw["files"] <= 0:
            raise ValueError
        if not re.fullmatch(r"[a-f0-9]{64}", raw["sha256"]):
            raise ValueError
        for entry in snapshot["tables"].values():
            uuid(entry["table_id"])
            for key in ("version", "rows", "unique_ids", "invalid_metadata_rows"):
                if type(entry[key]) is not int or entry[key] < 0:
                    raise ValueError
            if entry["rows"] != entry["unique_ids"] or entry["invalid_metadata_rows"]:
                raise ValueError
    except (KeyError, TypeError, ValueError, RecursionError):
        raise ValueError(
            "Invalid validation baseline; do not use it for acceptance"
        ) from None
    return snapshot


def validation_table_identity(spark_session, name):
    detail = spark_session.sql(f"DESCRIBE DETAIL {name}").first()
    if detail["format"] != "delta":
        raise ValueError("Validation requires managed Delta tables")
    version = spark_session.sql(f"DESCRIBE HISTORY {name} LIMIT 1").first()["version"]
    if type(version) is not int or version < 0:
        raise ValueError("Invalid Delta version")
    return uuid(detail["id"]), version


def validation_version_frame(spark_session, prefix, dataset, version):
    if type(version) is not int or version < 0:
        raise ValueError("Invalid baseline Delta version")
    name = table_name(prefix, dataset)
    return spark_session.sql(f"SELECT * FROM {name} VERSION AS OF {version}")


def validation_table_metrics(frame):
    from pyspark.sql import functions as F

    invalid = ~F.col("schema_version").eqNullSafe(F.lit(SCHEMA_VERSION))
    for key in ("source_path", "module", "coverage_status"):
        invalid = invalid | F.col(key).isNull() | (F.trim(F.col(key)) == "")
    for key in ("observation_id", "record_sha256"):
        invalid = invalid | F.col(key).isNull() | ~F.col(key).rlike(r"^[a-f0-9]{64}$")
    source = F.col("source_sha256")
    missing_marker = (
        (F.col("coverage_status") == "missing")
        & F.col("source_path").endswith("/_missing")
        & (source == "")
    )
    invalid = (
        invalid | source.isNull() | (~source.rlike(r"^[a-f0-9]{64}$") & ~missing_marker)
    )
    timestamp = F.col("observed_at_utc")
    invalid = invalid | (
        timestamp.isNotNull()
        & ~timestamp.rlike(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
    )
    result = frame.agg(
        F.count("*").alias("rows"),
        F.countDistinct("observation_id").alias("unique_ids"),
        F.sum(F.when(invalid, 1).otherwise(0)).alias("invalid_metadata_rows"),
    ).first()
    return {
        key: int(result[key] or 0)
        for key in ("rows", "unique_ids", "invalid_metadata_rows")
    }


def validation_compare(spark_session, current, frames, baseline):
    if baseline.get("include_eventstream_topology", False) != current.get(
        "include_eventstream_topology", False
    ):
        return [
            {
                "check": "eventstream_evidence_scope",
                "status": "NOT_COMPARABLE",
                "detail": "Eventstream evidence scope changed; capture a new baseline",
            }
        ]
    if baseline.get("include_shortcuts", False) != current.get(
        "include_shortcuts", False
    ):
        return [
            {
                "check": "shortcut_evidence_scope",
                "status": "NOT_COMPARABLE",
                "detail": "Shortcut evidence scope changed; capture a new baseline",
            }
        ]
    if set(current["tables"]) != set(baseline["tables"]):
        return [
            {
                "check": "selected_tables",
                "status": "NOT_COMPARABLE",
                "detail": "Selected validation tables changed; capture a new baseline",
            }
        ]
    for key in ("prefix", "raw_root", "permission_mode", "raw"):
        if baseline[key] != current[key]:
            return [
                {
                    "check": "unchanged_input_and_scope",
                    "status": "NOT_COMPARABLE",
                    "detail": "Raw evidence or settings changed; start a new experiment",
                }
            ]
    checks = [
        {
            "check": "unchanged_input_and_scope",
            "status": "PASS",
            "detail": "Same supported raw-file hashes and settings",
        }
    ]
    for dataset, entry in current["tables"].items():
        previous = baseline["tables"][dataset]
        if entry["table_id"] != previous["table_id"]:
            status, detail = "FAIL", "Table replaced or different Lakehouse selected"
        elif entry["rows"] != previous["rows"]:
            status, detail = "FAIL", "Row count changed with unchanged inputs"
        else:
            try:
                old = validation_version_frame(
                    spark_session, current["prefix"], dataset, previous["version"]
                ).select(*COMMON, *SCHEMAS[dataset])
                changed = (
                    frames[dataset].exceptAll(old).limit(1).count()
                    or old.exceptAll(frames[dataset]).limit(1).count()
                )
                status = "FAIL" if changed else "PASS"
                detail = "Table contents changed" if changed else "Exact rows unchanged"
            except Exception:  # noqa: BLE001 - Failed Spark actions cannot prove stability; do not expose backend payloads.
                status = "UNVERIFIED"
                detail = "Cannot compare Delta data; check retained versions and runtime access"
        checks.append({"check": dataset, "status": status, "detail": detail})
    return checks


def validation_assert_stable(spark_session, snapshot, read_raw):
    if validation_raw_digest(read_raw()) != snapshot["raw"]:
        raise ValueError("Raw evidence changed during validation; repeat when idle")
    for dataset, entry in snapshot["tables"].items():
        name = table_name(snapshot["prefix"], dataset)
        if validation_table_identity(spark_session, name) != (
            entry["table_id"],
            entry["version"],
        ):
            raise ValueError("A table changed during validation; repeat when idle")


def validation_reports(spark_session, display_frame, frames, mode, threshold, now):
    from pyspark.sql import functions as F

    health = frames["collection_health"].filter(
        ~F.col("module").isin(*PERMISSIONS) | (F.col("mode") == mode)
    )
    print("Retained coverage, selected permission mode only; at most 200 groups:")
    display_frame(
        health.groupBy("module", "mode", "coverage_status")
        .count()
        .orderBy("module", "mode", "coverage_status")
        .limit(200)
    )
    grouped = health.groupBy("module", "mode").agg(
        F.count("*").alias("observations"),
        F.max("observed_at_utc").alias("latest_known_observation_utc"),
        F.sum(F.when(F.col("observed_at_utc").isNull(), 1).otherwise(0)).alias(
            "unknown_timestamp_observations"
        ),
    )
    freshness = []
    for row in grouped.orderBy("module", "mode").limit(200).collect():
        entry = row.asDict()
        entry["known_observation_freshness"] = validation_freshness(
            entry["latest_known_observation_utc"], now, threshold
        )
        entry["newest_attempt_certainty"] = (
            "UNKNOWN_ATTEMPT_TIME"
            if entry["unknown_timestamp_observations"]
            else "KNOWN_RETAINED_TIMES"
        )
        freshness.append(entry)
    display_frame(
        spark_session.createDataFrame(
            freshness,
            "module string, mode string, observations long, "
            "latest_known_observation_utc string, unknown_timestamp_observations long, "
            "known_observation_freshness string, newest_attempt_certainty string",
        )
    )
    print(
        "A fresh known observation does not resolve unknown-time attempts. "
        "Missing modules are not proof of successful empty collection."
    )
    for dataset, keys in (
        (
            "permission_cycles",
            [
                "mode",
                "coverage_status",
                "chain_valid",
                "cycle_finished",
                "cycle_healthy",
            ],
        ),
        ("permission_resources", ["mode", "observation_unit", "coverage_status"]),
        ("job_resources", ["coverage_status"]),
        ("lineage_resources", ["evidence_type", "coverage_status"]),
        ("lineage_diagnostics", ["reason"]),
    ):
        frame = frames[dataset]
        if dataset.startswith("permission_"):
            frame = frame.filter(F.col("mode") == mode)
        print(f"{dataset}: retained coverage, not a current-state union")
        display_frame(frame.groupBy(*keys).count().orderBy(*keys).limit(200))
    if "estate_coverage" in frames:
        print(
            "Extended estate coverage: missing schema/sources are not successful zero."
        )
        display_frame(
            frames["estate_coverage"]
            .groupBy("analysis", "coverage_status", "issue")
            .count()
            .orderBy("analysis", "coverage_status")
            .limit(200)
        )
    if "pipeline_activity_resources" in frames:
        print(
            "Pipeline activity coverage: absent queries are not zero activity metrics."
        )
        display_frame(
            frames["pipeline_activity_resources"]
            .groupBy("mode", "observation_unit", "coverage_status")
            .count()
            .limit(200)
        )


def validate_rerun(
    spark_session,
    display_frame,
    *,
    raw_root,
    prefix,
    permission_mode,
    action,
    baseline_name,
    stale_after_hours=24,
    max_files=50000,
    max_bytes=128 * 1024 * 1024,
    max_file_bytes=8 * 1024 * 1024,
    include_estate_tables=False,
    include_module_tables=False,
    include_pipeline_activity_tables=False,
    include_shortcuts=False,
    include_eventstream_topology=False,
):
    if permission_mode not in {"Scoped", "Tenant"} or action not in {
        "capture",
        "compare",
    }:
        raise ValueError("Choose Scoped/Tenant and capture/compare explicitly")
    if (
        type(include_estate_tables) is not bool
        or type(include_module_tables) is not bool
        or type(include_pipeline_activity_tables) is not bool
        or type(include_shortcuts) is not bool
        or type(include_eventstream_topology) is not bool
    ):
        raise TypeError("Choose boolean table-scope inclusion flags")
    now = datetime.now(timezone.utc).isoformat()
    validation_freshness(None, now, stale_after_hours)
    path = validation_baseline_path(baseline_name, raw_root)
    if action == "capture" and path.exists():
        raise ValueError(
            "Baseline already exists; choose compare or a new BASELINE_NAME"
        )
    baseline = validation_load_baseline(path) if action == "compare" else None
    spark_session.conf.set("spark.sql.session.timeZone", "UTC")

    source_prefixes = (
        CORE_SOURCE_PREFIXES | ESTATE_PREFIXES | MODULE_PREFIXES
        if include_module_tables
        else CORE_SOURCE_PREFIXES | ESTATE_PREFIXES
        if include_estate_tables
        else CORE_SOURCE_PREFIXES
    )
    if include_pipeline_activity_tables:
        source_prefixes = source_prefixes | PIPELINE_ACTIVITY_PREFIXES
    if include_shortcuts:
        source_prefixes = source_prefixes | SHORTCUT_PREFIXES
    if include_eventstream_topology:
        source_prefixes = source_prefixes | EVENTSTREAM_PREFIXES

    def read_raw():
        return load_documents(
            raw_root,
            max_files=max_files,
            max_bytes=max_bytes,
            max_file_bytes=max_file_bytes,
            source_prefixes=source_prefixes,
        )

    snapshot = {
        "baseline_version": VALIDATION_BASELINE_VERSION,
        "contract_version": SCHEMA_VERSION,
        "captured_at_utc": utc(now),
        "prefix": prefix,
        "raw_root": Path(raw_root)
        .resolve()
        .relative_to(Path(LAKEHOUSE_FILES).resolve())
        .as_posix(),
        "permission_mode": permission_mode,
        "include_shortcuts": include_shortcuts,
        "include_eventstream_topology": include_eventstream_topology,
        "raw": validation_raw_digest(read_raw()),
        "tables": {},
    }
    frames = {}
    datasets = (
        MODULE_DATASETS
        if include_module_tables
        else ESTATE_DATASETS
        if include_estate_tables
        else CORE_DATASETS
    )
    if include_pipeline_activity_tables:
        datasets = (*datasets, *PIPELINE_ACTIVITY_SCHEMAS)
    for dataset in datasets:
        columns = SCHEMAS[dataset]
        name = table_name(prefix, dataset)
        read_curated(spark_session, prefix, dataset)
        table_id, version = validation_table_identity(spark_session, name)
        frame = validation_version_frame(spark_session, prefix, dataset, version)
        expected = to_frame(spark_session, dataset, []).schema
        if {field.name: field.dataType for field in frame.schema.fields} != {
            field.name: field.dataType for field in expected.fields
        }:
            raise ValueError("Curated schema differs from the Monitor contract")
        frame = frame.select(*COMMON, *columns)
        frames[dataset] = frame
        snapshot["tables"][dataset] = {
            "table_id": table_id,
            "version": version,
            **validation_table_metrics(frame),
        }
    display_frame(
        spark_session.createDataFrame(
            [{"dataset": key, **entry} for key, entry in snapshot["tables"].items()],
            "dataset string, table_id string, version long, rows long, "
            "unique_ids long, invalid_metadata_rows long",
        )
    )
    validation_reports(
        spark_session, display_frame, frames, permission_mode, stale_after_hours, now
    )
    validation_assert_stable(spark_session, snapshot, read_raw)
    if any(
        entry["rows"] != entry["unique_ids"] or entry["invalid_metadata_rows"]
        for entry in snapshot["tables"].values()
    ):
        raise ValueError(
            "Duplicate/null identities or invalid metadata; investigate before acceptance"
        )
    if action == "capture":
        validation_save_baseline(path, snapshot)
        print(
            "Baseline saved outside raw evidence. Rerun the notebooks in the selected table scope, then use action='compare'."
        )
        return snapshot
    checks = validation_compare(spark_session, snapshot, frames, baseline)
    validation_assert_stable(spark_session, snapshot, read_raw)
    display_frame(
        spark_session.createDataFrame(
            checks, "check string, status string, detail string"
        )
    )
    if all(check["status"] == "PASS" for check in checks):
        print(
            "RERUN CHECK PASSED. Coverage, freshness, Power Query parity and networking require separate review."
        )
    else:
        raise ValueError("Rerun validation did not pass; inspect the check summary")
    return checks
