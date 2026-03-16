# Configuration Reference

All settings are environment variables. Locally they are set in `local.settings.json` under `Values`. In Azure they are set as **Function App → Settings → Environment variables**.

---

## Required Settings

| Variable | Description |
|---|---|
| `TENANT_ID` | Azure AD tenant ID. Used by MSAL for Power BI / Fabric API token acquisition. |
| `CLIENT_ID` | App registration (service principal) client ID. |
| `CLIENT_SECRET` | App registration client secret. **Use a Key Vault reference in production.** |
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
| `CAPACITY_METRICS_DATASET_ID` | _(none)_ | Dataset ID for the Capacity Metrics module. |

---

## Per-Module Cron Overrides

Each module runs on the global timer schedule (`0 0 */4 * * *` — every 4 hours). You can override the effective schedule per module using cron syntax. If not set, the module runs every time the function fires.

| Variable | Module |
|---|---|
| `ACTIVITY_CRON` | Activity Events |
| `APPS_CRON` | Apps |
| `CAPACITY_CRON` | Capacity |
| `CATALOG_CRON` | Catalog Scans |
| `DOMAINS_CRON` | Domains |
| `GATEWAY_CRON` | Gateways |
| `GRAPH_CRON` | Graph (AAD Groups) |
| `REFRESHABLES_CRON` | Refreshables |
| `REFRESHHISTORY_CRON` | Refresh History |
| `ROLES_CRON` | Workspace Roles |
| `TENANT_CRON` | Tenant Settings |

**Example:** run Catalog only once a day at midnight UTC:
```
CATALOG_CRON=0 0 * * *
```

---

## Modules

All available module names for `APPLICATION_MODULES`:

| Name | Description |
|---|---|
| `Activity` | Power BI activity log events |
| `Apps` | Published Power BI apps |
| `Capacity` | Capacity details |
| `Catalog` | Full workspace/item catalog scan |
| `Domains` | Fabric domains |
| `FabricItems` | All Fabric items across the tenant |
| `Gateway` | On-premise and VNet gateways |
| `Graph` | Azure AD group membership |
| `Refreshables` | Refreshable datasets |
| `RefreshHistory` | Dataset refresh history |
| `Roles` | Workspace role assignments |
| `Tenant` | Tenant settings |
| `Workspaces` | Workspace metadata |

---

## Timer Schedule

The function is triggered on a CRON schedule defined in `function_app.py`:

```python
@app.schedule(schedule="0 0 */4 * * *", ...)
```

This fires every 4 hours at the top of the hour (UTC). Azure Functions uses a 6-field NCRONTAB format:

```
{second} {minute} {hour} {day} {month} {day-of-week}
```

To change the schedule, edit the `schedule` value in `function_app.py` before deploying.
