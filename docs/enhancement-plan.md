# Monitor Enhancement Plan (informed by FUAM)

Working document. Update the **Status** column as items are completed.
Status values: `todo`, `in-progress`, `blocked`, `deferred`, `done`, `skipped`.

Reference: FUAM = `fabric-toolbox/monitoring/fabric-unified-admin-monitoring`.
Constraint: the monitor is **not bound to Fabric**. Do not adopt `sempy`, `notebookutils`, `mssparkutils`, or Spark.
Use plain Python (`aiohttp`/`requests`, `pandas`/`pyarrow`/`deltalake`) against Blob/ADLS.

**API scope requirement:** every enhancement must identify Admin versus non-Admin
API usage explicitly. Before introducing or changing a non-Admin route, document
why it is needed, endpoints/methods, supported identities and resource permissions,
broader powers of required roles, discovery/selection boundaries and absent scope
controls, enablement/defaults, quotas/network constraints, saved data/sensitivity,
side effects and coverage/failure semantics. Separate offline tests from live
acceptance. Keep the customer-facing
[API scope register](configuration-reference.md#api-scope-and-authorization-boundaries)
and applicable module guidance consistent; admin discovery is not resource access.

## A. Bugs to fix

| # | Status | Area | File | Problem | Fix |
|---|--------|------|------|---------|-----|
| B1 | done | Catalog | `env/modules/catalog.py` | `lastFullScan` never saved by `audit.py`, so every run is a full scan | Persist `lastFullScan` in state when a full scan completes |
| B2 | done | Catalog | `env/modules/catalog.py` | Scan-status loop has no sleep (`scanStatusSleepSeconds` unused); persistent error spins forever | Sleep between polls, cap attempts, fail the batch |
| B3 | done | Catalog | `env/modules/catalog.py` | `time.sleep` blocks the event loop; `"ERRORs"` typo hides scan errors; `None` result raises | Use `asyncio.sleep`, fix key, guard `None` |
| B4 | done | Roles | `env/modules/roles.py` | Non-OK response leaves `continuationToken` `None`; `break` inside `if response.ok` so it retries forever | Break/raise on non-OK; add retry cap |
| B5 | done | Gateway | `env/modules/gateway.py` | `status_base` mutated and re-appended, so all entries identical; `results['value']` KeyError on non-200 | Copy dict per entry; check status code |
| B6 | done | Domains | `env/modules/domains.py` | Same `domain` dict reused for every workspace; appended again after loop; reads state key `activity` | Build a new dict per row; use the `domains` key; guard missing state |
| B7 | done | Audit | `env/audit.py` | `exclude_personal_workspaces()` / `exclude_inactivate_workspaces()` call a bool attribute, raising `TypeError` | Set the attribute instead of calling it |
| B8 | done | Audit | `env/audit.py` | State-read failure leaves `current_state` unbound (`NameError`) | Default to empty state |
| B9 | done | Audit | `env/audit.py` | `asyncio.gather` without `return_exceptions`; one failing module loses state for the others | `return_exceptions=True`; update state per successful module |
| B10 | done | Context | `env/context.py` | `convert_dt_str` calls `exit()` on bad date, killing the worker | Raise `ValueError` |
| B11 | done | Context | `env/context.py` | `get_cron` has no branches for Domains, FabricItems, Workspaces, CapacityMetrics; cron ignored | Add branches and env vars |
| B12 | done | Activity / RefreshHistory | `env/modules/activity.py`, `refreshhistory.py` | `{"ERROR"}`/429 swallowed, module still marked as run; days lost | Return failure to audit; do not advance `lastRun` |
| B13 | done | Activity | `env/audit.py` / state | Missing state defaults to `2024-05-31` (about 500 days of calls beyond 30-day retention) | Clamp start to max 30 days back |
| B14 | done | Async | `tenant.py`, `gateway.py`, `graph.py`, `roles.py`, `blob.py`, `local.py` | Blocking `requests`/SDK calls in async code; `os.chdir` is process-global | Move to `aiohttp`/`asyncio.to_thread`; use absolute paths |
| B15 | done | RefreshHistory | `env/modules/refreshhistory.py` | Whole list saved inside per-dataset loop (quadratic writes) | Save once after the loop |
| B16 | done | Config | `.env.example`, `app/monitor.py` | `.env.example` uses `TenantId`/`ClientId`; code reads `TENANT_ID`/`CLIENT_ID`/`CLIENT_SECRET` | Align names |

B1-B16 are implemented and were approved by Code Reviewer (127 passing unit tests). See [changelog.md](changelog.md) for behaviour details and the known non-blocking gaps.

## B. Enhancements (priority order)

| # | Status | Enhancement | Borrow from FUAM | Change in monitor | Fabric-independent approach |
|---|--------|-------------|------------------|-------------------|-----------------------------|
| E1 | done | Throttle-aware HTTP client (`Retry-After`, backoff, concurrency cap) | `src/01_Transfer_Incremental_Inventory_Unit.Notebook` (`RequestWithRetry`) | `env/context.py::invokeAPI`; adopt in `gateway.py`, `graph.py`, `roles.py`, `tenant.py` | One `aiohttp` helper with semaphore (16 for scanner) |
| E2 | done | Robust state: per-module success, UTC, per-day checkpoint | `Load_Activities_E2E.DataPipeline` day loop; `01_Create_Snapshot_Tables_Unit` | `env/audit.py`, `state.yaml` handling | State in Blob; update only on success |
| E3 | done | Incremental inventory with parallel scan polling | `01_Transfer_Incremental_Inventory_Unit` | `env/modules/catalog.py` | Poll `scanStatus` with sleeps; up to 16 concurrent scans; persist `lastFullScan` |
| E4 | todo | Silver/gold layer (keep raw JSON as bronze) | `02_Transfer_Activities_Unit`, `01_Tags_Unit`, `03_Aggregate_Activities_Unit`, `Init_FUAM_Lakehouse_Tables` | New `env/transform/` package | pandas/pyarrow to Parquet/Delta in same container |
| E5 | done (active items part not changed; see note below) | New modules: Git connections, tags, delegated tenant-setting overrides, widely shared links, active items | `01_Transfer_Git_Connections_Unit`, `01_Tags_Unit`, `Load_Delegated_Tenant_Settings_Overrides_E2E`, `01_Transfer_WidelyShared_*_Unit`, `01_Transfer_Active_Items_Unit` | New files in `env/modules/`; export in `env/modules/__init__.py` | Plain REST calls |
| E6 | done, with open concerns | Dated snapshot history (capacities, workspaces, items): raw dated layout exists (`<module>/YYYY/MM/DD/`); history tables (`*_history`) deferred along with E4, which is intentionally not pursued | `01_Create_Snapshot_Tables_Unit` | Domains folder date fix (`env/modules/domains.py`); see open concerns below | Raw dated folders in Blob; no `*_history` tables |
| E7 | done (validated live against the real Capacity Metrics model; 355 tests pass) | Capacity Metrics DAX per Metrics-app version and table | `01_Transfer_CapacityMetricData_Timepoints_Unit`, `02_..._ItemKind_Unit`, `03_..._ItemOperation_Unit` | `env/modules/capacity_metrics.py` | Keep `executeQueries` REST; do not use `sempy.evaluate_dax` |
| E8 | partial (optional retention infra done, default off; delayed pseudonymisation deferred; see "E8 and E9 outcome") | Anonymisation after N days, retention | `02_Transfer_Activities_Unit` (`anonymize_after_days`), `01_FUAM_Lakehouse_Backup` | Hash step in transform; lifecycle rule in `infra/core/storage/storage-account.bicep` | Blob lifecycle management |
| E9 | in-progress (MSAL token cache done; Key Vault reference wiring done in Bicep, not live-validated) | Auth hardening: token cache, Key Vault/cert secret | `media/documentation/FUAM_Authorization.md` | `env/clients/baseClient.py` | One MSAL `ConfidentialClientApplication` per client; Key Vault reference in Function App settings |
| E10 | built, awaiting Desktop validation (see "E10 outcome") | Reporting on raw JSON (no gold layer) | `FUAM_Core_SM.SemanticModel`, `Generate_Calendar_Table` | `Fabric/*.pbit`; new `pbip-local/MonitorRaw/` PBIP | Import of raw JSON from a local folder or Blob (Direct Lake needs Fabric) |
| E11 | done (366 tests pass; no remote check, by design) | Version check, changelog, update guide | `Check_FUAM_Version.Notebook`, `how-to/How_to_update_FUAM.md` | Version file, `docs/` | None needed |
| E12 | todo | Tests | Neither project has them | New `tests/` | Unit tests: `is_function_due`, pagination, state handling |

E1, E2, E3 are implemented and E9 is partly implemented. Code Reviewer approved the implementation and tests (226 passing, independent of the local time zone). Details are in [changelog.md](changelog.md).

### E8 and E9 outcome

Code Reviewer approved the infrastructure (Bicep) work for E8 and E9. It was **compile-validated only** (`az bicep build`); it has not been deployed. Parameters are described in [deployment.md](deployment.md) and [configuration-reference.md](configuration-reference.md#bicep-parameters-e08-and-e09).

**E8 (partial)**
- Done: optional blob retention through a storage lifecycle management policy (`infra/core/storage/storage-lifecycle-policy.bicep`, wired in `infra/main.bicep`). It is **off by default** (`enableRetention=false`).
- Deferred: delayed pseudonymisation or anonymisation after N days. It needs a field-by-field policy first (which fields are personal data, and how each is hashed or dropped).
- A native lifecycle rule is **not** anonymisation. It only deletes whole blobs by age. It does not alter or hash content, and it does not cover blob versions or snapshots.
- Default no-medallion scope: there is no silver/gold layer (E4 is not pursued), so retention applies only to raw module folders. There is no transform step in which a hash could run.

**E9 (Key Vault part)**
- Done in Bicep: `CLIENT_SECRET` can be set as a Key Vault reference to an existing secret, with opt-in RBAC (`Key Vault Secrets User`) for the Function App identity.
- Not live-validated: no deployment has been run. The first deploy can show the reference as unresolved until RBAC propagates.
- Not done: certificate-based credentials.

### E10 outcome

Status: **built, awaiting Desktop validation.** Final cycle-2 Code Reviewer verdict: **Approved** for production and tests, including the subsequent single-cycle partial-permission report. Native Power BI Desktop M/DAX/schema/open/refresh/render acceptance has **not** been performed for the updated project; this does not close E10.

- Location: `pbip-local/MonitorRaw/MonitorRaw.pbip` (TMDL semantic model, PBIR report, **12 pages**, up from 10). Pages 9–12 are **Connections inventory**, **Deployment operations**, **Item Permissions** and **Fabric Job History**; About includes collection diagnostics. Guide: [pbip-local/MonitorRaw/README.md](../pbip-local/MonitorRaw/README.md).
- No medallion layer: E4 is not pursued, so the model reads the raw dated JSON (`<module>/YYYY/MM/DD/`) in **Import** mode.
- Source selector: `SourceType` switches between a local folder (`LocalFolder`, the `LOCAL_OUTPUT_PATH` output; see [local-development.md](local-development.md#local-folder-poc-mode)) and Blob Storage (`BlobAccountUrl`, `BlobContainer`, `BlobRootPath`).
- E7 coverage: Capacity Metrics and Capacities tables (utilization and carry-over; latest run wins on reruns).
- E5 coverage: Git connections, Tags, Delegated settings and Widely shared links (latest snapshot, not summed across days). Activity is also covered.
- Fabric collector coverage: Connections, Deployment Pipelines, Deployment Operations and disconnected Collection Status now also include **Item Permissions**, **Item Permission Scope**, **Fabric Job History** and **Fabric Job Scope**, consuming immutable UTC resources/manifests for all four collectors. Health/About diagnostics and global `Load Errors` cover connections, deployments, permissions and jobs. See [collector configuration and limits](configuration-reference.md#scoped-fabric-collectors).
- Permissions select one validated linked cycle: newest useful finished cycle (including partially failed or successful-empty observations), otherwise newest useful in-progress cycle; no cross-cycle grant merge/carry-forward. Only successful access observations supply grants; failed/deferred/not-attempted targets mean unknown access, not zero. Selected evidence and latest attempts remain distinct with stale/previous-scope warnings. Page 11 has prominent partial coverage, disconnected manifest-derived Successful/Expected counts and outcome/HTTP/time/identity/cycle scope evidence that principal/grant slicers cannot hide. Invalid/broken/cyclic evidence contributes integrity load errors, separately from collection outcomes. Groups are not expanded; coverage is explicit items, not complete tenant/effective access. Full semantics: [report guide](../pbip-local/MonitorRaw/README.md#item-permissions-and-fabric-jobs).
- Job history combines successful committed observations from all retained runs, selecting newest state by workspace ID/item ID/job instance ID. Ongoing jobs update without duplicate inflation; old jobs beyond the API's recent-100 completed plus active window and deselected targets remain. Scope poll outcomes are separate; interrupted polls cannot identify unvisited targets. Raw failure payloads are excluded from report import. Polling gaps and deleted source history remain unrecoverable.
- With no permissions/jobs files, **Not collected** is expected, not healthy empty collection; report files do not establish live collector settings. Report pages never enable collectors or auto-select scopes. Choose exact workspace/item/type targets before setting `FABRIC_ITEM_ACCESS_SCOPE` / `FABRIC_ITEM_JOB_SCOPE` and deliberately selecting modules in `APPLICATION_MODULES`; see [settings and enablement](configuration-reference.md#settings-and-enablement) and [operating guidance](local-development.md#operating-the-four-fabric-collectors). No whole-tenant auto-enablement is implied.
- Connections select the latest healthy committed full snapshot; pipelines select latest committed successful discovery (usable even when a finished run has partial operation failures). Successful empty inventory clears older rows. Missing/failed/interrupted artifacts never become healthy empty snapshots; prior usable inventory is retained with warnings where available.
- Deployment history combines successful committed resources across all retained runs and selects newest `observedAt` per pipeline ID/operation ID. It retains operations outside the API's recent-20 window and from pipelines absent from current discovery; it cannot recover polling gaps or deleted source history. Current pipeline inventory is separate, with no invented operation rows.
- Null connection names remain null in the source column; UI labels alone fall back to identity. Only safe connection metadata is imported. Coverage is caller-visible, not tenant-wide; operation history requires pipeline Admin. Fact slicers do not filter disconnected collection health, and global `Load Errors` includes malformed/invalid or missing Fabric artifacts.
- Latest partial-permission cycle-2 reviewer-reported evidence: **8 targeted and 511 full offline tests passed** under DNS/socket guards; Ruff format/lint, static Python 3.10 syntax and parsing/reference checks passed (114 JSON files, 24 tables, 12 pages, 188 valid field references). The requests warning was nonfailing. Tests cover structure/bindings, missing-versus-zero counts, disconnected coverage and mutation/filter protections, not native M/DAX execution or TMDL schema validity; cached schemas were unavailable. This establishes neither Windows/Desktop behavior nor live API/storage integration.
- Open risks: Desktop-only behaviours and unverified E5 field names are listed in the [Validation status](../pbip-local/MonitorRaw/README.md#validation-status). Field names for the four E5 tables were not checked against real payloads.
- Privacy: the Activity table holds `UserId` (UPN/email). E8 retention is optional deletion, not anonymisation.
- To close E10: record actual Windows Desktop acceptance using the [full checklist](../pbip-local/MonitorRaw/README.md#acceptance-checklist), Local then Blob with matching controlled fixtures. Open/reload updated definitions and refresh all **12 pages**, verifying existing pages as well as new visuals/status/scopes/grants/jobs. Existing files suffice without `func start` or a Functions restart; later collector configuration/enablement requires a separate authorized host restart/start, not a report update.
- Native checks remain pending: empty/never-run new pages with Not collected, healthy/empty/partial finished permission cycles, in-progress fallback, newer all-failed cycles, single-cycle/no-mix selection, explicit stale/latest-attempt warnings, invalid/broken/cyclic evidence rejection and filter-resistant coverage/failed-target visibility. Also verify empty histories without invented facts, ongoing job/operation updates, old/deselected history retention, raw status values, null source names/UI-only labels and source-wide status/About/load diagnostics in Local and Blob modes. E5 real-payload name checks and existing capacity/activity acceptance remain required. Static approval alone does not establish that the report opens, refreshes or renders successfully.

### E7 outcome

E7 was approved by Code Reviewer (355 tests passing) and validated live against the real Capacity Metrics semantic model. `env/modules/capacity_metrics.py` was rewritten; the old query used a table (`CUDetail`) that does not exist. The new module runs scoped `SUMMARIZECOLUMNS` queries per capacity and per UTC day, and selects a measure set by probing for the `Cumulative carry over %` measure. It still uses the `executeQueries` REST API (no `sempy`). The output format changed and is breaking for consumers. Details: [changelog.md](changelog.md) and [configuration-reference.md](configuration-reference.md#capacity-metrics-capacitymetrics).

Remaining risks: Microsoft does not support consuming the model, so the schema may change between app versions, and an app upgrade can change the workspace and dataset IDs. The measure-set probe covers the two known versions only.

### E6 open concerns

E6 was approved by Code Reviewer (269 tests passing) and is marked done with these open concerns.

**Layout deviations from `<module>/YYYY/MM/DD/`**
- Apps write under `catalog/scans/` and `catalog/snapshots/`.
- `delegatedsettings/<scope>/` puts the scope before the date.
- Some folder names differ from module names: `fabricitems` -> `items/`, `refreshables` -> `datasetrefreshable/`, `refreshhistory` -> `datasetrefresh/`. Graph data is under `graph/`.

**Clocks** (resolved)
- Resolved: the mixed local/UTC clocks concern. Apps, capacity, capacity_metrics, workspaces, roles, fabricitems, tenant, graph, refreshables and refreshhistory now use `utc_now()`. The import-time module-level `today` is removed, so dates are computed per run. See [changelog.md](changelog.md).
- Remaining: `catalog_bkbk.py` (a dead file) still uses local time.

**Overwrites and stale files**
- Same-day reruns overwrite fixed-name files. Index-named files can leave stale pages from an earlier, longer run.
- `admin_paging` merges each endpoint into one file.
- `state.yaml` is overwritten each run. History would need blob versioning.

**Data semantics**
- Activity and Catalog write delta/event data, not full state per day. Full state is the last full scan plus later deltas.
- Snapshots do not record who changed an item. Use Activity events, and consider joining them to inventory.

**Missing features**
- Retention is optional and off by default (E8, see "E8 and E9 outcome").
- Legacy collectors have no `latest` pointer or per-run manifest. The four new [scoped Fabric collectors](configuration-reference.md#scoped-fabric-collectors) use run-ID folders and manifests; this does not migrate legacy outputs.

**Positioning.** Dated snapshots complement Terraform and Fabric CI/CD drift detection. They do not replace them.

### Not done, and why

| # | Reason it is not done |
|---|-----------------------|
| E4 | Needs a schema design decision first (silver/gold layout). Intentionally not pursued. |
| E5 (active items) | Done for `GitConnections`, `Tags`, `DelegatedSettings`, `WidelySharedLinks` (264 tests passing, approved by Code Reviewer). The "active items" part is unchanged: `FabricItems` already calls `/v1/admin/items`; `state=active`/tags handling is a follow-up. |
| E7 | Now done; see "E7 outcome" above. |
| E8 | Partial. Optional retention infra is done (default off, compile-validated only). Delayed pseudonymisation is deferred until a field-by-field policy exists. A native lifecycle rule is not anonymisation. |
| E9 (Key Vault part) | Key Vault reference wiring is done in Bicep (compile-validated only, not live-validated). Certificate credentials are not done. |
| E10 | Built, awaiting Desktop validation. The updated 12-page PBIP exists (`pbip-local/MonitorRaw/`, raw JSON Import, Local/Blob switch, E5/E7 and all four Fabric collectors) and has static Code Reviewer approval, but updated native open/refresh/rendering acceptance remains pending. Previously working pages do not validate this reconciliation. E5 field names remain unverified against real payloads. See "E10 outcome". |
| E11 | Now done (approved by Code Reviewer, 366 tests passing); see [updating.md](updating.md). Remaining gap: container images do not copy `VERSION` or `env/`, so containers log `unknown`. |
| E12 | Initial tests exist (226); add further tests as needed. |

## C. Suggested order of work

1. B7-B10 and B16 (small, unblock everything else).
2. E1 (HTTP client), then B2-B5, B12 on top of it.
3. E2 plus B1, B11, B13 (state).
4. E3 (catalog).
5. E4/E6 (transform and snapshots), then E5, E7.
6. E8-E12.

## D. Notes

- Analysis was a static read; nothing was executed against either repo.
- Measure real CU/API cost before and after changes if running on a shared capacity.

## E. Collection and lineage follow-up backlog

These are tracked follow-ups, not enabled features or authorization to expand
collection scopes, grant access, deploy infrastructure, or execute workloads.
Implementation requires confirming the scope, permissions, API budget and
validation approach for each item.

### Feature backlog

| # | Status | Item | Scope and considerations |
|---|--------|------|--------------------------|
| E13 | deferred | Automatic tenant-wide job discovery | Previously deferred. Jobs currently require explicit item scopes. Define supported types, filtering, pagination and polling budgets before expanding discovery. |
| E14 | in-progress | Automatic tenant-wide permission collection | Code complete and offline-tested: opt-in `FABRIC_ITEM_ACCESS_MODE=tenant` with active Admin item discovery, resumable permission collection, explicit unsupported/denied outcomes and existing quota controls. Default explicit scopes remain unchanged; tenant JSON stays separate, with explicit MonitorRaw `ItemPermissionMode=Tenant` input available. Live collection and new report refresh acceptance remain pending; tenant-wide collection is not enabled automatically. |
| E15 | done | Pipeline activity lineage (agreed static increment) | Added static notebook/child-pipeline calls, supported Copy source/sink references and nested activity traversal to new capture JSON only. No additional API requests, execution, report changes or automatic backfill. Dynamic/unsupported targets remain explicit diagnostics; live exports succeeded and the operator confirmed the seven-reference summary for the collected sample. Runtime lineage and PBIP integration remain outside this increment. |
| E16 | todo | Actual notebook runtime reads and writes | Current notebook analysis identifies potential dependencies only. Select an authorized execution-evidence source; definition capture must not execute notebooks. |
| E17 | todo | Lineage relationship change detection | Compare compatible complete observations to identify added/removed relationships. Missing, partial or failed collection must not imply deletion. |
| E18 | todo | Recursive impact analysis | Traverse upstream/downstream relationships with cycle protection and explicit coverage limits; do not present partial observations as a complete tenant graph. |
| E19 | todo | Column-level lineage | Determine supported metadata sources and mappings; current lineage does not establish column-level dependencies. |
| E20 | todo | Complete effective permissions | Expand group membership and reconcile inherited/direct access using supported evidence. Current item access observations are not complete effective-access calculations. |

E14 validation: 603 offline tests passed, including 12 new tenant-mode cases for
multi-workspace discovery beyond 50 items, pagination/overlap, restarts, bounded
admission/shared cooldowns, unsupported/denied targets, failed discovery,
empty results, invalid controls, manifest failure and checkpoint behavior.
Ruff lint/format, Python 3.10 syntax and whitespace checks passed.
This does not establish live tenant coverage, API cost or remote persistence.
Next acceptance gate: deliberately enable tenant mode and validate collected
scope/outcomes and quota-safe recovery before proceeding to another enhancement.
The initial collector increment excluded PBIP integration; the subsequent
approved MonitorRaw extension is described below. See
[tenant-mode scope and operation](configuration-reference.md#tenant-wide-permission-collection-opt-in).

E14 live sweep (2026-11-05): seven inventory pages discovered 101 active items
across 29 workspaces; all 101 received attempted access outcomes. The sweep saved
127 access rows from 48 successful items and recorded 53 failed items: three
Dataflow HTTP 404 responses (`errorCode=unrecognized`), plus 22 SemanticModels,
20 Reports, six Apps and two Dashboards without saved HTTP error diagnostics.
Those 50 failures require further diagnosis; the saved evidence does not
establish whether the API response shape or collector validation is at fault.
The bounded permissions-only runner exited normally after this cycle. Evidence
was committed, progress reset, the request gate was neither pending nor blocked,
and the success checkpoint remained unchanged as required for an unhealthy cycle.
Live acceptance remains pending; failed targets have unknown access.

An operator-approved diagnostic pass subsequently read one previously failed
Report, SemanticModel, App and Dashboard through the same quota gate. All four
returned HTTP 200 with permission lists, but `itemAccessDetails.type` and
`additionalPermissions` were null. The current collector rejects both shapes.
This confirms a collector-validation incompatibility for those four samples,
not the cause of every historical failure or a resolution of the Dataflow 404s.
Only sanitized response-shape diagnostics were retained separately; the pass
did not change permission progress, checkpoints, grants or production code.

Nullable-metadata correction: the operator subsequently approved a narrow
collector fix, focused tests and four follow-up reads. Scoped and tenant
collection now preserve explicit null detail types/additional permissions only
for the five query-typed Power BI types; missing/conflicting types and malformed
principals or permission lists still fail. The existing scoped MonitorRaw
validator and nullable detail-type column were kept consistent, without adding
tenant report integration. All four follow-up reads returned HTTP 200 and passed
the corrected validator. The 46 permission/report regression tests, Python 3.10
syntax, Ruff lint/format, whitespace checks and Microsoft Power Query syntax
parsing passed. Those checks do not execute M/DAX; basic operator Desktop
acceptance is recorded below.
The historical 53 failed outcomes were not rewritten and no new tenant sweep
was started; full recollection and the three Dataflow 404s remain outstanding.

Bounded Dataflow validation: all three failed identities matched the saved
active-item discovery exactly once, and their routes matched the documented
Admin access endpoint with `?type=Dataflow`. Three approved retries again returned
HTTP 404 with sanitized `errorCode=unrecognized`. The targets are in
Fabric-Engineering (two) and PipelineDemo (one); the inspected saved Scanner
result did not resolve their names or generation. The operator subsequently
confirmed that all three exact items still exist and are Dataflow Gen2. This
establishes an observed access-collection gap for those existing Gen2 items,
not universal Gen2 non-support or a permissions cause. Microsoft's underlying
reason remains unconfirmed and may require a support investigation.
Quota controls remained clear; progress and checkpoints were unchanged.
No fallback API, permission change, production-code change or new sweep was used.

Approved post-fix tenant sweep completed at 2026-11-05T15:20:51Z: seven inventory
pages discovered 101 items, all 101 access targets were attempted, 95 succeeded
and six failed, with 200 access-detail rows saved. Failures comprise the three
Dataflow HTTP 404s, two Apps and one SemanticModel; the latter three have no
saved HTTP status in the runner summary and their causes are not established.
Successful targets increased from 48 in the earlier sweep to 95, but this is
still partial coverage, not healthy end-to-end acceptance. Final immutable
evidence confirms `cycleFinished=true`, `cycleHealthy=false`, `complete=false`
and cursor 101/101. The success checkpoint stayed unchanged; the runner stopped
normally and the quota gate was clear. No further sweep or diagnostic calls
were started, and deeper Dataflow investigation remains deferred.

E15 validation: 591 offline tests passed, including parser and capture integration
regressions; targeted Ruff lint/format and whitespace checks passed. See
[supported shapes, output and limitations](configuration-reference.md#notebook-and-data-pipeline-definitions).
After the operator granted the service principal Contributor access to the six
failing workspaces, the live sweep completed at 2026-11-04T22:33:39Z with all 17
definitions saved, including all 12 previously failing items, and no HTTP errors.
The definition checkpoint advanced and progress finished. The operator reviewed
the summary of nine notebooks, eight pipelines, seven static references and four
analysis diagnostics and confirmed that it checks out. This records acceptance
of the presented sample, not exhaustive parser coverage, actual runtime lineage
or PBIP integration.

### Existing roadmap items retained

| Existing item | Status | Remaining work |
|---------------|--------|----------------|
| E9 | todo (certificate credentials) | Add certificate-based authentication; token caching and Key Vault secret-reference wiring already exist. |
| E8 | deferred (anonymisation) | Define a field-by-field policy before implementing delayed pseudonymisation/anonymisation. Optional retention deletes blobs; it does not anonymise them. |
| E4 / E6 | deferred | Silver/gold transforms and curated history tables remain intentionally outside the current raw-JSON scope; do not treat them as approved implementation work. |

### Operational and validation follow-ups

| # | Status | Item | Completion evidence |
|---|--------|------|---------------------|
| E21 | done | Resolve definition-export HTTP 401 responses | Following the operator's Contributor grants, all 12 previously failing Notebook/DataPipeline exports across six workspaces succeeded in a complete 17-item sweep on 2026-11-04. Saved files and checkpoint advancement verified; no HTTP errors. No private-link routing changes were needed for this test. Admin discovery alone does not grant export access. |
| E10 / Catalog | in-progress (basic Desktop checks accepted) | Operator confirmed both PBIP reports check out following the requested reopen/refresh and page checks. Detailed fixture/edge-case scenarios in the existing E10 acceptance checklist have not been individually confirmed. |
| E14 / MonitorRaw | basic Desktop checks verified; detailed scenarios pending | Operator screenshots show Scoped 12/13 and Tenant 95/101 successful targets, six tenant failures and 200 access-detail rows. Tenant permission load errors are zero. Shared `ItemPermissionMode` defaults to `Scoped`; `Tenant` loads only tenant evidence. Empty/broken-link fixtures and Local/Blob parity remain unconfirmed; historical job warnings stay preserved. |
| E8 / E9 deployment | deferred | Validate retention and Key Vault wiring in Azure | Requires an approved deployment and live verification. Existing Bicep compile checks do not prove deployed behavior. |
| E22 | in-progress | Commit and push the local runtime fixes | PR preparation approved: preserve local Desktop state, publish Scoped as the shared permission default, exclude unrelated Capacity_Gateways, validate the staged tree and check against remote main before opening the PR. Unresolved collection outcomes remain explicit limitations. |

Desktop validation update (2026-11-05): after confirming both projects opened
and rendered, the operator reported "The PBIP reports check out" following the
requested reopen/refresh and page checks. This records operator acceptance of
basic Desktop behavior, not independent verification of every fixture/edge-case
scenario. It preceded the E14 MonitorRaw extension and does not validate its
tenant input. Static notebook/pipeline references remain outside the reports.

MonitorRaw tenant integration: validates paginated discovery/access chains,
cross-workspace identities, ordered cursors, failures/deferrals and unknown
totals until inventory completes. Selected cycles and modes are not merged;
healthy empty tenant discovery clears older grants, and failed targets remain
unknown access. Existing canonical permission measures and disconnected global
coverage are preserved. Microsoft syntax parsing passed for the new parameter,
shared loader and permission/job routing expressions; static tests are not
native M execution. Subsequent operator screenshots confirm the selected
Scoped/Tenant views and counts above against existing output, without starting
Functions. Broader empty/broken-chain fixtures and Local/Blob parity remain part
of the unconfirmed Desktop checklist.

Job-history diagnostics: read-only inspection of 92 saved runs reproduced the
three load errors shown in Desktop. Three historical runs (2026-10-20,
2026-10-22 and 2026-11-04) have resource observation times later than their final
manifest times. A backwards wall-clock adjustment could explain the inversion,
but its historical cause is not established. The approved future-run guard
checks the maximum timestamp of saved resources before committing a final
manifest; backwards ordering raises and prevents success/checkpoint advancement.
No timestamp clamping, historical rewrite, report-validation relaxation or live
API calls were used. All three warnings remain visible as agreed.
