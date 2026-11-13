"""Generate self-contained Fabric ipynb files from the tested Python sources."""

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
SUBJECTS = {
    "01_monitor_inventory_health": (
        "Inventory and collection health",
        ("collection_health", "inventory"),
        "preview_inventory(spark, display, tables)",
    ),
    "02_monitor_permissions": (
        "Scoped and Tenant permission observations",
        ("permission_cycles", "permission_resources", "permission_grants"),
        "preview_permissions(spark, display, tables, PERMISSION_MODE)",
    ),
    "03_monitor_job_history": (
        "Job history and resource coverage",
        ("job_resources", "job_observations"),
        "preview_jobs(spark, display, tables)",
    ),
    "04_monitor_lineage": (
        "Scanner, static references and configured Lakehouse/shortcut/Eventstream relationships",
        ("lineage_resources", "lineage_edges", "lineage_diagnostics"),
        "preview_lineage(spark, display, tables)",
    ),
}
CONFIG = """# Attach lh_monitor as this notebook's DEFAULT Lakehouse before running.
RAW_ROOT = "/lakehouse/default/Files/monitor"
TABLE_PREFIX = "monitor_"
WRITE_TABLES = False  # Preview first; set True only for the curated Delta writes.
INCLUDE_SHORTCUTS = False  # Opt in to retained fabricshortcuts evidence in 01-04.
INCLUDE_EVENTSTREAM_TOPOLOGY = False  # Opt in to retained Eventstream configuration.
PERMISSION_MODE = "Scoped"  # Choose "Scoped" or "Tenant"; never combined.
MAX_RAW_FILES = 50000
MAX_RAW_BYTES = 128 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
"""
VISUAL_CONFIG = """# Attach the SAME default Lakehouse and use the same prefix as 01-04.
TABLE_PREFIX = "monitor_"
PERMISSION_MODE = "Scoped"  # Explicitly choose "Scoped" or "Tenant".
PERMISSION_CYCLE_ID = ""  # Empty selects latest attempt in the chosen mode.
STALE_AFTER_HOURS = 24
LINEAGE_SOURCE_PATH = ""  # Optional exact historical batch/resource; never a union.
MAX_GRAPH_EDGES = 40
"""
VALIDATION_CONFIG = """# Attach lh_monitor as DEFAULT; use the same raw root/prefix as 01-04.
RAW_ROOT = "/lakehouse/default/Files/monitor"
TABLE_PREFIX = "monitor_"
PERMISSION_MODE = "Scoped"
VALIDATION_ACTION = "capture"  # Save baseline, rerun 01-04, then choose "compare".
BASELINE_NAME = "rerun_baseline_001.json"  # Never overwritten; use a new name per test.
STALE_AFTER_HOURS = 24
MAX_RAW_FILES = 50000
MAX_RAW_BYTES = 128 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
INCLUDE_ESTATE_TABLES = False  # True only after publishing all of 07-11.
INCLUDE_MODULE_TABLES = False  # True after publishing 12-21; includes estate tables.
INCLUDE_PIPELINE_ACTIVITY_TABLES = False  # True only after publishing notebook 22.
INCLUDE_SHORTCUTS = False  # Match 01-04; adds raw evidence, not new tables.
INCLUDE_EVENTSTREAM_TOPOLOGY = False  # Match 01-04; no new tables.
"""
ESTATE_CONFIG = """# Attach lh_monitor as DEFAULT. Existing raw data only; no API calls.
RAW_ROOT = "/lakehouse/default/Files/monitor"
TABLE_PREFIX = "monitor_"
WRITE_TABLES = False  # Inspect coverage first, then enable curated writes.
MAX_RAW_FILES = 50000
MAX_RAW_BYTES = 128 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
"""
ESTATE_SUBJECTS = {
    "07_monitor_activity_events": ("Activity and audit events", "activity"),
    "08_monitor_estate_catalog_schema": (
        "Estate catalog and semantic-model schema",
        "catalog",
    ),
    "09_monitor_connections": ("Caller-visible Fabric connections", "connections"),
    "10_monitor_gateways": (
        "Gateways, datasources and connectivity observations",
        "gateways",
    ),
    "11_monitor_refresh_history": (
        "Dataset refresh history and reliability evidence",
        "refresh",
    ),
}
MODULE_SUBJECTS = {
    "12_monitor_apps": ("Published application inventory", "apps"),
    "13_monitor_capacity_performance": (
        "Capacity inventory and performance evidence",
        "capacity",
    ),
    "14_monitor_directory_licensing": (
        "Directory, memberships and licensing",
        "directory",
    ),
    "15_monitor_workspace_roles": ("Observed workspace role assignments", "roles"),
    "16_monitor_tenant_settings": (
        "Tenant settings and delegated overrides",
        "settings",
    ),
    "17_monitor_domains": ("Observed domains and workspace associations", "domains"),
    "18_monitor_git_connections": ("Workspace Git integration", "git"),
    "19_monitor_tags": ("Tag definitions and scope", "tags"),
    "20_monitor_broad_sharing": (
        "Organization-wide and publish-to-web sharing",
        "sharing",
    ),
    "21_monitor_deployment_pipelines": (
        "Deployment pipeline inventory and operations",
        "deployments",
    ),
}
ORCHESTRATOR_RUN = """if (
    not isinstance(NOTEBOOKS, list)
    or not NOTEBOOKS
    or any(not isinstance(name, str) or not name.strip() for name in NOTEBOOKS)
    or len(set(NOTEBOOKS)) != len(NOTEBOOKS)
):
    raise ValueError("NOTEBOOKS must be a nonempty list of unique notebook names")
if type(WRITE_TABLES) is not bool:
    raise ValueError("WRITE_TABLES must be True or False")
if type(INCLUDE_SHORTCUTS) is not bool:
    raise ValueError("INCLUDE_SHORTCUTS must be True or False")
if type(INCLUDE_EVENTSTREAM_TOPOLOGY) is not bool:
    raise ValueError("INCLUDE_EVENTSTREAM_TOPOLOGY must be True or False")
if PERMISSION_MODE not in {"Scoped", "Tenant"}:
    raise ValueError("Choose Scoped or Tenant explicitly")
if type(NOTEBOOK_TIMEOUT_SECONDS) is not int or NOTEBOOK_TIMEOUT_SECONDS <= 0:
    raise ValueError("NOTEBOOK_TIMEOUT_SECONDS must be a positive integer")

print("Publication enabled." if WRITE_TABLES else "PREVIEW ONLY: no Delta writes.")
results = []
for name in NOTEBOOKS:
    print(f"Running {name}")
    try:
        notebookutils.notebook.run(
            name,
            NOTEBOOK_TIMEOUT_SECONDS,
            {
                "RAW_ROOT": RAW_ROOT,
                "TABLE_PREFIX": TABLE_PREFIX,
                "WRITE_TABLES": WRITE_TABLES,
                "PERMISSION_MODE": PERMISSION_MODE,
                "INCLUDE_SHORTCUTS": INCLUDE_SHORTCUTS,
                "INCLUDE_EVENTSTREAM_TOPOLOGY": INCLUDE_EVENTSTREAM_TOPOLOGY,
            },
        )
        results.append({"notebook": name, "status": "Succeeded", "error": ""})
    except Exception as exc:  # noqa: BLE001 - Attempt every child, then fail overall.
        results.append(
            {
                "notebook": name,
                "status": "Failed",
                "error": str(exc),
            }
        )

display(spark.createDataFrame(results, "notebook string, status string, error string"))
failed = [result["notebook"] for result in results if result["status"] == "Failed"]
if failed:
    raise RuntimeError("Failed notebooks: " + ", ".join(failed))
print("All selected notebooks succeeded. Review collection coverage separately.")
"""


def cell(kind, source, index, *, parameters=False):
    if kind == "code":
        source = source.rstrip("\n")
    result = {
        "cell_type": kind,
        "id": hashlib.sha256(f"{index}:{source}".encode()).hexdigest()[:16],
        "metadata": {"tags": ["parameters"]} if parameters else {},
        "source": source.splitlines(keepends=True),
    }
    if kind == "code":
        result.update(execution_count=None, outputs=[])
    return result


def orchestrator_notebook():
    orchestrator_config = (
        "# Attach the SAME default Lakehouse as the child notebooks.\n"
        'RAW_ROOT = "/lakehouse/default/Files/monitor"\n'
        'TABLE_PREFIX = "monitor_"\n'
        "WRITE_TABLES = False  # Preview first; set True to publish Delta tables.\n"
        'PERMISSION_MODE = "Scoped"  # Choose "Scoped" or "Tenant".\n'
        "INCLUDE_PIPELINE_ACTIVITY = False  # Opt in after importing notebook 22.\n"
        "INCLUDE_SHORTCUTS = False  # Opt in to shortcut evidence in 01-04.\n"
        "INCLUDE_EVENTSTREAM_TOPOLOGY = False  # Opt in to topology evidence in 01-04.\n"
        "NOTEBOOK_TIMEOUT_SECONDS = 3600\n"
        "# Edit this list to match the imported notebook names in your workspace.\n"
        "NOTEBOOKS = [\n"
        + "".join(
            f"    {json.dumps(name)},\n"
            for name in (*SUBJECTS, *ESTATE_SUBJECTS, *MODULE_SUBJECTS)
        )
        + "]\n"
        + 'if INCLUDE_PIPELINE_ACTIVITY:\n    NOTEBOOKS.append("22_monitor_pipeline_activity")\n'
    )
    return notebook(
        [
            (
                "markdown",
                """# Monitor: serial notebook orchestrator

Import this notebook as **nb_orchestrator** alongside the 19 transformation
notebooks. Attach the same default Lakehouse (for example **lh_monitor**) to
the orchestrator and every child. Match the names in NOTEBOOKS to the imported
Fabric notebook names; remove entries for domains you do not want to process.
Notebooks 05 (visualization) and 06 (controlled rerun validation) are excluded.
Notebook 22 is excluded unless INCLUDE_PIPELINE_ACTIVITY=True; import it first.
INCLUDE_SHORTCUTS=True includes retained shortcut evidence in 01-04, without
adding writers or tables. Use the same flag in rerun validation notebook 06.
INCLUDE_EVENTSTREAM_TOPOLOGY=True includes retained Eventstream configuration
in 01-04, also without new tables/writers. Match this flag in notebook 06.

Run manually with WRITE_TABLES=False first. After reviewing coverage, set it
to True to publish. The executing identity needs raw-data read access and,
for publication, curated-table write access. Shell credentials are not used.
The child notebooks must retain their marked parameter cells.

Execution is serial because concurrent same-prefix publication is unsupported
and domain notebooks share estate_coverage. Each child is attempted even after
another fails. The final summary identifies failures by notebook name; any
failure raises after the summary so a calling pipeline is marked failed.
Use Fabric's child-run snapshots for detailed diagnostics.

Succeeded means execution succeeded, not that collection coverage is complete
or fresh. Missing/failed collection may be reported without an exception.
The orchestrator makes no collection API calls and does not save a separate
status table. Review run outputs as potentially sensitive operational metadata.

After manual acceptance, call this notebook from a scheduled pipeline and verify
the pipeline execution identity. Run after collection has finished; avoid
overlapping orchestrator runs or other writers to the same table prefix.
Generated notebook: edit build_monitor_notebooks.py and regenerate, not these cells.
""",
                False,
            ),
            ("code", orchestrator_config, True),
            ("code", ORCHESTRATOR_RUN, False),
        ]
    )


def notebook(cells):
    return {
        "cells": [
            cell(kind, source, index, parameters=parameters)
            for index, (kind, source, parameters) in enumerate(cells)
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Synapse PySpark",
                "language": "python",
                "name": "synapse_pyspark",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def generated_notebooks():
    library = embedded_library()
    estate_metadata = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in ast.parse((ROOT / "monitor_estate_analytics.py").read_text()).body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"ESTATE_DOMAINS", "ESTATE_SOURCES"}
    }
    estate_domains = estate_metadata["ESTATE_DOMAINS"]
    estate_sources = estate_metadata["ESTATE_SOURCES"]
    module_metadata = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in ast.parse((ROOT / "monitor_module_analytics.py").read_text()).body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"MODULE_DOMAINS", "MODULE_SOURCES"}
    }
    estate_domains.update(module_metadata["MODULE_DOMAINS"])
    estate_sources.update(module_metadata["MODULE_SOURCES"])
    result = {}
    for name, (title, datasets, preview) in SUBJECTS.items():
        intro = f"""# Monitor: {title}

Self-contained Fabric PySpark notebook; no repository modules or API credentials
are required. Raw Files are read-only. Review parameters, run in preview, inspect
coverage, then explicitly enable curated writes. Missing, invalid and failed
observations are not successful empty results. See notebooks/README.md for the
contract, limitations and execution order. Local checks do not prove Fabric execution.

The embedded implementation is generated; edit its Python sources in Git, not
these generated cells. Never copy collected rows or credentials into this file.
"""
        execute = f"""source_prefixes = set(CORE_SOURCE_PREFIXES)
if INCLUDE_SHORTCUTS:
    source_prefixes |= SHORTCUT_PREFIXES
if INCLUDE_EVENTSTREAM_TOPOLOGY:
    source_prefixes |= EVENTSTREAM_PREFIXES
documents = load_documents(
    RAW_ROOT,
    max_files=MAX_RAW_FILES,
    max_bytes=MAX_RAW_BYTES,
    max_file_bytes=MAX_FILE_BYTES,
    source_prefixes=source_prefixes,
)
tables = transform(
    documents,
    scanner_extractor=scan_snapshot,
    include_shortcuts=INCLUDE_SHORTCUTS,
    include_eventstream_topology=INCLUDE_EVENTSTREAM_TOPOLOGY,
)
counts = publish(
    spark,
    tables,
    {json.dumps(datasets)},
    TABLE_PREFIX,
    write=WRITE_TABLES,
)
print(counts)
"""
        result[name + ".ipynb"] = notebook(
            [
                ("markdown", intro, False),
                ("code", CONFIG, True),
                (
                    "markdown",
                    "## Embedded validation, scanner adapter and Delta helpers\n",
                    False,
                ),
                ("code", library, False),
                ("markdown", "## Transform and optionally publish\n", False),
                ("code", execute, False),
                (
                    "markdown",
                    "## Coverage-first preview (historical observations)\n",
                    False,
                ),
                ("code", preview, False),
            ]
        )
    result["05_monitor_visualizations.ipynb"] = notebook(
        [
            (
                "markdown",
                """# Monitor: coverage-first visualizations

Run 01-04 with curated writes enabled first. This notebook is read-only and
never starts collectors. Charts count observations unless labelled otherwise.
Retained job status is not proof of current polling health. A permission view
uses one explicit mode and cycle; a lineage view uses latest resource observations
or one exact historical source. Failures never fall back silently to old edges.
Principal IDs, names, UPNs, raw definitions and failure messages are not chart labels.
""",
                False,
            ),
            ("code", VISUAL_CONFIG, True),
            ("code", embedded_library(visualizations=True), False),
            (
                "code",
                """render(
    spark,
    display,
    prefix=TABLE_PREFIX,
    permission_mode=PERMISSION_MODE,
    permission_cycle_id=PERMISSION_CYCLE_ID,
    stale_after_hours=STALE_AFTER_HOURS,
    lineage_source_path=LINEAGE_SOURCE_PATH,
    max_graph_edges=MAX_GRAPH_EDGES,
)
""",
                False,
            ),
        ]
    )
    result["06_monitor_validation.ipynb"] = notebook(
        [
            (
                "markdown",
                """# Monitor: persistent rerun validation

Attach the same default Lakehouse as 01-05. Ensure collectors and other writers
are idle during this experiment. Run with VALIDATION_ACTION="capture" to save a
metadata-only baseline in Files/monitor_validation/BASELINE_NAME; an existing
file is never overwritten. No raw files, curated tables or controls are changed.

Rerun 01-04 with WRITE_TABLES=True and unchanged inputs/settings, then run this
notebook with VALIDATION_ACTION="compare" and the same BASELINE_NAME. The saved
baseline survives session restarts. Retained Delta versions are still required:
do not vacuum or change retention during the test. Compare checks exact rows,
not just counts. Changed raw evidence/settings make the test NOT_COMPARABLE.

PASS establishes rerun stability only, not fresh/complete collection, Power Query
parity, private connectivity or runtime lineage. Review the separate freshness
and retained-coverage reports. Never commit executed outputs or baseline files.

The default scope remains the original ten tables. INCLUDE_ESTATE_TABLES=True
selects the previous 25-table scope. After publishing all transformation notebooks,
INCLUDE_MODULE_TABLES=True selects all 48 tables (including estate tables).
These existing scopes are unchanged. After publishing notebook 22, explicitly
enable INCLUDE_PIPELINE_ACTIVITY_TABLES to add its two activity datasets.
INCLUDE_SHORTCUTS must match 01-04; it adds shortcut raw evidence to the same
table scope. Its default is False. A changed evidence scope is NOT_COMPARABLE.
INCLUDE_EVENTSTREAM_TOPOLOGY must also match 01-04 and defaults to False.
It adds raw evidence to existing tables, not new datasets. Use a new baseline
when changing either flag, even if no corresponding raw files have arrived.
Use a new baseline name when changing scope and rerun all writers in that scope.
""",
                False,
            ),
            ("code", VALIDATION_CONFIG, True),
            ("code", embedded_library(validation=True), False),
            (
                "code",
                """validation_result = validate_rerun(
    spark,
    display,
    raw_root=RAW_ROOT,
    prefix=TABLE_PREFIX,
    permission_mode=PERMISSION_MODE,
    action=VALIDATION_ACTION,
    baseline_name=BASELINE_NAME,
    stale_after_hours=STALE_AFTER_HOURS,
    max_files=MAX_RAW_FILES,
    max_bytes=MAX_RAW_BYTES,
    max_file_bytes=MAX_FILE_BYTES,
    include_estate_tables=INCLUDE_ESTATE_TABLES,
    include_module_tables=INCLUDE_MODULE_TABLES,
    include_pipeline_activity_tables=INCLUDE_PIPELINE_ACTIVITY_TABLES,
    include_shortcuts=INCLUDE_SHORTCUTS,
    include_eventstream_topology=INCLUDE_EVENTSTREAM_TOPOLOGY,
)
""",
                False,
            ),
        ]
    )
    for name, (title, domain) in {**ESTATE_SUBJECTS, **MODULE_SUBJECTS}.items():
        modules = name in MODULE_SUBJECTS
        extractor = (
            "module_extractor=transform_modules"
            if modules
            else "estate_extractor=transform_estate"
        )
        preview = "preview_modules" if modules else "preview_estate"
        datasets = ("estate_coverage", *estate_domains[domain])
        datasets_code = (
            "[\n"
            + "".join(f"        {json.dumps(dataset)},\n" for dataset in datasets)
            + "    ]"
        )
        result[name + ".ipynb"] = notebook(
            [
                (
                    "markdown",
                    f"""# Monitor: {title}

Answer domain questions using existing collected files only; no API calls,
collector changes or credentials are required. Attach the default Lakehouse,
preview first, inspect coverage, then explicitly enable WRITE_TABLES.

Missing data is NOT COLLECTED, not a successful empty answer. Legacy daily files
have no completion manifest or exact collection timestamp: source_date is only
the folder date. Charts label retained observations, not guaranteed current or
tenant-complete state. See notebooks/README.md for domain limits and output tables.

No raw files or controls are changed. Only insert-only managed Delta tables are
written when requested. Generated cells and executed outputs must not be edited
or committed as source.
""",
                    False,
                ),
                ("code", ESTATE_CONFIG, True),
                ("code", embedded_library(estate=True, modules=modules), False),
                (
                    "code",
                    f"""documents = load_documents(
    RAW_ROOT,
    max_files=MAX_RAW_FILES,
    max_bytes=MAX_RAW_BYTES,
    max_file_bytes=MAX_FILE_BYTES,
    source_prefixes={json.dumps(estate_sources[domain])},
    allow_empty=True,
)
tables = transform(
    documents,
    scanner_extractor=scan_snapshot,
    {extractor},
)
counts = publish(
    spark,
    tables,
    {datasets_code},
    TABLE_PREFIX,
    write=WRITE_TABLES,
)
print(counts)
{preview}(spark, display, tables, {json.dumps(domain)})
""",
                    False,
                ),
            ]
        )
    result["22_monitor_pipeline_activity.ipynb"] = notebook(
        [
            (
                "markdown",
                """# Monitor: pipeline activity metrics and query coverage

Optional, self-contained Fabric PySpark notebook. Attach the same default Lakehouse,
preview first and explicitly enable WRITE_TABLES to publish two additional tables.
Read existing fabricpipelineactivityruns files only; no APIs, credentials or workload
execution. Notebook 03 remains item job history; 21 remains deployment operations.

Inspect coverage before metrics: successful empty pipeline job history means no run
IDs were returned, not that zero activities ran. Failed, missing, unfinished or
malformed queries have unknown counts. Query windows filter last updates, not starts.
Recent API history and resource permissions limit coverage.

Historical observations retain query window, mode and source identity. The preview
selects the latest query attempt before admitting its activities, never falling back
to old metrics after a failed or empty query. Repeated polls are not additive facts.
ACTIVITY_SOURCE_PATH can select one exact historical successful query instead.
Inputs, arbitrary outputs and errors are not exported. IDs and activity names may
still be sensitive; chart labels use status/type, not those names.

Reported throughput keeps native engine/activity units; never sum rates or treat
chained activity counts as distinct end-to-end data movement. These metrics do not
establish runtime lineage or tenant-complete history. The existing notebook 06
10/25/48-table scopes stay unchanged unless its activity-table flag is enabled.
Generated notebook: edit Python sources, not these cells.
""",
                False,
            ),
            (
                "code",
                ESTATE_CONFIG
                + 'ACTIVITY_SOURCE_PATH = ""  # Optional exact historical query source.\n',
                True,
            ),
            ("code", embedded_library(pipeline=True), False),
            (
                "code",
                """documents = load_documents(
    RAW_ROOT,
    max_files=MAX_RAW_FILES,
    max_bytes=MAX_RAW_BYTES,
    max_file_bytes=MAX_FILE_BYTES,
    source_prefixes=PIPELINE_ACTIVITY_PREFIXES,
    allow_empty=True,
)
tables = transform(documents, pipeline_extractor=pipeline_activity_tables)
counts = publish(
    spark,
    tables,
    tuple(PIPELINE_ACTIVITY_SCHEMAS),
    TABLE_PREFIX,
    write=WRITE_TABLES,
)
print(counts)
preview_pipeline_activity(spark, display, tables, ACTIVITY_SOURCE_PATH)
""",
                False,
            ),
        ]
    )
    result["23_monitor_investigation.ipynb"] = notebook(
        [
            (
                "markdown",
                """# Monitor: resource investigation using retained evidence

Optional **read-only** notebook. Publish 01-04 first; publish 07 for activity
events and its estate coverage. Attach the same default Lakehouse and match
TABLE_PREFIX. Missing tables are reported as NOT PUBLISHED / UNKNOWN; tables
with invalid ownership fail rather than being treated as empty.

AUTO_DISCOVER=True discovers distinct workspace/item pairs from retained inventory
by default; no UUIDs are needed up front. A unique match is investigated
automatically. Multiple matches show numbered choices, not an arbitrary selection.
Narrow with optional case-insensitive WORKSPACE_SEARCH / ITEM_SEARCH name filters,
ITEM_TYPE or exact WORKSPACE_ID / ITEM_ID filters; or choose RESOURCE_NUMBER
from the displayed list and rerun. Numbers apply to this run's list and can change.
Name searches match retained historical names; hints are not current metadata.
Workspace name discovery uses retained Workspace rows; missing names stay unknown.
Discovery spans inventory sources/modes, not effective access or a current estate.
It deduplicates workspace/item IDs, not inventory history. Truncation is labelled.
With AUTO_DISCOVER=False, provide explicit WORKSPACE_ID and ITEM_ID UUIDs.
This manual opt-out also works when inventory is unpublished.

Select one PERMISSION_MODE for access evidence.
PERMISSION_CYCLE_ID optionally restricts access sections to one historical cycle;
empty shows separate retained observations across all cycles in that mode.
It never merges historical grants into an effective/current access list.

Sections correlate only by explicit identifiers. They are NOT a synchronized
snapshot or current estate: each row retains its own source, version, observation
time, scope and coverage. Read collection/resource outcomes alongside facts.
Later failed/empty attempts do not erase history or make old successes current.
Null collection times remain unknown, even when an event has an exact event time.

Direct incoming relationships require both target workspace and item IDs.
Unresolved references and transitive dependencies are not reconstructed. Scanner,
static and configured associations remain distinct; no relationship proves runtime
I/O, effective access, or the impact of removing a resource.

MAX_ROWS_PER_SECTION bounds driver/display rows (default 200, maximum 1000);
truncation is labelled. It does not bound Spark table scans or make counts complete.
Unknown-time rows sort first, then newest known observations.

No raw data, controls, tables, baselines, workloads or API configuration are changed.
No new API or permission is introduced: the executing Fabric identity needs read
access to these curated tables. Existing Admin/non-Admin collection boundaries
remain unchanged; see notebooks/README.md and docs/configuration-reference.md.
IDs, names, principal assignments and dependency references can be sensitive.
Restrict notebook/table access, clear outputs before sharing, and do not commit
executed evidence. This notebook is intentionally excluded from nb_orchestrator
and does not change validation scopes or the 50 managed datasets.

Generated notebook: edit Python sources, not these cells.
""",
                False,
            ),
            (
                "code",
                """# Attach the SAME default Lakehouse as the transformation notebooks.
TABLE_PREFIX = "monitor_"
AUTO_DISCOVER = True  # False requires both explicit IDs below.
WORKSPACE_SEARCH = ""  # Optional case-insensitive retained workspace-name substring.
ITEM_SEARCH = ""  # Optional case-insensitive retained item-name substring.
ITEM_TYPE = ""  # Optional exact item type, e.g. Notebook; case-insensitive.
RESOURCE_NUMBER = 0  # 0 = unique match only; otherwise choose a listed number.
WORKSPACE_ID = ""  # Optional exact filter; required when AUTO_DISCOVER=False.
ITEM_ID = ""  # Optional exact filter; required when AUTO_DISCOVER=False.
PERMISSION_MODE = "Scoped"  # Choose "Scoped" or "Tenant"; never combined.
PERMISSION_CYCLE_ID = ""  # Optional exact historical access cycle.
MAX_ROWS_PER_SECTION = 200
""",
                True,
            ),
            ("code", embedded_library(investigation=True), False),
            (
                "code",
                """run_investigation(
    spark,
    display,
    prefix=TABLE_PREFIX,
    auto_discover=AUTO_DISCOVER,
    workspace_id=WORKSPACE_ID,
    item_id=ITEM_ID,
    workspace_search=WORKSPACE_SEARCH,
    item_search=ITEM_SEARCH,
    item_type=ITEM_TYPE,
    resource_number=RESOURCE_NUMBER,
    permission_mode=PERMISSION_MODE,
    permission_cycle_id=PERMISSION_CYCLE_ID,
    max_rows=MAX_ROWS_PER_SECTION,
)
""",
                False,
            ),
        ]
    )
    result["24_monitor_silver_events.ipynb"] = notebook(
        [
            (
                "markdown",
                """# Silver: normalize event, artifact and execution evidence

Upload this notebook to your workspace's **Silver** folder. Attach **lh_monitor**
as DEFAULT and create its **silver** schema first. Workspace folders organize
notebooks; the output schema controls table placement. Tenant discovery is automatic
from the Fabric execution identity. A nonempty TENANT_ID overrides discovery;
AUTO_DISCOVER_TENANT=False requires a manual TENANT_ID.

Read-only inputs: existing dbo.monitor_* observations and Files/monitor/activity.
This notebook calls no collection APIs; tenant discovery uses Fabric's credential
utility. It does not create schemas, change
grants, replace the FM model, or move Bronze data. Preview first. WRITE_TABLES=True
replaces only owned Silver snapshots; retained Bronze evidence stays unchanged.

The first slice produces normalized events, scoped artifacts, retained execution
history/latest observations, activities, exact correlations, child-run links,
reported locations, quarantine, coverage and a readiness gate. Conflicting events
survive as conflict cases; ambiguous/scope-incompatible links are not promoted.
Legacy folder dates are not collection timestamps. Failed/empty latest polls are
labelled alongside historical statuses. Exact links do not prove who initiated a run.

INCLUDE_SENSITIVE_VALUES=False suppresses reported actor/IP values by default.
Keys, names, IDs, locations and notebook outputs can still be sensitive; hashing
and schema separation are not access controls. Enable raw actor/IP values only
after reviewing Lakehouse and downstream Build/export access. No credentials are
embedded or required; execution uses your signed-in Fabric identity.

Non-Admin scope: job/activity evidence remains limited by the original workspace/
item caller permissions, query windows and collector coverage. No API scope is
expanded. Activity metrics do not retain physical inputs/outputs. Historical
dependency closure, effective access and proven runtime destinations are not
implemented in this first slice. See notebooks/MEDALLION.md.

Inputs are version-pinned and rechecked; row/file/byte limits fail instead of
publishing truncated evidence. Processing is bounded on the Spark driver, not a
distributed production-scale correlation engine. Run serially with upstream and
medallion writers idle. There is no writer lock or cross-table transaction.
Gold accepts only a complete, matching Silver build. Keep Delta history.

Generated notebook: edit Python sources and regenerate; clear outputs before sharing.
""",
                False,
            ),
            (
                "code",
                """LAKEHOUSE_NAME = "lh_monitor"
AUTO_DISCOVER_TENANT = True
TENANT_ID = ""  # Optional manual override; evidence owner's tenant UUID, not a credential.
RAW_ROOT = "/lakehouse/default/Files/monitor"
WRITE_TABLES = False
INCLUDE_SENSITIVE_VALUES = False  # Explicit access/privacy review before True.
MAX_SOURCE_ROWS = 250000
MAX_TOTAL_ROWS = 500000
MAX_RAW_FILES = 10000
MAX_RAW_BYTES = 128 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
""",
                True,
            ),
            ("code", embedded_library(medallion=True), False),
            (
                "code",
                """run_silver(
    spark, display, lakehouse=LAKEHOUSE_NAME, tenant_id=TENANT_ID,
    auto_discover_tenant=AUTO_DISCOVER_TENANT,
    raw_root=RAW_ROOT, write=WRITE_TABLES,
    include_sensitive=INCLUDE_SENSITIVE_VALUES,
    max_source_rows=MAX_SOURCE_ROWS, max_total_rows=MAX_TOTAL_ROWS,
    max_raw_files=MAX_RAW_FILES, max_raw_bytes=MAX_RAW_BYTES,
    max_file_bytes=MAX_FILE_BYTES,
)
""",
                False,
            ),
        ]
    )
    result["25_monitor_gold_event_cases.ipynb"] = notebook(
        [
            (
                "markdown",
                """# Gold: event cases, execution facts and drillable evidence links

Upload to your workspace's **Gold** folder. Attach the same default **lh_monitor**
and create its **gold** schema. First publish Silver using notebook 24. A Silver
preview alone does not supply persisted input for this notebook.

Preview first. WRITE_TABLES=True replaces only owned Gold snapshots. It does not
change Bronze/Silver tables, collectors, permissions or semantic models. The
executing Fabric identity needs Silver read and, for publication, Gold write access.
No new API scope is introduced; existing Admin/non-Admin coverage limits remain.

Gold produces one case per event, typed trace edges, one fact per execution/activity,
an exact event/execution bridge, reported audit locations, coverage and a readiness gate. Artifact/reference
fan-out does not multiply run/activity facts. Movement metrics are not additive
across correlated events or chained activities. Exact correlation is not causality
or proof of the initiating actor. Missing links/metrics do not prove no runs.
Physical destinations remain null with an explicit evidence gap.

EVENT_ID optionally displays a bounded detailed case and trace. Default output is
aggregate counts, not raw actor/IP values. Details can contain sensitive keys,
artifact names and source paths. Clear outputs before sharing. Detail previews are
bounded, not full trace exports; publication never truncates data.

Child traversal is cycle-safe and capped explicitly. Historical dependency impact,
additional report dimensions and runtime endpoint collection remain follow-up work.
Run serially with Silver/Gold writers idle. Input versions/build IDs are checked
before publication and readiness; there is no distributed lock or cross-table
transaction. Consumers must respect the ready Gold build, not read partial writes.
See notebooks/MEDALLION.md. Local tests do not establish live Fabric execution.

Generated notebook: edit Python sources and regenerate, not these cells.
""",
                False,
            ),
            (
                "code",
                """LAKEHOUSE_NAME = "lh_monitor"
WRITE_TABLES = False
EVENT_ID = ""  # Optional provider event ID for sensitive detailed preview.
MAX_PREVIEW_ROWS = 50
MAX_SOURCE_ROWS = 250000
MAX_TOTAL_ROWS = 1000000
MAX_TRACE_DEPTH = 32
""",
                True,
            ),
            ("code", embedded_library(medallion=True), False),
            (
                "code",
                """run_gold(
    spark, display, lakehouse=LAKEHOUSE_NAME, write=WRITE_TABLES,
    event_id=EVENT_ID, max_preview_rows=MAX_PREVIEW_ROWS,
    max_source_rows=MAX_SOURCE_ROWS, max_total_rows=MAX_TOTAL_ROWS,
    max_trace_depth=MAX_TRACE_DEPTH,
)
""",
                False,
            ),
        ]
    )
    result["26_monitor_gold_investigation.ipynb"] = notebook(
        [
            (
                "markdown",
                """# Gold: investigate each event returned by your query

Import into the workspace's **Gold** folder and attach **lh_monitor** as the
default Lakehouse. Publish Silver with notebook 24 and Gold with notebook 25
first. This is a separate **read-only investigation notebook**, not another
transformation or writer. No helper upload, repository checkout or pasted setup
is required. It is not included in nb_orchestrator.

Run the cells in order. Setup pins all eight Gold Delta versions, requires one
ready build, checks matching build IDs, and creates temporary fm_gold_* views
in this Spark session. It sets the session timezone to UTC. It does not create
Lakehouse tables/schemas, change grants or models, or call collection APIs.
Keep writers idle; there is no cross-table transaction or writer lock.

Edit EVENTS_SQL to a read-only SELECT returning event_key. The default selects
the latest 50 events. The loop processes every unique key returned by that
selection, in first-returned order, printing SQL and displaying separate trace,
activity and reported-location results per event. Duplicate keys run once.
Invalid keys, mixed builds and query/display failures stop execution.

PRINT_QUERIES=False displays results without SQL. EXECUTE_QUERIES=False prints
investigation SQL only; setup and the event-selection query still execute.
Enable at least one output control. Large selections produce three queries and
three displays per event. Investigation queries do not limit rows, although
the Fabric UI can page/limit displayed results. Reopen setup to see a new build.

Empty activity results are expected when Bronze retained no executions/activities.
Exact correlation is not causality or proof of the initiating actor. Audit
locations are not physical runtime sources/sinks. Metrics are not additive
across correlated events or chained activities. Gold contains actor/IP keys,
not raw values. Outputs can still contain sensitive operational detail:
clear them before sharing or exporting the notebook.

See notebooks/GOLD_QUERIES.md and MEDALLION_EXPLAINED.md for interpretation.
Local tests do not establish live Fabric Spark/Delta acceptance.
Generated notebook: edit Python sources and regenerate, not these cells.
""",
                False,
            ),
            (
                "code",
                'LAKEHOUSE_NAME = "lh_monitor"\n\n'
                + gold_query_source(parameters=True),
                True,
            ),
            ("code", gold_query_source(), False),
            (
                "code",
                """gold_snapshot = open_gold_query_views(spark, lakehouse=LAKEHOUSE_NAME)
print("Opened published Gold snapshot:", gold_snapshot)
""",
                False,
            ),
            (
                "code",
                """events_df = spark.sql(EVENTS_SQL)
display(events_df)
""",
                False,
            ),
            (
                "code",
                """summary = run_gold_event_queries(
    spark, display, events_df,
    print_queries=PRINT_QUERIES, execute_queries=EXECUTE_QUERIES,
)
print("Completed:", summary)
""",
                False,
            ),
        ]
    )
    result["nb_orchestrator.ipynb"] = orchestrator_notebook()
    return result


def gold_query_source(*, parameters=False):
    source = (ROOT / "explore_gold_events.py").read_text()
    kinds = (
        (ast.Assign,) if parameters else (ast.Import, ast.ImportFrom, ast.FunctionDef)
    )
    return (
        "\n\n".join(
            ast.get_source_segment(source, node)
            for node in ast.parse(source).body
            if isinstance(node, kinds)
        )
        + "\n"
    )


def embedded_library(
    *,
    visualizations=False,
    validation=False,
    estate=False,
    modules=False,
    pipeline=False,
    investigation=False,
    medallion=False,
):
    paths = [
        REPO / "env/utility/lineage_edges.py",
        REPO / "env/utility/notebook_relationships.py",
        REPO / "env/utility/shortcut_relationships.py",
        REPO / "env/utility/eventstream_topology.py",
        ROOT / "monitor_analytics.py",
        ROOT / "monitor_fabric_runtime.py",
    ]
    if visualizations:
        paths.append(ROOT / "monitor_visualizations.py")
    if validation:
        paths.append(ROOT / "monitor_validation.py")
    if estate:
        paths.append(ROOT / "monitor_estate_analytics.py")
    if modules:
        paths.append(ROOT / "monitor_module_analytics.py")
    if pipeline:
        paths.append(ROOT / "monitor_pipeline_activity.py")
    if investigation:
        paths.append(ROOT / "monitor_investigation.py")
    if medallion:
        paths.extend(
            [ROOT / "monitor_medallion.py", ROOT / "monitor_medallion_runtime.py"]
        )
    imports, from_imports, bodies = set(), {}, []
    for path in paths:
        source = path.read_text().splitlines(keepends=True)
        for index, node in enumerate(ast.parse("".join(source)).body):
            import_node = isinstance(node, (ast.Import, ast.ImportFrom))
            if import_node and not (
                isinstance(node, ast.ImportFrom)
                and (
                    (node.module or "").startswith("notebooks.")
                    or node.module
                    in {
                        "env.utility.notebook_relationships",
                        "env.utility.shortcut_relationships",
                        "env.utility.eventstream_topology",
                    }
                )
            ):
                if isinstance(node, ast.ImportFrom):
                    aliases = from_imports.setdefault((node.module, node.level), set())
                    aliases.update((alias.name, alias.asname) for alias in node.names)
                else:
                    imports.add(ast.unparse(node))
            docstring = (
                index == 0
                and isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            )
            if import_node or docstring:
                for line in range(node.lineno - 1, node.end_lineno):
                    source[line] = ""
        bodies.append("".join(source).strip())
    for (module, level), aliases in from_imports.items():
        imports.add(
            ast.unparse(
                ast.ImportFrom(
                    module=module,
                    names=[
                        ast.alias(name=name, asname=alias)
                        for name, alias in sorted(
                            aliases, key=lambda value: (value[0], value[1] or "")
                        )
                    ],
                    level=level,
                )
            )
        )
    ordered_imports = sorted(
        imports, key=lambda value: (not value.startswith("import "), value)
    )
    return (
        '"""Embedded Monitor implementation; generated from tested repository sources."""\n\n'
        + "\n".join(ordered_imports)
        + "\n\n"
        + "\n\n\n".join(bodies)
        + "\n"
    )


def build():
    for name, value in generated_notebooks().items():
        (ROOT / name).write_text(json.dumps(value, indent=1) + "\n")


if __name__ == "__main__":
    build()
