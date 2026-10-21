# Changelog

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
