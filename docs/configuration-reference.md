# Configuration Reference

All settings are environment variables. Locally they are set in `local.settings.json` under `Values`. In Azure they are set as **Function App → Settings → Environment variables**.

Standalone Python and the Windows UI also accept JSON profiles for connection,
storage, module selection, and scheduling settings:

```powershell
python -m app.monitor --profile .\profiles\local-monitor.json
```

Profile values override environment values. Collector-specific options and scopes
(for example `CATALOG_LINEAGE_ENABLED` and `FABRIC_ITEM_JOB_SCOPE`) are still
environment variables; configure them in the process environment or the CLI's
`--env-file`.

---

## Required Settings

| Variable | Description |
|---|---|
| `TENANT_ID` | Azure AD tenant ID. Used by MSAL for Power BI / Fabric API token acquisition. |
| `CLIENT_ID` | App registration (service principal) client ID. |
| `CLIENT_SECRET` | App registration client secret. **Use a Key Vault reference in production.** |
| `CLOUD_ENVIRONMENT` | `Commercial` (default), `Gcc`, `GccHigh`, or `Dod`. Selects identity authority, API endpoints, and token scopes. |
| `APPLICATION_MODULES` | Comma-separated list of modules to run. See [Modules](#modules) below. |

> The legacy names `TenantId`, `ClientId` and `ClientSecret` are still accepted as fallbacks; the canonical names above take priority when both are set.

---

## Cloud Environment Behavior

| Value | Power BI API root | Graph root | Fabric REST / OneLake |
|---|---|---|---|
| `Commercial` | `https://api.powerbi.com/v1.0/myorg/` | `https://graph.microsoft.com/beta` | Enabled |
| `Gcc` | `https://api.powerbigov.us/v1.0/myorg/` | `https://graph.microsoft.com/beta` | Disabled |
| `GccHigh` | `https://api.high.powerbigov.us/v1.0/myorg/` | `https://graph.microsoft.us/beta` | Disabled |
| `Dod` | `https://api.mil.powerbigov.us/v1.0/myorg/` | `https://graph.microsoft.us/beta` | Disabled |

Non-Commercial runs skip all Fabric REST modules, including the new scoped and
definition collectors, GitConnections, Tags, and DelegatedSettings. Power BI
modules (including WidelySharedLinks) and Graph use the selected cloud endpoints.
Skipped Fabric modules do not authenticate or advance their checkpoints.
Authentication remains lazy so collector request gates are checked before token
acquisition. Runs with failed modules retain their previous checkpoints and
report an unsuccessful result after saving the other modules' progress.

## Storage Settings

Choose local files, Blob Storage URL (recommended), Blob Storage connection
string, or Fabric Lakehouse. `LOCAL_OUTPUT_PATH` is the explicit PoC override.
`OUTPUT_PATH` also selects local output; without any output/storage/lakehouse
settings, standalone Python uses `Data`.

### Option A — Blob Storage with URL auth (recommended)

Uses `DefaultAzureCredential` (Managed Identity in Azure, service principal locally). Works when shared key access is disabled on your storage account.

| Variable | Required | Description |
|---|---|---|
| `STORAGE_ACCOUNT_URL` | Yes | `https://<account>.blob.core.windows.net`, or the account's Azure Government `blob.core.usgovcloudapi.net` endpoint. |
| `STORAGE_ACCOUNT_CONTAINER_NAME` | Yes | Container name, e.g. `monitor` |
| `STORAGE_ACCOUNT_CONTAINER_ROOT_PATH` | No | Root path prefix inside the container, e.g. `stage` |
| `AZURE_TENANT_ID` | Yes (local) | Same as `TENANT_ID`. Read by `DefaultAzureCredential`. |
| `AZURE_CLIENT_ID` | Yes (local) | Same as `CLIENT_ID`. Read by `DefaultAzureCredential`. |
| `AZURE_CLIENT_SECRET` | Yes (local) | Same as `CLIENT_SECRET`. Read by `DefaultAzureCredential`. |

> In Azure with Managed Identity, `AZURE_*` variables are **not needed** — the identity is resolved automatically.

### Option B — Blob Storage with connection string

| Variable | Required | Description |
|---|---|---|
| `STORAGE_ACCOUNT_CONN_STR` or `STORAGE_ACCOUNT_CONNECTION_STRING` | Yes | Full connection string from the storage account Access keys blade. |
| `STORAGE_ACCOUNT_CONTAINER_NAME` | Yes | Container name. |
| `STORAGE_ACCOUNT_CONTAINER_ROOT_PATH` | No | Root path prefix. |

> Not recommended if "Allow storage account key access" is disabled on your storage account.

### Option D — Local folder (proof of concept)

Opt-in. When `LOCAL_OUTPUT_PATH` is set, it takes precedence over Options A–C: the Blob and Lakehouse settings are ignored, so a PoC run cannot write to production storage. See [local-development.md](local-development.md#local-folder-poc-mode).

| Variable | Required | Description |
|---|---|---|
| `LOCAL_OUTPUT_PATH` | Yes (for this mode) | Folder that receives all output, including `state.yaml`. `~` is expanded. Created if missing; startup fails if it is not a writable directory. |
| `COMMERCIAL_TENANT_ID` | No | Alias for `TENANT_ID`, honoured **only** when `LOCAL_OUTPUT_PATH` is set. |
| `COMMERCIAL_CLIENT_ID` | No | Alias for `CLIENT_ID`, honoured only in local mode. |
| `COMMERCIAL_CLIENT_SECRET` | No | Alias for `CLIENT_SECRET`, honoured only in local mode. |

In Commercial local mode the environment credential precedence is `COMMERCIAL_*` > canonical (`TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`) > legacy (`TenantId`, `ClientId`, `ClientSecret`). Profile credentials override environment credentials. Outside `LOCAL_OUTPUT_PATH` mode, or for sovereign clouds, the `COMMERCIAL_*` variables are ignored. They are never used for storage credentials. Legacy collectors ignore `DRY_RUN` in local mode; the four [scoped Fabric collectors](#scoped-fabric-collectors) reject `DRY_RUN=true` in every storage mode.

### Option C — Fabric Lakehouse

Used when running inside a Fabric environment.

OneLake output requires `CLOUD_ENVIRONMENT=Commercial`. Sovereign clouds must
use local files or Blob Storage.

| Variable | Required | Description |
|---|---|---|
| `LAKEHOUSE_NAME` | Yes | Name of the Lakehouse, e.g. `LochMonitor` |
| `WORKSPACE_NAME` | Yes | Name of the Fabric workspace |
| `PATH_IN_LAKEHOUSE` | No | Subfolder path inside the Lakehouse Files, e.g. `stage` |
| `ON_FABRIC` | No | `true` if running inside Fabric runtime (uses `/lakehouse/default/Files/...`). Default: `true` |

---

## Bicep parameters (E08 and E09)

These are parameters of `infra/main.bicep`, not app settings. Both features are optional. The infrastructure was compile-validated only (`az bicep build`) and has not been deployed. Full guidance is in [deployment.md](deployment.md#key-vault-reference-and-blob-retention-e09-and-e08).

| Parameter | Default | Description |
|---|---|---|
| `clientSecretKeyVaultSecretUri` | _(empty = off)_ | Versionless URI of an existing Key Vault secret. Sets the Function App `CLIENT_SECRET` to a Key Vault reference and enables a managed identity. |
| `assignKeyVaultAccess` | `false` | Grants the Function App identity `Key Vault Secrets User` on the existing vault. Only works if the vault uses RBAC authorization. Requires `keyVaultName` and `clientSecretKeyVaultSecretUri`, otherwise the deployment fails. |
| `keyVaultName` | _(empty)_ | Existing vault name. Required when `assignKeyVaultAccess` is true. |
| `keyVaultResourceGroupName` | main resource group | Resource group of the existing vault. |
| `enableRetention` | `false` | Creates a storage lifecycle rule that deletes old output blobs. Replaces any existing management policy on the storage account. |
| `retentionDays` | `90` | Days since last modification before deletion. Minimum 1. |
| `storageRetentionRootPath` | _(empty)_ | Root path inside the container (same as `STORAGE_ACCOUNT_CONTAINER_ROOT_PATH`). No leading or trailing slash. |
| `retentionModules` | `[]` | Module folder names to expire, for example `["activity"]`. Required and non-empty when `enableRetention` is true; entries must not contain slashes. |

---

## Optional Settings

| Variable | Default | Description |
|---|---|---|
| `DRY_RUN` | `false` | When `true`, prints what would be written to blob instead of writing it. Useful for local testing. |
| `ALL_WORKSPACES` | `false` | When `true`, retrieves all workspaces regardless of modification date. |
| `EXCLUDE_PERSONAL_WORKSPACES` | `true` | Excludes personal workspaces from modified-workspace catalog scans. |
| `EXCLUDE_INACTIVE_WORKSPACES` | `true` | Excludes inactive workspaces from modified-workspace catalog scans. |
| `IMPERSONATED_USER_NAME` | _(none)_ | UPN of a user to impersonate for API calls. |
| `CAPACITY_METRICS_DATASET_ID` | _(none)_ | Dataset ID of the Capacity Metrics app semantic model. If unset, the `CapacityMetrics` module logs a warning and returns success. See [Capacity Metrics](#capacity-metrics-capacitymetrics). |
| `CAPACITY_METRICS_DAYS_BACK` | `3` | Days of history to query, minimum 1, maximum 30. |
| `CAPACITY_METRICS_INCLUDE_SUSPENDED` | _(unset)_ | When `1`, `true`, `yes` or `on`, capacities that are not Active are also queried. |
| `GRAPH_EXTRACT_GROUPS` | _(off)_ | When `1`, `true`, `yes` or `on` (case-insensitive), the `Graph` module also writes `groups.json` and `groupmembers.json`. Any other value, or unset, leaves it off. See [Microsoft Graph](#microsoft-graph-graph). |
| `GRAPH_AUDIENCE_GROUP_PREFIXES` | `PowerBI,Power BI` | Comma-separated, case-insensitive group display-name prefixes that mark a group as a Power BI audience group (`isPowerBIAudienceGroup`). |
| `POWER_BI_AUDIENCE_GROUP_IDS` | _(unset)_ | Optional comma-separated audience group object IDs. Overrides prefix matching; membership includes users in nested groups. |
| `GRAPH_MAX_GROUPS_FOR_MEMBERS` | `200` | Maximum number of groups whose members are fetched. Audience groups are taken first. If there are more groups, a warning is logged and the member result is partial. An invalid value falls back to 200; a negative value is treated as 0. |
| `API_MAX_RETRIES` | `3` | Maximum retries for throttled or transient API responses (HTTP 429, 503, 504). |
| `API_MAX_CONCURRENCY` | `16` | Maximum concurrent API requests. |
| `API_MAX_RETRY_DELAY` | `120` | Cap, in seconds, on a single retry wait. |
| `CATALOG_LINEAGE_ENABLED` | `false` | When `1`, `true`, `yes` or `on` (case-insensitive), Catalog also extracts scanner lineage JSON. No extra API calls. |

### Scanner lineage

Include `Catalog` in `APPLICATION_MODULES` and set `CATALOG_LINEAGE_ENABLED=true`.
Catalog already requests lineage and datasource details; this option derives
normalized relationships from the same responses. It adds processing and storage
writes, not HTTP requests or separate retry loops. Existing scanner/admin API
access and tenant settings are still required; no new API permission is added.
The [Scanner response contract](https://learn.microsoft.com/en-us/rest/api/power-bi/admin/workspace-info-get-scan-result)
defines the standard report/model, upstream dataset/dataflow and datasource fields.
Dataflows use `objectId`. If present, `relations[].dependentOnArtifactId` is also
preserved as an item dependency; unknown fields are ignored.

Each successful batch writes
`lineage_edges/YYYY/MM/DD/<scan-id>.lineage_edges.json` through the existing
Local/Blob/Lakehouse snapshot writer. Dates/times are UTC; separate scan IDs keep
same-day observations distinct. Rewriting the same scan ID overwrites its file.
Existing `catalog/scans/` output is unchanged.

The JSON envelope contains `schemaVersion` (1), `source` (`Scanner`), `scanId`,
`observedAtUtc`, `scanMode` (`full`/`incremental`), `requestedWorkspaceIds`,
`returnedWorkspaceIds`, `items`, `complete`, and `edges`. Item inventory records
have `id`, `name`, `type`, and `workspaceId`, including returned items with no
relationships. Each edge has `QueryItemId`, `QueryItemName`, `QueryItemType`,
`QueryWorkspaceId`, `Direction`, `RelatedItemId`, `RelatedItemName`,
`RelatedItemType`, `RelatedWorkspaceId`, `RelationType`, and `Source`.
IDs are normalized to lowercase and rows are deterministically deduplicated.

For example, a report referencing a semantic model has an `upstream` edge from
the report to that model. When the model is also in the batch, a corresponding
`downstream` edge goes from the model to the report. Upstream dataset/dataflow
references preserve `groupId` as the target workspace ID. Unresolved references
retain their IDs, with unknown names/types/workspaces set to null rather than
guessed. Datasources are external endpoints, not item inventory: their edges use
type `DataSource`, with labels limited to datasource type, server and database.
Other connection fields and expressions are not copied into lineage output.

**Observation semantics:** `complete: true` means extraction of this retrieved
batch completed, not that every tenant workspace, item type, or dependency was
returned. A successful zero-edge result is persisted as `edges: []`; no modified
workspaces means no new file. Missing workspaces, optional metadata, and API
coverage gaps are not evidence of deletion or of no dependencies. Reverse edges
can only be emitted for supported items found in the same batch, not another
batch or prior run.

**Failures:** malformed recognized fields or failed lineage writes make that
Catalog run fail without advancing its `lastRun`/`lastFullScan`. Other successful
batch files may still exist and are not proof that the whole run succeeded.
Raw and lineage writes are not transactional; the legacy raw writer keeps its
existing error behavior. With lineage enabled, `DRY_RUN` cannot commit snapshots
or advance Catalog's checkpoint.

**Rollout:** run Catalog with `ALL_WORKSPACES=true` for an initial baseline, then
restore the normal setting/schedule for modified-workspace scans. A scheduled
invocation must still be due under `CATALOG_CRON`; the setting does not force an
immediate run. Existing saved scans are not automatically backfilled. A `full`
scan label reflects Catalog's existing mode, not guaranteed tenant coverage;
`ALL_WORKSPACES=true` is what removes the modification-date discovery filter.
Consumers must select complete observations by scope, not union every historical
edge as current state. The collector does not detect additions/removals, reconcile
cross-batch graphs, or query Fabric beta/pipeline APIs. The optional
[Catalog PBIP Lineage page](../pbip-local/Catalog/README.md) reads these JSON
observations directly; no curated Delta tables are required.

### Throttling and retries

API calls retry on 429, 503 and 504. When the response has a `Retry-After` header, that delay is used, up to `API_MAX_RETRY_DELAY` seconds. If a throttle asks for a longer wait than the cap (this can happen with long scanner throttles), the call is not held; it fails and the module is retried on the next run, because `lastRun` does not advance on failure.

`Roles` also has its own retry loop, which runs on top of the shared retry. A failing call can therefore take longer than the settings above suggest.

The four [scoped Fabric collectors](#scoped-fabric-collectors) use durable request gates instead of the legacy retry-delay cap. They preserve server cooldowns without applying `API_MAX_RETRY_DELAY`; item permissions defer retries to later invocations.

If you use `env/.env.example`, you can set these variables there as well. The file is not changed by this documentation update.

---

## Per-Module Cron Overrides

`CAPACITY_METRICS_CRON` is also accepted as an alias for `CAPACITYMETRICS_CRON`.

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
| `FABRICITEMACCESSPERMISSIONS_CRON` | Fabric Item Access Permissions |
| `FABRICITEMJOBHISTORY_CRON` | Fabric Item Job History |
| `FABRICCONNECTIONS_CRON` | Fabric Connections |
| `FABRICDEPLOYMENTPIPELINEOPERATIONS_CRON` | Fabric Deployment Pipeline Operations |
| `DELEGATEDSETTINGS_CRON` | Delegated Settings |
| `GATEWAY_CRON` | Gateways |
| `GITCONNECTIONS_CRON` | Git Connections |
| `GRAPH_CRON` | Graph (users, licences, groups) |
| `REFRESHABLES_CRON` | Refreshables |
| `REFRESHHISTORY_CRON` | Refresh History |
| `ROLES_CRON` | Workspace Roles |
| `TAGS_CRON` | Tags |
| `TENANT_CRON` | Tenant Settings |
| `WIDELYSHAREDLINKS_CRON` | Widely Shared Links |
| `WORKSPACES_CRON` | Workspaces |

A module's cron is evaluated against its `lastRun` in `state.yaml`. `lastRun` advances only when the module succeeds, so a failed module is retried on the next timer. With no state, the first run looks back 7 days; Activity never looks back more than 30 days. See [changelog.md](changelog.md).

Module cron settings are eligibility checks, **not additional timers**. The host also invokes once at startup (`run_on_startup=True`). An every-minute module cron does not make the daily host invoke every minute. The four collectors below observe current API results rather than backfilling from the 7-day initial checkpoint; permission slices advance `lastRun` only after a healthy full scope cycle.

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
| `FabricItemAccessPermissions` | Explicitly scoped preview admin item access observations (opt-in) |
| `FabricItemJobHistory` | Recent jobs for explicitly scoped supported Fabric items (opt-in) |
| `FabricItemDefinitions` | Tenant-discovered notebook/pipeline definitions and inferred notebook table/file references (opt-in) |
| `FabricConnections` | Caller-visible, metadata-only connection inventory (opt-in) |
| `FabricDeploymentPipelineOperations` | Caller-visible deployment pipelines and recent operations (opt-in, read-only) |
| `Gateway` | On-premise and VNet gateways |
| `GitConnections` | Workspace Git connections, preview API (opt-in) |
| `Graph` | Azure AD users, licences, SKUs and (opt-in) groups and group members; see [below](#microsoft-graph-graph) |
| `Refreshables` | Refreshable datasets |
| `RefreshHistory` | Dataset refresh history |
| `Roles` | Workspace role assignments |
| `Tags` | Tenant tags (opt-in) |
| `Tenant` | Tenant settings |
| `WidelySharedLinks` | Links shared to the whole organization and published to web (opt-in) |
| `Workspaces` | Workspace metadata |

### Notebook and data pipeline definitions

`FabricItemDefinitions` is **off unless explicitly added to `APPLICATION_MODULES`**.
It discovers active tenant items through the preview admin inventory, selects
`Notebook` and `DataPipeline`, and attempts exports with the caller's resource
permissions. Neither `ALL_WORKSPACES` nor `CATALOG_LINEAGE_ENABLED` enables or
limits this collector. It is independent of Catalog/Scanner and job history.

Restore the updated dependencies (`python -m pip install -r requirements.txt`).
Add these settings inside `Values` in `local.settings.json`, **merging the module
name into your existing list rather than replacing it**:

```json
{
  "APPLICATION_MODULES": "Catalog,FabricItemDefinitions",
  "FABRICITEMDEFINITIONS_CRON": "0 2 * * *"
}
```

The cron is UTC and applies to the last **successful full sweep**. An unfinished
or unhealthy sweep does not advance `lastRun`, so subsequent host invocations
remain eligible after it becomes due. Restart the Functions host after editing
settings. No settings, permission grants or live API calls are performed by the
implementation itself.

**Permissions and API traffic.** Tenant discovery uses
[`GET /v1/admin/items`](https://learn.microsoft.com/en-us/rest/api/fabric/admin/items/list-items)
(preview, 200 requests/hour, paginated), with authorized Fabric-admin/service-principal
access. Admin visibility **does not grant** definition access. The caller needs
item-level **read and write** permission for the export endpoints:

- [`POST /v1/workspaces/{workspaceId}/notebooks/{notebookId}/getDefinition?format=ipynb`](https://learn.microsoft.com/en-us/rest/api/fabric/notebook/items/get-notebook-definition).
  Delegated scope: `Notebook.ReadWrite.All` or `Item.ReadWrite.All`.
- [`POST /v1/workspaces/{workspaceId}/dataPipelines/{pipelineId}/getDefinition`](https://learn.microsoft.com/en-us/rest/api/fabric/datapipeline/items/get-data-pipeline-definition).
  Delegated scope: `DataPipeline.ReadWrite.All` or `Item.ReadWrite.All`.

Service principals/managed identities are supported by the documented endpoints,
subject to tenant settings and resource grants. Encrypted sensitivity labels can
impose additional export restrictions. Retrieval does not execute a notebook,
start a pipeline or modify its definition; the required write permission is an
API authorization requirement, not a request to change content. Azure Data Factory
resources outside Fabric and Fabric **deployment** pipelines are not collected.

Each sweep adds inventory-page requests, one export per selected item, and
operation-state/result requests for asynchronous exports. Admin page admissions
reserve 19 seconds plus a 5-second storage margin; export/poll admissions reserve
1 second plus that margin. Retry attempts use the same gate, including 429/503/504.
Server `Retry-After` values, including successful LRO polling headers, are
persisted without the legacy delay cap. URLs from `Location` headers are not
followed; polling uses validated operation UUIDs on the fixed Fabric host.

The request-admission window is **85 seconds**, leaving a 35-second HTTP/storage
reserve in a nominal 120-second slice. HTTP timeouts are 30 seconds total / 10
seconds connect. This is **not a hard wall-clock limit** on authentication, parsing,
storage or total invocation duration. Large tenants, long exports and cooldowns
require repeated host invocations. `progress.json` persists inventory pages,
selected identities, the item cursor, pending operation ID, sweep health and
linked manifest evidence. Deferred exports retain their cursor; resumed LROs are
polled without reposting the export. Denied/malformed items get failed observations
and do not starve later items. Only a wholly healthy full sweep advances the
checkpoint; a finished unhealthy sweep resets for later retry.
An interrupted/uncommitted earlier invocation marks the resumed sweep unhealthy,
so its cursor cannot turn unfinished evidence into a healthy checkpoint.

**One scheduler per output root is required.** The gate is not a distributed lock
and does not coordinate admin quota with `FabricItems`, permission discovery or
other applications. Schedule/budget these together. As with the scoped collectors,
invalid cooldowns block collection; `pending=true` after an unacknowledged request
requires investigation. Do not delete control files or shorten server cooldowns
to force a retry. Invalid progress files fail closed. Archive/restart a sweep only
after investigating its state; discovery is an observation over time, not an
atomic tenant snapshot, and inaccessible/deleted items are not successful empties.

**Output and privacy.** Relative to the existing configured output destination:

```text
fabricitemdefinitions/request_gate.json
fabricitemdefinitions/progress.json
fabricitemdefinitions/YYYY/MM/DD/runId/manifest.json
fabricitemdefinitions/YYYY/MM/DD/runId/inventory.json
fabricitemdefinitions/YYYY/MM/DD/runId/{workspaceId}_{itemId}.json
```

The inventory file is written when paged discovery completes. Per-item envelopes
carry parent IDs/type, UTC observation time and `complete`; successful `records[0]`
contains the original `definition` plus `decodedParts`. Pipeline content is the
JSON object at `records[0].decodedParts["pipeline-content.json"]`, not an opaque
base64 string. Extra definition parts are retained without using their paths as
local filenames. Pipeline activities are **not parsed for dependencies**.

Notebook records also have `notebookReferences`: `evidence="static_inference"`,
`runtimeVerified=false`, references and diagnostics. References identify
`read`/`write`, `table`/`path`, one-based cell/line evidence (the enclosing Python
call or start of the SQL block) and
`resolution="unresolved"`—not Fabric item IDs. Supported literal patterns include
`spark.table`, `spark.read.table`, file readers, file `.load`, classic DataFrame
writer `.saveAsTable`/`.insertInto`/file `.save`, `spark.sql` and `%%sql`/SQL cells.
Spark SQL SELECT/CTEs, INSERT, CREATE TABLE AS SELECT, UPDATE, DELETE and MERGE
are analyzed using SQLGlot; CTE aliases are not emitted as physical tables.
UPDATE/DELETE/MERGE targets are potential reads **and** writes.

Dynamic variables/f-strings and recognized unsupported I/O patterns produce
diagnostics, not guessed targets. This is not exhaustive language analysis:
aliases, helper functions, parameters, JDBC/options-based targets, Python
filesystem/Pandas calls, Delta merge builders, Writer V2, Scala/R and notebook
orchestration are not resolved. A reference can be a temporary view, relative
path or unexecuted branch; namespaces/default lakehouses are not resolved.
An empty reference list is **not proof of no I/O**. No captured code or SQL is
executed. Source definitions and lineage inference are separate from actual run
history, and these outputs are **not automatically added to existing PBIP graphs
or MonitorRaw**.

Unlike metadata-only collectors, definitions deliberately retain source code,
SQL, paths, parameters and any embedded values—including possible secrets.
Use restricted output storage, appropriate retention and access controls; do not
commit captured output. Payloads, tokens and server diagnostic bodies are not
logged. Per-run resource files are immutable observations, not change detection.
Require finished manifests and complete resource envelopes, following the sweep's
linked evidence when collection spans invocations. A partial manifest is not
tenant-complete coverage. Live tenant access, remote storage and coverage still
require operational validation.

### Scoped Fabric collectors

These four collectors are implemented but **off unless explicitly named in `APPLICATION_MODULES`**. No settings are enabled automatically. Configure credentials, actual API/resource permissions, output destination and deliberate scopes before enabling them. Existing Blob/local storage selection and legacy output layouts remain unchanged. These new outputs are **not automatically loaded by MonitorRaw or any existing report**; model/report integration is outside this change.

#### Settings and enablement

| Setting | Default / validation |
|---|---|
| `APPLICATION_MODULES` | Add any of the exact four names above to your existing comma-separated list, or use a separate collector-only configuration. |
| `FABRIC_ITEM_ACCESS_SCOPE` | No default. Required for `FabricItemAccessPermissions`: JSON array of **1–50** explicit objects with `workspaceId`, `itemId`, `type`. |
| `FABRIC_ITEM_JOB_SCOPE` | No default. Required for `FabricItemJobHistory`: JSON array of **1–100** objects with the same keys. Supported types: **`Notebook`, `DataPipeline`, `SparkJobDefinition`** only. |
| Four module-specific `*_CRON` variables above | Unset = eligible on every host invocation; otherwise evaluated in UTC against the last successful checkpoint. |

Both scopes require UUID workspace/item identifiers and a nonempty alphanumeric, case-sensitive API item type. Duplicate workspace/item pairs are rejected, even if their types differ. Permission scope accepts API item type names rather than a fixed local allowlist: the item must actually be returned with that type by admin discovery and supported by the access API. Invalid/missing scopes fail the enabled module, not an empty successful inventory. Neither scope is inferred from `ALL_WORKSPACES` or another collector.

For example, the following is a **`Values` fragment**, not a complete settings file. UUIDs are placeholders. Replace them with deliberately selected resources only after checking permissions and API budget:

```json
{
  "APPLICATION_MODULES": "FabricItemAccessPermissions,FabricItemJobHistory,FabricConnections,FabricDeploymentPipelineOperations",
  "FABRIC_ITEM_ACCESS_SCOPE": "[{\"workspaceId\":\"11111111-1111-1111-1111-111111111111\",\"itemId\":\"22222222-2222-2222-2222-222222222222\",\"type\":\"Report\"}]",
  "FABRIC_ITEM_JOB_SCOPE": "[{\"workspaceId\":\"11111111-1111-1111-1111-111111111111\",\"itemId\":\"33333333-3333-3333-3333-333333333333\",\"type\":\"Notebook\"}]"
}
```

The scope settings are JSON **strings** in `local.settings.json`/Function App settings; their decoded value is an array such as:

```json
[{"workspaceId":"11111111-1111-1111-1111-111111111111","itemId":"33333333-3333-3333-3333-333333333333","type":"Notebook"}]
```

Explicit scopes are deliberate permission and API-budget choices, **not a request for blanket tenant access**. Connections and pipeline discovery have no item scope setting and return only what this caller can see. See [operating guidance](local-development.md#operating-the-four-fabric-collectors) before starting a host.

#### Endpoints, permissions and coverage

All requests are read-only GETs under `https://api.fabric.microsoft.com/v1`, using Fabric-audience authentication. Authentication alone and admin discovery do not grant resource access. Tenant service-principal API settings and the endpoint's supported identity/authorization requirements must also be satisfied.

| Collector | Relative endpoints | Coverage / authorization limits |
|---|---|---|
| `FabricItemAccessPermissions` | `admin/items?workspaceId={workspaceId}`, then `admin/workspaces/{workspaceId}/items/{itemId}/users` | Preview admin access API; requires read-only admin API authorization (Fabric admin for a user, or an authorized service principal under the tenant's read-only admin API setting). Delegated admin access uses `Tenant.Read.All` or `Tenant.ReadWrite.All`; do not treat these as resource grants. Access endpoint limit: **200 requests/hour**. |
| `FabricItemJobHistory` | `workspaces/{workspaceId}/items/{itemId}/jobs/instances` | Caller needs actual access to the supported item/job history. Most items expose **100 recent completed jobs plus active jobs**, not unlimited history. |
| `FabricConnections` | `connections` | Caller-visible inventory, **not tenant-complete**. No credential or connection-permissions endpoint is called. |
| `FabricDeploymentPipelineOperations` | `deploymentPipelines`, then `deploymentPipelines/{pipelineId}/operations` | Caller-visible discovery, **not tenant-complete**; operation history requires pipeline **Admin**. Up to **20 recent deployments** per pipeline. No deployment is initiated. |

For item access, `?type={type}` is appended for the five Power BI types **`Report`, `Dashboard`, `SemanticModel`, `App`, `Dataflow`**; it is omitted for other Fabric types. Workspace-filtered admin discovery follows continuation tokens and matches only the configured workspace/item/type identities. A missing item, type mismatch, malformed response or inaccessible resource is a failure, not proof of no permissions. Access output is the API's `accessDetails` (principal and item access details), **not fully expanded effective access**: groups are not expanded, and it is not a tenant-wide permission audit.

API support and permissions can change, especially for preview endpoints. Check Microsoft's current references before granting access: [item access (preview)](https://learn.microsoft.com/en-us/rest/api/fabric/admin/items/list-item-access-details), [jobs](https://learn.microsoft.com/en-us/rest/api/fabric/core/job-scheduler/list-item-job-instances), [connections](https://learn.microsoft.com/en-us/rest/api/fabric/core/connections/list-connections), [pipeline operations](https://learn.microsoft.com/en-us/rest/api/fabric/core/deployment-pipelines/list-deployment-pipeline-operations).

Polling cannot recover jobs or deployments that aged out between invocations. `lastRun` is a success checkpoint, not an API history cursor.

#### Bounded permission cycles and durable quotas

Permission collection visits each configured workspace's inventory pages and then its configured items, in scope order grouped by workspace. Each invocation admits at most **6 single-attempt slices** within a **150-second admission budget**. It reserves **35 seconds** before starting another slice; each HTTP request has a **30-second total / 10-second connect timeout**. Slices are separated by **24 seconds**. The durable permission gate reserves a **19-second interval plus a 5-second storage-write margin** before sending; a reservation write exceeding that margin aborts safely. These are admission controls, **not a hard wall-clock limit on authentication, storage, or the whole invocation**.

One slice can observe one inventory page or one item's access response, and has its own run ID/manifest. `fabricitemaccesspermissions/progress.json` preserves the scope, task cursor, continuation token/history, discovered identities, health and linked evidence. Inventory continuation pages can span invocations. Denied/malformed targets are recorded and the cursor moves on so later targets are not starved; requests deferred before an attempt retain the current task. Attempted throttled requests are failures for cycle health and can advance the cursor. A finished unhealthy cycle resets for a later cycle without advancing `lastRun`. Only a **wholly healthy full cycle**, with its evidence persisted, advances the checkpoint.

Large scopes or long cooldowns need **multiple host invocations**. The collector does not schedule its own next invocation or guarantee cycle completion while the host is idle. See [repeated slices and recovery](local-development.md#operating-the-four-fabric-collectors).

Every collector stores `<module>/request_gate.json` containing `nextRequestUtc`, `blocked`, `pending`. Numeric-seconds and HTTP-date `Retry-After` values survive restarts and are not shortened to the legacy 120-second cap. Permission slices defer rather than wait through a cooldown. Other collectors normally pace attempts one second apart, use the shared retry count (default 3), and defer waits longer than 30 seconds to a later invocation. A missing cooldown on a retryable response uses exponential backoff starting at 2 seconds.

An invalid/unrepresentable `Retry-After` sets a fail-closed block. A timeout, cancellation, crash or failed response-ledger write can leave `pending=true`: the request may have reached the server, so later requests are blocked pending operator investigation. Invalid/unreadable control files also fail closed. **One scheduler per output root is required**: these files are not distributed locks and do not coordinate other clients or output roots consuming the same server quota. Do not delete a ledger or move a cooldown into the past to resume quickly.

#### Output contract and privacy

Folders are relative to the configured local output root, Blob container/root prefix, or Lakehouse Files prefix:

```text
fabricitemaccesspermissions/YYYY/MM/DD/runId/
fabricitemjobhistory/YYYY/MM/DD/runId/
fabricconnections/YYYY/MM/DD/runId/
fabricdeploymentpipelineoperations/YYYY/MM/DD/runId/
```

Dates and `observedAt` are UTC; run IDs prevent same-day observations from overwriting each other. Resource filenames are:

| Module folder | Resource files |
|---|---|
| `fabricitemaccesspermissions` | `inventory_{workspaceId}.json` or `{workspaceId}_{itemId}.json` per slice |
| `fabricitemjobhistory` | `{workspaceId}_{itemId}.json` |
| `fabricconnections` | `connections.json` |
| `fabricdeploymentpipelineoperations` | `pipelines.json`, then `{pipelineId}.json` |

Each resource envelope has `runId`, `observedAt`, `coverage`, `requestPath`, `parent`, `complete`, and either `records` or `error`. **`complete=true, records=[]` is an explicit successful empty observation**. A failed resource has `complete=false` and an error, with no records; never turn it into an empty success. Permission inventory records contain only selected workspace/item/type identities, not the full workspace inventory. Parent context identifies the item/workspace or deployment pipeline.

Each run starts with `manifest.json` (`finished=false`, `complete=false`), then writes a final manifest with `finished=true`. Manifests contain `runId`, `observedAt`, `coverage`, `complete`, `finished`, `resources` (file/parent/completion), `errors` and `execution`. Require a parsed, finished manifest and a complete resource envelope before consuming an observation. Missing/unparseable manifests or `finished=false` mean interrupted writes, not empty results. A finished but incomplete run can still contain usable successful resources; its overall checkpoint does not advance.

For permission slices, `execution` additionally contains `cycleFinished`, `nextTask`, `taskCount`, `cycleEvidence`, `deferred`, `attempts`, `cycleHealthy`. Intermediate manifests remain `complete=false` even after a successful resource. `progress.json` is mutable cycle control, **not a run manifest**. Each slice links the preceding manifest through `cycleEvidence`; follow the chain for cycle evidence rather than treating the last slice's files as the whole cycle. A cycle spans observations over time, not a point-in-time tenant snapshot.

Jobs retain `id`, `itemId`, `jobType`, `invokeType`, `status`, `rootActivityId`, `startTimeUtc`, `endTimeUtc`, `failureReason` when present. For current state, group by **workspaceId/itemId/job id** and select the latest valid `observedAt`; retain earlier observations for historical status. Pipeline discovery retains `id`, `displayName`; operations retain `id`, `type`, `status`, `lastUpdatedTime`, `executionStartTime`, `executionEndTime`, `sourceStageId`, `targetStageId`. Group operation state by **pipeline id/operation id**, latest `observedAt`. Repeated observations are not additional jobs/deployments; a terminal status seen later must not overwrite the historical observation semantics.

Connections save only **`id`, `displayName`, `gatewayId`, `connectivityType`, `privacyLevel`, `connectionDetails.type`** when present. Paths, connection strings, `credentialDetails`, tokens and unknown fields are discarded before writing. This is data minimization, not anonymisation: display names, principal identifiers/access details and job `failureReason` may still be sensitive. Restrict output access and set an appropriate evidence/retention policy.

The strict snapshot writer persists empty successes, propagates storage failures and rejects `DRY_RUN=true` in **all** storage modes. It does not log payloads or raw API error bodies. The legacy `save` path still skips empty lists and otherwise retains its existing behavior; this change does not migrate older collectors to envelopes/manifests.

### Microsoft Graph (`Graph`)

Reads Azure AD data through Microsoft Graph. Output goes under `graph/YYYY/MM/DD/` (UTC date).

| File | Written | Content |
|---|---|---|
| `users.json` | Always | All users (paged, `$top=999`): `id`, `displayName`, `userPrincipalName`, `mail`, `accountEnabled`, `userType`, `assignedLicenses`. |
| `userlicenses.json` | Always, when the users call succeeds | One row per user per assigned licence: `userId`, `userPrincipalName`, `skuId`, `disabledPlans`. |
| `subscribedskus.json` | Always | Subscribed SKUs. |
| `groups.json` | Only when `GRAPH_EXTRACT_GROUPS` is on | Security-enabled groups (paged), each with `isPowerBIAudienceGroup`. |
| `groupmembers.json` | Only when `GRAPH_EXTRACT_GROUPS` is on | One row per group per transitive user member (including nested groups), with `groupId`, `groupDisplayName`, `isPowerBIAudienceGroup` and member fields. |

**Permissions.** The app registration needs the Graph application permissions `User.Read.All`, `Group.Read.All` and `GroupMember.Read.All`, with admin consent.

**Group extraction.** It is off by default. Set `GRAPH_EXTRACT_GROUPS` to `1`, `true`, `yes` or `on` to enable it. Transitive members are fetched for at most `GRAPH_MAX_GROUPS_FOR_MEMBERS` groups (default 200), audience groups first. `POWER_BI_AUDIENCE_GROUP_IDS` selects audience groups explicitly; otherwise names starting with a `GRAPH_AUDIENCE_GROUP_PREFIXES` entry (default `PowerBI,Power BI`) mark audience groups. When more groups exist, a warning is logged and `groupmembers.json` is a partial result; raise the cap to cover them.

**Failures.** All pages are followed through `@odata.nextLink`. A failed or empty response, an error response, or a transport error (an exception from the request) counts as a failure, as does a failed member call for any group. The module then returns `False` and `lastRun` does not advance. Data from calls that succeeded is still saved.

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
