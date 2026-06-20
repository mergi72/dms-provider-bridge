param(
    [string]$Version = "v0.7.19-beta",
    [string]$BridgeExePath = "dist\dms-provider-bridge.exe",
    [string]$NssmExePath,
    [string]$InnoCompilerPath,
    [switch]$SkipCompile
)

$ErrorActionPreference = "Stop"

function Resolve-IsccPath {
    param([string]$ExplicitPath)

    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath) -and (Test-Path $ExplicitPath)) {
        return (Resolve-Path $ExplicitPath).Path
    }

    $candidates = @(
        "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }

    return $null
}

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

$payloadDir = Join-Path $repoRoot "artifacts\bridge-installer-payload"
$configPayloadDir = Join-Path $payloadDir "config"
$userConfigPayloadDir = Join-Path $payloadDir "user-config"
$userDriverConfigPayloadDir = Join-Path $userConfigPayloadDir "drivers"
$machineConfigTemplatePaths = @(
    "bridge.json",
    "auth\auth.json",
    "providers\provider.json",
    "providers\provider.local.json",
    "drivers\driver.json",
    "drivers\alfresco.json",
    "drivers\edocat.json",
    "drivers\webdav.json",
    "connections\connection.json",
    "connections\alfresco.json",
    "connections\edocat.json",
    "connections\webdav.json"
)
$userDriverLocalConfigNames = @(
    "alfresco.local.json",
    "edocat.local.json",
    "webdav.local.json"
)
$userDriverLocalTemplate = Join-Path $repoRoot "config\providers\provider.local.json"

if (-not (Test-Path $userDriverLocalTemplate)) {
    throw "Required user driver local config template missing: $userDriverLocalTemplate"
}

if (Test-Path $payloadDir) {
    Remove-Item -Path $payloadDir -Recurse -Force
}

New-Item -ItemType Directory -Path $payloadDir -Force | Out-Null
New-Item -ItemType Directory -Path $configPayloadDir -Force | Out-Null
New-Item -ItemType Directory -Path $userConfigPayloadDir -Force | Out-Null
New-Item -ItemType Directory -Path $userDriverConfigPayloadDir -Force | Out-Null

$bridgeExeParent = Split-Path -Parent $BridgeExePath
$bridgeInternalDir = Join-Path $bridgeExeParent "_internal"

Copy-Item -Path $BridgeExePath -Destination (Join-Path $payloadDir "dms-provider-bridge.exe") -Force
if (Test-Path $bridgeInternalDir) {
    Copy-Item -Path $bridgeInternalDir -Destination (Join-Path $payloadDir "_internal") -Recurse -Force
}
Copy-Item -Path $resolvedNssm -Destination (Join-Path $payloadDir "nssm.exe") -Force
Copy-Item -Path (Join-Path $repoRoot "scripts\install-bridge-service.ps1") -Destination (Join-Path $payloadDir "install-bridge-service.ps1") -Force
Copy-Item -Path (Join-Path $repoRoot "scripts\uninstall-bridge-service.ps1") -Destination (Join-Path $payloadDir "uninstall-bridge-service.ps1") -Force

foreach ($configName in $machineConfigTemplatePaths) {
    $configSource = Join-Path $repoRoot (Join-Path "config" $configName)
    if (-not (Test-Path $configSource)) {
        throw "Required machine config template missing: $configSource"
    }
    $configDestination = Join-Path $configPayloadDir $configName
    New-Item -ItemType Directory -Path (Split-Path -Parent $configDestination) -Force | Out-Null
    Copy-Item -Path $configSource -Destination $configDestination -Force
}

foreach ($configName in $userDriverLocalConfigNames) {
    Copy-Item -Path $userDriverLocalTemplate -Destination (Join-Path $userDriverConfigPayloadDir $configName) -Force
}

Write-Host "Installer payload prepared: $payloadDir"

if ($SkipCompile) {
    Write-Host "SkipCompile enabled, not invoking ISCC.exe."
    return
}

$iscc = Resolve-IsccPath -ExplicitPath $InnoCompilerPath
if ([string]::IsNullOrWhiteSpace($iscc)) {
    throw "Inno Setup compiler (ISCC.exe) not found. Install Inno Setup 6 or provide -InnoCompilerPath."
}

$coreIssPath = Join-Path $repoRoot "bridge-installer.iss"
if (-not (Test-Path $coreIssPath)) {
    throw "Installer script not found: $coreIssPath"
}

$bootstrapperIssPath = Join-Path $repoRoot "bridge-bootstrapper.iss"
if (-not (Test-Path $bootstrapperIssPath)) {
    throw "Installer bootstrapper script not found: $bootstrapperIssPath"
}

Push-Location $repoRoot
try {
    & $iscc $coreIssPath
    if ($LASTEXITCODE -ne 0) {
        throw "ISCC core setup build failed with exit code $LASTEXITCODE"
    }

    & $iscc $bootstrapperIssPath
    if ($LASTEXITCODE -ne 0) {
        throw "ISCC bootstrapper setup build failed with exit code $LASTEXITCODE"
    }

    $coreInstallerPath = Join-Path $repoRoot "artifacts\installer\DmsProviderBridgeSetupCore-$Version.exe"
    if (Test-Path $coreInstallerPath) {
        Remove-Item -Path $coreInstallerPath -Force
        Write-Host "Removed internal core setup artifact: $coreInstallerPath"
    }
}
finally {
    Pop-Location
}

Write-Host "Bridge setup installer build completed."
Write-Host "Output directory: $(Join-Path $repoRoot 'artifacts\installer')"
