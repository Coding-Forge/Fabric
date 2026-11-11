# Changelog

## Solution and notebook documentation

- Refresh the solution overview to distinguish API collection, the 21-notebook /
  48-dataset analytics suite and optional downstream consumption.
- Add a [notebook-by-notebook walkthrough](../notebooks/notebook-guide.md), import/run order, 10/25/48-table
  validation workflow and troubleshooting guidance, linked to the technical
  contracts and full collector coverage matrix.
- Document [Eventhouse versus Event Hubs](analytics-integration.md), optional KQL shortcut access and the
  proposed separate Delta-to-Event-Hubs-to-Splunk publisher. No publisher,
  connector, schedule or destination resource is implemented by this update.
- Clarify collector-versus-analytics notebook setup, Catalog-only
  `ALL_WORKSPACES` behavior, retry upgrade implications and remaining runtime,
  privacy and private-network acceptance gates.

## Legacy API cooldowns and long-running authentication

- Honor full `Retry-After` seconds/HTTP dates for legacy API and Gateway requests.
  `API_MAX_RETRY_DELAY` now caps only fallback exponential backoff, never a valid
  server cooldown. Share server waits per API origin in one Context, including
  final exhausted responses, without occupying concurrency slots while waiting.
- All registered legacy collectors resolve cached/renewable authentication per
  HTTP attempt after waits; allow one cache-evicting retry on 401, not on 403.
  Preserve the throttle retry budget and existing durable Fabric request gates.
- Remove Roles' nested retry loop. FabricItems uses iterative paging, detects
  repeated/invalid pages and returns failure rather than treating an exhausted
  throttle as an empty successful inventory. Gateway authentication/throttle
  failures leave connectivity unknown and fail the collection.
- Legacy cooldowns remain in-memory and do not coordinate other processes,
  survive host restarts or guarantee absence of 429s. No tenant API collection,
  settings changes or deployment is performed by these local fixes.

## Remaining collector-module analytics

- Added self-contained notebooks 12-21 for apps, capacity/performance, directory
  and licensing, workspace roles, tenant/delegated settings, domains, Git
  connections, tags, broad sharing and deployment pipeline operations.
- Added 23 scalar datasets, bringing the suite to 21 notebooks and 48 managed
  datasets with selected-field paths for all 23 registered collectors. The
  notebook guide includes a module/source/table coverage matrix and exclusions.
- Preserve optional/unknown collections, unscaled nullable metrics, unknown UTC
  for naive timepoints, content-versioned legacy observations and strict
  immutable deployment-run validation. Exclude identities by name/mail, Git
  owners/directories in clear text, URLs, credentials and raw payloads.
- Notebook 06 opts into all 48 tables with `INCLUDE_MODULE_TABLES`; original ten
  and 25-table/source scopes remain unchanged. Expanded scopes need a new baseline.
- Existing files only: no API collection, grants, schedules, deployment actions
  or Eventhouse/Splunk exports. Local validation is not Fabric runtime acceptance.

## Question-driven Fabric estate analytics

- Added notebooks 07-11 for activity events, estate catalog/semantic-model schema,
  caller-visible connections, gateways and dataset refresh history/refreshables.
  Each provides curated scalar datasets, charts and explicit collection gaps from
  existing raw files only; no collectors, APIs, grants or deployments are added.
- Preserve unknown versus empty schema/counts, historical observation grain,
  nullable/inverted durations, and legacy versions without invented collection
  timestamps. Exclude actor UPNs, IPs, credentials, connection paths, expressions
  and raw error messages; actor pseudonyms are not anonymous.
- Add optional expanded notebook-06 validation for all 25 tables while preserving
  original ten-table baselines and core schemas. Missing-source diagnostic markers
  remain valid metadata with explicit missing coverage, rather than failing hash checks.
- Physical Lakehouse/Warehouse schema discovery, complete tenant gateway/connection
  visibility, all-service logging, scheduling and external exports remain outside
  this existing-evidence increment.

## Persistent Fabric notebook validation

- Added `06_monitor_validation.ipynb` with restart-safe metadata baselines in
  `Files/monitor_validation`, separate from raw evidence and curated tables.
- Validate ten table contracts/schemas and observation identities, compare exact
  retained Delta contents after unchanged-input reruns, and report freshness and
  coverage separately. Changed inputs are not comparable; unavailable baseline
  versions are unverified, not successful. Existing baseline files are not overwritten.
- No collectors, schedules or remote deployments are started. Saved baseline
  capture is the only new write; comparison never changes data or controls.

## Uploadable Fabric analytics notebooks

- Added five self-contained, output-cleared PySpark notebooks under `notebooks/`
  for inventory/collection health, separate Scoped/Tenant permission cycles,
  retained job history, scanner/static lineage and coverage-first visualizations.
- Reuse existing raw evidence without API collection, definition execution or raw
  writes. Preview is the default; explicit curated writes use versioned contracts,
  insert-only Delta MERGEs and ownership/schema/immutable-content guards.
- Preserve successful empty observations, failed/unknown counts, strict immutable
  run/permission-chain validation and static-versus-runtime evidence limits.
  Legacy daily inventory/raw scans remain unverified, without invented timestamps.
- Added offline collector compatibility tests, generated-cell checks and manual
  upload/acceptance guidance. Fabric execution, private-only networking and full
  native Power Query parity remain workspace acceptance steps. Eventhouse/KQL
  ingestion and Splunk delivery are not implemented or provisioned.

## Fabric manifest timestamp-order guard

- Final manifests now fail before commit if host UTC is earlier than any resource
  successfully saved in that run, including failed-resource observations.
  An incomplete initial manifest remains uncommitted and the exception prevents
  success/checkpoint advancement through the existing audit failure path.
- Forward or equal timestamps retain existing behavior. No UTC values are
  clamped, no extra requests or automatic retries are added, and report
  validation remains unchanged. This prevents new inconsistent commits; it does
  not repair the three historical job-history timestamp warnings or establish
  why their timestamps were inverted.

## MonitorRaw tenant-permission input

- Added refresh-time `ItemPermissionMode=Scoped|Tenant`, default `Scoped`, to the
  existing Item Permissions page. Local and Blob sources load exactly one
  permission folder; unknown modes fail rather than falling back or merging.
- Added tenant linked-evidence validation for paginated discovery, cross-workspace
  inventories beyond 50 items, ordered access cursors, failures/deferrals, unknown
  totals during discovery and healthy empty tenant replacement.
- Preserved one-cycle partial/stale selection, successful-grants-only import and
  disconnected global coverage measures; source mode is visible in diagnostics.
  No API requests, collector/grant changes, group expansion or Catalog integration.
  Native Desktop validation is separate from offline wiring and syntax checks.

## Nullable Power BI permission metadata

- Fixed rejection of observed HTTP 200 access responses with null
  `itemAccessDetails.type` or `additionalPermissions`, limited to the five
  explicitly query-typed Power BI item types. Scoped and tenant collection retain
  the original nulls; conflicting types, missing detail types and malformed
  principals/permission lists still fail.
- Kept the existing scoped MonitorRaw validator and nullable detail-type column
  consistent. This adds no API, scope, grants, tenant-report integration or
  automatic recollection; historical failures and Dataflow 404s remain separate.

## Opt-in tenant-wide permission collection (E14)

- Added `FABRIC_ITEM_ACCESS_MODE=tenant` for paginated active-item discovery and
  access collection across all items returned by the Admin Items API. The default
  remains `scoped`, with its existing explicit 1-50 item configuration unchanged.
- Both routes are preview Admin APIs; no regular resource APIs, workspace role
  grants, workload execution or Graph expansion are introduced. Unsupported and
  inaccessible items remain failed coverage rather than successful empties.
- Tenant discovery/items resume through versioned `tenant_progress.json` and
  linked immutable manifests. Existing durable quota/Retry-After controls and
  invocation budgets are shared with scoped collection; only wholly healthy
  completed cycles advance the module checkpoint.
- Tenant snapshots use `fabricitemaccesspermissions_tenant/`, separate from
  scoped PBIP inputs. No settings are enabled, no controls reset, and no PBIP
  integration or live acceptance is included. See [scope, enablement and recovery](configuration-reference.md#tenant-wide-permission-collection-opt-in).

## Explicit Admin and non-Admin API scope documentation

- Added a customer-facing API scope register distinguishing Admin/Scanner
  collection, mixed Admin discovery/resource retrieval, regular Fabric/Power BI
  APIs and Microsoft Graph. Documented resource permissions, collection boundaries,
  defaults, sensitive output and coverage limits, including existing non-Admin
  calls in default modules.
- Called out Contributor's broader powers for definition exports and the current
  lack of a definition workspace/item allowlist. Group-based grants simplify
  administration but do not grant tenant-wide export access or filter discovery.
- Required explicit scope documentation for future non-Admin API changes.
  Clarified delegated versus app-only authorization, Graph SKU permissions and
  semantic-model Read/Build requirements. Documentation only: no API, runtime,
  configuration, permission or deployment changes.

## Static pipeline activity references (E15)

- Added `pipelineReferences` to new `FabricItemDefinitions` pipeline captures,
  alongside unchanged original definitions and decoded JSON. Parses literal
  notebook/child-pipeline calls, supported Copy source/sink targets and nested
  ForEach/Until/IfCondition/Switch activities without additional API requests.
- References retain JSON Pointer evidence and explicit item/connection/table/path
  context. Pipeline names remain names; missing workspace IDs are not inferred.
  Evidence is static and unresolved, never proof of execution or effective access.
- Dynamic/unsupported targets, queries and file selectors have explicit
  diagnostics, not guessed data endpoints. Partial analysis is separate from
  successful capture; malformed containers and traversal limits fail closed.
- No workloads, settings/grants, report changes or automatic backfill.
  Definition-export authorization and live acceptance remain separate from
  offline tests. See [supported shapes and limitations](configuration-reference.md#notebook-and-data-pipeline-definitions).

## Opt-in notebook and Data Factory definitions

- Added `FabricItemDefinitions`: resumable tenant admin discovery of notebooks
  and Fabric Data Factory pipelines, permission-checked definition exports and
  immutable observations with decoded JSON. Pipeline activities are retained,
  not interpreted for lineage; no notebook/pipeline is executed.
- Added SQLGlot-backed Spark SQL and Python AST analysis of supported literal
  notebook table/file reads and writes. Evidence is explicitly static inference,
  with unresolved targets and diagnostics—not proof of actual execution or
  exhaustive notebook coverage. Existing Scanner graphs are unchanged.
- Added a restricted, nonredirecting definition/LRO transport using the existing
  shared retry/concurrency gates. Durable cooldowns, inventory/item cursors,
  pending export IDs and linked manifests allow multi-invocation sweeps.
  Denied/malformed items fail coverage without hiding later items; incomplete
  sweeps and persistence failures do not advance the success checkpoint.
- Definitions may contain embedded sensitive values. No settings or permissions
  are enabled automatically. See [configuration, API load and restricted-storage
  guidance](configuration-reference.md#notebook-and-data-pipeline-definitions).
  Live tenant/API/storage validation remains separate from offline tests.

## Catalog PBIP: custom lineage charts

- Added **Lineage Graphs** with Microsoft Sankey, Microsoft Chord and ZoomCharts
  Drill Down Network PRO, preserving the existing Lineage detail page and gallery
  registrations. Capability-role bindings were verified against public publisher
  sources; Network uses category-based `Nodes`/`Size`, not Graph's Source/Target.
- Graph links use only selected-snapshot upstream records, oriented source to
  consumer and deduplicated by endpoint pair. Weights count dependencies, not
  data traffic. Canonical ID-based nodes prevent same-named models/reports
  merging; optional focus selects links touching either endpoint.
- Consumer-workspace filtering, existing coverage warnings, load errors and
  observation timestamps remain visible. Chord/Network direction and category
  limitations are explained on the page and in the
  [Catalog guide](../pbip-local/Catalog/README.md#lineage-graphs-sankey-chord-and-zoomcharts-network).
- No API collection change or license purchase. Native Desktop/custom-visual
  rendering, interaction and licensing acceptance remains required.

## Catalog PBIP: direct lineage page

- Added workspace/item selectors, upstream/downstream dependency tables, counts,
  observation timestamps, returned-empty workspace coverage and disconnected
  file-load diagnostics to `pbip-local/Catalog/Schema.pbip`.
- The Power Query loader selects the newest complete snapshot per returned
  workspace before expanding inventory/edges. It preserves empty observations
  and unresolved IDs rather than combining historical relationships as current.
  Rejected files warn that the selected basis may be stale.
- Added `CatalogOutputPath`, defaulting to `C:\Projects\Tests\monitor-poc-output`,
  shared by lineage and the existing Catalog scan queries. Existing collected
  files can be viewed without a Functions restart or new API run.
- Offline report/model contracts, Microsoft M syntax parsing and published PBIR
  schema validation do not establish native M/DAX execution or Desktop rendering.
  See [operation and Desktop acceptance](../pbip-local/Catalog/README.md).

## Opt-in Scanner lineage observations

- `CATALOG_LINEAGE_ENABLED=true` derives upstream/downstream relationships from
  Catalog's existing scanner responses without extra HTTP calls. Default-off
  behavior and raw scan output are unchanged.
- Versioned JSON under `lineage_edges/YYYY/MM/DD/<scan-id>.lineage_edges.json`
  includes batch coverage, supported item inventory, and explicit empty results.
  Reports, semantic models, dataflows (`objectId`), and datasource dependencies
  are supported; cross-batch targets retain unresolved IDs and available metadata.
- Enabled extraction or snapshot-write failures prevent Catalog checkpoint
  advancement. Successful sibling batches may remain; this is not a whole-run
  transaction. No relationship change detection, full tenant graph, reporting,
  historical backfill, or additional Fabric API collection is included.
- See [configuration and rollout](configuration-reference.md#scanner-lineage).

## MonitorRaw: job query repair and report relocation

- Moved the full project to `pbip-local/MonitorRaw/`, retaining its relative report/model links and source configuration.
- Restored report-facing job columns, UTC dates, duration and latest-observation deduplication after Desktop query troubleshooting. Empty job and permission lists are excluded before fact expansion; scope and collection diagnostics retain successful empty outcomes.
- Removed the temporary raw-file date table and item-ID-only job/scope relationship introduced during troubleshooting.
- Report checks now distinguish Desktop filter-pane metadata from actual saved filter definitions; mutations still verify that active filters cannot hide health diagnostics. Native Power BI refresh and rendering acceptance remain pending.

## MonitorRaw: Collection Status nullable table fix

Final Code Reviewer verdict: **Approved — production and tests**. Reported validation: **10 targeted and 513 full offline tests passed** under environment-isolated DNS/socket guards, including two new static test methods; Ruff format/lint and Python 3.10 syntax checks passed (execution used Python 3.12). **Native M/Power BI Desktop refresh remains unverified.**

- Fixes the Collection Status constructor behind “The columns of the specified table type must be nullable.” All 24 explicit `Table.FromRecords` columns are now nullable for `MissingField.UseNull`, correcting six previously nonnullable annotations. Omitted permission metadata stays null, not false or zero; existing values and producer validation are unchanged.
- No collector, scope, authentication, gate, cycle, partial-selection, DAX or model metadata behavior changes. Reload the updated `MonitorRaw.pbip` and refresh in Desktop, preserving unsaved work separately rather than saving stale definitions over the checkout; verify the error clears. No Functions start/restart, new collection, deployment or VERSION bump is needed. See the [troubleshooting note](../pbip-local/MonitorRaw/README.md#things-that-can-surprise-you).

## MonitorRaw: single-cycle partial-permission report

Final Code Reviewer verdict: **Approved — cycle 2**, production and tests for four scoped semantic files, ten report visual JSON files and `tests/test_monitorraw_report.py`. Reported validation: **8 targeted and 511 full offline tests passed** under DNS/socket guards; Ruff format/lint, static Python 3.10 syntax and reference checks passed (114 JSON files, 24 tables, 12 pages, 188 valid field references). The requests dependency warning was nonfailing. **Native Desktop M/DAX/schema/refresh/render acceptance remains pending; E10 is not closed.**

- Supersedes the earlier whole-healthy-only permission selection below: use one validated cycle, preferring the newest useful finished cycle (including partially failed and successful-empty observations), otherwise the newest useful in-progress cycle. No cross-cycle grant merge/carry-forward; selected evidence and newer attempts remain distinct with explicit stale warnings.
- Only successful access observations supply grants. Scope/status distinguish successful empty, failed, deferred, known-not-attempted and unresolved targets; failure is unknown access, not zero/no access. Page 11 adds prominent partial coverage, global Successful/Expected targets and outcome/HTTP/time/identity/cycle scope evidence. Disconnected manifest-derived coverage cannot be hidden by principal/grant slicers; load-error counts remain integrity diagnostics, separate from collection failures.
- No collector, scope, gate, checkpoint, other-collector or job-history semantics changed. The Dataflow 404/`unrecognized` cause remains unresolved; neither Gen2 unsupported nor healthy completion is established. Existing output needs only Desktop reopen/reload and **Home > Refresh**, not API calls or a Functions start/restart. No VERSION bump.
- [Selection details and pending acceptance checklist](../pbip-local/MonitorRaw/README.md#item-permissions-and-fabric-jobs), including single-cycle partial/stale evidence and filter-resistant warnings. This documentation update makes no runtime-validation claim.

## Gated Fabric GET: safe error-code diagnostics

Final independent Code Reviewer cycle3 verdict: **Approved — implementation and tests**. Reported validation: **75 focused, 143 expanded and 511 full offline tests passed** (seven new tests), Ruff format/lint and static Python 3.10 syntax checks passed. Execution used Python 3.12.3 with cleared environment and DNS/socket guards; no Python 3.10 runtime or tenant API validation is implied. The requests warning was baseline.

- Failed GETs for the four opt-in Fabric collectors include numeric HTTP status and sanitized `errorCode` in logs, returned errors and persisted manifest error entries. Only Microsoft-documented `ItemNotFound` and `InvalidItemType` are allowlisted; other nonempty strings become `unrecognized`. Missing/malformed or unreadable diagnostics become `unavailable`.
- Exact nonempty top-level `errorCode` strings take precedence over nested `error.code`; malformed/missing top-level values fall back to nested strings. Body inspection is bounded to 16 KiB plus a one-byte probe and a one-second read budget, with no extra HTTP requests. The original non-200 status is preserved; all-path status sanitization excludes invalid values and booleans. No raw messages, details, bodies, IDs, URLs, headers, tokens or arbitrary type/representation/exception text enter these diagnostics.
- Diagnostics only: retry/gate behavior, scope acceptance, cycle health, checkpoints and report selection are unchanged. The actual Dataflow 404 cause and healthy end-to-end completion remain unverified; 36 saved rows do not establish whole-scope success. No unsupported-type conclusion, scope exclusion or state reset is warranted.
- [Operating guidance and synthetic examples](local-development.md#gated-fabric-get-safe-error-code-diagnostics): the user restarts only the Functions host once, leaves Azurite running and collects the next log locally in existing `log-dump.json`. Legacy logs may contain private payloads; do not share raw logs publicly. Inventory paging/bounded slices may precede the actual Dataflow request; no immediate completion guarantee or repeated forced cycles.
- No live API call, host restart or deployment was performed in the review. No VERSION bump or new configuration keys.

## Permission collection: budget-aware gate pacing

Final independent Code Reviewer cycle3/3 verdict: **Approved — both production and tests**. Reported validation: **68 focused and 504 full offline tests passed** (six new tests), Ruff and static Python 3.10 syntax checks passed; execution used Python 3.12.3, not 3.10. The requests dependency warning was nonblocking. **Live cycle success remains unverified**; no tenant call, host restart, deployment or Desktop validation was performed in the review.

- Permission admission waits the actual remaining UTC gate delay when it and the reserve fit the monotonic budget, allows an exact fit, and rechecks with at most three sleeps. The six-slice cap, 150-second budget and 35-second reserve remain; no fixed pacing sleeps or quota bypass.
- Deadline checks cover authentication/setup and reservation writes; slow reservation writes fail closed with pending state preserved. The budget is not a hard timeout for all authentication/storage work. Long cooldowns defer work, pending/blocked gates remain fail-closed, and only a healthy completed cycle advances `lastRun`. Non-opt-in behavior is unchanged.
- [Local operating guidance](local-development.md#repeated-permission-slices): the user restarts only the Functions host once, leaves Azurite running and inspects latest logs/progress—not a guarantee of a complete cycle or continuous slices. Never clear state/gates or loop manual requests. Existing empty pipeline/history results can be legitimate.
- No claim that the current 13-item cycle completed; no unrelated report/configuration approval or VERSION change.

## MonitorRaw: four-collector report reconciliation

Final cycle-2 Code Reviewer verdict: **Approved — BOTH production and tests**, for static technical scope. Reported independent validation: **8 structural test methods (32 mutation cases) and 498 full offline tests passed**, Ruff format/lint and static reference/parsing checks passed. These do not execute M/DAX or validate native TMDL schemas. **Power BI Desktop open/refresh, rendering and Local/Blob acceptance remain pending; E10 is not closed.**

- Expanded `pbip-local/MonitorRaw/MonitorRaw.pbip` from 10 to **12 pages**, adding **Item Permissions** and **Fabric Job History** alongside Connections inventory and Deployment operations. Added **Item Permissions**, **Item Permission Scope**, **Fabric Job History** and **Fabric Job Scope** tables. Disconnected Collection Status/About diagnostics and global `Load Errors` cover all four collectors.
- Permissions select the last whole healthy cycle across validated inventory/access evidence links. Later partial/failed cycles retain last-good grants with stale/previous-scope warnings; invalid/missing links contribute load errors. Explicit zero-grant coverage does not fabricate grants; permission lists do not multiply rows and groups are not expanded into complete effective rights.
- Jobs combine successful committed observations across all retained runs, keeping newest state per workspace/item/job instance, including jobs outside the recent-100 completed-job window and deselected targets. Scope outcomes remain separate; raw failure payloads are not imported.
- Reads immutable UTC resource envelopes and finished manifests. Connections use the latest healthy committed full snapshot; pipelines use latest committed successful discovery. Successful empty inventory clears prior rows; missing/failed/incomplete attempts warn rather than masquerading as empty success.
- Retains successful committed operation observations across all retained runs, deduplicated by pipeline/operation ID using newest `observedAt`, including old operations/pipelines outside current discovery or the API's recent-20 window. Caller-visible coverage is not tenant-wide; operation history requires pipeline Admin.
- Preserves null connection names with UI-only label fallback and safe metadata only. Inventory/history slicers cannot hide disconnected health; global `Load Errors` includes invalid/missing Fabric artifacts.
- Permissions/jobs collectors are currently disabled with scopes unselected: **Not collected** is expected, not healthy empty data. Report pages do not select scopes or enable collection. Choose exact workspace/item/type targets before later deliberate [configuration](configuration-reference.md#settings-and-enablement).
- Report files need only Desktop reopen/reload and refresh, not a Functions restart. Later collector enablement/restart is a separate authorized user action. Windows guidance, source contract and pending native acceptance checklist: [MonitorRaw README](../pbip-local/MonitorRaw/README.md). No VERSION change.

## FabricConnections nullable names and Catalog empty discovery

Final independent Code Reviewer cycle3 verdict: **Approved** for production and tests. Reported validation: **490 full offline tests passed**; live resolution is not established.

- `FabricConnections` accepts an observed HTTP 200 response with `displayName: null` and preserves the null without inventing a name or dropping the connection. Missing, empty-string and wrong-type names still fail validation; strict ID/connectivity validation and the metadata allowlist remain. Nullable names are observed behavior, not an explicitly documented API contract.
- Catalog discovery accepts `[]` or `{"value":[]}` as successful no-work (`True`): no scan or catalog save, and `lastFullScan` unchanged. Errors, malformed responses and `None` still fail. Successful no-work remains eligible for the normal audit `lastRun` update.
- Logging, gates and checkpoints are otherwise unchanged. Follow the [existing host-only restart and sanitized-diagnostics guidance](local-development.md#fabricconnections-sanitized-failure-diagnostics); do not reset state or gates.

## FabricConnections: sanitized failure diagnostics

Final independent Code Reviewer cycle3 verdict: **Approved** for both production and tests. Reported validation: **487 full offline tests passed**; this does not establish live resolution.

- Added safe numeric HTTP/status-unavailable warnings and schema diagnostics using fixed field paths, expected shapes, observed missing/null/empty/type labels and record ordinals, including conflicting duplicates and malformed pages.
- Request-failure logs, returned errors and persisted manifest errors retain only integer HTTP statuses 100–599 (excluding booleans); otherwise status is `None`/JSON `null`. Diagnostics exclude credentials, identifiers, tokens, raw responses/connection values, connection paths/strings, request URLs/queries and arbitrary representation/type/exception text.
- The generic incomplete tail remains an outcome, not a root cause. Actual cause awaits evidence from the next run; collection acceptance, gates, storage and checkpoints are unchanged. No claim that underlying collector failures are all fixed.
- [Operating guidance and synthetic examples](local-development.md#fabricconnections-sanitized-failure-diagnostics), including restarting only the current Functions host once while leaving Azurite and existing gates/checkpoints/data intact.

## Four opt-in Fabric API collectors

Final independent Code Reviewer cycle3 verdict: **Approved** for production implementation and tests. Reported validation: 58 targeted and 483 full offline tests passed under Python 3.12; Ruff passed with target `py310` (not Python 3.10 execution). No live tenant authentication/API/storage integration validation or deployment is established by these results.

- Added `FabricItemAccessPermissions`, `FabricItemJobHistory`, `FabricConnections`, `FabricDeploymentPipelineOperations`. All require explicit selection in `APPLICATION_MODULES`; no settings are enabled automatically. Permissions require 1–50 explicit scoped items; jobs require 1–100 supported items (`Notebook`, `DataPipeline`, `SparkJobDefinition`).
- Permissions use workspace-filtered admin discovery and the preview admin item access endpoint, with bounded resumable slices, durable continuation/evidence and quota gates. Only a healthy full cycle advances `lastRun`; additional host invocations may be needed.
- Connections and pipeline inventory are caller-visible, not tenant-complete. Connections retain only allowlisted metadata, excluding credentials/paths. Pipeline operations require pipeline Admin. Jobs and deployments are polling observations with finite API history windows, not recoverable event streams.
- New immutable UTC `<module>/YYYY/MM/DD/runId/` resource envelopes and manifests distinguish empty success from failed/incomplete/interrupted collection. Durable cooldowns and fail-closed pending/invalid-header blocks require careful operator recovery. Legacy output paths and empty-list save behavior are unchanged.
- **At initial collector release, collection only:** the subsequent MonitorRaw reconciliation above integrates all four collectors. E10 remains awaiting Desktop validation.
- Enablement, permissions, schemas and limits: [configuration reference](configuration-reference.md#scoped-fabric-collectors). Scheduling, repeated slices and recovery: [operating guide](local-development.md#operating-the-four-fabric-collectors).

## Audit PBIP: drill-through detail pages

Reviewed and approved by Code Reviewer (after trivial fixes: `2.14.0` schema references downgraded to `2.12.0`). **Not validated in Power BI Desktop**: the hand-written PBIR drillthrough blocks have not been verified there. No code, tests or infrastructure changed.

- Three hidden drill-through pages in `pbip-local/Audits/Activities.pbip`: **User Detail** (drill on `activity[UserId]`), **Report Detail** (`activity[ItemName]`) and **Workspace Detail** (`activity[WorkSpaceName]`). Each has a back button, KPIs, by-day and by-category charts and a recent events table.
- User Detail also shows licences, Report Detail shows `CatalogReports`, and Workspace Detail shows catalog counts.
- New measures in the `Drillthrough` display folder of `_Measures`: `First Activity Time (Local)`, `Last Activity Time (Local)`, `Catalog Report Matches`, `Catalog Reports in Workspace`, `Catalog Datasets in Workspace` and `Licence Rows for User`. The catalog and licence measures use `TREATAS`, because there are no physical relationships from `activity` to the catalog tables or `UserLicenseActivity`.
- Usage: right-click a user, item or workspace in any visual, then **Drill through**.
- The new pages must be force-added when committing.
- Details: [pbip-local/Audits/AUDIT_DASHBOARD_BUILD_GUIDE.md](../pbip-local/Audits/AUDIT_DASHBOARD_BUILD_GUIDE.md#drill-through-detail-pages).

## Audit PBIP: risk and anomaly analytics

Reviewed and approved by Code Reviewer. **Not validated in Power BI Desktop**: the project was never opened or refreshed there. No code, tests or infrastructure changed.

- `pbip-local/Audits` `activity` table: new columns `Event Time Local`, `Event Date`, `Hour of Day`, `Day of Week` (+ sort), `Actor Type` (+ sort), `Operation Category` and `Is System Activity`. Rows are de-duplicated on `Id`.
- New Power Query parameter `Local UTC Offset Hours` (default `-4`, fixed offset, no daylight saving handling).
- 19 new measures in `_Measures` under `Risk & Anomalies` (spike detection against a prior-7-day baseline, off-hours share, failure rate, sharing/export/security counts, first-seen client IPs).
- `Risk & Anomalies` page rebuilt; `Customer Audit Overview` gained Actor Type and "Hide system activity" slicers and an hour-by-weekday matrix. System activity is hidden by default.
- Known risks: hand-written PBIR pieces (saved slicer state, TopN, measure filter) may need a check in Desktop; `First-Seen IPs` is 0 when the range starts at the first recorded event; `audit_date_slicer` has a hard-coded saved range.
- Details: [pbip-local/Audits/AUDIT_DASHBOARD_BUILD_GUIDE.md](../pbip-local/Audits/AUDIT_DASHBOARD_BUILD_GUIDE.md).
- **Refresh Health page** (`refresh_health`): slicers for Event Date, workspace, dataset and Actor Type; KPIs for refreshes, failures, failure rate, datasets refreshed and credential/parameter changes; charts by day, refresh type, hour and dataset; a last-refresh-per-dataset table and a credential/parameter changes table.
- **Activity vs Capacity page** (`activity_vs_capacity`): capacity and UTC date slicers; KPIs for peak utilization, activities, refreshes and throttled days; combo charts by UTC day and UTC hour (activity columns on `Y`, utilization line on `Y2`); a capacity table and a workspace bar chart.
- `activity` table: new DAX columns `Effective Activity`, `Capacity Key` (`UPPER(CapacityId)`), `Event Date UTC` and `Event Hour UTC`. New `UTC Hours` table (0-23), a disconnected axis for the hour chart.
- New relationships `activity[Capacity Key]` -> `Capacities[Capacity Id]` and `activity[Event Date UTC]` -> `dimDate[Date]`. Both are many-to-one, single direction, on unique dimension keys, and unmatched activity rows are ignored, not errors.
- 18 new measures in `_Measures`: 11 in folder `Refresh Health` and 7 in folder `Activity vs Capacity`.
- Fixes: the `risk_kpi_spikes` card had no query and now shows `Spike Days`; the `audit_top_reports` TopN is now restricted to `ViewReport` and `ReadArtifact`.
- Known risks: **not validated in Power BI Desktop**; combo chart roles `Y`/`Y2` were hand-written; `CapacityMetrics[Timepoint]` is assumed to be UTC (sample `2026-10-14T21:23:00`; the app can offset it); `Hours Since Last Refresh` uses UTC now; `Activities on Capacity` scans the table and may need optimising; the Activity vs Capacity date slicer is UTC while Refresh Health is local time.
- Correction: an earlier note said the Graph tables (groups, group members, user licences) are empty and that the module does not fetch them. That is no longer true. The `Graph` module (reviewed and approved by Code Reviewer; 425 tests pass) now:
  - fetches `users` with paging (`@odata.nextLink`, `$top=999`) and extra fields (`displayName`, `userPrincipalName`, `mail`, `accountEnabled`, `userType`, `assignedLicenses`);
  - always writes `userlicenses.json`, one row per user per assigned licence, built from `assignedLicenses` (when the users call succeeds);
  - writes `groups.json` and `groupmembers.json` only when `GRAPH_EXTRACT_GROUPS` is on (opt-in, default off). Groups are security-enabled groups, flagged `isPowerBIAudienceGroup` by name prefix;
  - counts transport errors (exceptions from a request) as failures, so the module returns `False` and `lastRun` does not advance. Failed member calls for individual groups also count as failures;
  - needs the Graph application permissions `User.Read.All`, `Group.Read.All` and `GroupMember.Read.All`.
- New settings `GRAPH_EXTRACT_GROUPS`, `GRAPH_AUDIENCE_GROUP_PREFIXES` and `GRAPH_MAX_GROUPS_FOR_MEMBERS`; see [configuration-reference.md](configuration-reference.md#microsoft-graph-graph).

## Enhancement E10: MonitorRaw Power BI Project

Reviewed and approved by Code Reviewer. **Not validated in Power BI Desktop**: the project was never opened or refreshed there. No code, tests or infrastructure changed.

- New PBIP `pbip-local/MonitorRaw/MonitorRaw.pbip`: TMDL semantic model (Import mode) and PBIR report with 8 pages (capacity utilization, carry-over, activity overview, git connections, tags, delegated settings, widely shared links, about and setup).
- Reads the raw JSON output directly (no silver/gold layer). Source is selected with `SourceType` (`Local` or `Blob`), plus `LocalFolder`, `BlobAccountUrl`, `BlobContainer` and `BlobRootPath`.
- Dates come from the `<module>/YYYY/MM/DD` folders, not modified time. E5 modules use the latest snapshot (not summed); capacity metrics reruns use latest-run-wins. Malformed JSON shows as Load Error rows.
- Privacy: the Activity table includes `UserId` (UPN/email).
- Known risks: Desktop-only behaviours and unverified field names for Git connections, Tags, Delegated settings and Widely shared links (wrong names give null columns, not errors). A wrong `LocalFolder` that exists but has no module folders gives empty tables without an error.
- `pbip-local/MonitorRaw/.gitignore` re-includes `*.json`, which the root `.gitignore` ignores.
- Details and the acceptance checklist: [pbip-local/MonitorRaw/README.md](../pbip-local/MonitorRaw/README.md). Plan status: [enhancement-plan.md](enhancement-plan.md#e10-outcome).

## Local-folder PoC mode

Reviewed and approved by Code Reviewer; 406 tests pass.

- New opt-in setting `LOCAL_OUTPUT_PATH`. When set, the monitor writes all output (including `state.yaml`) to that local folder instead of Blob Storage or a Lakehouse. Blob and Lakehouse settings are ignored in this mode.
- In local mode only, `COMMERCIAL_TENANT_ID`, `COMMERCIAL_CLIENT_ID` and `COMMERCIAL_CLIENT_SECRET` are accepted as service principal credentials. Precedence: `COMMERCIAL_*` > `TENANT_ID`/`CLIENT_ID`/`CLIENT_SECRET` > legacy `TenantId`/`ClientId`/`ClientSecret`. Without `LOCAL_OUTPUT_PATH` the aliases are ignored. They are never used for storage credentials, and values are not logged.
- The folder is created if missing; an unusable or non-writable path raises an error at startup.
- A failed local write fails the module, so `lastRun` does not advance.
- Local mode still calls the real Microsoft APIs; it is not an offline mode. See [local-development.md](local-development.md#local-folder-poc-mode).

## Enhancements E8 and E9: optional Bicep infrastructure

Reviewed and approved by Code Reviewer. Compile-validated only (`az bicep build`); **not deployed**, so not live-validated.

- **E9, Key Vault reference.** New parameter `clientSecretKeyVaultSecretUri` sets the Function App `CLIENT_SECRET` setting to a Key Vault reference to an existing secret. When it is set, the Function App gets a managed identity. New opt-in `assignKeyVaultAccess` (with `keyVaultName` and optional `keyVaultResourceGroupName`) assigns `Key Vault Secrets User` on the existing vault. This works only if the vault uses RBAC authorization. The deployment fails with a clear message if `assignKeyVaultAccess` is true without `keyVaultName` or the secret URI. On first deploy the reference can be unresolved until RBAC propagates; restart the app.
- **E8, retention.** New parameters `enableRetention` (default `false`), `retentionDays` (default 90, minimum 1), `storageRetentionRootPath` and `retentionModules`. When enabled, a storage lifecycle rule deletes block blobs under `<container>/<root>/<module>/` older than `retentionDays` (by last-modified time). `state.yaml` and `azure-webjobs*` containers never match. The deployment fails if `retentionModules` is empty or contains a slash. A storage account has one management policy, so enabling this replaces any existing policy.
- Delayed pseudonymisation is deferred until a field-by-field policy exists. A lifecycle rule is deletion, not anonymisation.
- `infra/main.bicep` loads `infra/abbreviations.json`. That file is not in `infra/` in this working copy and `*.json` is gitignored, so it must be present for `main.bicep` to compile. See [deployment.md](deployment.md#key-vault-reference-and-blob-retention-e09-and-e08).
- Details: [deployment.md](deployment.md), [managed-identity.md](managed-identity.md) and [configuration-reference.md](configuration-reference.md#bicep-parameters-e08-and-e09).

## Enhancement E11: Version file, startup version log, update guide

Reviewed and approved by Code Reviewer; 366 tests pass. Version `0.2.0` is the baseline.

- The top-level `VERSION` file (`0.2.0`) is the single source of truth.
- `env/version.py` `get_version()` returns the stripped contents, or `"unknown"` if the file is missing, unreadable or empty. It makes no network call.
- `app/monitor.py` logs `Starting Fabric Monitor run (version X)` at startup. INFO logs may not show unless logging is configured.
- No automatic remote update check, by design.
- `VERSION` ships with Function App deploys (`azure.yaml` and `.funcignore` do not exclude it).
- Known gap (pre-existing): `containers/Dockerfile` and `Dockerfile2` copy only `app/`, not `VERSION` or `env/`, so containers log the version as `unknown`. When fixed, add `COPY VERSION .` and `COPY env ./env`.
- New guide: [updating.md](updating.md).

## Enhancement E7: Capacity Metrics module rewritten

Reviewed and approved by Code Reviewer; 355 tests pass. Validated live against the real Capacity Metrics semantic model. Full settings are in [configuration-reference.md](configuration-reference.md#capacity-metrics-capacitymetrics).

- `env/modules/capacity_metrics.py` queries the Capacity Metrics app semantic model through the Power BI `executeQueries` REST API. The old query used a nonexistent `CUDetail` table.
- DirectQuery tables return empty results unless scoped. For each capacity and each UTC day, the module runs `SUMMARIZECOLUMNS` over `'All Measures'` measures, with `DEFINE MPARAMETER 'CapacitiesList'` and `TREATAS` on `'Capacities'[Capacity Id]` and `'Dates'[Date]`. Without the `MPARAMETER` the result is empty (verified).
- Version probe: if the measure `Cumulative carry over %` exists, the carry-over measure set is used (groups `utilization` and `carryover`). Otherwise the baseline set is used (`utilization` only). An HTTP 400 or error body means the measure is missing; any other failure fails the run.
- Capacities come from the `Capacities` table. Capacities that are not Active are skipped unless `CAPACITY_METRICS_INCLUDE_SUSPENDED` is set. Capacity IDs are validated as GUIDs.
- Window: UTC days from `max(today - CAPACITY_METRICS_DAYS_BACK, lastRun date - 1 day)` through today. `CAPACITY_METRICS_DAYS_BACK` defaults to 3 (min 1, max 30).
- If `CAPACITY_METRICS_DATASET_ID` is unset, the module logs a warning and returns success.
- Failures: a failed query makes the run return `False`, so `lastRun` does not advance, but the other queries continue. A 429 or 5xx after retries aborts the run. An empty result for an Active capacity logs a warning.
- **Breaking change: output format.** Previously the module wrote paged raw files. It now writes `capacity_metrics/YYYY/MM/DD/{runYYYYMMDD}_{capacityId}_{group}_{metricDayYYYYMMDD}.capacity_metrics.json`, with content `{capacityId, capacityName, sku, date, group, rows}`. Empty results are not saved. Update any consumer that reads the old files.
- Caveats: Microsoft does not support consuming this model, so the schema may change. Upgrading the app with "update workspace and app" can change the workspace and dataset IDs; update `CAPACITY_METRICS_DATASET_ID` afterwards.

## All clocks are UTC

Reviewed and approved by Code Reviewer; 288 tests pass under the default, UTC, Asia/Tokyo and America/Los_Angeles time zones.

- The modules `apps`, `capacity`, `capacity_metrics`, `workspaces`, `roles`, `fabricitems`, `tenant`, `graph`, `refreshables` and `refreshhistory` use `utc_now()`. Internally this is naive UTC; on the wire it is an ISO string ending in `Z`.
- The import-time module-level `today` is removed. Dates are computed on each run, so they stay correct in a long-lived Function host.
- File-name dates for `capacity`, `capacity_metrics` and `roles` now come from the same `pivotDate` as the folder, so a run that crosses midnight no longer splits across two dates.
- `convert_dt_str` normalises offset-aware datetimes to naive UTC.
- Cron expressions (the module `*_CRON` variables, via `croniter`) are evaluated in UTC. The `function_app.py` timer is 02:00 UTC. `WEBSITE_TIME_ZONE` affects only the Function timer trigger, not module crons. See [configuration-reference.md](configuration-reference.md#time-zones).
- Behaviour change: date folders use the UTC date. On a non-UTC host, runs near local midnight may land in a different folder than before.
- No local-time conversion helper was needed.
- Resolves the "mixed local/UTC clocks" concern under E6 ([enhancement-plan.md](enhancement-plan.md#e6-open-concerns)) and the B1–B16 gap about local-time state timestamps (E2).

### Known non-blocking notes

- `catalog_bkbk.py` (a dead file) still uses local time.
- Existing `ruff` findings remain. Clean them up in a separate commit, which also avoids rewriting CRLF files.
- Recommended: commit the UTC change on its own. `tests/` is untracked in git, so add it to that commit.
- The clock sweep test does not scan `function_app.py` or `time.time()`.
- The tests that use the real `croniter` run only when `croniter` is installed, and skip otherwise. The reviewer saw them run; the tester saw 2 skipped.

## Domains fix and E6 decision

Reviewed and approved by Code Reviewer; 269 tests passing.

- `domains.py`: the folder date is now the current UTC run date. Previously it was derived from `lastRun`, so a run could overwrite yesterday's file.
- `domains.py`: each row is its own dict, and an error returns `False`.
- E6 is marked done, with open concerns. The raw dated layout (`<module>/YYYY/MM/DD/`) exists. History tables (`*_history`) are deferred with E4, which is intentionally not pursued. Open concerns are listed in [enhancement-plan.md](enhancement-plan.md#e6-open-concerns).
- Known non-blocking gap: `ruff format` of `tests/test_domains.py` is still pending (cosmetic).

## Enhancement E5: four new opt-in modules

Reviewed and approved by Code Reviewer; implementation and tests (264 passing).

New modules, none of them in the default `APPLICATION_MODULES`. Add the names you want. Details are in [configuration-reference.md](configuration-reference.md#e5-admin-modules).

| Module | Endpoint | Output folder |
|---|---|---|
| `GitConnections` | `GET /v1/admin/workspaces/discoverGitConnections` (**preview API**) | `gitconnections/YYYY/MM/DD` |
| `Tags` | `/v1/admin/tags` | `tags/YYYY/MM/DD` |
| `DelegatedSettings` | `/v1/admin/{capacities,domains,workspaces}/delegatedTenantSettingOverrides` | `delegatedsettings/<scope>/YYYY/MM/DD` |
| `WidelySharedLinks` | Power BI admin `widelySharedArtifacts`: `linksSharedToWholeOrganization` and `publishedToWeb` | `widelysharedlinks/YYYY/MM/DD` (two files) |

- New cron variables: `GITCONNECTIONS_CRON`, `TAGS_CRON`, `DELEGATEDSETTINGS_CRON`, `WIDELYSHAREDLINKS_CRON`.
- Each run writes a point-in-time snapshot of the current state under that day's folder. It is not an incremental change feed.
- Failure behaviour: a 403 or 404 is logged as a warning and the module returns `False`. `lastRun` is not advanced, so the module retries on the next tick. Modules that call several endpoints (`DelegatedSettings`, `WidelySharedLinks`) save what succeeded; only the failed part is missing.
- Not changed: the "active items" part of E5. The existing `FabricItems` module already calls `/v1/admin/items`. Handling of `state=active` and tags there is a follow-up.

### Known non-blocking gaps

- `GitConnections` uses a preview API. If it is unavailable, it fails and retries on every tick.
- `admin_paging` treats an empty `{}` response as a failure.
- The new test file is not formatted with `ruff`.

## Enhancements E1, E2, E3 and E9 (partial), plus audit hardening

Reviewed and approved by Code Reviewer; 226 tests pass and do not depend on the local time zone.

### E1: throttle-aware retry

- `invokeAPI` retries HTTP 429, 503 and 504 and honours `Retry-After`.
- New settings: `API_MAX_RETRIES` (default 3), `API_MAX_CONCURRENCY` (default 16), `API_MAX_RETRY_DELAY` (default 120 seconds). See [configuration-reference.md](configuration-reference.md).
- Long scanner throttles can exceed the delay cap. The call then fails and is retried on the next run.

### E2: UTC timestamps and per-day activity checkpoint

- State timestamps are now written in UTC, which fixes the earlier local-time-with-`Z` gap. (Resolved for state and all modules; see "All clocks are UTC" above.)
- Activity keeps a per-day checkpoint, so a failure partway through a range does not repeat days already collected.

### E3: parallel catalog scans

- Catalog scan groups run concurrently, up to 16 at a time.
- Request headers are refreshed for each batch.

### E9 (partial): token cache

- MSAL tokens are cached. Key Vault support is not done.

### Audit hardening

- If reading state fails, the run aborts and does not overwrite `state.yaml`.
- A blank or missing state file is treated as a fresh state.
- `null` module entries in state are repaired. This closes the earlier `TypeError` gap.

### Known gaps

- `roles.py` has its own retry layered on top of the `invokeAPI` retry.
- Remaining `ruff` findings were there before this work.
- Tests use stubs for `yaml` and `croniter`.
- Items not done (E4–E8, E9 Key Vault, E10–E12) are listed with reasons in [enhancement-plan.md](enhancement-plan.md).
- Gaps listed under the B1–B16 section that this section does not mention (for example `Local_File_Management.save` swallowing `OSError`) are unchanged.

## Bug fixes B1–B16 (from [enhancement-plan.md](enhancement-plan.md))

Reviewed and approved by Code Reviewer; implementation and tests (127 unittest tests) passed.

### Behaviour changes

- **`lastRun` only advances on success.** After a run, `env/audit.py` advances a module's `lastRun` in `state.yaml` only if the module completed. A module fails by returning `False` or raising an exception. Failed modules keep their old `lastRun`, so the missed period is retried on the next run. One failing module no longer prevents the others from saving state (`asyncio.gather(..., return_exceptions=True)`). Activity and RefreshHistory now report API errors (including HTTP 429) as failures (B9, B12).
- **First run default is 7 days.** If a module has no `lastRun` (or it cannot be parsed), it runs, and its checkpoint is seeded to 7 days ago. A newly created `state.yaml` also uses 7 days ago for every module (B13).
- **Activity 30-day clamp.** The Activity start date is never earlier than 30 days back, matching the activity log retention, so a stale or missing state no longer triggers about 500 days of calls (B13).
- **Missing or unreadable state** is treated as empty state instead of raising `NameError` (B8). `Context.convert_dt_str` raises `ValueError` on a bad date instead of calling `exit()` (B10).
- **Catalog.**
  - `lastFullScan` is saved to `state.yaml` (under `catalog`) when a full scan completes without failures. A full scan runs when `lastFullScan` is missing or at least 30 days old; otherwise scans are incremental (B1).
  - Scan status polling sleeps 15 seconds between checks using `asyncio.sleep` (B2, B3).
  - Polling is capped at 120 checks per scan (about 30 minutes). Five consecutive status errors fail the batch. A failed batch makes the module return failure, and `lastFullScan` and `lastRun` are not advanced (B2, B3).
  - A `None` or error result is handled rather than raising.
- **Other modules.** Roles stops on non-OK responses with a retry cap (B4). Gateway builds a separate entry per gateway and checks the status code (B5). Domains builds a new row per workspace and reads the `domains` state key (B6). RefreshHistory saves once after the dataset loop (B15). `exclude_personal_workspaces()` / `exclude_inactivate_workspaces()` on `Audits` set the value instead of raising `TypeError` (B7). Blocking calls in async code were moved off the event loop and local paths are absolute (B14).

### New and aliased configuration (B11, B16)

- `TENANT_ID`, `CLIENT_ID` and `CLIENT_SECRET` are the canonical names. The legacy `TenantId`, `ClientId` and `ClientSecret` are still accepted as fallbacks.
- New per-module cron variables: `FABRICITEMS_CRON`, `WORKSPACES_CRON`, `CAPACITYMETRICS_CRON`. Domains already had `DOMAINS_CRON`; all four now take effect through `Context.get_cron`. See [configuration-reference.md](configuration-reference.md).

### Running the tests

From the repository root:

```
python3 -m unittest discover -s tests -t .
```

### Known non-blocking gaps

These were noted in review and are not fixed:

- `env/audit.py`: a module entry in `state.yaml` that is `null` can raise `TypeError` in the `setdefault` step that advances `lastRun`.
- `Local_File_Management.save` swallows `OSError`, so a failed local write is not reported as a module failure.
- `env/.env.examples` still uses the legacy names (`TenantId`, `ClientId`). They work through the aliases, but the canonical names are preferred.
- ~~State timestamps are written in local time even though they carry a `Z` suffix.~~ Resolved by E2 and the all-UTC change (see "All clocks are UTC").
- `refreshables.py` and `capacity_metrics.py` still use blocking `requests`.
