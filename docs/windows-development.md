# Windows Development

> **Linux/WSL2 users:** See [local-development.md](local-development.md) instead. This guide is for native Windows (PowerShell) development only.

---

## Prerequisites

Install the following before running setup:

| Tool | Install |
|---|---|
| Python 3.12 | [python.org/downloads](https://www.python.org/downloads/) — check **"Add Python to PATH"** during install |
| Node.js LTS | [nodejs.org](https://nodejs.org/) — required for Azure Functions Core Tools and Azurite |
| Git | [git-scm.com](https://git-scm.com/) |

---

## Quick Setup (Automated)

Open **PowerShell as Administrator**, navigate to the project root, then run:

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
cd C:\path\to\monitor
.\setup-windows.ps1
```

The script will:
1. Verify prerequisites and show what's missing
2. Install Azure Functions Core Tools v4 via npm (if not present)
3. Install Azurite (local storage emulator) via npm (if not present)
4. Create a `.venv` Python virtual environment and install all dependencies
5. Create a `local.settings.json` template if one doesn't exist

---

## Manual Setup

If you prefer manual steps or the script fails:

### 1. Install Azure Functions Core Tools

```powershell
npm install -g azure-functions-core-tools@4 --unsafe-perm true
```

Verify:
```powershell
func --version
# Should output 4.x.x
```

### 2. Install Azurite

```powershell
npm install -g azurite
```

> **Alternative:** Install the [Azurite VS Code extension](https://marketplace.visualstudio.com/items?itemName=Azurite.azurite) and start it from the Command Palette (`Ctrl+Shift+P` → `Azurite: Start`).

### 3. Create a Python virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> You will need to activate `.venv` each time you open a new terminal:
> ```powershell
> .\.venv\Scripts\Activate.ps1
> ```

---

## Configure local.settings.json

Fill in your credentials. The file is gitignored and never deployed.

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

See [configuration-reference.md](configuration-reference.md) for all available settings.

---

## Running Locally

You need **two PowerShell terminals** open at the same time.

### Terminal 1 — Start Azurite

`AzureWebJobsStorage` is set to `UseDevelopmentStorage=true`, which requires Azurite to be running on port 10000. Start it first:

```powershell
azurite --location C:\azurite
```

> Create `C:\azurite` first if it doesn't exist: `mkdir C:\azurite`

Leave this terminal running. You should see:
```
Azurite Blob service is starting at http://127.0.0.1:10000
Azurite Queue service is starting at http://127.0.0.1:10001
Azurite Table service is starting at http://127.0.0.1:10002
```

### Terminal 2 — Start the Function

```powershell
cd C:\path\to\monitor
.\.venv\Scripts\Activate.ps1
func start
```

The function fires immediately on startup (`run_on_startup=True`) so you don't need to wait for the timer.

---

## Dry Run Mode

To test without writing to blob storage, set in `local.settings.json`:

```json
"DRY_RUN": "true"
```

Output will print what would be written:
```
============================================================
[DRY RUN] Would write to blob: stage/activity/2026/03/14/20260314_00001.json
============================================================
{ ... json content ... }
============================================================
```

---

## Troubleshooting

### `func` not recognized after npm install

Close and reopen PowerShell so the PATH update from npm takes effect.

### ExecutionPolicy error when activating .venv

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Azurite port in use

Another process is using port 10000. Find and stop it:
```powershell
netstat -ano | findstr :10000
taskkill /PID <pid> /F
```

### SSL errors calling Power BI API

On Windows, aiohttp uses the system resolver which handles IPv4/IPv6 correctly. If you see SSL timeouts, try:
```json
"WEBSITE_USE_PLACEHOLDER": "0"
```
in `local.settings.json` — this disables a Functions host optimization that can interfere with async code on Windows.

### `DefaultAzureCredential` fails locally

Ensure `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` are all set in `local.settings.json`. These are the exact variable names `DefaultAzureCredential` looks for.

### `cryptography` package fails to install (no C compiler)

Install the pre-built wheel:
```powershell
pip install cryptography --only-binary :all:
```

---

## Notes on Windows vs Linux/WSL2

| Behaviour | Linux/WSL2 | Windows |
|---|---|---|
| aiohttp IPv4 enforcement | Forced via `socket.AF_INET` (SSL hang fix) | Not needed — Windows DNS resolver handles IPv4/IPv6 correctly |
| Virtual environment activation | `source .venv/bin/activate` | `.\.venv\Scripts\Activate.ps1` |
| Azurite start directory | `/tmp/azurite` | `C:\azurite` |
| Line endings | LF | CRLF (git handles via `.gitattributes`) |

The code itself is fully cross-platform. The IPv4 enforcement in `env/context.py` is conditional:
```python
_CONNECTOR_KWARGS = dict(family=socket.AF_INET) if platform.system() != "Windows" else {}
```
