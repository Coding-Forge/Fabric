# Changelog

## Enhancement E10: MonitorRaw Power BI Project

Reviewed and approved by Code Reviewer. **Not validated in Power BI Desktop**: the project was never opened or refreshed there. No code, tests or infrastructure changed.

- New PBIP `Fabric/MonitorRaw/MonitorRaw.pbip`: TMDL semantic model (Import mode) and PBIR report with 8 pages (capacity utilization, carry-over, activity overview, git connections, tags, delegated settings, widely shared links, about and setup).
- Reads the raw JSON output directly (no silver/gold layer). Source is selected with `SourceType` (`Local` or `Blob`), plus `LocalFolder`, `BlobAccountUrl`, `BlobContainer` and `BlobRootPath`.
- Dates come from the `<module>/YYYY/MM/DD` folders, not modified time. E5 modules use the latest snapshot (not summed); capacity metrics reruns use latest-run-wins. Malformed JSON shows as Load Error rows.
- Privacy: the Activity table includes `UserId` (UPN/email).
- Known risks: Desktop-only behaviours and unverified field names for Git connections, Tags, Delegated settings and Widely shared links (wrong names give null columns, not errors). A wrong `LocalFolder` that exists but has no module folders gives empty tables without an error.
- `Fabric/MonitorRaw/.gitignore` re-includes `*.json`, which the root `.gitignore` ignores.
- Details and the acceptance checklist: [Fabric/MonitorRaw/README.md](../Fabric/MonitorRaw/README.md). Plan status: [enhancement-plan.md](enhancement-plan.md#e10-outcome).

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
