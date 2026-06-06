param(
    [string]$Version = "v0.2.3-alpha",
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

if (Test-Path $payloadDir) {
    Remove-Item -Path $payloadDir -Recurse -Force
}

New-Item -ItemType Directory -Path $payloadDir -Force | Out-Null
New-Item -ItemType Directory -Path $configPayloadDir -Force | Out-Null

Copy-Item -Path $BridgeExePath -Destination (Join-Path $payloadDir "dms-provider-bridge.exe") -Force
Copy-Item -Path $resolvedNssm -Destination (Join-Path $payloadDir "nssm.exe") -Force
Copy-Item -Path (Join-Path $repoRoot "scripts\install-bridge-service.ps1") -Destination (Join-Path $payloadDir "install-bridge-service.ps1") -Force
Copy-Item -Path (Join-Path $repoRoot "scripts\uninstall-bridge-service.ps1") -Destination (Join-Path $payloadDir "uninstall-bridge-service.ps1") -Force
Copy-Item -Path (Join-Path $repoRoot "config\*.json") -Destination $configPayloadDir -Force

Write-Host "Installer payload prepared: $payloadDir"

if ($SkipCompile) {
    Write-Host "SkipCompile enabled, not invoking ISCC.exe."
    return
}

$iscc = Resolve-IsccPath -ExplicitPath $InnoCompilerPath
if ([string]::IsNullOrWhiteSpace($iscc)) {
    throw "Inno Setup compiler (ISCC.exe) not found. Install Inno Setup 6 or provide -InnoCompilerPath."
}

$issPath = Join-Path $repoRoot "bridge-installer.iss"
if (-not (Test-Path $issPath)) {
    throw "Installer script not found: $issPath"
}

Push-Location $repoRoot
try {
    & $iscc $issPath
    if ($LASTEXITCODE -ne 0) {
        throw "ISCC build failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Host "Bridge setup installer build completed."
Write-Host "Output directory: $(Join-Path $repoRoot 'artifacts\installer')"
