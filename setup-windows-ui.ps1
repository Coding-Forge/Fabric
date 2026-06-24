# Fabric Monitor - Windows UI Setup
# Run from the repository root:
#   cd C:\Projects\Fabric\monitor
#   .\setup-windows-ui.ps1

param(
    [string]$PythonVersion = "3.12"
)

$ErrorActionPreference = "Stop"

Write-Host "`n=== Fabric Monitor - Windows UI Setup ===" -ForegroundColor Cyan

function Test-PythonVersion {
    param([string]$Version)

    $result = & py "-$Version" --version 2>$null
    return $LASTEXITCODE -eq 0
}

function Resolve-PythonVersion {
    param([string]$Version)

    if (Test-PythonVersion -Version $Version) {
        return $Version
    }

    $armVersion = "$Version-arm64"
    if (Test-PythonVersion -Version $armVersion) {
        Write-Host "Python $Version was not found, but $armVersion is installed." -ForegroundColor Yellow
        Write-Host "Using $armVersion and ARM64-compatible dependency markers." -ForegroundColor Yellow
        return $armVersion
    }

    return $null
}

Write-Host "`n[1/3] Checking Python $PythonVersion..." -ForegroundColor Yellow
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Host "Python launcher 'py' was not found." -ForegroundColor Red
    Write-Host "Install Python $PythonVersion from https://www.python.org/downloads/ and check 'Add python.exe to PATH'." -ForegroundColor Red
    exit 1
}

$ResolvedPythonVersion = Resolve-PythonVersion -Version $PythonVersion

if (-not $ResolvedPythonVersion) {
    Write-Host "Python $PythonVersion is not installed or is not registered with the Python launcher." -ForegroundColor Red
    Write-Host "Installed Python versions:" -ForegroundColor Yellow
    py -0p
    Write-Host "`nInstall Python $PythonVersion, then re-run this script." -ForegroundColor Red
    exit 1
}

py "-$ResolvedPythonVersion" --version

Write-Host "`n[2/3] Creating virtual environment..." -ForegroundColor Yellow
if (-not (Test-Path ".venv")) {
    py "-$ResolvedPythonVersion" -m venv .venv
    Write-Host "Created .venv" -ForegroundColor Green
} else {
    Write-Host ".venv already exists" -ForegroundColor Green
}

Write-Host "`n[3/3] Installing dependencies..." -ForegroundColor Yellow
$env:PIP_PREFER_BINARY = "1"
$env:AIOHTTP_NO_EXTENSIONS = "1"
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nDependency installation failed." -ForegroundColor Red
    Write-Host "Delete .venv and re-run this script. If it still fails, install Microsoft C++ Build Tools or use Python $PythonVersion x64." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host @"

=== Setup complete ===

Start the UI with:

  cd C:\Projects\Fabric\monitor
  .\.venv\Scripts\Activate.ps1
  python -m app.windows_ui

If PowerShell blocks activation, run:

  Set-ExecutionPolicy RemoteSigned -Scope CurrentUser

"@ -ForegroundColor Cyan
