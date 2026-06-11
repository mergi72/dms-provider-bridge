param(
    [string]$Version = "v0.4.16",
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

function New-ZipFromDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceDir,
        [Parameter(Mandatory = $true)]
        [string]$DestinationPath
    )

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem

    $resolvedSource = (Resolve-Path $SourceDir).Path
    $sourcePrefix = $resolvedSource.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

    if (Test-Path $DestinationPath) {
        Remove-Item -Path $DestinationPath -Force
    }

    $zip = [System.IO.Compression.ZipFile]::Open($DestinationPath, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        Get-ChildItem -Path $resolvedSource -File -Recurse | Sort-Object FullName | ForEach-Object {
            $relativePath = $_.FullName.Substring($sourcePrefix.Length).Replace([System.IO.Path]::DirectorySeparatorChar, "/")
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $_.FullName, $relativePath, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
        }
    }
    finally {
        $zip.Dispose()
    }
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
$userConfigTarget = Join-Path $staging "user-config"
$zipPath = Join-Path $OutputDir "DmsProviderBridgeService-$Version.zip"
$configWhitelist = @(
    "bridge.json",
    "alfresco.json",
    "edocat.json"
)
$userProviderLocalConfigNames = @(
    "alfresco.local.json",
    "edocat.local.json"
)

if (Test-Path $staging) {
    Remove-Item -Path $staging -Recurse -Force
}

New-Item -ItemType Directory -Path $staging -Force | Out-Null
New-Item -ItemType Directory -Path $configTarget -Force | Out-Null
New-Item -ItemType Directory -Path $userConfigTarget -Force | Out-Null

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

foreach ($configName in $userProviderLocalConfigNames) {
    Set-Content -Path (Join-Path $userConfigTarget $configName) -Value "{}" -Encoding ASCII
}

New-ZipFromDirectory -SourceDir $staging -DestinationPath $zipPath

Write-Host "Bridge service package created: $zipPath"
