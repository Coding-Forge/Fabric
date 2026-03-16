# Local Development

## Prerequisites

| Tool | Install |
|---|---|
| Python 3.12 | [python.org](https://www.python.org/downloads/) or `conda create -n monitor python=3.12` |
| Azure Functions Core Tools v4 | See below |
| Node.js (for Azurite) | [nodejs.org](https://nodejs.org/) |
| Azurite (local storage emulator) | `npm install -g azurite` |

### Install Azure Functions Core Tools

**Ubuntu / Debian / WSL:**
```bash
wget -q https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/packages-microsoft-prod.deb
sudo dpkg -i packages-microsoft-prod.deb
sudo apt-get update
sudo apt-get install azure-functions-core-tools-4
```

**macOS:**
```bash
brew tap azure/functions
brew install azure-functions-core-tools@4
```

**npm (any platform):**
```bash
npm install -g azure-functions-core-tools@4 --unsafe-perm true
```

---

## Project Setup

```bash
# Clone and enter the project
cd /path/to/monitor

# Install Python dependencies
pip install -r requirements.txt
```

---

## Configure local.settings.json

`local.settings.json` is gitignored and never deployed. It holds secrets for local runs only.

Copy the structure below and fill in your values:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",

    "TENANT_ID": "<your-tenant-id>",
    "CLIENT_ID": "<your-app-registration-client-id>",
    "CLIENT_SECRET": "<your-app-registration-client-secret>",

    "AZURE_TENANT_ID": "<your-tenant-id>",
    "AZURE_CLIENT_ID": "<your-app-registration-client-id>",
    "AZURE_CLIENT_SECRET": "<your-app-registration-client-secret>",

    "APPLICATION_MODULES": "Activity,Apps,Capacity,Catalog,Domains,FabricItems,Gateway,Graph,Refreshables,RefreshHistory,Roles,Tenant,Workspaces",

    "STORAGE_ACCOUNT_URL": "https://<your-storage-account>.blob.core.windows.net",
    "STORAGE_ACCOUNT_CONTAINER_NAME": "monitor",
    "STORAGE_ACCOUNT_CONTAINER_ROOT_PATH": "stage",

    "DRY_RUN": "false",
    "ALL_WORKSPACES": "false"
  }
}
```

> **Note:** `TENANT_ID` / `CLIENT_ID` / `CLIENT_SECRET` are used by the Fabric/Power BI API calls via MSAL.  
> `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` are the standard env vars read automatically by `DefaultAzureCredential` for authenticating to Blob Storage.  
> Both sets should point to the same service principal.

See [configuration-reference.md](configuration-reference.md) for a full list of all settings.

---

## Start Azurite (local Azure Storage emulator)

`AzureWebJobsStorage` is set to `UseDevelopmentStorage=true`, which requires Azurite to be running on port 10000 before you start the function.

Open a **dedicated terminal** and run:

```bash
azurite --location /tmp/azurite --debug /tmp/azurite/debug.log
```

Leave this running. Azurite emulates Blob (port 10000), Queue (10001), and Table (10002) storage locally.

> **Tip:** You can also start Azurite from within VS Code using the [Azurite extension](https://marketplace.visualstudio.com/items?itemName=Azurite.azurite) via the Command Palette → `Azurite: Start`.

---

## Run the Function Locally

In a **second terminal**, from the project root:

```bash
func start
```

You should see:

```
Functions:
    Fabric_Monitor: timerTrigger
```

Because `run_on_startup=True` is set in `function_app.py`, the function fires immediately when the host starts. You do not need to wait for the timer schedule.

---

## Dry Run Mode

To see what would be written to blob storage without actually writing anything, set:

```json
"DRY_RUN": "true"
```

Output will appear in the terminal like:

```
============================================================
[DRY RUN] Would write to blob: stage/activity/2026/03/14/20260314_00001.json
============================================================
{ ... json content ... }
============================================================
```

Set back to `"false"` when you are ready to write real data.

---

## Verify API calls

Every API call logs a single line:

```
[API] GET https://api.powerbi.com/v1.0/myorg/admin/activityevents?... -> HTTP 200 | records: 312
[API] POST https://api.powerbi.com/v1.0/myorg/admin/workspaces/getInfo -> HTTP 202 | records: 1
```

Common HTTP errors:
- **403** — Service principal missing Power BI admin role or API consent. See [managed-identity.md](managed-identity.md).
- **401** — Token acquisition failed. Check `CLIENT_ID` / `CLIENT_SECRET` / `TENANT_ID`.
- **429** — Throttled. The function will need to retry (not currently automatic).

---

## Blob Storage Diagnostics

Every blob read/write logs:

```
[READ] Attempting to read blob: container=monitor path=stage/state.yaml
[BLOB READ] Using URL auth: https://... | blob: stage/state.yaml
[BLOB READ] Read 847 bytes from stage/state.yaml

[BLOB WRITE] Successfully wrote 12430 bytes to stage/activity/2026/03/14/20260314_00001.json
```

If `state.yaml` does not exist in the container yet, the function will automatically create a fresh one on the first run.
