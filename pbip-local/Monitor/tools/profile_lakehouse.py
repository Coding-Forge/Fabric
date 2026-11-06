"""Read-only, version-pinned profiling of the Monitor Lakehouse."""

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from azure.identity import AzureCliCredential, ClientSecretCredential
from deltalake import DeltaTable, QueryBuilder

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from notebooks.monitor_analytics import COMMON, SCHEMAS

WORKSPACE = "1f681810-ec02-411f-ac4b-9b5544272273"
LAKEHOUSE = "f1d6b7d9-f02b-4a44-9828-8dd5da8d6822"
PROFILE_FIELDS = {
    "coverage_status",
    "mode",
    "module",
    "item_type",
    "status",
    "resource_outcome",
    "evidence_type",
    "direction",
    "resolution",
    "schema_coverage",
    "principal_type",
    "workspace_role",
    "analysis",
    "scope_type",
    "metric_group",
    "metric_name",
    "sku",
    "region",
    "connectivity_type",
    "connection_type",
    "provider_type",
    "group_rule",
    "connectivity_observation",
    "coverage",
    "issue",
}


def credential():
    keys = ("COMMERCIAL_TENANT_ID", "COMMERCIAL_CLIENT_ID", "COMMERCIAL_CLIENT_SECRET")
    if all(os.environ.get(key) for key in keys):
        return ClientSecretCredential(
            tenant_id=os.environ[keys[0]],
            client_id=os.environ[keys[1]],
            client_secret=os.environ[keys[2]],
            connection_timeout=15,
            read_timeout=30,
        )
    return AzureCliCredential()


def summarize(dataset, arrow, version):
    columns = arrow.to_pydict()
    result = {
        "delta_version": version,
        "row_count": arrow.num_rows,
        "schema": {field.name: str(field.type) for field in arrow.schema},
        "missing_contract_columns": sorted(
            set(COMMON | SCHEMAS[dataset]) - set(columns)
        ),
        "null_counts": {
            name: column.null_count
            for name, column in zip(arrow.column_names, arrow.columns)
        },
        "observation_id_duplicates": arrow.num_rows
        - len(set(columns["observation_id"])),
        "categories": {},
        "time_ranges": {},
        "id_distinct_counts": {},
    }
    for name, values in columns.items():
        present = [v for v in values if v is not None]
        if name in PROFILE_FIELDS:
            counts = Counter(present)
            result["categories"][name] = dict(counts.most_common(30))
            if len(counts) > 30:
                result["categories"][name]["<other categories>"] = sum(
                    counts.values()
                ) - sum(v for _, v in counts.most_common(30))
        if name.endswith(("_utc", "_date")) or name == "source_date":
            result["time_ranges"][name] = {
                "min": min(present, default=None),
                "max": max(present, default=None),
            }
        if name.endswith("_id"):
            result["id_distinct_counts"][name] = len(set(present))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    profile = {
        "profiled_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace_id": WORKSPACE,
        "lakehouse_id": LAKEHOUSE,
        "schema": "dbo",
        "read_only": True,
        "cross_table_transaction": False,
        "datasets": {},
    }
    all_observations = set()
    workspace_ids = set()
    item_workspaces = defaultdict(set)
    with credential() as identity:
        for dataset in SCHEMAS:
            uri = f"abfss://{WORKSPACE}@onelake.dfs.fabric.microsoft.com/{LAKEHOUSE}/Tables/dbo/monitor_{dataset}"
            options = {
                "bearer_token": identity.get_token(
                    "https://storage.azure.com/.default"
                ).token,
                "use_fabric_endpoint": "true",
            }
            delta = DeltaTable(uri, storage_options=options)
            version = delta.version()
            arrow = pa.table(
                QueryBuilder()
                .register("source", delta)
                .execute("SELECT * FROM source")
                .read_all()
            )
            info = summarize(dataset, arrow, version)
            ids = arrow.column("observation_id").to_pylist()
            info["cross_dataset_observation_id_collisions"] = len(
                all_observations.intersection(ids)
            )
            all_observations.update(ids)
            if "workspace_id" in arrow.column_names:
                workspaces = arrow.column("workspace_id").to_pylist()
                workspace_ids.update(v for v in workspaces if v)
                if "item_id" in arrow.column_names:
                    for workspace, item in zip(
                        workspaces, arrow.column("item_id").to_pylist()
                    ):
                        if item:
                            item_workspaces[item].add(workspace)
            cache = args.cache_dir / f"{dataset}.parquet"
            pq.write_table(arrow, cache, compression="zstd")
            info["cache_sha256"] = hashlib.sha256(cache.read_bytes()).hexdigest()
            profile["datasets"][dataset] = info
            print(
                f"{dataset}: {arrow.num_rows} rows; Delta v{version}; coverage={info['categories'].get('coverage_status', {})}",
                flush=True,
            )
    profile["cross_dataset"] = {
        "distinct_observation_ids": len(all_observations),
        "distinct_workspace_ids": len(workspace_ids),
        "distinct_item_ids": len(item_workspaces),
        "item_ids_with_multiple_known_workspaces": sum(
            len({w for w in values if w}) > 1 for values in item_workspaces.values()
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, indent=2) + "\n")
    print("Aggregate profile saved. Curated row cache is separate from the PBIP.")


if __name__ == "__main__":
    main()
