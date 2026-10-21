# Monitor Enhancement Plan (informed by FUAM)

Working document. Update the **Status** column as items are completed.
Status values: `todo`, `in-progress`, `done`, `skipped`.

Reference: FUAM = `fabric-toolbox/monitoring/fabric-unified-admin-monitoring`.
Constraint: the monitor is **not bound to Fabric**. Do not adopt `sempy`, `notebookutils`, `mssparkutils`, or Spark.
Use plain Python (`aiohttp`/`requests`, `pandas`/`pyarrow`/`deltalake`) against Blob/ADLS.

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
- No `latest` pointer and no per-run manifest.

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
