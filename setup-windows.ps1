# Fabric Monitor - Windows Development Setup
# Run this script once from the project root in a PowerShell Admin terminal:
#   Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
#   cd C:\path\to\monitor
#   .\setup-windows.ps1

param(
    [string]$PythonVersion = "3.12",
    [string]$EnvName = "monitor"
)

Write-Host "`n=== Fabric Monitor - Windows Dev Setup ===" -ForegroundColor Cyan

# ── 1. Check prerequisites ─────────────────────────────────────────────────────
Write-Host "`n[1/5] Checking prerequisites..." -ForegroundColor Yellow

$missing = @()

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    $missing += "Python $PythonVersion  ->  https://www.python.org/downloads/"
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    $missing += "Node.js  ->  https://nodejs.org/"
}
if (-not (Get-Command func -ErrorAction SilentlyContinue)) {
    $missing += "Azure Functions Core Tools  ->  install below or via: npm install -g azure-functions-core-tools@4"
}

if ($missing.Count -gt 0) {
    Write-Host "`nThe following tools are missing. Install them and re-run this script:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}

Write-Host "  Python : $(python --version)" -ForegroundColor Green
Write-Host "  Node   : $(node --version)"   -ForegroundColor Green
Write-Host "  func   : $(func --version)"   -ForegroundColor Green

# ── 2. Install Azure Functions Core Tools (if missing) ────────────────────────
if (-not (Get-Command func -ErrorAction SilentlyContinue)) {
    Write-Host "`n[2/5] Installing Azure Functions Core Tools v4..." -ForegroundColor Yellow
    npm install -g azure-functions-core-tools@4 --unsafe-perm true
} else {
    Write-Host "`n[2/5] Azure Functions Core Tools already installed." -ForegroundColor Green
}

# ── 3. Install Azurite ─────────────────────────────────────────────────────────
Write-Host "`n[3/5] Installing Azurite (local storage emulator)..." -ForegroundColor Yellow
if (Get-Command azurite -ErrorAction SilentlyContinue) {
    Write-Host "  Azurite already installed: $(azurite --version)" -ForegroundColor Green
} else {
    npm install -g azurite
    Write-Host "  Azurite installed." -ForegroundColor Green
}

# ── 4. Create and activate Python virtual environment ─────────────────────────
Write-Host "`n[4/5] Setting up Python virtual environment (.venv)..." -ForegroundColor Yellow

if (-not (Test-Path ".venv")) {
    python -m venv .venv
    Write-Host "  Created .venv" -ForegroundColor Green
} else {
    Write-Host "  .venv already exists" -ForegroundColor Green
}

& .\.venv\Scripts\Activate.ps1

Write-Host "  Installing dependencies from requirements.txt..." -ForegroundColor Yellow
pip install -r requirements.txt --quiet
Write-Host "  Dependencies installed." -ForegroundColor Green

# ── 5. Check local.settings.json ───────────────────────────────────────────────
Write-Host "`n[5/5] Checking local.settings.json..." -ForegroundColor Yellow

if (-not (Test-Path "local.settings.json")) {
    Write-Host "  local.settings.json not found - creating from template..." -ForegroundColor Yellow
    $template = @'
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "TENANT_ID": "",
    "CLIENT_ID": "",
    "CLIENT_SECRET": "",
    "AZURE_TENANT_ID": "",
    "AZURE_CLIENT_ID": "",
    "AZURE_CLIENT_SECRET": "",
    "APPLICATION_MODULES": "Activity,Apps,Capacity,Catalog,Domains,FabricItems,Gateway,Graph,Refreshables,RefreshHistory,Roles,Tenant,Workspaces",
    "STORAGE_ACCOUNT_URL": "https://<your-storage-account>.blob.core.windows.net",
    "STORAGE_ACCOUNT_CONTAINER_NAME": "monitor",
    "STORAGE_ACCOUNT_CONTAINER_ROOT_PATH": "stage",
    "DRY_RUN": "true",
    "ALL_WORKSPACES": "false"
  }
}
'@
    $template | Out-File -FilePath "local.settings.json" -Encoding UTF8
    Write-Host "  local.settings.json created - fill in your credentials before running." -ForegroundColor Yellow
} else {
    Write-Host "  local.settings.json exists." -ForegroundColor Green
}

# ── Done ───────────────────────────────────────────────────────────────────────
Write-Host "`n=== Setup complete! ===" -ForegroundColor Cyan
Write-Host @"

Next steps:
  1. Fill in your credentials in local.settings.json
  2. Start Azurite in a separate terminal:
       azurite --location C:\azurite
  3. Activate the virtual environment (if not already active):
       .\.venv\Scripts\Activate.ps1
  4. Start the function:
       func start

See docs\windows-development.md for full instructions.
"@ -ForegroundColor White
