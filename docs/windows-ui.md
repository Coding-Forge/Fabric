# Windows Desktop UI

The Windows desktop UI is for non-developers who want to run Fabric Monitor without typing CLI commands. It uses the same monitor runner as the CLI, so profiles created for the UI can also be used from automation or PowerShell.

## Prerequisites

- Windows desktop machine
- Python 3.12 recommended
- Project dependencies installed

If `.venv\Scripts\Activate.ps1` does not exist, the virtual environment has not been created yet.

## First-time setup

From the repository root:

```powershell
cd C:\Projects\Fabric\monitor
.\setup-windows-ui.ps1
```

The setup script checks for Python 3.12, creates `.venv`, and installs `requirements.txt`. If only `3.12-arm64` is installed, the script uses ARM64-compatible dependency markers and skips packages that do not have Windows ARM64 wheels.

If Python 3.12 is not installed, install Python 3.12 from [python.org](https://www.python.org/downloads/) and re-run the script. During installation, check **Add python.exe to PATH**.

## Start the UI

From the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m app.windows_ui
```

The UI opens a window named **Fabric Monitor**.

If PowerShell blocks activation scripts, run this once:

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## Configure a run

### Service principal

On the **Configuration** tab, fill in:

| Field | Description |
|---|---|
| Tenant ID | Microsoft Entra tenant ID |
| Client ID | Service principal application/client ID |
| Client secret | Service principal secret |

The client secret is masked in the UI.

### Output storage

Choose one storage mode:

| Mode | Required fields |
|---|---|
| Local files | Local output path |
| Blob Storage URL | Blob account URL, Blob container, optional Blob root path |
| Blob Storage connection string | Blob connection string, Blob container, optional Blob root path |
| Fabric Lakehouse | Lakehouse name, Workspace name, optional Path in lakehouse |

The UI only displays the fields needed for the selected storage mode. Changing the storage mode hides unrelated fields to reduce confusion.

For a simple local desktop run, choose **Local files** and keep `Data` as the output path.

### Run options

| Option | Effect |
|---|---|
| Full catalog workspace scan | Runs catalog in full workspace scan mode, equivalent to CLI `--base` |
| Dry run for Blob Storage writes | Prints blob writes without writing data, equivalent to CLI `--dry-run` |
| Exclude personal workspaces | Excludes personal workspaces from catalog modified-workspace scans |
| Exclude inactive workspaces | Excludes inactive workspaces from catalog modified-workspace scans |
| Include client secret when saving profile | Saves `CLIENT_SECRET` into the JSON profile. Leave unchecked unless the profile is stored securely. |

## Select modules

Open the **Modules** tab and select the monitor modules to run. The selected modules are written to `APPLICATION_MODULES`.

Common starting set:

```text
Activity, Apps, Catalog, Graph, Tenant, RefreshHistory, Gateway
```

## Run the monitor

Click **Run Monitor**.

The UI starts the CLI in the background using:

```powershell
python -m app.monitor --profile <temporary-profile>
```

Output appears on the **Run Log** tab. Click **Stop** to terminate a running monitor process.

## Save and load profiles

Click **Save Profile** to save a JSON profile. By default, the client secret is not saved. This is safer for shared desktops.

Click **Load Profile** to restore a saved profile.

Example profile:

```json
{
  "TENANT_ID": "<tenant-id>",
  "CLIENT_ID": "<client-id>",
  "APPLICATION_MODULES": "Activity,Catalog,Tenant",
  "OUTPUT_PATH": "Data",
  "ALL_WORKSPACES": false,
  "EXCLUDE_PERSONAL_WORKSPACES": true,
  "EXCLUDE_INACTIVE_WORKSPACES": true
}
```

If the profile does not include `CLIENT_SECRET`, enter the secret in the UI before running.

## Use the same profile from CLI

Profiles created by the UI can also be run from PowerShell:

```powershell
python -m app.monitor --profile .\profiles\local-monitor.json
```

Override modules for one run:

```powershell
python -m app.monitor --profile .\profiles\local-monitor.json --modules Activity,Catalog
```

Run a full catalog scan:

```powershell
python -m app.monitor --profile .\profiles\local-monitor.json --base
```

Use a specific `.env` file:

```powershell
python -m app.monitor --env-file .\.env
```

## Troubleshooting

| Issue | Fix |
|---|---|
| UI does not open | Confirm Python includes Tkinter: `python -m tkinter` |
| Run fails immediately | Check Tenant ID, Client ID, Client secret, and selected modules |
| Blob Storage URL auth fails locally | Set `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET`, or use connection string mode |
| Dependency install fails on Python ARM64 | Delete `.venv` and re-run `.\setup-windows-ui.ps1`. The requirements file includes ARM64 wheel-compatible versions for packages that need them. |
| No output files are created | Check selected storage mode and output path/container/lakehouse settings |
