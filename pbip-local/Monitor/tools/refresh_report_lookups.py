"""Refresh only the derived report lookups; preview unless --publish is given."""

import argparse
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq
from deltalake import DeltaTable, write_deltalake
from deltalake.exceptions import TableNotFoundError
from estate_model import (
    BUILD_TYPES,
    DERIVED_SCHEMAS,
    LAKEHOUSE,
    PREFIX,
    PROJECT,
    WORKSPACE,
    build_dimensions,
    frame,
)
from profile_lakehouse import credential


def source_uri(table):
    return f"abfss://{WORKSPACE}@onelake.dfs.fabric.microsoft.com/{LAKEHOUSE}/Tables/dbo/{table}"


def assert_owned(table, name):
    if table.metadata().description != ownership(name):
        raise ValueError(f"Refusing to overwrite an unowned report table: {name}")


def ownership(name):
    return json.dumps(
        {"contract": "fabric-estate-report", "version": 1, "dataset": name},
        sort_keys=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    profile = json.loads((PROJECT / "analysis/data-profile.json").read_text())
    sources = {}
    for dataset, info in profile["datasets"].items():
        path = args.cache_dir / f"{dataset}.parquet"
        if hashlib.sha256(path.read_bytes()).hexdigest() != info["cache_sha256"]:
            raise ValueError(
                "The profiled row cache changed; reprofile instead of mixing inputs"
            )
        sources[dataset] = pq.read_table(path)
    derived = build_dimensions(sources, profile)
    print(
        "Validated derived table row counts:",
        {name: table.num_rows for name, table in derived.items()},
    )
    if not args.publish:
        print(
            "PREVIEW ONLY: no Lakehouse writes. Use --publish only for the approved report lookups."
        )
        return
    with credential() as identity:

        def options():
            return {
                "bearer_token": identity.get_token(
                    "https://storage.azure.com/.default"
                ).token,
                "use_fabric_endpoint": "true",
                "azure_disable_tagging": "true",
            }

        def verify_versions():
            for dataset, info in profile["datasets"].items():
                current = DeltaTable(
                    source_uri("monitor_" + dataset), storage_options=options()
                )
                if current.version() != info["delta_version"]:
                    raise ValueError(
                        "Source versions changed; reprofile with collectors/writers idle"
                    )
                if current.metadata().configuration.get("monitor.contract") != "1":
                    raise ValueError(
                        "Source table ownership is not the expected Monitor contract"
                    )

        verify_versions()
        # Check all collisions before writing anything, including the readiness gate.
        for name in DERIVED_SCHEMAS:
            try:
                existing = DeltaTable(
                    source_uri(PREFIX + name), storage_options=options()
                )
            except TableNotFoundError:
                continue
            assert_owned(existing, name)

        def publish(name, table):
            if name not in DERIVED_SCHEMAS:
                raise ValueError(
                    "Only explicitly registered report lookups may be written"
                )
            uri = source_uri(PREFIX + name)
            try:
                existing = DeltaTable(uri, storage_options=options())
            except TableNotFoundError:
                mode = "error"
            else:
                assert_owned(existing, name)
                mode = "overwrite"
            write_deltalake(
                uri,
                table,
                mode=mode,
                storage_options=options(),
                description=ownership(name),
            )
            result = DeltaTable(uri, storage_options=options())
            assert_owned(result, name)
            if result.count() != table.num_rows:
                raise ValueError(
                    "Published lookup row count differs from the validated build"
                )
            print(f"Published {PREFIX + name}: {table.num_rows} rows", flush=True)

        building = derived["build"].to_pylist()
        building[0]["state"] = "building"
        publish("build", frame(building, BUILD_TYPES))
        for name, table in derived.items():
            if name not in ("build", "context"):
                publish(name, table)
        publish("context", derived["context"])
        verify_versions()
        publish("build", derived["build"])
    print(
        "All lookups committed and verified; the 48 curated source tables were not changed."
    )


if __name__ == "__main__":
    main()
