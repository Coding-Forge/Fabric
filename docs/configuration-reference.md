# Configuration Reference

All settings are environment variables. Locally they are set in `local.settings.json` under `Values`. In Azure they are set as **Function App → Settings → Environment variables**.

---

## Required Settings

| Variable | Description |
|---|---|
| `TENANT_ID` | Azure AD tenant ID. Used by MSAL for Power BI / Fabric API token acquisition. |
| `CLIENT_ID` | App registration (service principal) client ID. |
| `CLIENT_SECRET` | App registration client secret. **Use a Key Vault reference in production.** |

> The legacy names `TenantId`, `ClientId` and `ClientSecret` are still accepted as fallbacks; the canonical names above take priority when both are set.
| `APPLICATION_MODULES` | Comma-separated list of modules to run. See [Modules](#modules) below. |

---

## Storage Settings

Exactly one storage mode must be configured: **Blob Storage URL** (recommended), **Blob Storage connection string**, or **Fabric Lakehouse**.

### Option A — Blob Storage with URL auth (recommended)

Uses `DefaultAzureCredential` (Managed Identity in Azure, service principal locally). Works when shared key access is disabled on your storage account.

| Variable | Required | Description |
|---|---|---|
| `STORAGE_ACCOUNT_URL` | Yes | `https://<account>.blob.core.windows.net` |
| `STORAGE_ACCOUNT_CONTAINER_NAME` | Yes | Container name, e.g. `monitor` |
| `STORAGE_ACCOUNT_CONTAINER_ROOT_PATH` | No | Root path prefix inside the container, e.g. `stage` |
| `AZURE_TENANT_ID` | Yes (local) | Same as `TENANT_ID`. Read by `DefaultAzureCredential`. |
| `AZURE_CLIENT_ID` | Yes (local) | Same as `CLIENT_ID`. Read by `DefaultAzureCredential`. |
| `AZURE_CLIENT_SECRET` | Yes (local) | Same as `CLIENT_SECRET`. Read by `DefaultAzureCredential`. |

> In Azure with Managed Identity, `AZURE_*` variables are **not needed** — the identity is resolved automatically.

### Option B — Blob Storage with connection string

| Variable | Required | Description |
|---|---|---|
| `STORAGE_ACCOUNT_CONN_STR` | Yes | Full connection string from the storage account Access keys blade. |
| `STORAGE_ACCOUNT_CONTAINER_NAME` | Yes | Container name. |
| `STORAGE_ACCOUNT_CONTAINER_ROOT_PATH` | No | Root path prefix. |

> Not recommended if "Allow storage account key access" is disabled on your storage account.

### Option C — Fabric Lakehouse

Used when running inside a Fabric environment.

| Variable | Required | Description |
|---|---|---|
| `LAKEHOUSE_NAME` | Yes | Name of the Lakehouse, e.g. `LochMonitor` |
| `WORKSPACE_NAME` | Yes | Name of the Fabric workspace |
| `PATH_IN_LAKEHOUSE` | No | Subfolder path inside the Lakehouse Files, e.g. `stage` |
| `ON_FABRIC` | No | `true` if running inside Fabric runtime (uses `/lakehouse/default/Files/...`). Default: `true` |

---

## Optional Settings

| Variable | Default | Description |
|---|---|---|
| `DRY_RUN` | `false` | When `true`, prints what would be written to blob instead of writing it. Useful for local testing. |
| `ALL_WORKSPACES` | `false` | When `true`, retrieves all workspaces regardless of modification date. |
| `IMPERSONATED_USER_NAME` | _(none)_ | UPN of a user to impersonate for API calls. |
| `CAPACITY_METRICS_DATASET_ID` | _(none)_ | Dataset ID of the Capacity Metrics app semantic model. If unset, the `CapacityMetrics` module logs a warning and returns success. See [Capacity Metrics](#capacity-metrics-capacitymetrics). |
| `CAPACITY_METRICS_DAYS_BACK` | `3` | Days of history to query, minimum 1, maximum 30. |
| `CAPACITY_METRICS_INCLUDE_SUSPENDED` | _(unset)_ | When `1`, `true`, `yes` or `on`, capacities that are not Active are also queried. |
| `API_MAX_RETRIES` | `3` | Maximum retries for throttled or transient API responses (HTTP 429, 503, 504). |
| `API_MAX_CONCURRENCY` | `16` | Maximum concurrent API requests. |
| `API_MAX_RETRY_DELAY` | `120` | Cap, in seconds, on a single retry wait. |

### Throttling and retries

API calls retry on 429, 503 and 504. When the response has a `Retry-After` header, that delay is used, up to `API_MAX_RETRY_DELAY` seconds. If a throttle asks for a longer wait than the cap (this can happen with long scanner throttles), the call is not held; it fails and the module is retried on the next run, because `lastRun` does not advance on failure.

`Roles` also has its own retry loop, which runs on top of the shared retry. A failing call can therefore take longer than the settings above suggest.

If you use `env/.env.example`, you can set these variables there as well. The file is not changed by this documentation update.

---

## Per-Module Cron Overrides

Each module runs on the global timer schedule (`0 0 2 * * *` — daily at 02:00 UTC, defined in `function_app.py`). You can override the effective schedule per module using cron syntax. If not set, the module runs every time the function fires.

| Variable | Module |
|---|---|
| `ACTIVITY_CRON` | Activity Events |
| `APPS_CRON` | Apps |
| `CAPACITY_CRON` | Capacity |
| `CAPACITYMETRICS_CRON` | Capacity Metrics |
| `CATALOG_CRON` | Catalog Scans |
| `DOMAINS_CRON` | Domains |
| `FABRICITEMS_CRON` | Fabric Items |
| `DELEGATEDSETTINGS_CRON` | Delegated Settings |
| `GATEWAY_CRON` | Gateways |
| `GITCONNECTIONS_CRON` | Git Connections |
| `GRAPH_CRON` | Graph (AAD Groups) |
| `REFRESHABLES_CRON` | Refreshables |
| `REFRESHHISTORY_CRON` | Refresh History |
| `ROLES_CRON` | Workspace Roles |
| `TAGS_CRON` | Tags |
| `TENANT_CRON` | Tenant Settings |
| `WIDELYSHAREDLINKS_CRON` | Widely Shared Links |
| `WORKSPACES_CRON` | Workspaces |

A module's cron is evaluated against its `lastRun` in `state.yaml`. `lastRun` advances only when the module succeeds, so a failed module is retried on the next timer. With no state, the first run looks back 7 days; Activity never looks back more than 30 days. See [changelog.md](changelog.md).

**Example:** run Catalog only once a day at midnight UTC:
```
CATALOG_CRON=0 0 * * *
```

### Time zones

All module clocks are UTC. Module cron expressions (the `*_CRON` variables, evaluated with `croniter`) are evaluated in UTC, whatever the host's local time zone. `WEBSITE_TIME_ZONE` affects only the Azure Functions timer trigger in `function_app.py`. It does not change module crons, `lastRun` values or folder dates.

Date folders (`<module>/YYYY/MM/DD/`) use the UTC date. On a non-UTC host, a run near local midnight can land in a different folder than it did before this change. Wire timestamps are ISO strings ending in `Z`.

---

## Modules

All available module names for `APPLICATION_MODULES`:

| Name | Description |
|---|---|
| `Activity` | Power BI activity log events |
| `Apps` | Published Power BI apps |
| `Capacity` | Capacity details |
| `CapacityMetrics` | Capacity Metrics app data (utilization, carry-over) via `executeQueries`; see [below](#capacity-metrics-capacitymetrics) |
| `Catalog` | Full workspace/item catalog scan |
| `DelegatedSettings` | Delegated tenant-setting overrides for capacities, domains and workspaces (opt-in) |
| `Domains` | Fabric domains |
| `FabricItems` | All Fabric items across the tenant |
| `Gateway` | On-premise and VNet gateways |
| `GitConnections` | Workspace Git connections, preview API (opt-in) |
| `Graph` | Azure AD group membership |
| `Refreshables` | Refreshable datasets |
| `RefreshHistory` | Dataset refresh history |
| `Roles` | Workspace role assignments |
| `Tags` | Tenant tags (opt-in) |
| `Tenant` | Tenant settings |
| `WidelySharedLinks` | Links shared to the whole organization and published to web (opt-in) |
| `Workspaces` | Workspace metadata |

### Capacity Metrics (`CapacityMetrics`)

Queries the Capacity Metrics app semantic model through the Power BI `executeQueries` REST API.

**Prerequisites**
- Tenant setting **Dataset Execute Queries REST API** is enabled.
- The service principal is allowed to use Power BI APIs and is a member of the workspace that holds the Metrics app.
- `CAPACITY_METRICS_DATASET_ID` is set to that semantic model's dataset ID.

**Settings:** `CAPACITY_METRICS_DATASET_ID`, `CAPACITY_METRICS_DAYS_BACK` (default 3, range 1-30) and `CAPACITY_METRICS_INCLUDE_SUSPENDED` (see [Optional Settings](#optional-settings)); schedule with `CAPACITYMETRICS_CRON`.

**Behaviour**
- Capacities are read from the `Capacities` table. Non-Active capacities are skipped unless `CAPACITY_METRICS_INCLUDE_SUSPENDED` is truthy. Capacity IDs are validated as GUIDs.
- Window: UTC days from `max(today - DAYS_BACK, lastRun date - 1 day)` through today.
- For each capacity and UTC day, a scoped `SUMMARIZECOLUMNS` query runs over `'All Measures'`. Scoping uses `DEFINE MPARAMETER 'CapacitiesList'` plus `TREATAS` on `'Capacities'[Capacity Id]` and `'Dates'[Date]`. DirectQuery tables return empty results without this scoping.
- Version probe: if the measure `Cumulative carry over %` exists, groups `utilization` and `carryover` are queried; otherwise only `utilization`.
- A failed query makes the run return `False` (`lastRun` does not advance) while the remaining queries continue. A 429 or 5xx after retries aborts the run. An empty result for an Active capacity logs a warning.

**Output.** `capacity_metrics/YYYY/MM/DD/{runYYYYMMDD}_{capacityId}_{group}_{metricDayYYYYMMDD}.capacity_metrics.json`, containing `{capacityId, capacityName, sku, date, group, rows}`. Empty results are not saved. This replaces the earlier paged raw files and is a breaking change for consumers.

**Caveats.** Microsoft does not support consuming this model, so its schema may change. Upgrading the app with "update workspace and app" can change the workspace and dataset IDs; update `CAPACITY_METRICS_DATASET_ID` afterwards.

### E5 admin modules

`GitConnections`, `Tags`, `DelegatedSettings` and `WidelySharedLinks` are **opt-in**. They are not in the default modules, so add them to `APPLICATION_MODULES`, for example:

```
APPLICATION_MODULES=Activity,Catalog,GitConnections,Tags,DelegatedSettings,WidelySharedLinks
```

**Permissions.** The caller must be a Fabric admin, or a service principal with `Tenant.Read.All`. For a service principal, enable the tenant setting **Service principals can access read-only admin APIs**.

**Rate limits.** The admin APIs allow 25 requests per minute. The shared links API allows 200 per hour.

| Module | Endpoint | Output path (each ends in `YYYY/MM/DD`) |
|---|---|---|
| `GitConnections` | `GET /v1/admin/workspaces/discoverGitConnections` (preview) | `gitconnections/` |
| `Tags` | `/v1/admin/tags` | `tags/` |
| `DelegatedSettings` | `/v1/admin/capacities/delegatedTenantSettingOverrides`, `/v1/admin/domains/...`, `/v1/admin/workspaces/...` | `delegatedsettings/<scope>/` (scope = capacities, domains or workspaces) |
| `WidelySharedLinks` | Power BI admin `widelySharedArtifacts/linksSharedToWholeOrganization` and `.../publishedToWeb` | `widelysharedlinks/` (two files) |

**Snapshot semantics.** Modules that list full state write a full copy on each run. A same-day rerun overwrites the earlier files, so compare days to see changes. `Activity` and `Catalog` write delta/event data instead of full state. The `domains` folder date is the current UTC run date.

**Failures.** A 403 or 404 is logged as a warning and the module returns `False`. `lastRun` does not advance, so the module retries on the next tick. For modules with several endpoints (`DelegatedSettings`, `WidelySharedLinks`), data from endpoints that succeeded is still saved. `GitConnections` uses a preview API, so it keeps retrying each tick if the API is unavailable. An empty `{}` response from `admin_paging` is treated as a failure.

Active items are not a separate module: `FabricItems` already calls `/v1/admin/items`. `state=active` and tags handling there is a follow-up.

---

## Timer Schedule

The function is triggered on a CRON schedule defined in `function_app.py`:

```python
@app.schedule(schedule="0 0 2 * * *", ...)
```

This fires once a day at 02:00 UTC. If you set `WEBSITE_TIME_ZONE`, the timer trigger follows that zone; module crons stay in UTC (see [Time zones](#time-zones)). Azure Functions uses a 6-field NCRONTAB format:

```
{second} {minute} {hour} {day} {month} {day-of-week}
```

To change the schedule, edit the `schedule` value in `function_app.py` before deploying.
