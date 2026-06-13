param(
    [ValidateSet("User", "Service")]
    [string]$RuntimeMode = "User",
    [string]$ServiceName = "DMSProviderBridge",
    [string]$ServiceDisplayName = "DMS Provider Bridge",
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

function Write-InstallLog {
    param(
        [ValidateSet("INFO", "STEP", "OK", "WARN", "FAIL")]
        [string]$Level,
        [string]$Message
    )

    Write-Host ("[{0,-5}] {1}" -f $Level, $Message)
}

function Write-Info {
    param([string]$Message)
    Write-InstallLog -Level "INFO" -Message $Message
}

function Write-Step {
    param([string]$Message)
    Write-InstallLog -Level "STEP" -Message $Message
}

function Write-Ok {
    param([string]$Message)
    Write-InstallLog -Level "OK" -Message $Message
}

function Write-Warn {
    param([string]$Message)
    Write-InstallLog -Level "WARN" -Message $Message
}

function Test-IsAdministrator {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($currentIdentity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Wait-BridgeHealth {
    param([string]$Url, [int]$TimeoutSeconds)
    Write-Step "Health check..."
    Write-Info "Waiting for bridge startup..."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $attempt = 0
    while ((Get-Date) -lt $deadline) {
        $attempt++
        Write-Info "Health attempt $attempt/$TimeoutSeconds"
        try {
            $response = Invoke-RestMethod -Method Get -Uri $Url -TimeoutSec 5
            if ($response.status -eq "ok") {
                Write-Ok "GET $Url"
                return $response
            }
            Write-Warn "Health response status was '$($response.status)'"
        }
        catch {
            Write-Warn "Health attempt failed: $($_.Exception.Message)"
        }
        Start-Sleep -Seconds 1
    }
    throw "Bridge health check did not pass within $TimeoutSeconds s: $Url"
}

function Test-BridgeProviders {
    param([string]$BaseUrl)

    $providersUrl = "$BaseUrl/bridge/wfx/providers"
    Write-Step "Provider check..."
    try {
        $response = Invoke-RestMethod -Method Get -Uri $providersUrl -TimeoutSec 10
        if ($response.ok -ne $true) {
            throw "Provider endpoint returned ok=$($response.ok)"
        }

        $providers = @($response.data.providers)
        if ($providers.Count -eq 0) {
            throw "Provider endpoint returned no providers."
        }

        foreach ($provider in $providers) {
            Write-Ok "$provider"
        }
        Write-Info "Providers loaded: $($providers.Count)"
        return $response
    }
    catch {
        Write-InstallLog -Level "FAIL" -Message "GET $providersUrl"
        throw
    }
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

function Get-UserNameLeaf {
    param([string]$UserName)

    if ([string]::IsNullOrWhiteSpace($UserName)) {
        return ""
    }

    $normalized = $UserName.Trim()
    if ($normalized.Contains("\")) {
        return ($normalized.Split("\")[-1])
    }
    if ($normalized.Contains("@")) {
        return ($normalized.Split("@")[0])
    }
    return $normalized
}

function Resolve-ProfilePathByUserNameLeaf {
    param([string]$UserName)

    $leaf = Get-UserNameLeaf -UserName $UserName
    if ([string]::IsNullOrWhiteSpace($leaf)) {
        return $null
    }

    $profileListRoot = "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList"
    try {
        $profiles = Get-ChildItem -Path $profileListRoot -ErrorAction Stop
        foreach ($profileKey in $profiles) {
            try {
                $profile = (Get-ItemProperty -Path $profileKey.PSPath -Name ProfileImagePath -ErrorAction Stop).ProfileImagePath
                $profilePath = [Environment]::ExpandEnvironmentVariables($profile)
                if ([string]::IsNullOrWhiteSpace($profilePath)) {
                    continue
                }

                $profileLeaf = Split-Path -Leaf $profilePath
                if ($profileLeaf -ieq $leaf) {
                    return $profilePath
                }
            }
            catch {
                continue
            }
        }
    }
    catch {
        Write-Warn "Could not read Windows profile list while resolving AppData for '$UserName': $($_.Exception.Message)"
    }

    $usersPath = Join-Path $env:SystemDrive "Users\$leaf"
    if (Test-Path $usersPath) {
        return $usersPath
    }

    return $null
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

    $profilePath = Resolve-ProfilePathByUserNameLeaf -UserName $UserName
    if (-not [string]::IsNullOrWhiteSpace($profilePath)) {
        return (Join-Path $profilePath "AppData\Roaming")
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

    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline) {
        if (-not (Get-Service -Name $Name -ErrorAction SilentlyContinue)) {
            return
        }
        Start-Sleep -Milliseconds 500
    }

    throw "Service '$Name' could not be removed before reinstall."
}

function Remove-LegacyBridgeServices {
    param([string]$CurrentName)

    $legacyNames = @("DmsProviderBridge")
    foreach ($legacyName in $legacyNames) {
        if ($legacyName -ieq $CurrentName) {
            continue
        }
        if (Get-Service -Name $legacyName -ErrorAction SilentlyContinue) {
            Write-Warn "Removing legacy service: $legacyName"
            Remove-ExistingBridgeService -Name $legacyName
            Write-Ok "Legacy service removed: $legacyName"
        }
    }
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
            Write-Warn "Missing source config: $fileName"
            continue
        }

        $targetPath = Join-Path $TargetDir $fileName
        $sourceResolved = (Resolve-Path $sourcePath).Path
        $targetResolved = $null
        if (Test-Path $targetPath) {
            $targetResolved = (Resolve-Path $targetPath).Path
        }

        if ($sourceResolved -ieq $targetResolved) {
            Write-Ok "$fileName (source equals target)"
            continue
        }

        if ((Test-Path $targetPath) -and -not $Overwrite) {
            Write-Ok "$fileName (already exists)"
            continue
        }

        Copy-Item -Path $sourcePath -Destination $targetPath -Force:$Overwrite
        Write-Ok $fileName
        $copied++
    }

    return $copied
}

if (-not (Test-IsAdministrator)) {
    throw "Install requires elevated PowerShell (Run as Administrator)."
}

function Invoke-Nssm {
    param(
        [string[]]$Arguments,
        [switch]$IgnoreFailure
    )

    $commandText = "$NssmExePath $($Arguments -join ' ')"
    Write-Info "NSSM: $commandText"
    $output = & $NssmExePath @Arguments 2>&1
    $exitCode = $LASTEXITCODE

    foreach ($line in @($output)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$line)) {
            Write-Info "NSSM output: $line"
        }
    }

    if ($exitCode -ne 0 -and -not $IgnoreFailure) {
        throw "NSSM command failed with exit code $exitCode`: $commandText"
    }

    if ($exitCode -ne 0) {
        Write-Warn "NSSM command ignored exit code $exitCode`: $commandText"
    }
}

Write-Info "Starting installation..."
Write-Info "Runtime mode: $RuntimeMode"
Write-Info "Install root: $InstallRoot"

if ($RuntimeMode -eq "Service") {
    Write-Step "Checking NSSM..."
    if ([string]::IsNullOrWhiteSpace($NssmExePath) -or -not (Test-Path $NssmExePath)) {
        throw "NSSM executable not found. Provide -NssmExePath."
    }
    Write-Ok "NSSM: $NssmExePath"
}

# Resolve bridge exe: explicit param, then next to this script, then dist/ in repo
if ([string]::IsNullOrWhiteSpace($BridgeExePath)) {
    Write-Step "Resolving bridge executable..."
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
Write-Ok "Bridge executable: $BridgeExePath"

# Resolve config dir: explicit param, then config/ next to this script, then config/ in repo
if ([string]::IsNullOrWhiteSpace($BridgeConfigDirPath)) {
    Write-Step "Resolving config payload..."
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $candidates = @(
        (Join-Path $scriptDir "config"),
        (Join-Path $scriptDir "..\config")
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $BridgeConfigDirPath = (Resolve-Path $c).Path; break }
    }
}

if ([string]::IsNullOrWhiteSpace($UserConfigSourceDirPath)) {
    Write-Step "Resolving user config payload..."
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $candidates = @(
        (Join-Path $scriptDir "user-config"),
        (Join-Path $scriptDir "..\user-config")
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $UserConfigSourceDirPath = (Resolve-Path $c).Path; break }
    }
}

if ($RuntimeMode -eq "User" -and [string]::IsNullOrWhiteSpace($RunAsUser)) {
    $RunAsUser = Resolve-CurrentUserName
}

$userConfigOwner = $RunAsUser
if ([string]::IsNullOrWhiteSpace($userConfigOwner)) {
    $userConfigOwner = Resolve-CurrentUserName
}

if ([string]::IsNullOrWhiteSpace($ConfigRoot)) {
    $userRoamingAppData = Resolve-UserRoamingAppDataPath -UserName $userConfigOwner
    if (-not [string]::IsNullOrWhiteSpace($userRoamingAppData)) {
        $ConfigRoot = Join-Path $userRoamingAppData "DMS Provider\config"
    }
    elseif ($RuntimeMode -eq "User") {
        if ([string]::IsNullOrWhiteSpace($userRoamingAppData)) {
            throw "RuntimeMode=User could not resolve roaming AppData for '$userConfigOwner'. Provide -ConfigRoot explicitly."
        }
    }
    else {
        Write-Warn "Could not resolve user AppData for '$userConfigOwner'. Falling back to ProgramData user config root."
        $ConfigRoot = Join-Path $env:ProgramData "DMS Provider\config"
    }
}

$bridgeExeTargetPath = Join-Path $InstallRoot "dms-provider-bridge.exe"
$machineConfigRoot = Join-Path $env:ProgramData "DMS Provider\config"
$userConfigRoot = $ConfigRoot
$bridgeLogs = Join-Path $InstallRoot "logs"
$stdoutLog = Join-Path $bridgeLogs "bridge-stdout.log"
$stderrLog = Join-Path $bridgeLogs "bridge-stderr.log"

Write-Step "Creating application directories..."
New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
Write-Ok $InstallRoot
New-Item -ItemType Directory -Path $bridgeLogs -Force | Out-Null
Write-Ok $bridgeLogs

Write-Step "Creating ProgramData config..."
New-Item -ItemType Directory -Path $machineConfigRoot -Force | Out-Null
Write-Ok $machineConfigRoot

Write-Step "Creating AppData config..."
Write-Info "AppData config owner: $userConfigOwner"
New-Item -ItemType Directory -Path $userConfigRoot -Force | Out-Null
Write-Ok $userConfigRoot

Write-Step "Copying bridge executable..."
Copy-Item -Path $BridgeExePath -Destination $bridgeExeTargetPath -Force
Write-Ok $bridgeExeTargetPath

$bridgeInternalSource = Join-Path (Split-Path -Parent $BridgeExePath) "_internal"
if (Test-Path $bridgeInternalSource) {
    $bridgeInternalTarget = Join-Path $InstallRoot "_internal"
    Write-Step "Copying bridge runtime directory..."
    if (Test-Path $bridgeInternalTarget) {
        Remove-Item -Path $bridgeInternalTarget -Recurse -Force
    }
    Copy-Item -Path $bridgeInternalSource -Destination $bridgeInternalTarget -Recurse -Force
    Write-Ok $bridgeInternalTarget
}

$machineConfigNames = @(
    "bridge.json",
    "alfresco.json",
    "edocat.json"
)

$userConfigNames = @(
    "alfresco.local.json",
    "edocat.local.json"
)

Write-Step "Copying default configuration..."
$machineCopied = Copy-ConfigFilesByName -SourceDir $BridgeConfigDirPath -TargetDir $machineConfigRoot -FileNames $machineConfigNames -Overwrite
if ($machineCopied -gt 0) {
    Write-Ok "Machine bridge config templates copied from: $BridgeConfigDirPath"
}
elseif (-not [string]::IsNullOrWhiteSpace($BridgeConfigDirPath) -and (Test-Path $BridgeConfigDirPath)) {
    Write-Ok "Machine bridge config templates already present or source equals target: $BridgeConfigDirPath"
}
else {
    Write-Warn "Machine bridge config directory not provided or not found. Expected target: $machineConfigRoot"
}

$userCopied = Copy-ConfigFilesByName -SourceDir $UserConfigSourceDirPath -TargetDir $userConfigRoot -FileNames $userConfigNames
if ($userCopied -gt 0) {
    Write-Ok "User bridge config seeded from: $UserConfigSourceDirPath"
}
elseif (-not [string]::IsNullOrWhiteSpace($UserConfigSourceDirPath) -and (Test-Path $UserConfigSourceDirPath)) {
    Write-Ok "User bridge config already present or no seed file found: $UserConfigSourceDirPath"
}

$bridgeBaseUrl = Resolve-BridgeBaseUrl -Url $HealthUrl

if ($RuntimeMode -eq "User") {
    # User mode is for interactive desktop usage (for example Total Commander).
    Write-Step "Removing existing Windows service if present..."
    Remove-ExistingBridgeService -Name $ServiceName
    Remove-LegacyBridgeServices -CurrentName $ServiceName
    Write-Ok "Service cleanup: $ServiceName"
    Write-Step "Registering scheduled task..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null

    $launcherPath = Join-Path $InstallRoot "start-bridge-usermode.ps1"
    Write-Step "Writing user mode launcher..."
    Write-UserModeLauncher -Path $launcherPath -BridgeExe $bridgeExeTargetPath -MachineConfigDir $machineConfigRoot -UserConfigDir $userConfigRoot -WorkingDir $InstallRoot
    Write-Ok $launcherPath

    $taskAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcherPath`""
    $taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User $RunAsUser
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId $RunAsUser -LogonType InteractiveToken -RunLevel Highest

    Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $taskTrigger -Principal $taskPrincipal -Force | Out-Null
    Write-Ok "Scheduled task registered: $TaskName"

    if ($StartImmediately) {
        Write-Step "Starting scheduled task..."
        Start-ScheduledTask -TaskName $TaskName
        Write-Ok "Scheduled task started: $TaskName"
        Wait-BridgeHealth -Url $HealthUrl -TimeoutSeconds $HealthTimeoutSeconds | Out-Null
        Test-BridgeProviders -BaseUrl $bridgeBaseUrl | Out-Null
    }

    Write-Info "Installation completed successfully."
    Write-Info "Task: $TaskName"
    Write-Info "Run as user: $RunAsUser"
    Write-Info "Health: $HealthUrl"
    Write-Info "Swagger UI: $bridgeBaseUrl/docs"
    Write-Info "OpenAPI: $bridgeBaseUrl/openapi.json"
    Write-Info "Logs: $bridgeLogs"
    return
}

Write-Step "Registering Windows service..."
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
Invoke-Nssm -Arguments @("stop", $ServiceName) -IgnoreFailure
Invoke-Nssm -Arguments @("remove", $ServiceName, "confirm") -IgnoreFailure
Remove-LegacyBridgeServices -CurrentName $ServiceName

Invoke-Nssm -Arguments @("install", $ServiceName, $bridgeExeTargetPath)
Invoke-Nssm -Arguments @("set", $ServiceName, "AppDirectory", $InstallRoot)
Invoke-Nssm -Arguments @("set", $ServiceName, "DisplayName", $ServiceDisplayName)
Invoke-Nssm -Arguments @("set", $ServiceName, "AppStdout", $stdoutLog)
Invoke-Nssm -Arguments @("set", $ServiceName, "AppStderr", $stderrLog)
Invoke-Nssm -Arguments @("set", $ServiceName, "AppEnvironmentExtra", "DMS_PROVIDER_MACHINE_CONFIG_DIR=$machineConfigRoot", "DMS_PROVIDER_USER_CONFIG_DIR=$userConfigRoot", "DMS_PROVIDER_LOG_DIR=$bridgeLogs")
Write-Ok "$ServiceDisplayName registered"

if ($ServiceAccount -eq "LocalSystem") {
    Invoke-Nssm -Arguments @("set", $ServiceName, "ObjectName", "LocalSystem")
}
else {
    $resolvedServiceUser = Resolve-ServiceUserName -Mode $ServiceAccount -ExplicitUserName $ServiceUserName
    if ([string]::IsNullOrWhiteSpace($ServicePassword)) {
        throw "ServiceAccount=$ServiceAccount requires -ServicePassword."
    }
    Write-Info "Service account: $resolvedServiceUser"
    Invoke-Nssm -Arguments @("set", $ServiceName, "ObjectName", $resolvedServiceUser, $ServicePassword)
}

$registeredService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($null -eq $registeredService) {
    throw "Service '$ServiceName' was not found after NSSM registration."
}
Write-Ok "Service exists: $ServiceName"

Invoke-Nssm -Arguments @("set", $ServiceName, "Start", "SERVICE_AUTO_START")
Write-Step "Starting service..."
Invoke-Nssm -Arguments @("start", $ServiceName)
Write-Ok "Service start requested: $ServiceName"
Wait-BridgeHealth -Url $HealthUrl -TimeoutSeconds $HealthTimeoutSeconds | Out-Null
Test-BridgeProviders -BaseUrl $bridgeBaseUrl | Out-Null

Write-Info "Installation completed successfully."
Write-Info "Service: $ServiceName"
Write-Info "Install root: $InstallRoot"
Write-Info "Machine config: $machineConfigRoot"
Write-Info "Bridge exe: $bridgeExeTargetPath"
Write-Info "Health: $HealthUrl"
Write-Info "Swagger UI: $bridgeBaseUrl/docs"
Write-Info "OpenAPI: $bridgeBaseUrl/openapi.json"
Write-Info "Service user: $(if ($ServiceAccount -eq 'LocalSystem') { 'LocalSystem' } elseif ($ServiceAccount -eq 'CurrentUser') { Resolve-ServiceUserName -Mode 'CurrentUser' -ExplicitUserName '' } else { $ServiceUserName })"
Write-Info "Logs: $bridgeLogs"
