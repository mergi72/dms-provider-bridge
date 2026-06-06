param(
    [ValidateSet("User", "Service")]
    [string]$RuntimeMode = "User",
    [string]$ServiceName = "DmsProviderBridge",
    [string]$TaskName = "DmsProviderBridgeUser",
    [string]$RunAsUser,
    [string]$InstallRoot = "$env:ProgramFiles\DMS Provider",
    [string]$ConfigRoot = "$env:ProgramData\DMSProvider\config",
    [string]$BridgeExePath,
    [string]$BridgeConfigDirPath,
    [string]$NssmExePath,
    [ValidateSet("LocalSystem", "CurrentUser", "CustomUser")]
    [string]$ServiceAccount = "LocalSystem",
    [string]$ServiceUserName,
    [string]$ServicePassword,
    [switch]$StartImmediately,
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

function Resolve-CurrentUserName {
    $envUser = $env:USERNAME
    $envDomain = $env:USERDOMAIN
    if ([string]::IsNullOrWhiteSpace($envUser)) {
        throw "Could not resolve current user from environment."
    }
    return if ([string]::IsNullOrWhiteSpace($envDomain)) { $envUser } else { "$envDomain\$envUser" }
}

function Write-UserModeLauncher {
    param(
        [string]$Path,
        [string]$BridgeExe,
        [string]$ConfigDir,
        [string]$WorkingDir
    )

    $launcher = @"

$env:DMS_PROVIDER_CONFIG_DIR = '$ConfigDir'
Start-Process -FilePath '$BridgeExe' -WorkingDirectory '$WorkingDir' -WindowStyle Hidden
"@

    Set-Content -Path $Path -Value $launcher -Encoding ASCII
}

function Remove-ExistingBridgeService {
    param([string]$Name)

    $existing = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if ($null -eq $existing) {
        return
    }

    sc.exe stop $Name | Out-Null 2>&1
    sc.exe delete $Name | Out-Null 2>&1
}

if (-not (Test-IsAdministrator)) {
    throw "Install requires elevated PowerShell (Run as Administrator)."
}

if ($RuntimeMode -eq "Service") {
    if ([string]::IsNullOrWhiteSpace($NssmExePath) -or -not (Test-Path $NssmExePath)) {
        throw "NSSM executable not found. Provide -NssmExePath."
    }
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
    Get-ChildItem -Path $BridgeConfigDirPath -Filter "*.json" -File |
        Where-Object { $_.Name -notlike "*.local.json" } |
        ForEach-Object {
            Copy-Item -Path $_.FullName -Destination (Join-Path $bridgeConfigTargetDir $_.Name) -Force
        }
    Write-Host "Bridge config copied from: $BridgeConfigDirPath"
}
else {
    Write-Host "Bridge config directory not provided or not found, skipping config copy."
    Write-Host "Place config files manually into: $bridgeConfigTargetDir"
}

$bridgeBaseUrl = Resolve-BridgeBaseUrl -Url $HealthUrl

if ($RuntimeMode -eq "User") {
    if ([string]::IsNullOrWhiteSpace($RunAsUser)) {
        $RunAsUser = Resolve-CurrentUserName
    }

    # User mode is for interactive desktop usage (for example Total Commander).
    Remove-ExistingBridgeService -Name $ServiceName
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null

    $launcherPath = Join-Path $InstallRoot "start-bridge-usermode.ps1"
    Write-UserModeLauncher -Path $launcherPath -BridgeExe $bridgeExeTargetPath -ConfigDir $bridgeConfigTargetDir -WorkingDir $InstallRoot

    $taskAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcherPath`""
    $taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User $RunAsUser
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId $RunAsUser -LogonType InteractiveToken -RunLevel Highest

    Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $taskTrigger -Principal $taskPrincipal -Force | Out-Null

    if ($StartImmediately) {
        Start-ScheduledTask -TaskName $TaskName
        Wait-BridgeHealth -Url $HealthUrl -TimeoutSeconds $HealthTimeoutSeconds
    }

    Write-Host ""
    Write-Host "Bridge started successfully."
    Write-Host "Runtime mode:    User"
    Write-Host "Task:            $TaskName"
    Write-Host "Run as user:     $RunAsUser"
    Write-Host "Install root:    $InstallRoot"
    Write-Host "Config root:     $bridgeConfigTargetDir"
    Write-Host "Bridge exe:      $bridgeExeTargetPath"
    Write-Host "Health:          $HealthUrl"
    Write-Host "Swagger UI:      $bridgeBaseUrl/docs"
    Write-Host "OpenAPI:         $bridgeBaseUrl/openapi.json"
    Write-Host "Logs:            $bridgeLogs"
    return
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
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

Write-Host ""
Write-Host "Bridge started successfully."
Write-Host "Runtime mode:    Service"
Write-Host "Service:        $ServiceName"
Write-Host "Install root:   $InstallRoot"
Write-Host "Config root:    $bridgeConfigTargetDir"
Write-Host "Bridge exe:     $bridgeExeTargetPath"
Write-Host "Health:         $HealthUrl"
Write-Host "Swagger UI:     $bridgeBaseUrl/docs"
Write-Host "OpenAPI:        $bridgeBaseUrl/openapi.json"
Write-Host "Service user:   $(if ($ServiceAccount -eq 'LocalSystem') { 'LocalSystem' } elseif ($ServiceAccount -eq 'CurrentUser') { Resolve-ServiceUserName -Mode 'CurrentUser' -ExplicitUserName '' } else { $ServiceUserName })"
Write-Host "Logs:           $bridgeLogs"
