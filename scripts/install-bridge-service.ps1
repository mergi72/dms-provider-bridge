param(
    [string]$ServiceName = "DmsProviderBridge",
    [string]$InstallRoot = "$env:ProgramFiles\DMS Provider",
    [string]$ConfigRoot = "$env:ProgramData\DMSProvider\config",
    [string]$BridgeExePath,
    [string]$BridgeConfigDirPath,
    [string]$NssmExePath,
    [ValidateSet("LocalSystem", "CurrentUser", "CustomUser")]
    [string]$ServiceAccount = "LocalSystem",
    [string]$ServiceUserName,
    [string]$ServicePassword,
    [int]$HealthTimeoutSeconds = 30,
    [string]$HealthUrl = "http://127.0.0.1:8765/health"
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($currentIdentity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Wait-BridgeHealth {
    param([string]$Url, [int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Method Get -Uri $Url -TimeoutSec 5
            if ($response.status -eq "ok") {
                Write-Host "Bridge health check passed: $Url"
                return
            }
        }
        catch { }
        Start-Sleep -Seconds 1
    }
    throw "Bridge health check did not pass within $TimeoutSeconds s: $Url"
}

function Resolve-BridgeBaseUrl {
    param([string]$Url)

    $uri = [Uri]$Url
    $builder = [UriBuilder]::new($uri)
    $builder.Path = ""
    $builder.Query = ""
    $builder.Fragment = ""
    return $builder.Uri.AbsoluteUri.TrimEnd('/')
}

function Resolve-ServiceUserName {
    param([string]$Mode, [string]$ExplicitUserName)
    if ($Mode -eq "CustomUser") {
        if ([string]::IsNullOrWhiteSpace($ExplicitUserName)) {
            throw "ServiceAccount=CustomUser requires -ServiceUserName."
        }
        return $ExplicitUserName
    }
    if ($Mode -eq "CurrentUser") {
        $envUser = $env:USERNAME
        $envDomain = $env:USERDOMAIN
        if ([string]::IsNullOrWhiteSpace($envUser)) {
            throw "ServiceAccount=CurrentUser could not resolve USERNAME from environment."
        }
        return if ([string]::IsNullOrWhiteSpace($envDomain)) { $envUser } else { "$envDomain\$envUser" }
    }
    return ""
}

if (-not (Test-IsAdministrator)) {
    throw "Install requires elevated PowerShell (Run as Administrator)."
}

if ([string]::IsNullOrWhiteSpace($NssmExePath) -or -not (Test-Path $NssmExePath)) {
    throw "NSSM executable not found. Provide -NssmExePath."
}

# Resolve bridge exe: explicit param, then next to this script, then dist/ in repo
if ([string]::IsNullOrWhiteSpace($BridgeExePath)) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $candidates = @(
        (Join-Path $scriptDir "dms-provider-bridge.exe"),
        (Join-Path $scriptDir "..\dist\dms-provider-bridge.exe")
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $BridgeExePath = (Resolve-Path $c).Path; break }
    }
}

if ([string]::IsNullOrWhiteSpace($BridgeExePath) -or -not (Test-Path $BridgeExePath)) {
    throw "Bridge executable not found. Provide -BridgeExePath."
}

# Resolve config dir: explicit param, then config/ next to this script, then config/ in repo
if ([string]::IsNullOrWhiteSpace($BridgeConfigDirPath)) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $candidates = @(
        (Join-Path $scriptDir "config"),
        (Join-Path $scriptDir "..\config")
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $BridgeConfigDirPath = (Resolve-Path $c).Path; break }
    }
}

$bridgeExeTargetPath = Join-Path $InstallRoot "dms-provider-bridge.exe"
$bridgeConfigTargetDir = $ConfigRoot
$bridgeLogs = Join-Path $InstallRoot "logs"
$stdoutLog = Join-Path $bridgeLogs "bridge-stdout.log"
$stderrLog = Join-Path $bridgeLogs "bridge-stderr.log"

New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
New-Item -ItemType Directory -Path $bridgeLogs -Force | Out-Null
New-Item -ItemType Directory -Path $bridgeConfigTargetDir -Force | Out-Null

Copy-Item -Path $BridgeExePath -Destination $bridgeExeTargetPath -Force

if (-not [string]::IsNullOrWhiteSpace($BridgeConfigDirPath) -and (Test-Path $BridgeConfigDirPath)) {
    Copy-Item -Path (Join-Path $BridgeConfigDirPath "*.json") -Destination $bridgeConfigTargetDir -Force
    Write-Host "Bridge config copied from: $BridgeConfigDirPath"
}
else {
    Write-Host "Bridge config directory not provided or not found, skipping config copy."
    Write-Host "Place config files manually into: $bridgeConfigTargetDir"
}

& $NssmExePath stop $ServiceName | Out-Null 2>&1
& $NssmExePath remove $ServiceName confirm | Out-Null 2>&1

& $NssmExePath install $ServiceName $bridgeExeTargetPath
& $NssmExePath set $ServiceName AppDirectory $InstallRoot
& $NssmExePath set $ServiceName AppStdout $stdoutLog
& $NssmExePath set $ServiceName AppStderr $stderrLog
& $NssmExePath set $ServiceName AppEnvironmentExtra "DMS_PROVIDER_CONFIG_DIR=$bridgeConfigTargetDir"

if ($ServiceAccount -eq "LocalSystem") {
    & $NssmExePath set $ServiceName ObjectName LocalSystem
}
else {
    $resolvedServiceUser = Resolve-ServiceUserName -Mode $ServiceAccount -ExplicitUserName $ServiceUserName
    if ([string]::IsNullOrWhiteSpace($ServicePassword)) {
        throw "ServiceAccount=$ServiceAccount requires -ServicePassword."
    }
    & $NssmExePath set $ServiceName ObjectName $resolvedServiceUser $ServicePassword
}

& $NssmExePath set $ServiceName Start SERVICE_AUTO_START
& $NssmExePath start $ServiceName
Wait-BridgeHealth -Url $HealthUrl -TimeoutSeconds $HealthTimeoutSeconds

$bridgeBaseUrl = Resolve-BridgeBaseUrl -Url $HealthUrl

Write-Host ""
Write-Host "Bridge started successfully."
Write-Host "Service:        $ServiceName"
Write-Host "Install root:   $InstallRoot"
Write-Host "Config root:    $bridgeConfigTargetDir"
Write-Host "Bridge exe:     $bridgeExeTargetPath"
Write-Host "Health:         $HealthUrl"
Write-Host "Swagger UI:     $bridgeBaseUrl/docs"
Write-Host "OpenAPI:        $bridgeBaseUrl/openapi.json"
Write-Host "Service user:   $(if ($ServiceAccount -eq 'LocalSystem') { 'LocalSystem' } elseif ($ServiceAccount -eq 'CurrentUser') { Resolve-ServiceUserName -Mode 'CurrentUser' -ExplicitUserName '' } else { $ServiceUserName })"
Write-Host "Logs:           $bridgeLogs"
