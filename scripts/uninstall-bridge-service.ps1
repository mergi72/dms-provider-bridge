param(
    [ValidateSet("Auto", "User", "Service")]
    [string]$RuntimeMode = "Auto",
    [string]$ServiceName = "DMSProviderBridge",
    [string]$TaskName = "DmsProviderBridgeUser",
    [string]$InstallRoot = "$env:ProgramFiles\DMS Provider",
    [string]$ConfigRoot = "$env:ProgramData\DMS Provider\config",
    [string]$NssmExePath,
    [switch]$KeepBridgeFiles,
    [switch]$KeepConfigFiles
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($currentIdentity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdministrator)) {
    throw "Uninstall requires elevated PowerShell (Run as Administrator)."
}

if (($RuntimeMode -eq "Service" -or $RuntimeMode -eq "Auto") -and -not [string]::IsNullOrWhiteSpace($NssmExePath) -and (Test-Path $NssmExePath)) {
    & $NssmExePath stop $ServiceName | Out-Null 2>&1
    & $NssmExePath remove $ServiceName confirm | Out-Null 2>&1
}

if ($RuntimeMode -eq "Service" -or $RuntimeMode -eq "Auto") {
    sc.exe stop $ServiceName | Out-Null 2>&1
    sc.exe delete $ServiceName | Out-Null 2>&1
}

if ($RuntimeMode -eq "User" -or $RuntimeMode -eq "Auto") {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
}

if (-not $KeepBridgeFiles) {
    if (Test-Path $InstallRoot) {
        Remove-Item -Path $InstallRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if (-not $KeepConfigFiles) {
    if (Test-Path $ConfigRoot) {
        Remove-Item -Path $ConfigRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Bridge runtime uninstalled."
Write-Host "Runtime mode: $RuntimeMode"
Write-Host "Service: $ServiceName"
Write-Host "Task: $TaskName"
Write-Host "Bridge files kept: $KeepBridgeFiles"
Write-Host "Config files kept: $KeepConfigFiles"
