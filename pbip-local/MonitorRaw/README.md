# MonitorRaw (Power BI Project)

> **Validation status: basic Desktop checks and Scoped/Tenant permission views were verified by the operator. Historical job-history load warnings remain; the full scenario checklist is not yet confirmed.** See [Validation status](#validation-status).

## What it is

`MonitorRaw.pbip` is a Power BI Project (PBIP) that reports directly on the raw JSON files the monitor writes. It has no silver/gold layer (plan item E4 is not pursued); every table is built in Power Query from the dated module folders.

- Semantic model: `MonitorRaw.SemanticModel/` in TMDL format, **Import** mode.
- Report: `MonitorRaw.Report/` in PBIR format, 12 pages.
- Source: a local folder (the `LOCAL_OUTPUT_PATH` output) or Azure Blob Storage, chosen with the `SourceType` parameter.

The Fabric pages cover `FabricConnections`, `FabricDeploymentPipelineOperations`, `FabricItemAccessPermissions` and `FabricItemJobHistory`. **Item Permissions** supports the collector's scoped and tenant evidence through the `ItemPermissionMode` parameter, defaulting to `Scoped`. Opening the report or selecting `Tenant` does not enable collection or call tenant APIs.

**No-output state:** with no corresponding permissions/jobs output, **Not collected** is expected—not healthy empty collection. The report reads files, not live collector settings: this state can mean disabled, unconfigured or never run; it does not establish the current configuration.

## Prerequisites

- Power BI Desktop on Windows, a recent release. Older builds may not open PBIR/TMDL projects.
- In Desktop, under **File > Options and settings > Options > Preview features**, enable the **Power BI Project (.pbip) save option** and the **TMDL view** if your Desktop version still lists them as previews, then restart Desktop. Newer versions may have these on already.
- Monitor output to read: either a folder produced with `LOCAL_OUTPUT_PATH` (see [local-development.md](../../docs/local-development.md#local-folder-poc-mode)) or a Blob container written by the monitor.

## Open the project

On Windows, open `pbip-local/MonitorRaw/MonitorRaw.pbip` from your updated checkout in Power BI Desktop. Set the parameters (below), then **Home > Refresh**. Existing collector output is sufficient: you do **not** need to run `func start`, restart a host, call APIs, or collect new data to refresh this report.

If the project is already open, close it without saving stale definitions over the updated files, then reopen the updated `.pbip`. Reload the definitions before refreshing; an already-open Desktop session may still contain the older model/report.

Report project-file changes need only this Desktop reopen/reload and refresh, **not a Functions restart**. If collection is wanted later, first choose the exact workspace/item/type targets, then configure `FABRIC_ITEM_ACCESS_SCOPE` and/or `FABRIC_ITEM_JOB_SCOPE` and deliberately select the corresponding modules in `APPLICATION_MODULES`. See [settings and enablement](../../docs/configuration-reference.md#settings-and-enablement) and [operating the four Fabric collectors](../../docs/local-development.md#operating-the-four-fabric-collectors) for authorization, limits and quota-safe operation. Do not auto-select items or enable whole-tenant collection. Applying those collector settings later requires an authorized Functions host restart/start, which can immediately call real APIs; it is a separate user action, not part of updating this report.

## Parameters

| Parameter | Used when | Meaning |
|-----------|-----------|---------|
| `SourceType` | always | `Local` or `Blob`. Default `Local`. |
| `ItemPermissionMode` | permissions | `Scoped` (default) reads `fabricitemaccesspermissions`; `Tenant` reads `fabricitemaccesspermissions_tenant`. Choose in **Transform data > Manage Parameters**, then apply and refresh. This is a refresh-time source parameter, not a slicer, and never merges the two modes or falls back to another folder. |
| `LocalFolder` | `Local` | Absolute path of the folder that contains the module folders (`activity`, `capacity_metrics`, `fabricconnections`, ...). Set it to your `LOCAL_OUTPUT_PATH` output root; for example, `C:\path\to\monitor-output`. Do not assume the saved development value is suitable for your machine. |
| `BlobAccountUrl` | `Blob` | Storage account URL, `https://<storage-account>.blob.core.windows.net/`. |
| `BlobContainer` | `Blob` | Container name (`STORAGE_ACCOUNT_CONTAINER_NAME`). |
| `BlobRootPath` | `Blob` | Root path inside the container (`STORAGE_ACCOUNT_CONTAINER_ROOT_PATH`). Leave empty when the module folders sit directly in the container. |

Replace the placeholders with your own values. Do not commit your values, SAS tokens or account keys.

## How dates are determined

Dates come from the `<module>/YYYY/MM/DD` folder layout (UTC), **not** from file modified time. Copying or syncing files does not change the dates. For `delegatedsettings` the scope folder sits before the date (`delegatedsettings/<scope>/YYYY/MM/DD/`).

## Tables

| Table | Module folder | Notes |
|-------|---------------|-------|
| Capacity Metrics | `capacity_metrics` | One row per capacity and timepoint. Utilization and carry-over groups are merged. |
| Capacities | `capacity_metrics` | Capacity dimension (id, name, SKU), latest run wins. |
| Activity | `activity` | Lean activity event table. |
| Git Connections | `gitconnections` | Latest snapshot. |
| Tags | `tags` | Latest snapshot. |
| Delegated Settings | `delegatedsettings` | Latest snapshot per scope; one row per override. |
| Widely Shared Links | `widelysharedlinks` | Latest snapshot per endpoint (organization, published to web). |
| Connections | `fabricconnections` | Latest healthy committed full inventory; nullable source names preserved. |
| Deployment Pipelines | `fabricdeploymentpipelineoperations` | Latest committed successful full discovery, including successful empty discovery. |
| Deployment Operations | `fabricdeploymentpipelineoperations` | All retained committed successful history observations, deduplicated by pipeline/operation identity. |
| Item Permissions | `fabricitemaccesspermissions` or `fabricitemaccesspermissions_tenant` | Selected by `ItemPermissionMode`; successful access observations from one validated selected cycle, including partial cycles. Permission lists do not multiply rows. |
| Item Permission Scope | same selected permission folder | Known targets in that cycle, distinguishing successful zero grants, failure, deferral and not attempted; unresolved identities/counts remain explicit in status. |
| Fabric Job History | `fabricitemjobhistory` | Latest observation per workspace/item/job instance across all retained runs; no raw failure payloads imported. |
| Fabric Job Scope | `fabricitemjobhistory` | Latest finished poll's explicit target outcomes, including successful zero observations and failed targets; unvisited targets cannot be inferred. |
| Collection Status | derived from all four Fabric collectors | Disconnected diagnostic rows, including not-collected, empty-success and failed/incomplete states. |
| Calendar | derived | Dates found in Capacity Metrics and Activity, plus today. |

## Report pages

1. Capacity utilization
2. Carry-over
3. Activity overview
4. Git connections
5. Tags
6. Delegated settings
7. Widely shared links
8. About and setup
9. Connections inventory
10. Deployment operations
11. Item Permissions
12. Fabric Job History

**Connections inventory** has connection and gateway-ID counts, connectivity-type and gateway-assignment slicers, a type chart, a safe-metadata inventory table and collection status. **Deployment operations** has visible-pipeline and operation counts, failed/executing counts, average duration, status/date charts, date/pipeline/status/type slicers, a separate current-pipeline inventory and a retained operation-detail table.

**Item Permissions (page 11)** has a prominent **PARTIAL COVERAGE** warning, global collection status, observed grant/item/principal counts and **Successful Targets / Expected Targets** coverage—not a complete-cycle-only card. Its scope table shows workspace/item IDs and type, `Collection Outcome`, HTTP status, returned access details, observation UTC and cycle ID, sorted by outcome so unsuccessful targets remain visible. Principal/access-detail rows and slicers show observed grants, not complete effective access. Coverage counts come from validated manifests in disconnected Collection Status, not filtered grant rows: principal/grant slicers cannot hide the warning or change global target coverage.

**Fabric Job History** presents job/status/duration summaries, retained job details, explicit poll coverage, slicers and collection health. **About and setup** includes all four collectors' state, last attempt/snapshot UTC, snapshot row count, coverage and load diagnostics.

## Data semantics

- **Latest snapshot (E5 modules).** Git connections, tags, delegated settings and widely shared links write a full copy each day. The model keeps only the files of the most recent date (per scope or endpoint where there is one). Days are **not summed**.
- **Capacity metrics reruns.** The latest run wins per (capacity, group, timepoint), so a rerun for the same day is not double counted. The run is taken from the file name prefix.
- **Carry-over.** Carry-over columns are empty when the Capacity Metrics app version does not expose them; the report shows a status message.
- **Malformed JSON.** Legacy tables retain parse failures as rows with `Load Error` filled in; their empty files give no rows and no error. Fabric artifacts instead go through envelope/manifest validation (below). The report-wide `Load Errors` measure includes both legacy parse failures and invalid/missing Fabric artifacts. Collection failure or interruption is also reported through collection status; a zero load-error count alone is not proof of collection success.

### Fabric resource and manifest contract

Both sources (Local and Blob) read the same immutable UTC run layout:

```text
fabricconnections/YYYY/MM/DD/runId/
  connections.json
  manifest.json
fabricdeploymentpipelineoperations/YYYY/MM/DD/runId/
  pipelines.json
  {pipelineId}.json
  manifest.json
fabricitemaccesspermissions/YYYY/MM/DD/runId/
  inventory_{workspaceId}.json OR {workspaceId}_{itemId}.json
  manifest.json
fabricitemaccesspermissions_tenant/YYYY/MM/DD/runId/
  inventory.json OR {workspaceId}_{itemId}.json
  manifest.json
fabricitemjobhistory/YYYY/MM/DD/runId/
  {workspaceId}_{itemId}.json
  manifest.json
```

`{pipelineId}.json` is one operation-history resource per discovered pipeline. Resource envelopes contain `runId`, UTC `observedAt`, `coverage`, `requestPath`, `parent`, `complete`, and either `records` or `error`. Pipeline operation resources carry pipeline identity/name in `parent.deploymentPipeline`. Manifests contain `runId`, `observedAt`, `coverage`, `finished`, `complete`, `resources` (file, parent and completion), `errors` and `execution`. See the [full output contract](../../docs/configuration-reference.md#output-contract-and-privacy).

The model validates paths, JSON shapes and record fields, and requires a parsed **finished** manifest agreeing with the resource filename, parent and completion before consuming a successful observation. For permissions, a finished slice manifest may belong to a still-in-progress cycle; the validated linked chain is required. `finished=false`, missing manifests, truncated/malformed files or invalid envelopes are not empty successes. Mutable request gates/progress files are not report facts.

- **Connections snapshot.** Select the newest healthy committed full inventory by observation time. A valid `complete=true, records=[]` clears older inventory and reports success with zero visible connections. A newer failed/incomplete/interrupted run leaves the last healthy snapshot visible with a stale/incomplete warning. With no successful snapshot, counts are blank rather than a fabricated zero.
- **Pipeline discovery.** Select the newest committed successful discovery, including an empty list that clears the current pipeline inventory. A finished run with failed operation resources can still supply valid discovery and successful histories, but overall health warns that histories may be partial/stale. Failed or uncommitted discovery does not replace the last successful discovery with false empty data.
- **Retained operation history.** Combine successful committed operation resources from **all retained runs**, including usable resources in a finished but partially failed run. Deduplicate by **pipeline ID + operation ID**, taking newest `observedAt` (run ID breaks ties), so a later observation updates an ongoing operation rather than adding another deployment. Older operations remain even after leaving the API's **20 recent deployments per pipeline** window or after their pipeline disappears from current discovery. Source retention/deletion still limits what can be loaded. This is latest observed state per operation, not a visual status-transition log, and polling gaps cannot be recovered.
- **No invented operations.** A visible pipeline with successful empty history appears only in the pipeline inventory, not as a synthetic operation row. Execution date comes from execution start UTC. Missing start/end times or an end before start yield blank duration; raw API status/type values are preserved.
- **Nullable connection names and safe fields.** `Display Name` preserves source nulls. Only the UI `Connection Label` falls back to `Unnamed connection (<id>)`; it does not change the source name. The imported metadata allowlist is ID, display name, gateway ID, connectivity type, privacy level and `connectionDetails.type`. Credentials, connection paths/strings, tokens and unknown fields are excluded. Gateway assignment means an ID was reported, not independently verified gateway health.
- **Coverage and health.** Connections and pipeline discovery are **caller-visible, not tenant-wide**; operation history requires pipeline **Admin**. `Collection Status` is disconnected from the inventory/history tables, so their slicers cannot hide collection health. The deployment pipeline slicer uses retained operation history, so old pipelines remain selectable even when absent from current inventory. Counts respond to relevant fact filters; status/snapshot diagnostics remain source-wide. Zero visible inventory is an explicit success only with a committed successful snapshot, not evidence of tenant-wide absence.

### Item permissions and Fabric jobs

- **Explicit permission mode.** Only the selected folder is loaded, for Local or
  Blob sources. Both modes use the existing page and global health measures;
  status and coverage text identify the mode. Switching the report parameter
  does not alter collector settings, APIs, grants, gates or checkpoints. Missing
  tenant files mean **Not collected**, not permission to load scoped evidence.
- **Tenant evidence and coverage.** Validate finished slice manifests and their
  complete linked discovery/access history, unique workspace/item identities,
  discovered counts, ordered access cursors and monotonic cycle health.
  Cross-mode/cycle links, missing predecessors, conflicting types and invalid
  progression are rejected; chains are bounded to 10,000 slices. Unlike scoped
  evidence, tenant cycles are not limited to 50 targets. Expected total remains
  unknown until discovery completes. Denied/unsupported/not-found outcomes
  remain failed/unknown access, not empty grants or effective access.
  A healthy finished discovery returning zero tenant items is selectable even
  without access requests: it clears older grants and reports successful zero
  coverage. Failed/incomplete discovery cannot do so.

- **Nullable Power BI access metadata.** For query-typed Report, Dashboard,
  SemanticModel, App and Dataflow targets, a returned null access-detail type or
  additional-permissions field is accepted without replacing the source value.
  `Item Type` still comes from the validated target; `Access Detail Type` can be
  blank. Missing/conflicting detail types and malformed principal/permission
  fields remain invalid. This compatibility correction requires a Desktop
  reopen/refresh to validate; it does not recover failed historical observations.

- **Single selected permission cycle (partial-permission policy).** Follow immutable manifests' `execution.cycleEvidence` links across inventory/access slices and validate the chain, task progression, selected inventory and target coverage. Prefer the newest **finished cycle with at least one successful access observation**, including successful empty observations; the cycle need not be healthy overall. Otherwise use the newest useful **in-progress cycle** with successful access observations from finished slice manifests. Never merge cycles or carry forward grants from other cycles. A finished partially failed cycle can therefore replace an older healthy cycle, while an older useful finished cycle takes precedence over a newer in-progress cycle. Selected-cycle identity/state and observation range remain separate from latest-attempt identity/state/time; older selected evidence carries an explicit **STALE** warning and its scope may differ. A successful final slice alone proves neither chain validity nor completeness. Missing, malformed, cyclic or inconsistent evidence links are not admitted and contribute to global `Load Errors`.
- **Only successful observations supply grants.** Failed, deferred and known-not-attempted targets have **unknown access**, not “no access”; their returned-access counts are blank. Scope rows distinguish `Collected`, `Collected: zero grants`, `Failed`, `Deferred` and `Not attempted`, with available HTTP/time/run/cycle evidence. When no successful access observation is selectable, grant counts stay blank, not false zero; valid unsuccessful evidence can still supply scope/status. Inventory may identify unvisited targets, but the report does not read configured scope to invent missing identities. Unknown target identities/counts and an unresolved expected total remain explicit in global status.
- **Zero grants are coverage, not grants.** A successfully collected target with `records=[]` appears in **Item Permission Scope** with zero `Returned Access Details`; it creates no synthetic grant row. A selected cycle containing only successful empty access observations can clear older grants, even if other targets failed; partial coverage must remain visible. Grants are distinct principal/access details with normalized permission lists, not one row per permission string. Group membership is **not expanded**; even tenant discovery does not establish fully expanded effective access or a complete tenant audit. Linked slices are observations over time, not a simultaneous snapshot.
- **Source-wide coverage is not collection success.** Successful/expected, failed, deferred, known-not-attempted and unknown target counts come from validated cycle evidence in disconnected Collection Status, independently of grant/principal filters. For illustration only, **12/13** successfully read targets is partial coverage even when grant rows are present; it is not a tenant baseline or guaranteed result. `Collection Status[Error Count]` and global `Load Errors` count artifact/evidence integrity problems, not ordinary collection failures. Valid failed outcomes can have zero load errors; inspect outcome/status fields separately. The unresolved Dataflow HTTP 404 with sanitized `errorCode=unrecognized` does not establish that Gen2 is unsupported or fixed. This report change does not alter scope, collectors, gates or checkpoints: an unhealthy collection cycle still does not advance `lastRun`.
- **Retained job state.** Read successful committed job resources from **all retained runs**, including usable resources in finished partial polls and observations for subsequently deselected targets. Deduplicate by **workspace ID + item ID + job instance ID**, selecting newest `observedAt` (run ID breaks ties). An ongoing job's later status/duration updates one job rather than inflating counts. Old jobs remain after leaving the API's **100 recent completed jobs plus active jobs** window. This is latest observed state, not a status-transition log; polling gaps and deleted source history cannot be recovered.
- **Explicit job scope and health.** **Fabric Job Scope** shows committed target outcomes from the latest finished poll, including zero observations and failures, separately from retained history. Interrupted polls cannot establish unvisited targets. An incomplete/failed latest poll warns even when older jobs remain visible. Only explicit `Notebook`, `DataPipeline` and `SparkJobDefinition` targets are supported. A zero-job scope row is not an invented job.
- **Safe import and raw values.** Job status/type values are preserved; missing or inverted start/end times yield blank duration. The report does **not** import `failureReason` or other raw failure payloads, even if present in collector output. Principal names/UPNs and identifiers can still be sensitive: restrict access to source files and the report. All four collectors feed disconnected health/About diagnostics and global `Load Errors`; zero load errors alone does not establish collection success.

## Things that can surprise you

- **Fabric Job History: field access on Null / broken job visuals.** Successful empty `records=[]` observations are excluded before list expansion in the job and permission fact queries; they remain visible in scope and collection diagnostics, not as null jobs or grants. The job query expands only allowed record fields and restores the report-facing column names, UTC dates, duration and latest-observation deduplication. The temporary raw `FileDate` date table and item-ID-only scope relationship created during Desktop troubleshooting are removed; job coverage stays separate from retained job facts. Reopen the updated project and refresh existing files to validate the fix in Desktop; offline checks do not execute M or render visuals.
- **Collection Status: “The columns of the specified table type must be nullable.”** This error can block multiple queries. The fix makes all 24 explicit columns in its `Table.FromRecords` type nullable, as required with `MissingField.UseNull`, including fields always supplied by producers. This does not erase data or turn existing values into nulls; omitted permission metadata remains null, not false or zero. Preserve any unsaved Desktop work separately, then close/reload the updated `MonitorRaw.pbip` without saving stale definitions over the checkout and select **Home > Refresh**. Verify that the error clears and inspect refreshed Collection Status/About diagnostics: previously loaded partial facts do not establish current refresh or collection success. No `func start`, collector restart, API call or deployment is needed. Production and tests were approved; 513 offline tests passed, including static regression checks, but native M/Desktop refresh has not been verified.
- **Wrong `LocalFolder` can look empty.** An existing folder with no module subfolders gives empty legacy tables. Connections/deployments show `Never run / no collection files`; permissions/jobs show `Not collected`. None has a successful snapshot. Check the root path, row counts and About diagnostics after the first refresh; absence of files is not successful empty collection.
- **Privacy.** The Activity table contains `UserId` (a UPN or email address), which is personal data. Restrict who can open the report and the file, and treat published copies accordingly. Blob retention is optional and off by default; see [deployment.md](../../docs/deployment.md#key-vault-reference-and-blob-retention-e09-and-e08) and the [E8 outcome](../../docs/enhancement-plan.md#e8-and-e9-outcome). Retention deletes whole blobs by age. It is not anonymisation.
- **Service refresh.** A local folder source needs an on-premises data gateway to refresh in the Power BI service. Blob mode does not.
- **Blob credentials.** In Blob mode, Desktop asks for credentials (for example an account key or organizational account) the first time. Enter them in Desktop; they are not stored in the project.
- **`.gitignore`.** The repository root `.gitignore` ignores `*.json`. PBIP and PBIR definitions are JSON, so `pbip-local/MonitorRaw/.gitignore` re-includes them and ignores Desktop's local `.pbi/` state and cache.

## Validation status

**Operator confirmation (2026-11-05): "The PBIP reports check out."** This followed
the requested reopen/refresh and page checks and records basic Desktop
acceptance. The detailed fixture/edge-case scenarios below have not been
individually confirmed. Subsequent operator screenshots verify the permission
page renders in both modes: Scoped shows 12/13 successful targets; Tenant shows
95/101 successful targets, six failures and 200 access-detail rows, matching
saved evidence. Tenant permission diagnostics show zero load errors.
About shows three historical job-history integrity errors: in three runs,
resource timestamps exceed final manifest timestamps by about 0.58–1.50 seconds.
The source files and warnings remain preserved. A future-run collector guard
rejects such final commits; it does not repair historical evidence.
Healthy empty tenant cycles, broken-link fixtures and Local/Blob parity remain
unconfirmed in Desktop.
The supplied final Code Reviewer verdict for the partial-permission report was
**Approved — cycle 2**, covering the four scoped semantic files, ten report visual
JSON files and `tests/test_monitorraw_report.py`.

The final cycle-2 reviewer reported **8 targeted tests and 511 full offline tests passed** under DNS/socket guards, Ruff format/lint and static Python 3.10 syntax checks passed, plus **114 JSON files, 24 tables, 12 pages and 188 valid field references** checked. The requests dependency warning was nonfailing. `tests/test_monitorraw_report.py` covers structure/bindings, disconnected global coverage, missing-versus-zero counts, payload/parent/field mutations and filter protections. These are **not native M/DAX execution, TMDL/Microsoft schema validation, Windows tests, live API/storage validation, or evidence of rendered visuals**; cached schema validation was unavailable. No such native validation is claimed; review approval does not establish that the report opens or refreshes successfully.

Previously documented Desktop-only risks still requiring acceptance:

- **Blob `Name` column.** The Blob source assumes `Name` is the full virtual path of the blob. If it is not, the Blob tables load empty.
- **Credential or privacy-level prompt in Local mode.** The unused Blob placeholder may still trigger a credential or privacy-level prompt in Local mode.
- **Missing-folder detection.** It relies on the `DataSource.NotFound` error reason. A different reason would raise an error instead of giving an empty table.
- **Percent columns.** They assume fractions (for example `0.85`), formatted as `0.0%`. Values on a 0-100 scale would display 100 times too large.
- **Time zones.** `ToUtcDateTime` handles only `Z` and `+` offsets. Negative offsets are not converted.
- **Activity duplicates.** There is no Event Id dedupe for Activity. A re-fetch of a day with fewer pages could double count events.
- **Theme.** The theme reference is `CY24SU10` without a static resource. Desktop may prompt or warn.
- **Visual schema versions.** The visual schema versions are unconfirmed.

**Field names not verified.** The field names for **Git connections, Tags, Delegated settings and Widely shared links** were **not** verified against real payloads. These tables read fields through a null-tolerant accessor, so a wrong name produces a null column, not an error. A table can look healthy and still have empty columns. Check one real file per module and compare it with the table columns.

## Acceptance checklist

Run this in Desktop and record the results.

Basic Desktop checks above do not establish every scenario below. Detailed
fixture checks remain unconfirmed unless specifically recorded.

- [ ] Open `MonitorRaw.pbip`. The project loads without errors.
- [ ] **Local mode.** Set `SourceType = Local` and `LocalFolder` to a `LOCAL_OUTPUT_PATH` sample. Refresh. No credential or privacy prompt, or you can resolve it.
- [ ] Row counts are plausible for each table listed above, including all four new permission/job tables and Collection Status for all four collectors. Compare with source files, not merely the latest folder's row count.
- [ ] In a separate test output root, `Load Errors` is 0 for good data. A malformed legacy file produces a Load Error row; malformed/invalid Fabric JSON/envelopes/manifests produce About diagnostics and contribute to `Load Errors`, not fabricated inventory/operations.
- [ ] For each of the four E5 tables, open one real JSON file and confirm the columns are filled, not null.
- [ ] Use separate fixtures for missing module files, committed successful empty data, failed resources, unfinished/interrupted runs, missing manifests and invalid artifact shapes. Missing/failed data must not read as healthy zero; successful empty inventory must clear older inventory. Failed latest connection inventory or pipeline discovery must retain the prior usable snapshot with a warning; test permission selection separately below. Restore the intended source afterward.
- [ ] **Blob mode.** Set `SourceType = Blob` with `BlobAccountUrl`, `BlobContainer` and `BlobRootPath`. Enter credentials. Refresh. Row counts match Local mode for the same data.
- [ ] All 12 pages render with no visual errors, including existing pages, new slicers/status cards, scope/grant/job tables and About collection diagnostics. Confirm the same fixtures have matching counts, selected observations, raw status values and errors in Local and Blob modes.
- [ ] First test permissions/jobs with no collection files: new pages are empty with **Not collected**, blank unknown counts and no healthy-zero claim. Opening/refreshing does not enable collectors or select scopes.
- [ ] Refresh `ItemPermissionMode=Scoped`, then `Tenant`. Confirm the page/About mode label, source-isolated counts and unchanged job visuals. Missing tenant files must not fall back to scoped grants. Restore the intended parameter afterward.
- [ ] In a separate fixture root, test tenant multi-workspace discovery beyond 50 items, incomplete discovery with unknown expected total, failed/deferred/unvisited targets, a healthy empty tenant cycle clearing old grants and broken/conflicting evidence links producing load errors rather than grants.
- [ ] Then use a separate controlled-data root to test a complete healthy multi-slice permission cycle, successful zero-grant targets, duplicate access details/permission lists, and a later healthy cycle clearing prior grants. Scope counts reconcile without fake grant rows or permission-list multiplication.
- [ ] Test a newer finished partially failed permission cycle: select its successful access observations only, replacing older grants without mixing cycles. Failed/deferred/not-attempted targets remain unknown, not zero access; successful empty targets have scope rows but no fabricated grants.
- [ ] Test useful in-progress evidence both with and without an older useful finished cycle: prefer the finished cycle when available; otherwise select the newest useful in-progress cycle. Verify selected cycle/state/observation range and latest attempt/cycle/time are distinct, with stale/previous-scope warnings when older evidence is selected.
- [ ] Test a newer all-failed or deferred cycle: it must not displace useful selected grants or silently become healthy zero; preserve latest-attempt/stale warnings. With no successful selectable observations, grant counts remain blank while valid unsuccessful scope evidence remains visible. Verify unresolved identities/counts and unknown expected totals are not invented.
- [ ] Missing/malformed/broken/cyclic/inconsistent evidence chains are not admitted and raise diagnostics and `Load Errors`; a final successful slice alone must not count as a complete cycle. A valid failed target need not increase integrity errors, but must remain visible in outcomes/status.
- [ ] On page 11, check the prominent partial warning, Successful/Expected target cards, outcome-sorted scope table, HTTP/time/ID/cycle columns and layout without overlaps. Apply principal/grant slicers: observed grant counts may change, but global coverage, warnings and the failed target must remain visible. Reconcile against the selected manifest chain, not a presumed row-count baseline.
- [ ] Test job polls with zero observations, partial failures, missing/invalid artifacts and interrupted/unvisited targets. Scope outcomes must not fabricate jobs or complete coverage. Across retained runs, repeated ongoing jobs update status/duration without double counting; the same job ID under different workspace/item parents stays distinct. Jobs outside the recent-100 window and from deselected items remain visible. No raw failure payload is imported.
- [ ] A connection with `displayName: null` remains present with null `Display Name` and an ID-based UI label; safe metadata renders without credential/path fields.
- [ ] A visible pipeline with successful empty history remains in pipeline inventory with no invented operation row.
- [ ] Across retained runs, an ongoing operation observed again updates status/duration without double counting. The same operation ID in two pipelines remains two operations. Old operations outside the API's recent-20 window and operations from no-longer-discovered pipelines remain visible/selectable.
- [ ] Connection, gateway, pipeline, workspace, item, principal, date, status and type filters produce expected fact counts without duplicate inflation. Health/last-attempt/snapshot diagnostics stay source-wide and visible under those filters, including failure states. Clear slicers to reconcile totals; test nullable timestamps/durations, null source names, UI-only labels and unrecognised API status values.
- [ ] Reconcile one capacity's utilization for one day against the Capacity Metrics app (percent values are fractions, not x100).
- [ ] Confirm the Activity row count for one day against the source files (no duplicates).
