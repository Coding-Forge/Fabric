# Windows UI Release and Launcher

The easiest way for non-developer users to run the monitor is a release zip that contains the solution folder plus a double-click launcher.

## Recommended User Experience

Give users a zip file such as:

```text
fabric-monitor-windows-ui.zip
```

The user extracts it to a local folder, then double-clicks:

```text
Run Fabric Monitor UI.cmd
```

The launcher:

1. Creates `.venv` if it does not exist.
2. Installs `requirements.txt` the first time it runs.
3. Starts the Windows UI with:

```text
python -m app.windows_ui
```

Users do not need to know the Python command line after Python is installed.

## Create a Desktop Icon

After extracting the release folder, users can double-click:

```text
Create Desktop Shortcut.cmd
```

This creates:

```text
Fabric Monitor UI.lnk
```

on the user's desktop. The shortcut points to `Run Fabric Monitor UI.cmd`.

The shortcut uses this icon by default:

```text
icons\monitor-dashboard.ico
```

Five themed icons are included:

| Icon | Suggested use |
|---|---|
| `icons\monitor-dashboard.ico` | Default monitor dashboard launcher |
| `icons\audit-shield.ico` | Audit/compliance-focused deployment |
| `icons\activity-pulse.ico` | Activity monitoring deployment |
| `icons\license-audit.ico` | License usage and assignment tracking |
| `icons\audience-usage.ico` | Power BI audience usage tracking |

To use a different icon, edit `Create Desktop Shortcut.cmd` and change:

```cmd
set "ICON=%SCRIPT_DIR%icons\monitor-dashboard.ico"
```

to another `.ico` file in the `icons` folder.

## Release Zip Contents

Include these files and folders:

```text
app/
docs/
env/
schema_examples/
.env.example
requirements.txt
Run Fabric Monitor UI.cmd
Create Desktop Shortcut.cmd
icons/
README.md
```

Do not include:

```text
.venv/
__pycache__/
monitor-output/
*.log
*.json profiles that contain secrets
```

## Python Requirement

Users need Python 3.10 or later installed on Windows.

If the `py` launcher is available, the script uses:

```text
py -3 -m venv .venv
```

Otherwise, it falls back to:

```text
python -m venv .venv
```

## Profile and Secrets

Users should create or load a profile from the Windows UI. Do not ship customer-specific secrets in a release zip.

The UI validates that the client secret does not look like a secret ID. Users must paste the Entra client secret **value**, not the secret ID.

## Enterprise Packaging Option

For managed enterprise deployment, package the same release folder with Intune, Configuration Manager, or another software distribution tool.

Recommended enterprise flow:

1. Install Python 3.10+ through the enterprise software catalog.
2. Deploy the release zip to a standard path, for example:

```text
C:\Program Files\Fabric Monitor
```

3. Create a Start Menu or Desktop shortcut to:

```text
Run Fabric Monitor UI.cmd
```

4. Store profiles outside the installation folder, for example:

```text
%USERPROFILE%\Documents\Fabric Monitor Profiles
```

## Future Enhancement: Single EXE

If you want no Python prerequisite, package the UI with PyInstaller into a single executable. That is a separate release build step and should be done in a clean build pipeline so the executable is reproducible and does not include secrets.

