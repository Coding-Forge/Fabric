# One-step local dev launcher for Windows (PowerShell)
# Usage: .\dev.ps1
# First-time setup: run .\setup-windows.ps1 first

param()

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# ── Prerequisites check ────────────────────────────────────────────────────────
foreach ($cmd in @("func", "azurite")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: '$cmd' is not installed or not on PATH." -ForegroundColor Red
        Write-Host "Run .\setup-windows.ps1 first, or see docs\windows-development.md." -ForegroundColor Red
        exit 1
    }
}

# ── Ensure .venv exists ────────────────────────────────────────────────────────
if (-not (Test-Path ".venv")) {
    Write-Host "[setup] Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
    & .\.venv\Scripts\Activate.ps1
    Write-Host "[setup] Installing dependencies..." -ForegroundColor Yellow
    pip install -r requirements.txt --quiet
} else {
    & .\.venv\Scripts\Activate.ps1
}

# ── Ensure local.settings.json exists ─────────────────────────────────────────
if (-not (Test-Path "local.settings.json")) {
    if (Test-Path "local.settings.example") {
        Write-Host "[setup] local.settings.json not found — copying from example..." -ForegroundColor Yellow
        Copy-Item "local.settings.example" "local.settings.json"
    }
    Write-Host "Fill in your credentials in local.settings.json, then re-run." -ForegroundColor Yellow
    exit 0
}

# ── Start Azurite (background) ─────────────────────────────────────────────────
$azuriteDir = "C:\azurite"
$null = New-Item -ItemType Directory -Force -Path $azuriteDir

if (Get-Process -Name "azurite" -ErrorAction SilentlyContinue) {
    Write-Host "[azurite] Already running — skipping." -ForegroundColor Green
} else {
    Write-Host "[azurite] Starting in background (location: $azuriteDir)..." -ForegroundColor Yellow
    Start-Process "azurite" -ArgumentList "--location `"$azuriteDir`"" -WindowStyle Minimized
    Start-Sleep -Seconds 1
    Write-Host "[azurite] Started." -ForegroundColor Green
}

# ── Start Azure Function ───────────────────────────────────────────────────────
Write-Host ""
Write-Host "Starting Azure Function host..." -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop."
Write-Host ""
func start
