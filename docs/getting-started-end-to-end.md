# End-to-End Getting Started Guide

A walkthrough for taking the Fabric Monitor repo from `git clone` to data landing in a Fabric Lakehouse (or Blob/local files) and a report on top of it. Use it as a customer-facing checklist.

**Flow:** Clone → Entra app (service principal) → Fabric tenant settings → API permissions → Python env → `.env` → local dry run → real run → Lakehouse tables → reports → schedule/deploy.

---

## 0. Prerequisites

| Need | Notes |
|---|---|
| Fabric/Power BI **admin** access | Needed once, to enable service principal API access |
| Entra ID rights to create an app registration | Or ask an Entra admin to create it |
| Python 3.12 (3.10.13+ works) | Check "Add to PATH" on Windows |
| Git, VS Code | Recommended VS Code extensions: Python, Pylance, Jupyter, Azure Functions |
| Optional | Node.js + Azurite + Azure Functions Core Tools v4 (local timer function), Docker (containers) |
| Storage target | One of: local folder, Azure Blob, or a Fabric Lakehouse |

> Fabric Lakehouse/OneLake output works only for `CLOUD_ENVIRONMENT=Commercial`. For `Gcc`, `GccHigh`, `Dod` use Blob or local files.

---

## 1. Clone and open

```powershell
git clone <repo-url> fabric-monitor
cd fabric-monitor
code .
```

Key folders:

| Path | Purpose |
|---|---|
| `app/monitor.py` | Standalone entry point (`python -m app.monitor`) |
| `env/modules/` | One file per data source (activity, catalog, capacity, ...) |
| `env/clients/`, `env/utility/` | API clients, Blob/OneLake/local writers |
| `function_app.py` | Azure Functions timer trigger (every 4 hours) |
| `notebooks/` | One Jupyter notebook per module, for learning/experimenting |
| `schema_examples/` | Sample JSON schemas (Activity, Catalog) |
| `Fabric/*.pbit` | Power BI report templates |
| `infra/`, `azure.yaml` | Bicep/azd deployment |
| `containers/` | Dockerfiles |
| `docs/` | Detailed docs (configuration, deployment, managed identity, ...) |

---

## 2. Create the service principal

1. Entra ID → **App registrations** → **New registration** (single tenant).
2. Record **Application (client) ID** and **Directory (tenant) ID**.
3. **Certificates & secrets** → new client secret. Record the value (shown once).
4. Create an Entra **security group** (e.g. `FabricMonitor-SPs`) and add the app's service principal as a member.

---

## 3. Fabric admin portal settings

Fabric admin portal → **Tenant settings** → **Developer settings**:

- **Service principals can use Fabric APIs** → Enabled, scoped to the security group above.

Under **Admin API settings**:

- **Service principals can access read-only admin APIs** → Enabled for the same group.
- **Enhance admin APIs responses with detailed metadata** and **...with DAX and mashup expressions** → Enabled (needed for the Catalog scan detail).

Settings can take up to ~15 minutes to propagate.

---

## 4. API permissions (Entra → app → API permissions)

| API | Permission | Type |
|---|---|---|
| Microsoft Graph | `Directory.Read.All` | Application |
| Microsoft Graph | `User.Read.All` | Application |
| Microsoft Graph | `User.Read` | Delegated |
| Power BI Service | `Tenant.Read.All` | Delegated |

Grant admin consent. The Graph permissions are only required for the `Graph` module (AAD groups / licenses).

> If the app uses service principal auth for Power BI admin APIs, Microsoft states the app must **not** have admin-consent-required Power BI permissions configured. If admin calls return 401, remove the Power BI permission and rely on the tenant settings in step 3.

---

## 5. Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
pip install -r requirements.txt
```

macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.

Windows shortcut: `setup-windows.ps1` automates this; `setup-windows-ui.ps1` sets up the desktop UI.

---

## 6. Configure `.env`

Copy the template and fill it in (never commit `.env`):

```powershell
Copy-Item .env.example .env
```

Minimum settings:

```ini
TENANT_ID=<tenant guid>
CLIENT_ID=<app client id>
CLIENT_SECRET=<secret>
CLOUD_ENVIRONMENT=Commercial
APPLICATION_MODULES=Activity,Workspaces,Catalog
```

Start with 2-3 modules, then widen. Available modules: `Activity, Apps, Capacity, CapacityMetrics, Catalog, Domains, FabricItems, Gateway, Graph, Refreshables, RefreshHistory, Roles, Tenant, Workspaces`.

Choose **one** storage target:

**A. Local files (easiest first run)**
```ini
OUTPUT_PATH=Data
```

**B. Azure Blob (recommended for shared use)**
```ini
STORAGE_ACCOUNT_URL=https://<account>.blob.core.windows.net
STORAGE_ACCOUNT_CONTAINER_NAME=monitor
STORAGE_ACCOUNT_CONTAINER_ROOT_PATH=stage
AZURE_TENANT_ID=<same as TENANT_ID>
AZURE_CLIENT_ID=<same as CLIENT_ID>
AZURE_CLIENT_SECRET=<same as CLIENT_SECRET>
```
Grant the service principal **Storage Blob Data Contributor** on the account/container.

**C. Fabric Lakehouse**
```ini
WORKSPACE_NAME=<workspace name>
LAKEHOUSE_NAME=<lakehouse name>
PATH_IN_LAKEHOUSE=stage
ON_FABRIC=false        # false when running from your laptop/Azure; true inside a Fabric notebook
AZURE_TENANT_ID=...    # same SP values as above
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
```
Add the service principal to the Fabric workspace as **Contributor** (Workspace → Manage access), and create the Lakehouse first. Files are written under `Files/<PATH_IN_LAKEHOUSE>/...` (for example `activity/yyyy/mm/dd/yyyymmdd_00001.json`).

Optional: per-module schedules (`ACTIVITY_CRON`, `CATALOG_CRON`, ...), `DRY_RUN`, `ALL_WORKSPACES`. See [configuration-reference.md](configuration-reference.md) for everything.

---

## 7. First run

```powershell
# Dry run: shows what would be written, nothing is saved
$env:DRY_RUN="true"; python -m app.monitor --modules Activity

# Real run of selected modules
$env:DRY_RUN="false"; python -m app.monitor --modules Activity,Workspaces

# First-time full catalog scan of all workspaces (run once, then incremental)
python -m app.monitor --base

# One module on its own
python -m env.modules.activity
```

Notes:
- `state.yaml` records each module's last run; the Activity module resumes from `lastRun` and walks forward one UTC day at a time.
- Activity Events API: max 200 requests/hour, 28-day lookback, one UTC day per request, paged via `continuationUri`.
- Troubleshoot: 401/403 → step 3/4; no data → check module list and `state.yaml`; SSL errors → see [local-development.md](local-development.md).

Verify output files exist in your chosen storage (`Data\`, the blob container, or Lakehouse **Files**).

---

## 8. Get data into Lakehouse **tables**

The monitor writes raw **JSON files** to the Lakehouse `Files` area. To query them, convert to Delta tables with a Fabric notebook (attached to the Lakehouse):

```python
from pyspark.sql import functions as F

df = spark.read.option("multiLine", True).json("Files/stage/activity/*/*/*/*.json")

# Choose the schema you want in the table (the API has no $select)
cols = ["Id", "CreationTime", "Activity", "UserId", "WorkspaceName", "ItemName", "IsSuccess"]
df = df.select(*[c for c in cols if c in df.columns])

(df.write.mode("append").format("delta").saveAsTable("activity_events"))
```

Tips:
- Use `Files/stage/catalog/...` the same way for catalog tables; see `schema_examples/` for field lists.
- API-level filtering is limited: Activity Events supports only `$filter` on `Activity` and `UserId` (`eq`, `and`). Column selection is done in the notebook or in the module before saving.
- Make loads idempotent: de-duplicate on `Id` (Activity) or use `MERGE` when appending.
- Schedule the notebook from a Fabric **Data Pipeline** after the monitor run.

---

## 9. Reports

Templates are in `Fabric/`:

- `FabricMonitor-BlobStorage.pbit` – reads directly from the Blob container (needs storage account name, container, UTC offset, RangeStart/RangeEnd, key/SAS).
- `pbimonitorwithflow.pbit` + `FabricFlow.json` – uses a Dataflow Gen1; replace `<your account here>` and `<your container name here>` in the JSON before import.

For Lakehouse-based reporting, create a semantic model over the Delta tables from step 8 and build reports on it (Direct Lake).

---

## 10. Schedule it (pick one)

| Option | How |
|---|---|
| **Azure Functions** (timer, every 4h) | `function_app.py`; deploy with `azd up` (see [deployment.md](deployment.md), [managed-identity.md](managed-identity.md)). Use Managed Identity and Key Vault references instead of secrets. |
| **Container** | `docker build -t monitor/fabric:1.0 -f containers/Dockerfile2 .` (run-once) or `containers/Dockerfile` (cron); push to ACR; run on ACI/ACA/AKS. |
| **Fabric/Synapse notebooks** | See [azure-synapse-notebooks.md](azure-synapse-notebooks.md); set `ON_FABRIC=true` to write to `/lakehouse/default/Files`. |
| **Windows desktop UI** | `Run Fabric Monitor UI.cmd`; see [windows-ui.md](windows-ui.md). |

Local Functions test: install Core Tools + Azurite, copy `local.settings.example` to `local.settings.json`, start `azurite`, then `func start`.

---

## 11. Customer onboarding checklist

- [ ] App registration + secret created; SP in security group
- [ ] Fabric tenant settings enabled for that group
- [ ] Graph/Power BI API permissions granted (if needed)
- [ ] SP added to Fabric workspace (Lakehouse) or given Blob data role
- [ ] `.env` filled, `DRY_RUN` test passes
- [ ] First real run for `Activity` succeeds; files visible in storage
- [ ] `--base` catalog scan completed
- [ ] Notebook creates Delta tables
- [ ] Report connected
- [ ] Schedule/deployment chosen; secrets moved to Key Vault / Managed Identity

## Helpful links

- [Configuration reference](configuration-reference.md) · [API endpoints](api-endpoints.md) · [Local development](local-development.md) · [Deployment](deployment.md) · [Enterprise best practices](enterprise-deployment-best-practices.md)
