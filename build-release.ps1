[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$Version = "1.0.0",
    [string]$OutputDirectory = "release",
    [switch]$IncludeSetupScripts,
    [switch]$IncludeContainers,
    [switch]$IncludeInfra,
    [switch]$IncludeNotebooks,
    [switch]$IncludeFabricAssets,
    [switch]$IncludeAzureDevOps,
    [switch]$IncludeAllOptional,
    [switch]$NoClean
)

$ErrorActionPreference = "Stop"

function Copy-ReleaseItem {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath,
        [Parameter(Mandatory = $true)]
        [string]$SourceRoot,
        [Parameter(Mandatory = $true)]
        [string]$StagingRoot
    )

    $source = Join-Path $SourceRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source)) {
        Write-Warning "Skipping missing path: $RelativePath"
        return
    }

    $destination = Join-Path $StagingRoot $RelativePath
    $destinationParent = Split-Path -Parent $destination
    if ($destinationParent -and -not (Test-Path -LiteralPath $destinationParent)) {
        New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
    }

    $item = Get-Item -LiteralPath $source
    if ($item.PSIsContainer) {
        Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
    }
    else {
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }
}

function Remove-ReleaseJunk {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $directoryNames = @(
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".pbi",
        "monitor-output",
        "GeneralDynamics"
    )

    foreach ($name in $directoryNames) {
        Get-ChildItem -Path $Path -Recurse -Force -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq $name } |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }

    $filePatterns = @(
        "*.pyc",
        "*.pyo",
        "*.log",
        ".env",
        "local.settings.json",
        "state.yaml",
        "monitor-profile.json",
        "packages-microsoft-prod.deb"
    )

    foreach ($pattern in $filePatterns) {
        Get-ChildItem -Path $Path -Recurse -Force -File -Filter $pattern -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction SilentlyContinue
    }
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

$safeVersion = $Version.TrimStart("v")
$zipName = "fabric-monitor-windows-ui-v$safeVersion.zip"
$outputRoot = if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    $OutputDirectory
}
else {
    Join-Path $scriptRoot $OutputDirectory
}
$stagingRoot = Join-Path $outputRoot "fabric-monitor-windows-ui-v$safeVersion"
$zipPath = Join-Path $outputRoot $zipName

$requiredItems = @(
    "app",
    "docs",
    "env",
    "icons",
    "schema_examples",
    ".env.example",
    "requirements.txt",
    "README.md",
    "Run Fabric Monitor UI.cmd",
    "Create Desktop Shortcut.cmd"
)

$optionalItems = [ordered]@{
    SetupScripts = @("setup-windows-ui.ps1", "setup-windows.ps1")
    Containers   = @("containers")
    Infra        = @("infra", "azure.yaml", "BICEP_README.md")
    Notebooks    = @("notebooks", "Fabric GIT Notebook test.Notebook", "test.ipynb", "testing.ipynb", "zz.ipynb")
    FabricAssets = @("Fabric", "activity.json.txt", "PublicLibrary.yml")
    AzureDevOps  = @(".azdo")
}

$includeItems = New-Object System.Collections.Generic.List[string]
$requiredItems | ForEach-Object { $includeItems.Add($_) }

if ($IncludeAllOptional -or $IncludeSetupScripts) {
    $optionalItems.SetupScripts | ForEach-Object { $includeItems.Add($_) }
}
if ($IncludeAllOptional -or $IncludeContainers) {
    $optionalItems.Containers | ForEach-Object { $includeItems.Add($_) }
}
if ($IncludeAllOptional -or $IncludeInfra) {
    $optionalItems.Infra | ForEach-Object { $includeItems.Add($_) }
}
if ($IncludeAllOptional -or $IncludeNotebooks) {
    $optionalItems.Notebooks | ForEach-Object { $includeItems.Add($_) }
}
if ($IncludeAllOptional -or $IncludeFabricAssets) {
    $optionalItems.FabricAssets | ForEach-Object { $includeItems.Add($_) }
}
if ($IncludeAllOptional -or $IncludeAzureDevOps) {
    $optionalItems.AzureDevOps | ForEach-Object { $includeItems.Add($_) }
}

$includeItems = $includeItems | Select-Object -Unique

if ($PSCmdlet.ShouldProcess($zipPath, "Build release zip")) {
    New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

    if (-not $NoClean) {
        if (Test-Path -LiteralPath $stagingRoot) {
            Remove-Item -LiteralPath $stagingRoot -Recurse -Force
        }
        if (Test-Path -LiteralPath $zipPath) {
            Remove-Item -LiteralPath $zipPath -Force
        }
    }

    New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null

    foreach ($item in $includeItems) {
        Copy-ReleaseItem -RelativePath $item -SourceRoot $scriptRoot -StagingRoot $stagingRoot
    }

    Remove-ReleaseJunk -Path $stagingRoot

    $manifest = [ordered]@{
        name = "Fabric Monitor Windows UI"
        version = $safeVersion
        createdUtc = (Get-Date).ToUniversalTime().ToString("o")
        requiredItems = $requiredItems
        optionalIncluded = @($includeItems | Where-Object { $_ -notin $requiredItems })
        excludedPatterns = @(".venv", "__pycache__", ".git", ".pbi", "monitor-output", "GeneralDynamics", "*.pyc", "*.log", ".env", "local.settings.json", "state.yaml", "monitor-profile.json")
        entryPoint = "Run Fabric Monitor UI.cmd"
        shortcutCreator = "Create Desktop Shortcut.cmd"
    }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -Path (Join-Path $stagingRoot "release-manifest.json") -Encoding UTF8

    Compress-Archive -Path (Join-Path $stagingRoot "*") -DestinationPath $zipPath -Force

    Write-Host "Release zip created:"
    Write-Host $zipPath
    Write-Host ""
    Write-Host "Included items:"
    $includeItems | Sort-Object | ForEach-Object { Write-Host " - $_" }
}

