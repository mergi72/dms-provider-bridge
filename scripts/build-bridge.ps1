param(
    [string]$Name = "dms-provider-bridge",
    [string]$OutputDir = "dist",
    [switch]$SkipPyInstallerInstall
)

$ErrorActionPreference = "Stop"

function Resolve-PythonExe {
    $repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
    $candidates = @(
        (Join-Path $repoRoot ".venv312\Scripts\python.exe"),
        (Join-Path $repoRoot ".venv\Scripts\python.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return $pythonCmd.Source
    }

    throw "Python executable was not found (.venv312/.venv/PATH)."
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$pythonExe = Resolve-PythonExe
$entryScript = Join-Path $repoRoot "src\dms_provider_bridge\main.py"
$configDir = Join-Path $repoRoot "config"
$outputPath = Join-Path $repoRoot $OutputDir
$pyiRoot = Join-Path $repoRoot "artifacts\bridge-onefile"
$workPath = Join-Path $pyiRoot "build"
$specPath = Join-Path $pyiRoot "spec"
$configStageDir = Join-Path $pyiRoot "config"
$configWhitelist = @(
    "bridge.json",
    "alfresco.json",
    "edocat.json",
    "fso.json"
)

if (-not (Test-Path $entryScript)) {
    throw "Entry script not found: $entryScript"
}

if (-not (Test-Path $configDir)) {
    throw "Config directory not found: $configDir"
}

New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
New-Item -ItemType Directory -Path $workPath -Force | Out-Null
New-Item -ItemType Directory -Path $specPath -Force | Out-Null
if (Test-Path $configStageDir) {
    Remove-Item -Path $configStageDir -Recurse -Force
}
New-Item -ItemType Directory -Path $configStageDir -Force | Out-Null

foreach ($configName in $configWhitelist) {
    $configSource = Join-Path $configDir $configName
    if (-not (Test-Path $configSource)) {
        throw "Required config template missing: $configSource"
    }
    Copy-Item -Path $configSource -Destination (Join-Path $configStageDir $configName) -Force
}

if (-not $SkipPyInstallerInstall) {
    Write-Host "Installing/updating PyInstaller in selected environment..."
    & $pythonExe -m pip install --upgrade pyinstaller
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install PyInstaller."
    }
}

$separator = [IO.Path]::PathSeparator
$addData = "$configStageDir${separator}config"

Write-Host "Building onefile bridge executable..."
& $pythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name $Name `
    --paths (Join-Path $repoRoot "src") `
    --hidden-import dms_provider_bridge.app `
    --hidden-import dms_provider_bridge.app.server `
    --hidden-import dms_provider_bridge.providers.alfresco `
    --hidden-import dms_provider_bridge.providers.edocat `
    --hidden-import dms_provider_bridge.providers.fso `
    --add-data $addData `
    --distpath $outputPath `
    --workpath $workPath `
    --specpath $specPath `
    $entryScript

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$exePath = Join-Path $outputPath "$Name.exe"
if (-not (Test-Path $exePath)) {
    throw "Expected executable not found: $exePath"
}

Write-Host "Bridge executable ready: $exePath"
