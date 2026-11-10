# Monitor analytics notebooks

The 21 numbered notebooks transform, visualize and validate **existing collected
evidence**, not API responses fetched by a second collector. They are
self-contained `.ipynb` files:
upload the notebooks themselves, with no repository checkout, Python helper
upload, credentials, `%run` dependency or package installation cell.

Existing `activity.ipynb`, `catalog.ipynb`, `Deconstruct.ipynb` and `nbk.ipynb`
are older experiments and are unchanged. They are not prerequisites for this suite.

## Optional serial orchestrator

Import [nb_orchestrator.ipynb](nb_orchestrator.ipynb) as **nb_orchestrator** to
run all 19 transformation notebooks from one entry point. Attach the same default
Lakehouse to it and its children. Its parameter cell lets you select notebook
names, raw root, table prefix, permission mode, timeout and `WRITE_TABLES`
(False by default). Preview manually, then enable writes when ready.

It attempts every selected notebook serially, displays a named success/failure
summary and raises if any failed so a calling pipeline fails too. Collection
coverage warnings are separate from execution failures; inspect child-run
outputs. Notebooks 05 and 06 are intentionally excluded. Avoid overlapping runs
and other writers to the same prefix. After manual acceptance, test it through
a pipeline under the intended execution identity before scheduling.

## Choose a guide

| Need | Read |
|---|---|
| Understand what each of 01-21 does, choose a notebook, or follow the run order | [Notebook walkthrough](notebook-guide.md) |
| Look up tables, observation grain, scope, limits or baseline semantics | This technical reference |
| Distinguish Eventhouse/KQL access from Event Hubs/Splunk delivery | [Integration options and implementation status](../docs/analytics-integration.md) |
| Change collection/API authorization rather than transform existing files | [Collector configuration](../docs/configuration-reference.md) |

## Upload and first run

1. In the **FabricMonitor** workspace, initially import these six files as notebooks:
   `01_monitor_inventory_health.ipynb`, `02_monitor_permissions.ipynb`,
   `03_monitor_job_history.ipynb`, `04_monitor_lineage.ipynb`,
   `05_monitor_visualizations.ipynb` and `06_monitor_validation.ipynb`.
2. Attach **lh_monitor as the default Lakehouse to each notebook**. Select a
   supported Fabric PySpark runtime with Spark, Delta, pandas and matplotlib.
   Do not use the legacy local `environment.yml` to configure the Fabric runtime.
3. Review the first parameter cell. Defaults read
   `/lakehouse/default/Files/monitor`, use curated table prefix `monitor_`,
   and select permission mode `Scoped`. Change it to `Tenant` if that is the
   view you want. Both modes are retained separately in curated history.
4. Run 01 through 04 with **`WRITE_TABLES = False` first**. These preview counts
   and coverage without creating tables. Missing/failed/invalid coverage is an
   operational result to investigate, not proof the notebook failed to execute.
5. After reviewing the results and target Lakehouse, set **`WRITE_TABLES = True`**
   in each of 01-04 and rerun. Notebooks 07-21 follow the same preview/write
   workflow for their domain tables. Notebook 06 can save a metadata-only
   validation baseline outside raw evidence, as described below. Run one copy of each
   notebook at a time; concurrent writers to the same table prefix are unsupported.
6. Run 05 with the same default Lakehouse and table prefix. It only reads curated
   tables. A missing table produces an actionable error, not a successful empty chart.

These are **ready for import and workspace validation**, not a claim of completed
Fabric execution. Local tests validate Python transformations, real offline
collector output compatibility, standalone generated cells and write guards.
Fabric mounting, Spark/Delta integration, capacity, identity, network access and
full Power Query/Desktop parity still need workspace acceptance.

Manual runs use the executing Fabric identity, not this collector's shell
`CLIENT_*` variables. That identity needs raw-data read and curated-table write
access. Review scheduling/execution identity separately before automation.
No collector, notebook job, schedule, grant or cloud resource is created here.

## Notebooks and output tables

All names below have the configured prefix, for example `monitor_inventory`.

| Notebook | Tables | Grain |
|---|---|---|
| 01 Inventory/health | `collection_health`, `inventory` | One source/run coverage observation; one observed workspace/item per source |
| 02 Permissions | `permission_cycles`, `permission_resources`, `permission_grants` | One cycle-tip observation; one slice/resource outcome; one distinct principal/access-detail observation |
| 03 Jobs | `job_resources`, `job_observations` | One polled item outcome; one job per source observation |
| 04 Lineage | `lineage_resources`, `lineage_edges`, `lineage_diagnostics` | One item/evidence observation, including zero-edge items; one directional edge; one static-analysis diagnostic |
| 05 Visualizations | None | Coverage charts, permission-assignment counts, retained job status/durations, evidence charts and a bounded directed lineage graph |
| 06 Validation | None | Saved baseline, exact rerun comparison, identity/schema checks, freshness and retained coverage |
| 07 Activity events | `activity_events`, shared `estate_coverage` | One event observation per retained source/version |
| 08 Estate catalog/schema | `catalog_workspaces`, `catalog_items`, `catalog_models`, `model_tables`, `model_columns`, `model_measures`, `model_relationships`, shared `estate_coverage` | Returned workspace/item/model/table/column/measure/relationship observations |
| 09 Connections | `connection_observations`, shared `estate_coverage` | One caller-visible connection per successful immutable resource |
| 10 Gateways | `gateway_observations`, `gateway_datasources`, `gateway_status`, shared `estate_coverage` | One gateway, datasource or connectivity observation per dated source/version |
| 11 Refresh history | `refresh_observations`, `refreshable_observations`, shared `estate_coverage` | One dataset refresh or refreshable inventory observation per source/version |
| 12 Apps | `apps`, shared `estate_coverage` | One app per source/version |
| 13 Capacity/performance | `capacities`, `capacity_metric_observations`, shared `estate_coverage` | One capacity; one returned metric/timepoint per queried capacity/group/day and source/version |
| 14 Directory/licensing | `directory_users`, `directory_groups`, `group_memberships`, `user_licenses`, `subscribed_skus`, shared `estate_coverage` | User/group, transitive user membership, user/SKU assignment and subscribed SKU observations |
| 15 Workspace roles | `workspace_role_scopes`, `workspace_role_assignments`, shared `estate_coverage` | One workspace scope; one observed role assignment |
| 16 Tenant settings | `tenant_settings`, `delegated_setting_scopes`, `delegated_setting_overrides`, `tenant_setting_groups`, shared `estate_coverage` | Tenant setting, delegated entity/scope, override and enabled/excluded group rule observations |
| 17 Domains | `domains`, `domain_workspaces`, shared `estate_coverage` | Observed domain and domain/workspace association |
| 18 Git connections | `workspace_git_connections`, shared `estate_coverage` | One workspace integration per source/version |
| 19 Tags | `tags`, shared `estate_coverage` | One tag definition and scope per source/version |
| 20 Broad sharing | `organization_shares`, `publish_to_web_shares`, shared `estate_coverage` | One artifact/access/share-type observation per source/version |
| 21 Deployment pipelines | `deployment_pipelines`, `deployment_operation_resources`, `deployment_operations`, shared `estate_coverage` | One discovered pipeline, history-resource outcome and operation per immutable poll |

There are **48 managed datasets** across 19 transformation notebooks. Notebook 05
is read-only visualization; 06 validates and optionally saves baseline metadata.

The notebooks do **not** export to Splunk, ingest into KQL/Eventhouse or provision
either service. The scalar, versioned tables provide a boundary for that later
work. Validate customer scope, delivery mechanism, schemas, retention, cost and
authorization before any external publication. Splunk does not require Eventhouse.
No Event Hubs publisher is implemented either; a proposed separate publisher is
described in the [integration guide](../docs/analytics-integration.md).

## Shared contract and reruns

Every table includes:

- `schema_version`, `observation_id`, `source_path`, `source_sha256` and
  `record_sha256`: contract version, deterministic observation identity and
  source/derived-content hashes.
- `observed_at_utc`: normalized ISO-8601 UTC text with fixed microsecond precision;
  null when the source has no trustworthy exact observation time.
- `module`, `mode`, `run_id`, `cycle_id` and `coverage_status`: provenance and
  explicit scope. Fields not applicable to that dataset remain null.

Business columns and their explicit Spark scalar types are defined in
`monitor_analytics.py` (`COMMON` and `SCHEMAS`). Permission lists are JSON arrays
stored as strings, not comma-separated text. A null additional-permissions list
remains JSON `null`, distinct from an empty array.

Reads reconcile the retained supported raw files on every run. Writes are
incremental **insert-only Delta MERGEs** by deterministic `observation_id`;
there is no separate notebook checkpoint to reset. Reprocessing unchanged files
does not add duplicate observations. Old successful history is not deleted when
a newer resource is failed, empty, omitted or outside scope.

Committed observations must not change in place. Existing table ownership,
schema and hashes are checked before the write phase. Unexpected changes fail
rather than overwrite. Unfinished/invalid diagnostic artifacts and legacy daily
files use content-versioned IDs, so a legitimate initial-to-final manifest
transition or another observed version of a legacy daily file is not a collision.
Legacy versions are not given fabricated exact observation times.

Managed tables carry `monitor.contract` and `monitor.dataset` properties. A
preexisting table without matching ownership/schema is rejected. For an
intentional new contract or isolated experiment, use a new prefix such as
`monitor_v2_` consistently in all notebooks. Nothing drops, truncates,
overwrites or vacuums a table. Retention is an operator decision. Writes across
tables are not transactional: after a partial write failure, investigate and
rerun the same unchanged input/prefix to complete missing inserts.

## Evidence and coverage rules

**Immutable runs:** manifests and resources must agree on physical path, run ID,
parent, outcome, expected filename/endpoint and UTC order. Unlisted, missing,
malformed or clock-inverted artifacts quarantine the run. Unfinished manifests
produce no facts. This is deliberately stricter than report loaders that admit
individually matching resources from an otherwise damaged run; it never relaxes
the report's historical timestamp warnings. Within a structurally valid,
finished partial run, independently successful resources remain usable.

**Permissions:** Scoped/Tenant inputs never fall back to each other. Evidence
links resolve only against already enumerated manifests in the same module;
JSON cannot trigger arbitrary path reads. Cycles must have continuous cursors,
ordered inventory/access, monotonic health, valid deferrals and no completed
predecessor. Only successful resource records produce grant facts.

`record_count=0` means a successful empty resource; null means failure/unknown.
The selected view uses one mode and cycle, not a union of grants from historical
cycles. `cycle_id` is the first slice's run ID. Successful empty tenant discovery
is valid and can replace the selected old cycle without deleting its history.
Principal IDs/types and observed permissions are retained; principal names, UPNs,
raw definitions and failure messages are not exported. These are observed grants,
**not** expanded groups or complete effective permissions.

**Jobs:** deduplicate current *retained job status* by workspace/item/job ID and
latest observation. Keep per-item collection coverage alongside it: a failed
latest poll does not make the last observed status current. Missing end times
and inverted durations stay unknown. API history windows and polling gaps cannot
be reconstructed, and an empty poll does not mean historical jobs were deleted.

**Lineage:** normalized `lineage_edges/.../*.lineage_edges.json` supplies scanner
batch inventory, references and zero-edge item observations. Existing raw
`catalog/scans/.../*.scanResults[.fullscan].json` is also normalized using the
same scanner extractor, but remains `legacy_unverified`: its requested scope,
scan identity and exact observation time are not available. Synthetic adapter
batch keys are internal only; source provenance remains the actual raw file.
Missing/excluded workspaces are never inferred as deleted.

Notebook/pipeline definition references use the collector's saved static
analysis; no source code or SQL is executed. Scanner relationships and
`static_inference` remain separate. **Neither proves runtime I/O.** Job
execution status does not verify a lineage edge. Dynamic/unsupported expressions
remain diagnostics rather than guessed dependencies. Raw definition contents,
connection payloads and failure messages are not copied to the curated tables.

**Legacy inventory:** `items/...` and `workspaces/...` rows have no immutable
completion manifest or exact observation timestamp. They remain
`legacy_unverified`, including empty files, not successful tenant snapshots.

**Safety bounds:** reading is driver-side, intended for the current collection
size, with configurable defaults of 50,000 supported JSON files, 128 MiB total
and 8 MiB per file. Controls (`request_gate.json`, progress files and `state.yaml`)
are not facts and are never changed. The raw folder must exist under the attached
Lakehouse's `Files`; escaping paths and symlinks are rejected. For larger estates,
design distributed ingestion rather than arbitrarily removing these safeguards.

## Reading the visualizations

The charts distinguish retained observations from current unique inventory and
show missing/invalid/failed coverage alongside useful data. `STALE_AFTER_HOURS`
defaults to 24 as a display threshold, not an API retention promise.

Set `PERMISSION_MODE` explicitly. `PERMISSION_CYCLE_ID=""` selects the latest
attempt in that mode, not the last successful cycle. Unknown-timestamp cycle
evidence blocks automatic selection; inspect health and select an explicit
historical cycle if necessary.

The default graph selects the latest timestamped observation per
workspace/item/evidence kind **before** filtering successful resources. A
successful zero-edge observation removes old edges from that selected view
without deleting history. A failed latest resource does not fall back to old
edges. Historical invalid/unfinished lineage evidence conservatively blocks
automatic graph selection. After inspection, `LINEAGE_SOURCE_PATH` can select
one exact historical resource or scanner batch, including a legacy raw scan.
This is explicitly a historical view, never a union labelled "current".

The graph is capped at `MAX_GRAPH_EDGES` (40 by default, maximum 200), with
truncation labelled. Query item IDs are abbreviated; external references are
hashed in labels rather than printing connection paths. Reference/table/path
values and principal IDs in the underlying tables can still be sensitive:
restrict table access and do not publish them automatically.

## Private networking and acceptance

Local OneLake connectivity does not establish access with public networking
disabled. Validate collector-to-OneLake, Fabric execution/data access, DNS,
tenant Private Link policy, runtime identity and any future outbound destination
independently. Do not enable public access or assume a shortcut bypasses policy.
Private-network validation is a deployment acceptance gate, not implemented
infrastructure in these notebooks.

For workspace acceptance, compare selected inputs/results with Power Query,
check both permission modes and a known failed/empty cycle, rerun unchanged
inputs to confirm unchanged table counts, inspect partial/invalid coverage,
and verify a newer zero-edge observation does not retain prior selected edges.
Review raw/curated permissions and costs before scheduling.

## Notebook 06: saved rerun baseline

After 01-04 publish successfully, attach the same default Lakehouse to
`06_monitor_validation.ipynb`. Match `RAW_ROOT`, `TABLE_PREFIX` and
`PERMISSION_MODE` to your other notebooks. The workflow is:

1. Keep collectors and other table writers idle; do not change raw files during
   the experiment. Run 06 with **`VALIDATION_ACTION = "capture"`** and a new
   `BASELINE_NAME`, initially `rerun_baseline_001.json`.
2. The notebook checks all ten table contracts/schemas, duplicate or null
   observation IDs, metadata validity, and stable raw/table inputs. It saves only
   hashes, counts, settings, Delta table IDs and versions to
   **`Files/monitor_validation/<BASELINE_NAME>`**. It never overwrites an existing
   baseline, writes into `Files/monitor`, changes controls or changes Delta tables.
3. Rerun 01-04 with `WRITE_TABLES = True` and unchanged evidence/settings.
4. Run 06 with **`VALIDATION_ACTION = "compare"`** and the same baseline name.
   Restarting the notebook session is fine; the baseline is read from the Lakehouse.
   Exact multiset comparison against the saved Delta versions detects same-count
   mutations as well as added/deleted rows. A new Delta commit with identical
   contents is allowed.

`PASS` means unchanged-input rerun stability, **not** full data acceptance.
Review freshness and coverage separately: stale observations, unknown timestamps,
failed/invalid/unfinished coverage, and legacy unverified inputs remain visible.
Freshness is for the latest **known** retained time per module/mode; unknown-time
attempts explicitly leave the newest attempt uncertain. Coverage summaries are
retained observations, not a current permission union or proof of complete scope.
They display at most 200 aggregate groups, never principal rows or connection paths.

Changed raw evidence or settings yields `NOT_COMPARABLE`, not an idempotence
failure. A replaced table or changed content fails the comparison. Concurrent
changes during inspection abort the run. Empty tables can pass identity/rerun
checks without proving data availability. Expected collector modules, actual
scope, a known failed/empty cycle, and Power Query parity still need manual review.

The saved metadata does not retain Delta data files or history. Compare promptly;
do not vacuum or change retention during the test. An unavailable baseline version
is `UNVERIFIED`, never `PASS`. A missing/invalid/partially written baseline requires
investigation or a new baseline name, not overwriting the previous file. Review
access to these operational metadata files and never commit them or executed
outputs. Capture writes only its new baseline file; compare is read-only.

## Expanded validation scope

By default, 06 validates the original ten core tables and their original source
folders. Existing core baselines remain readable. After publishing all of 07-11,
import the updated 06 and set **`INCLUDE_ESTATE_TABLES = True`** to validate all
25 managed tables, including the shared estate coverage table. Capture a new
baseline name for this expanded scope; different table selections are
`NOT_COMPARABLE`. The schema/ownership contract for existing core tables is unchanged.
Known missing-source diagnostics legitimately have no source hash; they remain
coverage warnings, not malformed metadata.

After publishing all of 12-21 as well, set **`INCLUDE_MODULE_TABLES = True`** to
validate all **48** datasets; this implies estate tables, regardless of the estate
flag. Capture another new baseline name, rerun all transformation notebooks in
that scope, then compare. The default ten-table and opt-in 25-table scopes retain
their previous table/source selections; neither silently expands to 48.

## Question-driven notebooks 07-11

Import the five additional notebooks, attach **lh_monitor** as the default
Lakehouse, and keep the same raw root/table prefix as 01-06. Each reads only its
relevant source folders within the existing safety limits. Run in preview
(`WRITE_TABLES = False`), inspect charts and coverage, then rerun with writes
enabled. There are no new API requests, collectors, grants or scheduled runs.
No data is sent to Eventhouse or Splunk.

| Notebook | Questions and source | Boundaries |
|---|---|---|
| `07_monitor_activity_events.ipynb` | What activity operations were recorded, when, in which workload/workspace/item, and how many distinct actors/event IDs? Reads `activity/`. | Power BI activity evidence, not every Fabric/Azure/Purview log. Event time is provider-defined UTC; collection time/completeness are unverified. Actors are stable unsalted SHA-256 pseudonyms, **not anonymous**; names/UPNs, IPs and payloads are excluded. |
| `08_monitor_estate_catalog_schema.ipynb` | Which collected workspaces/items exist, and which semantic-model tables, columns, measures and relationships were returned? Reads `items/`, `workspaces/`, `catalog/scans/`. | Missing model schema is `not_returned`, not zero tables. Returned empty arrays are distinct from omitted arrays. Warehouse/Lakehouse item inventory does **not** discover their physical schemas. Expressions are not exported; measure expression availability is recorded. |
| `09_monitor_connections.ipynb` | What connection types/privacy levels were observed and which gateway IDs are associated with them? Reads `fabricconnections/`. | Caller-visible, not tenant-complete. Validate immutable runs/endpoints; failed/unfinished resources create no connection facts. Healthy empty resources have zero records; failed/unknown resources have null counts. Connection paths and credentials remain excluded. |
| `10_monitor_gateways.ipynb` | What gateways/datasources were collected, and which connectivity responses were observed? Reads `gateways/`. | Missing status/detail files are flagged. Historical status is not current connectivity, tenant completeness or guaranteed VNet coverage. Legacy JSON-encoded arrays are supported. User lists, connection details and raw error messages are excluded. |
| `11_monitor_refresh_history.ipynb` | What dataset refresh statuses, durations and failure codes were retained, and what refreshable inventory/statistics were returned? Reads `datasetrefresh/`, `datasetrefreshable/`. | Dataset refresh history is separate from Fabric item jobs. API windows/gaps cannot be reconstructed. Ongoing/inverted/unknown durations remain null; missing failure counts are not zero. Error messages and configured-by identities are excluded. Refreshable kinds remain as returned, or unknown. |

Each includes domain charts and bounded metadata views as appropriate. Charts
explicitly count **retained raw-file observations**, not current unique inventory
or deduplicated refresh KPIs. Event/refresh identity counts appear separately.
Repeated history windows and daily snapshots can produce multiple observations
of the same event, run, gateway, model or connection. Table consumers must select
the appropriate date/source and grain rather than unioning all snapshots as current.
Metadata views show at most 100 rows; this is not exhaustive estate display.

Legacy daily files have no immutable completion manifest or exact collection
timestamp. `source_date` is a folder date only; real event/refresh timestamps
are separate fields. Activity and dataset refresh timestamp fields are defined
as UTC by the provider, including values serialized without a timezone suffix.
Legacy source versions use content-versioned observation IDs and insert-only
persistence, never destructive updates. Unsupported/malformed recognized files
are quarantined into `estate_coverage` with null counts, not successful empty facts.
No supported files produces an explicit NOT COLLECTED preview; optional empty
tables do not prove collection success. Missing categories/types and collector
visibility must be reviewed before claiming estate completeness or scheduling.
Review access to these tables: schema names/resource identifiers and actor
pseudonyms can still be sensitive.

## Remaining-module notebooks 12-21

Import these ten notebooks, attach **lh_monitor** as default, preview with
`WRITE_TABLES = False`, then enable writes after inspecting coverage. They read
existing files only. A module that has not collected usable files produces
**NOT COLLECTED**, not fabricated business rows. Missing expected artifacts are
shown separately, including optional Graph groups and delegated-setting scopes.
Legacy snapshots cannot establish pagination completeness or exact collection time.

| Notebook | Questions | Important limits |
|---|---|---|
| `12_monitor_apps.ipynb` | Which apps and owning workspace IDs were observed? | App inventory, not audience/access membership; complete paging is unverified. |
| `13_monitor_capacity_performance.ipynb` | Which capacity SKUs/states/regions and utilization/carryover timepoints were collected? | CapacityMetrics is opt-in. Known returned measures retain provider values/units, nullable values and query date. A naive timepoint has unknown UTC. Charts select one capacity/group/metric/query-day/source-date; snapshots must not be added as KPIs. |
| `14_monitor_directory_licensing.ipynb` | Which user types/account states, group types, user memberships, licenses and subscribed SKU quantities were observed? | Group extraction is optional; membership extraction is capped and contains transitive **users**, not direct nesting/effective access. Missing quantities remain null. Names, UPNs and mail are excluded. UUIDs remain joinable; opaque identities are hashed, not anonymous. |
| `15_monitor_workspace_roles.ipynb` | Which workspace role assignments were returned, and which workspaces lacked role details? | Missing/null users differs from an empty returned list. Workspace roles are distinct from item grants and do not compute effective permissions. |
| `16_monitor_tenant_settings.ipynb` | Which tenant settings, delegated overrides and enabled/excluded security-group rules were observed? | Keeps capacity/domain/workspace scope and delegation origin separate; no inferred precedence or effective policy. Missing override collections stay unknown. |
| `17_monitor_domains.ipynb` | Which domains and workspace associations were retained? | The collector omits domains with no workspaces; this is not complete domain inventory. Duplicate domain metadata is collapsed within a source; conflicting metadata quarantines that file. |
| `18_monitor_git_connections.ipynb` | Which providers/repositories/branches, connection states and sync times were returned? | No code or live sync-health verification. Owner and directory values are hashed; URLs and credentials are excluded. Organization/project/repository/branch names remain sensitive metadata. |
| `19_monitor_tags.ipynb` | Which tag definitions and tenant/domain scopes were observed? | Item/tag assignments are not collected. |
| `20_monitor_broad_sharing.ipynb` | Which artifacts had organization-wide or publish-to-web sharing observations? | No link URLs, sharer names/emails or live link verification; not complete effective-access evidence. |
| `21_monitor_deployment_pipelines.ipynb` | Which pipelines, deployment operation statuses/times and failed history polls were retained? | Caller-visible discovery; history needs pipeline Admin and exposes up to 20 recent deployments. Valid finished partial runs retain independent outcomes; failed counts are null, healthy empty counts zero. Invalid/unfinished runs produce no facts. No deployments are triggered. |

## Registered collector coverage

Every one of the **23 registered modules** now has a curated business-data path.
This matrix describes selected fields, not every raw field, successful collection
or tenant-complete coverage. Raw JSON and controls remain unchanged.

| Registered module | Raw folder(s) | Notebook / table family | Deliberate partial coverage |
|---|---|---|---|
| Activity | `activity` | 07 / `activity_events` | Selected event fields; no raw identity/IP/payload |
| Apps | `catalog/snapshots` | 12 / `apps` | Inventory only |
| Capacity | `capacity` | 13 / `capacities` | Selected capacity metadata |
| CapacityMetrics | `capacity_metrics` | 13 / `capacity_metric_observations` | Known utilization/carryover measures; optional collection |
| Catalog | `catalog/scans`, `lineage_edges` | 01, 04, 08 / inventory, lineage, `catalog_*`, `model_*` | Scanner-returned schema only; no expression text or physical Lakehouse/Warehouse schema |
| DelegatedSettings | `delegatedsettings` | 16 / `delegated_setting_*`, `tenant_setting_groups` | Observed rules, not effective policy |
| Domains | `domains` | 17 / `domains`, `domain_workspaces` | Domains without workspaces absent upstream |
| FabricConnections | `fabricconnections` | 09 / `connection_observations` | Caller-visible; no connection paths or credentials |
| FabricDeploymentPipelineOperations | `fabricdeploymentpipelineoperations` | 21 / `deployment_*` | Caller-visible recent history and resource outcomes |
| FabricItemAccessPermissions | `fabricitemaccesspermissions`, `fabricitemaccesspermissions_tenant` | 02 / `permission_*` | Selected mode/cycle; no effective-access/group expansion |
| FabricItemDefinitions | `fabricitemdefinitions` | 04 / `lineage_*` | Static references/diagnostics only, not a complete definition-part catalog |
| FabricItemJobHistory | `fabricitemjobhistory` | 03 / `job_*` | Retained polling history, not every historical execution |
| FabricItems | `items` | 01, 08 / `inventory`, `catalog_items` | Selected inventory fields |
| Gateway | `gateways` | 10 / `gateway_*` | Selected inventory/connectivity; gateway users/access deliberately excluded |
| GitConnections | `gitconnections` | 18 / `workspace_git_connections` | Selected integration metadata |
| Graph | `graph` | 14 / directory, membership, license, SKU tables | Optional/capped memberships; selected non-name fields |
| RefreshHistory | `datasetrefresh` | 11 / `refresh_observations` | Retained API history; no raw failure messages |
| Refreshables | `datasetrefreshable` | 11 / `refreshable_observations` | Selected inventory/statistics |
| Roles | `roles` | 15 / `workspace_role_*` | Observed workspace roles only |
| Tags | `tags` | 19 / `tags` | Definitions only |
| Tenant | `tenant` | 16 / `tenant_settings`, `tenant_setting_groups` | Returned tenant settings, not complete effective policy |
| WidelySharedLinks | `widelysharedlinks` | 20 / `organization_shares`, `publish_to_web_shares` | Artifact exposure metadata only |
| Workspaces | `workspaces` | 01, 08 / `inventory`, `catalog_workspaces` | Selected inventory fields |

## Development

The `.py` files are tested source; the generated `.ipynb` files are the upload
artifacts. Shared code and the existing pure scanner normalizer are embedded
into each notebook, so no repository imports remain in the upload.

```bash
.venv/bin/python notebooks/build_monitor_notebooks.py
.venv/bin/python -m unittest tests.test_monitor_notebooks tests.test_monitor_module_notebooks -q
ruff check --target-version py310 notebooks/monitor_analytics.py \
  notebooks/monitor_fabric_runtime.py notebooks/monitor_visualizations.py \
  notebooks/monitor_validation.py notebooks/monitor_estate_analytics.py \
  notebooks/monitor_module_analytics.py \
  notebooks/build_monitor_notebooks.py \
  tests/test_monitor_notebooks.py tests/test_monitor_module_notebooks.py
ruff check --target-version py310 --config 'builtins = ["spark", "display"]' \
  notebooks/[0-2][0-9]_monitor_*.ipynb
ruff format --check notebooks/[0-2][0-9]_monitor_*.ipynb
```

Do not edit generated cells or commit executed notebook outputs. Regenerate
after source changes; tests detect stale generated notebooks.
