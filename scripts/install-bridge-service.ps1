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
    [string]$UserConfigSourceDirPath,
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
        [string]$MachineConfigDir,
        [string]$UserConfigDir,
        [string]$WorkingDir
    )

    $launcher = @"

$env:DMS_PROVIDER_MACHINE_CONFIG_DIR = '$MachineConfigDir'
$env:DMS_PROVIDER_USER_CONFIG_DIR = '$UserConfigDir'
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


function Copy-ConfigFilesByName {
    param(
        [string]$SourceDir,
        [string]$TargetDir,
        [string[]]$FileNames,
        [switch]$Overwrite
    )

    if ([string]::IsNullOrWhiteSpace($SourceDir) -or -not (Test-Path $SourceDir)) {
        return 0
    }

    $copied = 0
    foreach ($fileName in $FileNames) {
        $sourcePath = Join-Path $SourceDir $fileName
        if (-not (Test-Path $sourcePath)) {
            continue
        }

        $targetPath = Join-Path $TargetDir $fileName
        $sourceResolved = (Resolve-Path $sourcePath).Path
        $targetResolved = $null
        if (Test-Path $targetPath) {
            $targetResolved = (Resolve-Path $targetPath).Path
        }

        if ($sourceResolved -ieq $targetResolved) {
            continue
        }

        if ((Test-Path $targetPath) -and -not $Overwrite) {
            continue
        }

        Copy-Item -Path $sourcePath -Destination $targetPath -Force:$Overwrite
        $copied++
    }

    return $copied
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

if ($RuntimeMode -eq "User" -and [string]::IsNullOrWhiteSpace($RunAsUser)) {
    $RunAsUser = Resolve-CurrentUserName
}

if ([string]::IsNullOrWhiteSpace($ConfigRoot)) {
    if ($RuntimeMode -eq "User") {
        $userRoamingAppData = Resolve-UserRoamingAppDataPath -UserName $RunAsUser
        if ([string]::IsNullOrWhiteSpace($userRoamingAppData)) {
            throw "RuntimeMode=User could not resolve roaming AppData for '$RunAsUser'. Provide -ConfigRoot explicitly."
        }
        $ConfigRoot = Join-Path $userRoamingAppData "DMS Provider\config"
    }
    else {
        $ConfigRoot = Join-Path $env:ProgramData "DMS Provider\config"
    }
}

$bridgeExeTargetPath = Join-Path $InstallRoot "dms-provider-bridge.exe"
$machineConfigRoot = Join-Path $env:ProgramData "DMS Provider\config"
$userConfigRoot = $ConfigRoot
$bridgeLogs = Join-Path $InstallRoot "logs"
$stdoutLog = Join-Path $bridgeLogs "bridge-stdout.log"
$stderrLog = Join-Path $bridgeLogs "bridge-stderr.log"

New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
New-Item -ItemType Directory -Path $bridgeLogs -Force | Out-Null
New-Item -ItemType Directory -Path $machineConfigRoot -Force | Out-Null
New-Item -ItemType Directory -Path $userConfigRoot -Force | Out-Null

Copy-Item -Path $BridgeExePath -Destination $bridgeExeTargetPath -Force

$machineConfigNames = @(
    "bridge.json",
    "alfresco.json",
    "edocat.json",
    "fso.json"
)

$userConfigNames = @()

$machineCopied = Copy-ConfigFilesByName -SourceDir $BridgeConfigDirPath -TargetDir $machineConfigRoot -FileNames $machineConfigNames -Overwrite
if ($machineCopied -gt 0) {
    Write-Host "Machine bridge config templates copied from: $BridgeConfigDirPath"
}
elseif (-not [string]::IsNullOrWhiteSpace($BridgeConfigDirPath) -and (Test-Path $BridgeConfigDirPath)) {
    Write-Host "Machine bridge config templates already present or source equals target: $BridgeConfigDirPath"
}
else {
    Write-Host "Machine bridge config directory not provided or not found. Expected target: $machineConfigRoot"
}

if ($RuntimeMode -eq "User") {
    $userCopied = Copy-ConfigFilesByName -SourceDir $UserConfigSourceDirPath -TargetDir $userConfigRoot -FileNames $userConfigNames
    if ($userCopied -gt 0) {
        Write-Host "User bridge config seeded from: $UserConfigSourceDirPath"
    }
    elseif (-not [string]::IsNullOrWhiteSpace($UserConfigSourceDirPath) -and (Test-Path $UserConfigSourceDirPath)) {
        Write-Host "User bridge config already present or no seed file found: $UserConfigSourceDirPath"
    }
}

$bridgeBaseUrl = Resolve-BridgeBaseUrl -Url $HealthUrl

if ($RuntimeMode -eq "User") {
    # User mode is for interactive desktop usage (for example Total Commander).
    Remove-ExistingBridgeService -Name $ServiceName
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null

    $launcherPath = Join-Path $InstallRoot "start-bridge-usermode.ps1"
    Write-UserModeLauncher -Path $launcherPath -BridgeExe $bridgeExeTargetPath -MachineConfigDir $machineConfigRoot -UserConfigDir $userConfigRoot -WorkingDir $InstallRoot

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
    Write-Host "Config root:     $userConfigRoot"
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
& $NssmExePath set $ServiceName AppEnvironmentExtra "DMS_PROVIDER_MACHINE_CONFIG_DIR=$machineConfigRoot"

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
Write-Host "Config root:    $machineConfigRoot"
Write-Host "Bridge exe:     $bridgeExeTargetPath"
Write-Host "Health:         $HealthUrl"
Write-Host "Swagger UI:     $bridgeBaseUrl/docs"
Write-Host "OpenAPI:        $bridgeBaseUrl/openapi.json"
Write-Host "Service user:   $(if ($ServiceAccount -eq 'LocalSystem') { 'LocalSystem' } elseif ($ServiceAccount -eq 'CurrentUser') { Resolve-ServiceUserName -Mode 'CurrentUser' -ExplicitUserName '' } else { $ServiceUserName })"
Write-Host "Logs:           $bridgeLogs"
