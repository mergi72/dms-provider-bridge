param(
    [string]$Version = "v0.2.5-alpha",
    [string]$BridgeExePath = "dist\dms-provider-bridge.exe",
    [string]$NssmExePath,
    [string]$OutputDir = "artifacts\service-package"
)

$ErrorActionPreference = "Stop"

function Resolve-NssmPath {
    param([string]$ExplicitPath)

    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath) -and (Test-Path $ExplicitPath)) {
        return (Resolve-Path $ExplicitPath).Path
    }

    $candidates = @(
        "C:\tools\nssm\win64\nssm.exe",
        "C:\tools\nssm\nssm.exe",
        "$env:ProgramFiles\nssm\nssm.exe",
        "$env:ProgramFiles(x86)\nssm\nssm.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }

    return $null
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

if (-not [System.IO.Path]::IsPathRooted($BridgeExePath)) {
    $BridgeExePath = Join-Path $repoRoot $BridgeExePath
}

if (-not (Test-Path $BridgeExePath)) {
    throw "Bridge executable not found: $BridgeExePath"
}

$resolvedNssm = Resolve-NssmPath -ExplicitPath $NssmExePath
if ([string]::IsNullOrWhiteSpace($resolvedNssm)) {
    throw "NSSM executable not found. Provide -NssmExePath."
}

if (-not [System.IO.Path]::IsPathRooted($OutputDir)) {
    $OutputDir = Join-Path $repoRoot $OutputDir
}

$staging = Join-Path $OutputDir "staging"
$configTarget = Join-Path $staging "config"
$zipPath = Join-Path $OutputDir "DmsProviderBridgeService-$Version.zip"
$configWhitelist = @(
    "default.json",
    "alfresco.json",
    "edocat.json",
    "fso.json",
    "user.json"
)

if (Test-Path $staging) {
    Remove-Item -Path $staging -Recurse -Force
}

New-Item -ItemType Directory -Path $staging -Force | Out-Null
New-Item -ItemType Directory -Path $configTarget -Force | Out-Null

Copy-Item -Path $BridgeExePath -Destination (Join-Path $staging "dms-provider-bridge.exe") -Force
Copy-Item -Path $resolvedNssm -Destination (Join-Path $staging "nssm.exe") -Force
Copy-Item -Path (Join-Path $repoRoot "scripts\install-bridge-service.ps1") -Destination (Join-Path $staging "install-bridge-service.ps1") -Force
Copy-Item -Path (Join-Path $repoRoot "scripts\uninstall-bridge-service.ps1") -Destination (Join-Path $staging "uninstall-bridge-service.ps1") -Force

foreach ($configName in $configWhitelist) {
    $configSource = Join-Path $repoRoot (Join-Path "config" $configName)
    if (-not (Test-Path $configSource)) {
        throw "Required config template missing: $configSource"
    }
    Copy-Item -Path $configSource -Destination (Join-Path $configTarget $configName) -Force
}

if (Test-Path $zipPath) {
    Remove-Item -Path $zipPath -Force
}

Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -Force

Write-Host "Bridge service package created: $zipPath"
