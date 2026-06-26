# Local Development

This guide covers local development setup for **Linux, macOS, and Windows** (native PowerShell and WSL2).

> **Windows quick-start:** An automated setup script is also available — see [windows-development.md](windows-development.md).

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.12 | [python.org](https://www.python.org/downloads/) — on Windows check **"Add Python to PATH"** during install |
| Azure Functions Core Tools | v4 | See below |
| Node.js | LTS | [nodejs.org](https://nodejs.org/) — required for Azurite and Core Tools |
| Azurite | latest | `npm install -g azurite` |
| Git | latest | [git-scm.com](https://git-scm.com/) |

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

**Windows / npm (any platform):**
```powershell
npm install -g azure-functions-core-tools@4 --unsafe-perm true
```

> **Windows note:** Close and reopen PowerShell after installing so the PATH update from npm takes effect.

Verify the installation on any platform:
```bash
func --version
# Should output 4.x.x
```

---

## VS Code Extensions

Install the following extensions for the best development experience:

| Extension | ID | Purpose |
|---|---|---|
| Python | `ms-python.python` | Python language support, linting, and formatting |
| Pylance | `ms-python.vscode-pylance` | Type checking and IntelliSense |
| Python Debugger | `ms-python.debugpy` | Debugging support for Python code |
| Azure Functions | `ms-azuretools.vscode-azurefunctions` | Run, debug, and deploy Azure Functions locally |
| Azurite | `Azurite.azurite` | Start local Azure Storage emulator directly from VS Code |
| Jupyter | `ms-toolsai.jupyter` | Run and edit `.ipynb` notebooks |
| Bicep | `ms-azuretools.vscode-bicep` | Syntax highlighting and validation for infrastructure files |

Install all at once from the terminal:

**Linux / macOS / WSL:**
```bash
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension ms-python.debugpy
code --install-extension ms-azuretools.vscode-azurefunctions
code --install-extension Azurite.azurite
code --install-extension ms-toolsai.jupyter
code --install-extension ms-azuretools.vscode-bicep
```

**Windows (PowerShell):**
```powershell
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension ms-python.debugpy
code --install-extension ms-azuretools.vscode-azurefunctions
code --install-extension Azurite.azurite
code --install-extension ms-toolsai.jupyter
code --install-extension ms-azuretools.vscode-bicep
```

---

## Project Setup

### Linux / macOS

```bash
# Enter the project
cd /path/to/monitor

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
cd C:\path\to\monitor

# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install Python dependencies
pip install -r requirements.txt
```

> If you see an ExecutionPolicy error when activating the virtual environment:
> ```powershell
> Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

> You will need to activate `.venv` each time you open a new terminal.

### Python packages installed

All dependencies are declared in `requirements.txt`. Key packages include:

| Package | Purpose |
|---|---|
| `azure-functions` | Azure Functions Python worker |
| `azure-identity` | `DefaultAzureCredential` and service principal auth |
| `azure-storage-blob` | Blob Storage read/write |
| `azure-storage-file-datalake` | Data Lake (ADLS Gen2) support |
| `azure-keyvault` | Key Vault secret retrieval |
| `msal` | MSAL token acquisition for Power BI / Fabric APIs |
| `pandas` / `numpy` / `pyarrow` | Data processing and Parquet output |
| `PyYAML` | `state.yaml` read/write |
| `python-dotenv` | `.env` file support for local overrides |
| `aiohttp` | Async HTTP client for API calls |
| `codetiming` | Execution timing decorators |
| `croniter` | Cron expression parsing for schedules |

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

### APPLICATION_MODULES

The `APPLICATION_MODULES` setting is a comma-separated list of data collection modules to enable. All modules are enabled by default:

| Module | Description |
|---|---|
| `Activity` | Power BI activity events (audit log) |
| `Apps` | Power BI apps published in the tenant |
| `Capacity` | Fabric / Power BI Premium capacities |
| `Catalog` | Full workspace and item catalog via the scanner (`getInfo`) API |
| `Domains` | Fabric domains |
| `FabricItems` | Fabric-specific items (lakehouses, notebooks, pipelines, etc.) |
| `Gateway` | On-premises and VNet data gateways |
| `Graph` | Azure AD users and groups via Microsoft Graph |
| `Refreshables` | Datasets / semantic models that support scheduled refresh |
| `RefreshHistory` | Refresh history for all refreshable items |
| `Roles` | Workspace role assignments |
| `Tenant` | Tenant-level settings |
| `Workspaces` | All workspaces in the tenant |

Remove any module name from the list to skip it on each run.

---

## Start Azurite (local Azure Storage emulator)

`AzureWebJobsStorage` is set to `UseDevelopmentStorage=true`, which requires Azurite to be running on port 10000 before you start the function.

### Linux / macOS

Open a **dedicated terminal** and run:

```bash
azurite --location /tmp/azurite --debug /tmp/azurite/debug.log
```

### Windows (PowerShell)

```powershell
# Create the data directory once
mkdir C:\azurite

azurite --location C:\azurite
```

### All platforms

Leave this terminal running. Azurite emulates Blob (port 10000), Queue (10001), and Table (10002) storage locally. You should see:

```
Azurite Blob service is starting at http://127.0.0.1:10000
Azurite Queue service is starting at http://127.0.0.1:10001
Azurite Table service is starting at http://127.0.0.1:10002
```

> **VS Code tip:** You can start Azurite directly from VS Code using the [Azurite extension](https://marketplace.visualstudio.com/items?itemName=Azurite.azurite) via the Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`) → `Azurite: Start`. This avoids needing a dedicated terminal.

---

## Run the Function Locally

Open a **second terminal** (separate from the Azurite terminal), then from the project root:

### Linux / macOS

```bash
source .venv/bin/activate
func start
```

### Windows (PowerShell)

```powershell
.\.venv\Scripts\Activate.ps1
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

---

## Windows Troubleshooting

### `func` not recognized after npm install

Close and reopen PowerShell so the PATH update from npm takes effect.

### ExecutionPolicy error when activating `.venv`

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Azurite port already in use

Another process is using port 10000. Find and stop it:

```powershell
netstat -ano | findstr :10000
taskkill /PID <pid> /F
```

### SSL errors calling the Power BI API

On Windows, `aiohttp` uses the system resolver which handles IPv4/IPv6 correctly. If you see SSL timeouts, try adding this to `local.settings.json`:

```json
"WEBSITE_USE_PLACEHOLDER": "0"
```

This disables a Functions host optimization that can interfere with async code on Windows.

### `DefaultAzureCredential` fails locally

Ensure `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` are all set in `local.settings.json`. These are the exact variable names `DefaultAzureCredential` looks for.

### `cryptography` package fails to install (no C compiler)

Install the pre-built wheel instead:

```powershell
pip install cryptography --only-binary :all:
```
