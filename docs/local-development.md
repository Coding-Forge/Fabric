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

The `APPLICATION_MODULES` setting is a comma-separated list of data collection modules to enable. The example above selects the following modules; optional modules are not enabled automatically:

| Module | Description |
|---|---|
| `Activity` | Power BI activity events (audit log) |
| `Apps` | Power BI apps published in the tenant |
| `Capacity` | Fabric / Power BI Premium capacities |
| `Catalog` | Full workspace and item catalog via the scanner (`getInfo`) API |
| `Domains` | Fabric domains |
| `FabricItems` | Fabric-specific items (lakehouses, notebooks, pipelines, etc.) |
| `Gateway` | On-premises and VNet data gateways |
| `Graph` | Azure AD users, licences and SKUs via Microsoft Graph; groups and group members only when `GRAPH_EXTRACT_GROUPS` is on (see [configuration-reference.md](configuration-reference.md#microsoft-graph-graph)) |
| `Refreshables` | Datasets / semantic models that support scheduled refresh |
| `RefreshHistory` | Refresh history for all refreshable items |
| `Roles` | Workspace role assignments |
| `Tenant` | Tenant-level settings |
| `Workspaces` | All workspaces in the tenant |

Remove any module name from the list to skip it on each run.

The four opt-in collectors `FabricItemAccessPermissions`, `FabricItemJobHistory`, `FabricConnections` and `FabricDeploymentPipelineOperations` require deliberate enablement. The first two also require explicit JSON item scopes. See [settings, endpoints and output contract](configuration-reference.md#scoped-fabric-collectors) and [operating guidance](#operating-the-four-fabric-collectors) below.

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

## Local-folder PoC mode

For a proof of concept you can write output to a local folder instead of Blob Storage. This needs no storage account, but it is **not an offline mode**: the monitor still calls the real Microsoft APIs (Power BI, Fabric, Graph) with a real service principal.

### Set it up

1. Set `LOCAL_OUTPUT_PATH` to a folder, for example `~/monitor-poc-output`. It is created if missing; startup fails if it is not a writable directory.
2. Provide credentials. In this mode `COMMERCIAL_TENANT_ID`, `COMMERCIAL_CLIENT_ID` and `COMMERCIAL_CLIENT_SECRET` are accepted from the environment. Precedence is `COMMERCIAL_*` > `TENANT_ID`/`CLIENT_ID`/`CLIENT_SECRET` > legacy `TenantId`/`ClientId`/`ClientSecret`. The aliases are ignored when `LOCAL_OUTPUT_PATH` is not set.
3. Set `APPLICATION_MODULES` as usual.
4. Start the host with `func start` (Azurite is still needed for `AzureWebJobsStorage`).

When `LOCAL_OUTPUT_PATH` is set, Blob and Lakehouse settings are ignored. Output uses the same layout as Blob mode, for example `<LOCAL_OUTPUT_PATH>/activity/YYYY/MM/DD/...`.

### Things to know

- **A run starts immediately.** The timer has `run_on_startup=True`, so starting the Functions host triggers a run straight away, which calls the real APIs.
- **`local.settings.json` wins over your shell.** Core Tools loads `Values` from `local.settings.json` and these override variables exported in the shell. A stale `TENANT_ID`, `CLIENT_ID` or similar left in that file will take precedence over what you exported. Remove or update it. Note that `COMMERCIAL_*` still outranks the canonical names if both end up in the environment.
- **Legacy collectors ignore `DRY_RUN` in local mode.** The four new Fabric collectors instead reject `DRY_RUN=true` in every storage mode; it is not an offline API test switch.
- **Keep the output folder out of git.** The output can contain tenant data. Put it outside the repository or make sure it is gitignored, and do not commit it.
- **`state.yaml` lives in the output folder.** Keep it to continue incrementally. For the four new Fabric collectors, root state is separate from module-local quota/progress controls: deleting root state does not reset those controls and must not be used to bypass them.
- **A failed local write fails the module.** The module returns failure and `lastRun` does not advance, so it is retried on the next run.
- **`azure-identity` must still be installed.** It comes with `requirements.txt`; local mode does not remove the dependency.

Example `Values` additions (placeholders only):

```json
"LOCAL_OUTPUT_PATH": "~/monitor-poc-output",
"COMMERCIAL_TENANT_ID": "<tenant-id>",
"COMMERCIAL_CLIENT_ID": "<client-id>",
"COMMERCIAL_CLIENT_SECRET": "<client-secret>"
```

See [configuration-reference.md](configuration-reference.md#option-d--local-folder-proof-of-concept).

## Operating the four Fabric collectors

The [configuration reference](configuration-reference.md#scoped-fabric-collectors) defines the exact module/cron names, scope limits, endpoints and envelope schema. All four collectors' immutable output is integrated into the 12-page [MonitorRaw report](../pbip-local/MonitorRaw/README.md), with native Desktop acceptance still pending. Report-only updates need Desktop reopen/reload and **Home > Refresh** against existing output, not `func start`, API calls or a host restart.

### Before enabling

1. Confirm API/tenant authorization and actual resource permissions for the intended caller. Admin inventory access does not grant job history access; pipeline operation history requires pipeline Admin. Connections and pipelines are caller-visible, not tenant-complete.
2. Choose a small, deliberate scope: `FABRIC_ITEM_ACCESS_SCOPE` has 1–50 workspace/item/type objects; `FABRIC_ITEM_JOB_SCOPE` has 1–100 and supports only `Notebook`, `DataPipeline`, `SparkJobDefinition`. Use the escaped JSON-string examples in the reference. Do not paste tenant identifiers or secrets into committed examples.
3. Choose the output root and run **one scheduler against it**. For a local trial, set `LOCAL_OUTPUT_PATH` outside the repository; Blob/Lakehouse settings are then ignored. This still authenticates and calls real APIs. Azurite only emulates host storage; it does not mock Microsoft APIs.
4. Only after these choices, explicitly add the desired exact module names to `APPLICATION_MODULES`. Remove unrelated modules if this is intended to be a collector-only trial. Do not use `DRY_RUN=true`: strict snapshots cannot be committed in dry-run mode.
5. Start `func start` only when authorized to make real requests. It invokes once on startup, then daily at 02:00 UTC by default. Inspect the output manifests/resources and persisted controls; do not equate a log saying the outer run finished with a healthy collection cycle.

### Repeated permission slices

A permission invocation admits at most six single-attempt slices within a 150-second admission budget, with a 35-second admission reserve and 30-second HTTP timeout. Authentication and storage are not bounded by that budget. A workspace can need multiple inventory pages before its configured item access calls. Larger scopes, failures and server cooldowns can therefore require multiple invocations.

**Approved permission pacing fix:** when a local UTC request gate is still slightly in the future, admission now waits the actual remaining delay and rechecks the gate instead of returning early or using a fixed sleep. Waiting is allowed only when the delay plus the admission reserve fits the remaining monotonic budget (an exact fit is allowed), with at most three sleeps/rechecks. Deadline checks include authentication/setup and reservation writes; a slow reservation write fails closed with the durable pending reservation intact rather than sending a late request. This is an admission budget, not a hard timeout for all authentication or storage work. Durable quota spacing and server cooldowns are not bypassed.

Leaving the host running does **not** immediately resume an incomplete cycle: with the current trigger it next invokes on the daily timer. A module cron such as `FABRICITEMACCESSPERMISSIONS_CRON=*/5 * * * *` only checks eligibility on those invocations; it does not create five-minute wakeups. For a controlled local continuation, wait for the prior invocation to end, stop the host, and start it again when the persisted gate permits. Each startup supplies another invocation, subject to the module's cron/checkpoint; do not overlap hosts or loop restarts to evade a cooldown. For ongoing higher-frequency polling, the operator must separately arrange an authorized host invocation cadence (the timer schedule is currently defined in `function_app.py`); this documentation change does not alter it.

**Next local check after the fix (user action):** once the current invocation has ended, press **Ctrl+C only in the Functions host terminal**, leave Azurite running, then run `func start` once from the repository root with the existing virtual environment active. Inspect the latest invocation's sanitized logs, manifests and `progress.json` for progress; a short gate delay that fits the budget no longer requires repeated manual early starts. This does not guarantee a full cycle in that invocation or continuous slices after it ends. Long `Retry-After` cooldowns defer work rather than justify repeated manual requests; pending/blocked gates remain fail-closed. Never clear state or gates to force this check.

Incomplete/unhealthy cycles return failure, leaving `lastRun` unchanged, so subsequent invocations remain eligible once their cron is due. Only a fully healthy completed scope cycle advances the checkpoint. Later resources are still visited after earlier resource failures; an unhealthy finished cycle starts afresh on a later invocation. Use manifests' `execution` and `progress.json` to distinguish continuation from a completed cycle. Inventory and access observations across slices are not simultaneous.

Choose job/pipeline polling cadence for expected volume: most job APIs retain 100 recent completed jobs plus active jobs, and pipeline history exposes up to 20 recent deployments. Faster polling can reduce gaps but cannot recover already-aged-out records. Keep immutable observations and compute latest state by parent IDs plus record ID and `observedAt`, rather than summing repeated polls.

Existing pipeline inventory/history can legitimately be empty; emptiness alone is not evidence of a pacing failure. Check the corresponding successful manifest rather than assuming records must exist.

### Investigating blocked collection and changing scope

Controls live under the **configured output root/prefix**, not necessarily the repository:

- All four module folders have `request_gate.json`: `nextRequestUtc`, `blocked`, `pending`.
- `fabricitemaccesspermissions/progress.json` holds scope/cursor/continuations, cycle health and a link to prior immutable manifest evidence.
- Resource observations and `manifest.json` live in `<module>/YYYY/MM/DD/runId/`.

Numeric and HTTP-date cooldowns persist across process restarts. A future `nextRequestUtc` means no request before that time: permission admission may wait and recheck within its remaining budget as described above; otherwise work defers to a later eligible invocation. An invalid header sets `blocked=true`; an unacknowledged request can leave `pending=true`, including after a transport timeout. In the latter case the server may have processed the request. The gate will not automatically clear either flag merely because time passed.

For recovery, stop the scheduler and preserve the ledger, progress, manifests and relevant sanitized logs. Investigate the response/cooldown, request timing, storage failures and other clients sharing the same quota. Establish a safe next-request time before any operator-controlled repair; keep it at least as late as every known server cooldown and account for ambiguous attempts. There is no automatic repair command. If the server outcome/cooldown cannot be established, leave collection blocked and escalate to the API/service owner. Do **not** casually delete/reinitialize a quota ledger, clear flags without evidence, or reset its timestamp into the past. A shared output root does not coordinate external clients using the same quota.

Changing permission scope while `progress.json` exists is rejected (including ordering changes). With the scheduler stopped, **archive `fabricitemaccesspermissions/progress.json` before explicitly starting a new scope**. Preserve its linked immutable evidence and the original scope for auditability; the unfinished old cycle must not be reported as completed. Keep `request_gate.json` and honor all existing quota reservations/cooldowns. Scope replacement is not quota recovery. Check cron eligibility separately if the old scope had already advanced `lastRun`.

**Validation boundary:** the final independent cycle3 Code Reviewer verdict reported production and tests **Approved**, with 58 targeted and 483 full offline tests passing under Python 3.12, plus Ruff with target `py310`. A lint target is not execution under Python 3.10. No live tenant authentication, actual API or storage integration validation, deployment, or Desktop validation is established for these collectors by those offline results.

For the narrow permission pacing fix, the final independent cycle3/3 Code Reviewer verdict was **Approved — both production and tests**: reported validation was **68 focused and 504 full offline tests passed** (six new tests), with the offline environment cleared and a DNS/socket guard, plus Ruff and static Python 3.10 syntax checks. Execution used Python 3.12.3, not Python 3.10; a requests dependency warning was nonblocking. Live success remains unverified: these results do not establish that the current permission cycle or all 13 scoped items completed. No tenant call, host restart, deployment or Desktop validation was performed in that review; no unrelated report or configuration approval is implied.

### Gated Fabric GET: safe error-code diagnostics

Failed GET requests for the four opt-in Fabric collectors now include the numeric HTTP status and a sanitized `errorCode` in logs, returned errors and persisted manifest error entries. This is a **diagnostics-only** change: it does not change retries, quotas, scope acceptance, cycle health, checkpoints or report selection.

- The only API error codes retained are `ItemNotFound` and `InvalidItemType`, verified against Microsoft Fabric documentation; this is not an allowlist of every documented Fabric error code.
- An exact, nonempty string at top-level `errorCode` takes precedence. Only a missing or malformed top-level value falls back to a nonempty string at `error.code`. An unknown nonempty top-level string yields `unrecognized`, even when the nested code is allowlisted. Missing/malformed candidates yield `unavailable`.
- The response-body diagnostic read accepts at most **16 KiB**, with one extra byte as an oversize probe and a **one-second read budget**. Oversized, unparseable, invalidly encoded, unreadable or timed-out diagnostics yield `unavailable`; the original HTTP failure status (including 404) is preserved. This inspection makes no extra HTTP requests. JSON-only test/adapter fallback does not relax the code allowlist.
- Status sanitization across logs, returned errors and manifests retains only exact integers 100–599, excluding booleans; invalid values become `None`/JSON `null` (logged as status unavailable). Diagnostic values never include raw server messages, details, bodies, identifiers, URLs, headers, tokens, or arbitrary type, representation or exception text.

Synthetic log examples only — **not observed Dataflow responses**:

```text
Fabric GET failed: HTTP 404 errorCode=ItemNotFound
Fabric GET failed: HTTP 400 errorCode=InvalidItemType
Fabric GET failed: HTTP 404 errorCode=unrecognized
Fabric GET failed: HTTP 404 errorCode=unavailable
```

**Current evidence boundary:** the actual Dataflow 404 cause remains unresolved, including with sanitized `errorCode=unrecognized`; this does not establish that Gen2 is unsupported. Healthy end-to-end completion/checkpoint advancement remains pending. Saved grant rows do not establish whole-scope success: a failed target still prevents a healthy collection cycle. The approved partial-permission report now shows successful access observations from **one validated cycle**, preferring the newest useful finished cycle, otherwise useful in-progress evidence, without cross-cycle merging. Successful empty, failed, deferred and unvisited/unknown targets stay distinct; failure means unknown access, not no access. Selected evidence versus latest-attempt/stale warnings and global manifest-derived coverage survive principal/grant filters; integrity load-error counts are separate from collection outcomes. See the [report semantics and pending Desktop checklist](../pbip-local/MonitorRaw/README.md#item-permissions-and-fabric-jobs). This report policy does not change collectors, scope, gates, cycle health or checkpoints. Do not drop/exclude failed scope entries, clear state/gates/checkpoints, add configuration keys, or force repeated full cycles to obtain success.

**Next evidence (user action only):** after the current invocation ends and existing gates permit, restart only the Functions host once (`Ctrl+C`, then `func start` with the existing virtual environment active); leave Azurite running. Copy the next invocation's log into the existing `log-dump.json` for local review. Legacy/other logging may contain private payloads: inspect and redact excerpts before sharing, and never publish the raw log. A fresh cursor with Dataflow early in scope can still require inventory pages and normal bounded slices across startup and later scheduled invocations before the actual request yields its diagnostic code; immediate full-cycle completion is not guaranteed.

Final independent Code Reviewer cycle3 verdict: **Approved** for implementation and tests. Reported validation: **75 focused, 143 expanded and 511 full offline tests passed**, including seven new tests; Ruff format/lint and static Python 3.10 syntax checks passed. Execution used Python 3.12.3 with cleared environment and DNS/socket guards, not Python 3.10 execution or 511 tenant API calls. The requests dependency warning was baseline. No live API call, host restart or deployment was performed in that review; offline success does not establish the actual 404 cause or live recovery.

### FabricConnections: sanitized failure diagnostics

The diagnostics-only change received a final independent Code Reviewer cycle3 **Approved** verdict for both production and tests; reported validation was **487 full offline tests passed**. The later nullable-name and Catalog empty-discovery correction also received a final independent cycle3 **Approved** verdict for production and tests, with **490 full offline tests passed**. Neither result establishes live resolution; the next run must confirm the outcome.

**Nullable connection names:** an observed HTTP 200 response containing `displayName: null` is now accepted, preserving the explicit null in the saved connection metadata. No fallback name is invented and the connection is not dropped. This is observed API behavior, not an explicitly documented nullable API contract. Missing names, empty strings and non-string/non-null names still fail validation. Strict `id` and `connectivityType` validation and the metadata allowlist remain unchanged.

The final `fabricconnections resource incomplete: connections` warning and persisted `Resource inaccessible, malformed, or incomplete` error describe the outcome, **not the root cause**. Look earlier in the same invocation for HTTP, transport or schema-validation diagnostics:

- Safe GET logging reports `Fabric GET: HTTP <numeric status>` at INFO level and `Fabric GET failed: HTTP <numeric status>` for non-200 responses. Collector request failures report a numeric HTTP status or `HTTP status unavailable`.
- Schema warnings identify fixed schema field paths, the expected type/shape and an observed label: missing, null, empty string or a fixed type category. A one-based record ordinal is included where applicable (`record=-` when not applicable). Checks cover required connection metadata, `connectionDetails.type`, conflicting duplicate identities, response/page shape and continuation fields. Identical duplicates remain accepted; conflicting duplicates remain rejected.
- Request-failure status sanitization covers logs, returned errors and persisted manifest errors: only integers from 100 through 599 are retained (booleans excluded); other status values become `None` (`null` in persisted JSON), with logs saying status unavailable.

Synthetic examples only — these are **not observed failures**:

```text
Fabric GET: HTTP 200
fabricconnections Fabric request failed: HTTP 403
fabricconnections Fabric request failed: HTTP status unavailable
fabricconnections validation failed: record=1 field=displayName expected=nonempty string or null observed=missing
fabricconnections validation failed: record=1 field=connectionDetails.type expected=nonempty string observed=empty string
fabricconnections validation failed: record=- field=$.value expected=list observed=null
Fabric records validation failed: record=2 field=id expected=unique identity or identical duplicate observed=conflicting duplicate object
```

These diagnostics exclude credentials, user/resource identifiers, tokens, raw responses, raw connection values (including connection paths and strings), request URLs/queries, and arbitrary representations, type names or exception text. Fixed schema paths such as `connectionDetails.type` are labels, not connection values. Neither the diagnostics nor the nullable-name correction claims that all collector failures are fixed or that permissions caused the failure. Apart from accepting and preserving explicit null names, collection validation is unchanged; logging, quota gates, storage and checkpoint behavior are unchanged.

**Get the next evidence:** when the current invocation has ended and the persisted gate permits another attempt, press **Ctrl+C only in the current Functions host terminal**. Leave Azurite running. From the repository root with the existing virtual environment activated, run `func start` once. Startup invokes the monitor and may call real APIs; do not overlap hosts or repeatedly restart to bypass a gate. Preserve existing gates, checkpoints and collected data; do not reset them to obtain diagnostics. Inspect the earlier sanitized warnings and manifest outcome from that invocation. Review any shared excerpt for sensitive content from other logging sources.

### Catalog: empty discovery is successful no-work

Workspace discovery returning either `[]` or `{"value":[]}` is valid no-work: Catalog returns `True`, performs no scan or catalog save, and leaves `lastFullScan` unchanged. Success remains eligible for the normal audit `lastRun` update; it does not mean a full scan completed. Error responses, malformed responses/records and `None` still return failure. Other logging, gates and checkpoint rules are unchanged.

---

## Dry Run Mode

For legacy collectors, to see what would be written to blob storage without actually writing anything, set:

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

This still permits real API calls. The four new Fabric collectors reject dry-run snapshot writes in all storage modes; use offline tests for validation without API calls.

---

## Verify API calls

Legacy API calls log lines such as:

```
[API] GET https://api.powerbi.com/v1.0/myorg/admin/activityevents?... -> HTTP 200 | records: 312
[API] POST https://api.powerbi.com/v1.0/myorg/admin/workspaces/getInfo -> HTTP 202 | records: 1
```

The four new Fabric collectors use sanitized `Fabric GET: HTTP <status>` INFO logging (when INFO is enabled), excluding request paths, URLs/queries and response bodies. Failed gated GETs also include a safe `errorCode`; see [error-code diagnostics and the next evidence-gathering step](#gated-fabric-get-safe-error-code-diagnostics). Their durable manifests/gates are the collection outcome evidence. See [FabricConnections failure diagnostics](#fabricconnections-sanitized-failure-diagnostics) for schema warning examples.

Common HTTP errors:
- **403** — Service principal missing Power BI admin role or API consent. See [managed-identity.md](managed-identity.md).
- **401** — Token acquisition failed. Check `CLIENT_ID` / `CLIENT_SECRET` / `TENANT_ID`.
- **429** — Throttled. Shared retries apply where allowed; the four Fabric collectors persist cooldowns, and permission retries defer to a later eligible invocation. See [throttling and retries](configuration-reference.md#throttling-and-retries).

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
