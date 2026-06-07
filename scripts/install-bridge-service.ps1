param(
    [ValidateSet("User", "Service")]
    [string]$RuntimeMode = "User",
    [string]$ServiceName = "DmsProviderBridge",
    [string]$TaskName = "DmsProviderBridgeUser",
    [string]$RunAsUser,
    [string]$InstallRoot = "$env:ProgramFiles\DMS Provider",
    [string]$ConfigRoot,
    [string]$BridgeExePath,
    [string]$BridgeConfigDirPath,
    [string]$UserConfigTemplatePath,
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

function Resolve-UserRoamingAppDataPath {
    param([string]$UserName)

    if ([string]::IsNullOrWhiteSpace($UserName)) {
        if (-not [string]::IsNullOrWhiteSpace($env:APPDATA)) {
            return $env:APPDATA
        }
        return $null
    }

    try {
        $sid = ([System.Security.Principal.NTAccount]::new($UserName)).Translate([System.Security.Principal.SecurityIdentifier]).Value
        $profileKey = "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\$sid"
        $profile = (Get-ItemProperty -Path $profileKey -Name ProfileImagePath -ErrorAction Stop).ProfileImagePath
        $profilePath = [Environment]::ExpandEnvironmentVariables($profile)
        if (-not [string]::IsNullOrWhiteSpace($profilePath)) {
            return (Join-Path $profilePath "AppData\Roaming")
        }
    }
    catch {
        if ($UserName -ieq (Resolve-CurrentUserName) -and -not [string]::IsNullOrWhiteSpace($env:APPDATA)) {
            return $env:APPDATA
        }
    }

    return $null
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

function Resolve-UserConfigTemplate {
    param(
        [string]$ExplicitPath,
        [string]$ScriptDir,
        [string]$MachineConfigDir
    )

    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
        $candidates += $ExplicitPath
    }

    if (-not [string]::IsNullOrWhiteSpace($ScriptDir)) {
        $candidates += (Join-Path $ScriptDir "config\user.json")
        $candidates += (Join-Path $ScriptDir "..\config\user.json")
    }

    if (-not [string]::IsNullOrWhiteSpace($MachineConfigDir)) {
        $candidates += (Join-Path $MachineConfigDir "user.json")
    }

    foreach ($candidate in $candidates) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path $candidate)) {
            return (Resolve-Path $candidate).Path
        }
    }

    return $null
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

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($RuntimeMode -eq "User" -and [string]::IsNullOrWhiteSpace($RunAsUser)) {
    $RunAsUser = Resolve-CurrentUserName
}

if ([string]::IsNullOrWhiteSpace($ConfigRoot)) {
    if ($RuntimeMode -eq "User") {
        $userRoamingAppData = Resolve-UserRoamingAppDataPath -UserName $RunAsUser
        if ([string]::IsNullOrWhiteSpace($userRoamingAppData)) {
            throw "RuntimeMode=User could not resolve roaming AppData for '$RunAsUser'. Provide -ConfigRoot explicitly."
        }
        $ConfigRoot = Join-Path $userRoamingAppData "DMS Bridge\config"
    }
    else {
        $ConfigRoot = Join-Path $env:ProgramData "DMSProvider\config"
    }
}

$bridgeExeTargetPath = Join-Path $InstallRoot "dms-provider-bridge.exe"
$bridgeConfigTargetDir = $ConfigRoot
$machineConfigTargetDir = Join-Path $env:ProgramData "DMSProvider\config"
$bridgeLogs = Join-Path $InstallRoot "logs"
$stdoutLog = Join-Path $bridgeLogs "bridge-stdout.log"
$stderrLog = Join-Path $bridgeLogs "bridge-stderr.log"
$allowedMachineConfigFiles = @(
    "default.json",
    "alfresco.json",
    "edocat.json",
    "fso.json"
)

New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
New-Item -ItemType Directory -Path $bridgeLogs -Force | Out-Null
New-Item -ItemType Directory -Path $bridgeConfigTargetDir -Force | Out-Null
New-Item -ItemType Directory -Path $machineConfigTargetDir -Force | Out-Null

Copy-Item -Path $BridgeExePath -Destination $bridgeExeTargetPath -Force

if (-not [string]::IsNullOrWhiteSpace($BridgeConfigDirPath) -and (Test-Path $BridgeConfigDirPath)) {
    foreach ($configName in $allowedMachineConfigFiles) {
        $sourcePath = Join-Path $BridgeConfigDirPath $configName
        if (-not (Test-Path $sourcePath)) {
            continue
        }

        $targetPath = if ($RuntimeMode -eq "Service") {
            Join-Path $bridgeConfigTargetDir $configName
        }
        else {
            Join-Path $machineConfigTargetDir $configName
        }

        if ((Resolve-Path $sourcePath).Path -ne $targetPath) {
            Copy-Item -Path $sourcePath -Destination $targetPath -Force
        }
    }
    Write-Host "Bridge machine config synchronized from: $BridgeConfigDirPath"
}
else {
    Write-Host "Bridge config directory not provided or not found, skipping config copy."
    Write-Host "Place machine config files manually into: $machineConfigTargetDir"
}

$invalidMachineUserConfig = Join-Path $machineConfigTargetDir "user.json"
if (Test-Path $invalidMachineUserConfig) {
    Remove-Item -Path $invalidMachineUserConfig -Force -ErrorAction SilentlyContinue
    Write-Host "Removed invalid machine-scoped user config: $invalidMachineUserConfig"
}

if ($RuntimeMode -eq "User") {
    $resolvedUserConfigTemplate = Resolve-UserConfigTemplate -ExplicitPath $UserConfigTemplatePath -ScriptDir $scriptDir -MachineConfigDir $BridgeConfigDirPath
    $userConfigTarget = Join-Path $bridgeConfigTargetDir "user.json"
    if (-not (Test-Path $userConfigTarget) -and -not [string]::IsNullOrWhiteSpace($resolvedUserConfigTemplate)) {
        Copy-Item -Path $resolvedUserConfigTemplate -Destination $userConfigTarget
    }
}

$bridgeBaseUrl = Resolve-BridgeBaseUrl -Url $HealthUrl

if ($RuntimeMode -eq "User") {
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
