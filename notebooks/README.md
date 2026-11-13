# Monitor analytics notebooks

The 26 numbered notebooks transform, visualize and validate **existing collected
evidence**, not API responses fetched by a second collector. They are
self-contained `.ipynb` files:
upload the notebooks themselves, with no repository checkout, Python helper
upload, credentials, `%run` dependency or package installation cell.

The older `activity.ipynb`, `catalog.ipynb`, `Deconstruct.ipynb` and `nbk.ipynb`
experiments have been removed. They are not prerequisites for this suite.

## Silver and Gold first slice

Upload [24_monitor_silver_events.ipynb](24_monitor_silver_events.ipynb) into the
workspace's **Silver** folder and
[25_monitor_gold_event_cases.ipynb](25_monitor_gold_event_cases.ipynb) into **Gold**.
Create the `silver` and `gold` schemas in the same Lakehouse and attach it as
default to both notebooks. Run Silver preview first with automatic tenant discovery
(`AUTO_DISCOVER_TENANT=True`, `TENANT_ID=""`), or an explicit manual tenant override;
publish Silver before Gold can read its ready build. Both default to
`WRITE_TABLES=False`; raw actor/IP values are suppressed by default.

These are separate owned medallion snapshots, not additions to the existing
50-dataset Bronze contract or notebook 06 scopes. They are not included in
`nb_orchestrator`. See [medallion runbook and contracts](MEDALLION.md) for event
correlation, publication/access safeguards, limits and remaining work.

For read-only per-event investigation, import
[26_monitor_gold_investigation.ipynb](26_monitor_gold_investigation.ipynb) into
**Gold** after publishing 24/25. It opens its own pinned Gold views, lets you
select events, and prints/displays trace, activity and location queries per key.
No pasted setup or helper upload is required; see [Gold query examples](GOLD_QUERIES.md).

## Optional serial orchestrator

Import [nb_orchestrator.ipynb](nb_orchestrator.ipynb) as **nb_orchestrator** to
run all 19 transformation notebooks from one entry point. Attach the same default
Lakehouse to it and its children. Its parameter cell lets you select notebook
names, raw root, table prefix, permission mode, timeout and `WRITE_TABLES`
(False by default). Preview manually, then enable writes when ready.
Notebook 22 is a separate opt-in: import it, then set the orchestrator's
`INCLUDE_PIPELINE_ACTIVITY = True` to add it to the existing 19 writers.
Notebook 23 is a separate read-only investigation tool and is never added
to the orchestrator.

It attempts every selected notebook serially, displays a named success/failure
summary and raises if any failed so a calling pipeline fails too. Collection
coverage warnings are separate from execution failures; inspect child-run
outputs. Notebooks 05 and 06 are intentionally excluded. Avoid overlapping runs
and other writers to the same prefix. After manual acceptance, test it through
a pipeline under the intended execution identity before scheduling.

## Choose a guide

| Need | Read |
|---|---|
| Understand Bronze/Silver/Gold, the transformations, your preview and remaining gaps | [Medallion explanation](MEDALLION_EXPLAINED.md) |
| Query published Gold event cases, artifact labels, traces and metrics | [Gold query examples](GOLD_QUERIES.md) |
| Understand what each of 01-26 does, choose a notebook, or follow the run order | [Notebook walkthrough](notebook-guide.md) |
| Refine Bronze events/artifacts into Silver and Gold investigation cases | [Medallion runbook](MEDALLION.md) |
| Investigate one resource across inventory, access, activity, jobs and references | [Optional notebook 23](#optional-notebook-23-resource-investigation) |
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
| 04 Lineage | `lineage_resources`, `lineage_edges`, `lineage_diagnostics` | One item/evidence observation, including zero-edge items; one directional reference or configured association; one diagnostic |
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
| 22 Pipeline activity (optional) | `pipeline_activity_resources`, `pipeline_activity_observations` | One collection/resource outcome; one activity run per retained successful query observation |
| 23 Resource investigation (optional) | None | Read-only, bounded evidence sections for one explicit workspace/item |

There are **50 managed datasets** across 20 transformation notebooks when optional
22 is included; the existing 19 writers still publish their original 48. Notebook 05
is read-only visualization; 06 validates and optionally saves baseline metadata;
23 is read-only investigation. Neither orchestrator defaults nor validation
table scopes change when importing 23.

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
Updated notebooks recognize a typed Dataflow not-found lookup followed by a
quota-paced untyped **Admin** lookup. A strictly validated pending transition
holds the cursor and prior health; it is not a successful empty permission poll.
The original 404 remains historical evidence, while a failed final lookup still
makes the cycle unhealthy. Reimport the regenerated notebooks together with the
collector update. Existing unhealthy cycles resume rather than being reset or
retroactively repaired; further collector invocations and a fresh cycle may be
needed before the checkpoint succeeds.

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
analysis; no source code or SQL is executed. Scanner relationships,
`static_inference`, `configuration_metadata` and optional
`shortcut_configuration` and `eventstream_configuration` remain separate.
**None proves runtime I/O.** Job
execution status does not verify a lineage edge. Dynamic/unsupported expressions
remain diagnostics rather than guessed dependencies. Raw definition contents,
connection payloads and failure messages are not copied to the curated tables.

**Configured Lakehouses:** notebook 04 also reads
`decodedParts["notebook-content.ipynb"].metadata.dependencies.lakehouse` from
retained successful definitions, including captures made before this analytics
update. It adds `configuration_metadata` resource/edge observations to the
existing lineage tables, without adding tables, collection requests or permissions.
`relation_type` is `default_lakehouse` or `known_lakehouse`,
`direction="association"`, `resolution="configured_id"` and
`runtime_verified=false`. These declarations do not establish read/write activity,
existence, access rights or effective permissions. A known Lakehouse is not
necessarily used by the notebook.

Identifiers are UUID-validated and duplicate Lakehouses are collapsed, preferring
the default role. Workspace IDs come only from explicit metadata, including a
duplicate declaration; missing IDs stay null rather than assuming the notebook's
workspace. Names and arbitrary metadata are not exported. Missing decoded notebook
content produces `missing` configuration coverage; absent attachment declarations
in available content produce a successful zero. Malformed/conflicting declarations
produce `invalid` coverage and no configuration edges, without discarding independent
static references. Failed resources remain failed, not successful empty associations.

Regenerate/import the updated notebooks, run 04 in preview and inspect its
configuration coverage before enabling `WRITE_TABLES`. After publication, 05 draws
configured associations as dashed green lines without dataflow arrows. Scanner
and potential static references retain their existing styles. Historical rows
remain observations, not proof of current configuration; unchanged-input reruns
are insert-only and do not duplicate them. Dashboard/PBIP integration is not added.

**Optional shortcuts:** enable the `FabricShortcuts` collector separately, then
set `INCLUDE_SHORTCUTS=True` consistently in 01-04 (or `nb_orchestrator`) and 06.
The default is False. Notebook 01 includes collection health, and 04 appends
`shortcut_configuration` evidence to the existing lineage tables. Table counts
and default raw scopes do not change; changing this flag requires a new baseline.
Old baselines remain readable as shortcut-disabled.

OneLake target workspace/item UUIDs are configured identities, not verified
existence, access or runtime I/O. External references are fingerprints; missing
target details and unsupported types remain unresolved edges with diagnostics.
Names, paths, URLs and arbitrary payloads are not exported. Shortcut transforms
are reported only as nullable configuration flags. Fingerprints are not anonymity
or a guarantee of matching physical storage.

Notebook 05 draws shortcut associations as dashed green, non-directional lines.
Automatic selection requires shortcut collection health from 01, uses the
latest successful collection attempt's exclusion scope, and selects latest item
attempts before filtering success. A latest partial/failed collection suppresses
automatic shortcut edges rather than falling back; empty item observations clear
older selected edges. Historical rows remain available with an exact
`LINEAGE_SOURCE_PATH`. No target traversal, bucket/table scan, access test or
runtime lineage is performed. See [collector permissions, scope and
quotas](../docs/configuration-reference.md#lakehouse-shortcut-relationships-fabricshortcuts).

**Optional Eventstream topology:** separately enable `FabricEventstreamTopology`
for collection, then set `INCLUDE_EVENTSTREAM_TOPOLOGY=True` in 01-04 or
`nb_orchestrator`, and match it in 06. It defaults to False, adds raw evidence
to the existing health/lineage tables and changes no table/writer counts.
Changing it requires a new baseline, even with no new raw files.

`eventstream_configuration` separates node membership (`topology_node`),
declared input links (`topology_input`) and selected targets (`topology_target`).
`record_count` counts these graph records, not events or executions. Sources,
streams, operators and destinations are represented without connector payloads,
names, URLs, queries or schemas. Names become fingerprints scoped to the owning
item; selected reported statuses are not measured runtime health. Explicit
supported target workspace/item IDs are configuration only; event-source targets
can be subscription scope, not data dependencies. Missing workspaces are never
inferred. Missing inputs, dangling names and unsupported targets remain diagnostics.

Notebook 05 draws membership in dashed gray, declared inputs as dashed purple
configuration arrows, and targets as non-directional dashed green associations.
Latest successful sweep selection prevents fallback after newer failed/empty
attempts; exact historical source selection remains available. No events are
read, operators executed, targets traversed or permissions tested.
See [API permissions and collection boundaries](../docs/configuration-reference.md#eventstream-topology-fabriceventstreamtopology).

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

Notebook 22 is excluded from all three scopes by default. After publishing it,
set **`INCLUDE_PIPELINE_ACTIVITY_TABLES = True`** to add its two tables and raw
source prefix to whichever scope you selected (12, 27 or 50 tables). Capture a
new baseline name: changed table/source scope is `NOT_COMPARABLE`, not a rerun
failure or permission to replace an older baseline. No existing table schema,
contract version or default validation/orchestrator scope is changed.

## Optional notebook 22: Data Factory pipeline activity

Import `22_monitor_pipeline_activity.ipynb`, attach the same default Lakehouse,
match `RAW_ROOT`/`TABLE_PREFIX`, and preview before enabling `WRITE_TABLES`.
It reads only retained `fabricpipelineactivityruns` snapshots. It neither
collects data nor executes pipelines; the executing Fabric identity needs raw
read access and, for publication, Delta-table write access.

`pipeline_activity_resources` separates collection, inventory, pipeline-job
history and activity-query coverage. A successful empty job list has a known
zero job count but **does not invent an activity-query result or zero activity
metrics**. Missing/failed/unfinished/invalid evidence remains unknown.
`pipeline_activity_observations` has one activity per successful query source,
not repeated rows per endpoint. Explicit mode never invents an owning item ID.
Both tables retain mode, source hashes/times and `scope_id`; query rows also
retain the explicit UTC last-updated window. Activity facts retain reported
status/timing, selected native output metrics and optional child-run identity.
No inputs, error text or arbitrary outputs are exported; activity names and IDs
still require restricted storage.

Historical polls remain separate. The preview selects the latest configured
scope in each mode, then the latest query attempt per workspace/run **before**
admitting metrics. Failed or successful-empty queries never fall back to older
metrics. Unknown-time/invalid/unfinished collection attempts block automatic
selection; `ACTIVITY_SOURCE_PATH` can explicitly select one valid historical
query. Different query windows are not a complete current-state or lifetime
history guarantee. Discovery sweep-health flags are not independently certified
tenant completeness.

Missing metrics stay null; explicit zero stays zero. Throughput retains its
reported engine/activity units; do not sum rates, infer throughput from query
window length, or add chained activity row/byte counts as distinct pipeline
movement. Runtime activity facts do not establish runtime lineage.
Notebook 03 remains item job history; 21 remains deployment operations.
The existing notebook 05 charts do not automatically include these extra tables.

## Optional notebook 23: resource investigation

Import `23_monitor_investigation.ipynb`, attach the same default Lakehouse and
match `TABLE_PREFIX`. Publish 01-04 for inventory, health, item access, jobs and
lineage; publish 07 for activity events and activity-analysis coverage.
Unpublished sections report **NOT PUBLISHED / UNKNOWN** and do not stop the
other sections. An existing table with an invalid Monitor ownership contract
raises an error rather than masquerading as missing evidence.

**Discovery is automatic by default (`AUTO_DISCOVER=True`)**; no workspace/item
IDs are required up front. Run with the default parameters to see distinct
workspace/item pairs from retained `inventory`. A unique match opens its
investigation automatically. Multiple matches show numbered choices and stop
before investigating any item; nothing is selected arbitrarily.

Narrow the list with optional case-insensitive `WORKSPACE_SEARCH` and
`ITEM_SEARCH` name substrings or exact `ITEM_TYPE`. Optional canonical
`WORKSPACE_ID` / `ITEM_ID` filters work independently, including for unnamed
resources. Alternatively set `RESOURCE_NUMBER` to a displayed number and rerun.
Numbering applies to the **current run's** filtered, ID-sorted list and can
change with inventory/filters; use the displayed IDs for a stable selection.
Leave `RESOURCE_NUMBER=0` when changing filters to use unique-match automation.
With `AUTO_DISCOVER=False`, discovery is skipped and both explicit UUIDs are
required; manual investigation also works when inventory is unpublished.

Discovery deduplicates workspace/item pairs across retained sources/modes,
excluding Workspace records as item candidates. Workspace names come from those
retained Workspace records; missing names stay unknown. Filters can match
historical names, including prior names. Display hints are alphabetically first
retained matching labels, **not authoritative current names/types**. Missing
workspace/name evidence is not fetched from APIs or guessed. Item candidates
can include resources no longer present; discovery is an index, not a current
or complete estate. It does not merge permission evidence between modes.

Set one `PERMISSION_MODE` for the investigation.
An optional exact `PERMISSION_CYCLE_ID` restricts the permission sections.
Without it, grants/resources remain individual historical observations across
all retained cycles **in that mode**, never a merged effective/current access
list. No group expansion or workspace-role inheritance is calculated.
Collection health and permission-cycle outcomes are labelled collection/cycle-wide,
not resource coverage; activity coverage is analysis-wide.

Each section preserves row-level provenance and coverage. This is a dossier of
retained evidence, **not a synchronized snapshot, current inventory, complete
history, deletion detector or aggregate permission list**. A later failed/empty
attempt does not erase older rows or make those rows current. Read resource
outcomes alongside facts. Null observation times stay unknown; event timestamps
and legacy folder dates do not substitute for collection time. Repeated polls,
event observations and grants must not be added as distinct operations/access.

Lineage includes owned references and direct incoming references only when both
related workspace and item IDs explicitly match. Unknown workspaces are not
inferred. Incoming rows retain the referencing item's provenance. Scanner,
static inference and configuration evidence remain distinct; no traversal,
runtime I/O verification or removal-impact calculation is performed. Activity
events without explicit matching workspace/item IDs cannot be attributed.

`MAX_ROWS_PER_SECTION` defaults to 200 and permits 1-1000. Each Spark query
collects at most the limit plus one row to detect truncation; only the limit is
displayed. Unknown-time rows sort first, followed by newest known observations,
with observation ID as a deterministic tie-breaker. Truncated sections are not
complete totals. Discovery uses the same limit plus one to detect truncation
of distinct candidate pairs; a truncated list of one never counts as a unique
match. This bounds driver/display data, **not Spark table scans/cost**.

The notebook needs only curated-table read access under its executing Fabric
identity. It adds **no APIs, Admin/non-Admin divergence, collection permissions,
managed tables, writes, baselines, scheduling or workload execution**; existing
[collector scopes and permissions](../docs/configuration-reference.md) remain
unchanged. Restrict notebook/table access: identifiers, item names, assignments
and dependency references can be sensitive. Clear outputs before sharing.

For live acceptance, run first with blank IDs to verify discovery. Check a unique
name/type match, an ambiguous list, numbered selection, missing names/inventory,
truncation and the manual opt-out. Select a known item and verify exact cross-workspace
isolation, both permission modes and an explicit historical cycle; compare
failed/empty resource attempts with retained facts, known incoming references
and missing/unattributed activity. Test a low row cap and an unpublished domain.
Local tests do not establish Fabric execution or private-network access.

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

Every one of the **26 registered modules** has a curated business-data path
when its corresponding optional notebook is included.
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
| FabricEventstreamTopology | `fabriceventstreamtopology` | 01, 04, 05 with `INCLUDE_EVENTSTREAM_TOPOLOGY=True` / health, lineage | Eventstream Read required; declared nodes/inputs and selected targets, never runtime/target-access proof |
| FabricItemAccessPermissions | `fabricitemaccesspermissions`, `fabricitemaccesspermissions_tenant` | 02 / `permission_*` | Selected mode/cycle; no effective-access/group expansion |
| FabricItemDefinitions | `fabricitemdefinitions` | 04 / `lineage_*` | Static references/diagnostics only, not a complete definition-part catalog |
| FabricItemJobHistory | `fabricitemjobhistory` | 03 / `job_*` | Retained polling history, not every historical execution |
| FabricItems | `items` | 01, 08 / `inventory`, `catalog_items` | Selected inventory fields |
| FabricPipelineActivityRuns | `fabricpipelineactivityruns` | Optional 22 / `pipeline_activity_*` | Mixed Admin/non-Admin collection; recent API history, query windows and workspace opt-outs; no runtime-lineage inference |
| FabricShortcuts | `fabricshortcuts` | 01, 04, 05 with `INCLUDE_SHORTCUTS=True` / health, lineage | Lakehouses only; item Read required; configured IDs or unresolved fingerprints, never runtime/target-access proof |
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
artifacts. Shared code, the pure scanner normalizer and the configured-Lakehouse
extractor are embedded
into each notebook, so no repository imports remain in the upload.

```bash
.venv/bin/python notebooks/build_monitor_notebooks.py
.venv/bin/python -m unittest tests.test_monitor_notebooks tests.test_monitor_module_notebooks tests.test_monitor_pipeline_activity tests.test_shortcut_relationships tests.test_eventstream_topology tests.test_monitor_investigation -q
ruff check --target-version py310 notebooks/monitor_analytics.py \
  env/utility/notebook_relationships.py \
  env/utility/shortcut_relationships.py \
  env/utility/eventstream_topology.py \
  notebooks/monitor_fabric_runtime.py notebooks/monitor_visualizations.py \
  notebooks/monitor_validation.py notebooks/monitor_estate_analytics.py \
  notebooks/monitor_module_analytics.py \
  notebooks/monitor_pipeline_activity.py \
  notebooks/monitor_investigation.py \
  notebooks/build_monitor_notebooks.py \
  tests/test_monitor_notebooks.py tests/test_monitor_module_notebooks.py \
  tests/test_monitor_investigation.py
ruff check --target-version py310 --config 'builtins = ["spark", "display"]' \
  notebooks/[0-2][0-9]_monitor_*.ipynb
ruff format --check notebooks/[0-2][0-9]_monitor_*.ipynb
```

Do not edit generated cells or commit executed notebook outputs. Regenerate
after source changes; tests detect stale generated notebooks.
