[Setup]
AppId={{CFD8BDCC-B59A-4CB3-93D7-530BB5283773}
AppName=DMS Provider Bridge Setup
AppVersion=0.4.2
AppPublisher=mergi72
DefaultDirName={autopf}\DMS Provider
DefaultGroupName=DMS Provider Bridge
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=artifacts\installer
OutputBaseFilename=DmsProviderBridgeSetup-v0.4.2
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "artifacts\bridge-installer-payload\dms-provider-bridge.exe"; DestDir: "{tmp}\dms-provider-payload\app"; Flags: ignoreversion deleteafterinstall
Source: "artifacts\bridge-installer-payload\nssm.exe"; DestDir: "{tmp}\dms-provider-payload\app"; Flags: ignoreversion deleteafterinstall
Source: "artifacts\bridge-installer-payload\install-bridge-service.ps1"; DestDir: "{tmp}\dms-provider-payload\app"; Flags: ignoreversion deleteafterinstall
Source: "artifacts\bridge-installer-payload\uninstall-bridge-service.ps1"; DestDir: "{tmp}\dms-provider-payload\app"; Flags: ignoreversion deleteafterinstall
Source: "artifacts\bridge-installer-payload\config\bridge.json"; DestDir: "{tmp}\dms-provider-payload\config"; Flags: ignoreversion deleteafterinstall
Source: "artifacts\bridge-installer-payload\config\alfresco.json"; DestDir: "{tmp}\dms-provider-payload\config"; Flags: ignoreversion deleteafterinstall
Source: "artifacts\bridge-installer-payload\config\edocat.json"; DestDir: "{tmp}\dms-provider-payload\config"; Flags: ignoreversion deleteafterinstall
Source: "artifacts\bridge-installer-payload\config\fso.json"; DestDir: "{tmp}\dms-provider-payload\config"; Flags: ignoreversion deleteafterinstall
Source: "artifacts\bridge-installer-payload\user-config\alfresco.local.json"; DestDir: "{tmp}\dms-provider-payload\user-config"; Flags: ignoreversion deleteafterinstall
Source: "artifacts\bridge-installer-payload\user-config\edocat.local.json"; DestDir: "{tmp}\dms-provider-payload\user-config"; Flags: ignoreversion deleteafterinstall
Source: "artifacts\bridge-installer-payload\user-config\fso.local.json"; DestDir: "{tmp}\dms-provider-payload\user-config"; Flags: ignoreversion deleteafterinstall

[Code]
procedure WriteLog(LogPath: String; Message: String);
var
  Line: String;
begin
  Line := GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':') + ' ' + Message + #13#10;
  SaveStringToFile(LogPath, Line, True);
  Log(Message);
end;

procedure EnsureDir(Path: String; LogPath: String);
begin
  WriteLog(LogPath, '[STEP] Creating directory: ' + Path);
  if not ForceDirectories(Path) then begin
    WriteLog(LogPath, '[FAIL] Directory was not created: ' + Path);
    RaiseException('Directory was not created: ' + Path);
  end;
  WriteLog(LogPath, '[ OK ] ' + Path);
end;

procedure CopyFileChecked(SourcePath: String; TargetPath: String; LogPath: String; PreserveExisting: Boolean);
begin
  WriteLog(LogPath, '[STEP] Copying file: ' + SourcePath + ' -> ' + TargetPath);
  if PreserveExisting and FileExists(TargetPath) then begin
    WriteLog(LogPath, '[ OK ] Existing file preserved: ' + TargetPath);
    exit;
  end;
  if not CopyFile(SourcePath, TargetPath, False) then begin
    WriteLog(LogPath, '[FAIL] File was not copied: ' + TargetPath);
    RaiseException('File was not copied: ' + TargetPath);
  end;
  WriteLog(LogPath, '[ OK ] ' + TargetPath);
end;

procedure RunUserStructurePhase();
var
  UserRoot: String;
  UserConfigRoot: String;
  PayloadUserConfig: String;
  LogPath: String;
begin
  UserRoot := ExpandConstant('{userappdata}\DMS provider');
  UserConfigRoot := UserRoot + '\config';
  PayloadUserConfig := ExpandConstant('{tmp}\dms-provider-payload\user-config');
  LogPath := UserRoot + '\installer-structure.log';

  WizardForm.StatusLabel.Caption := 'Creating user config structure...';
  ForceDirectories(UserRoot);
  WriteLog(LogPath, '[INFO] User structure phase started');
  WriteLog(LogPath, '[INFO] Effective user AppData: ' + ExpandConstant('{userappdata}'));

  EnsureDir(UserRoot, LogPath);
  EnsureDir(UserConfigRoot, LogPath);

  CopyFileChecked(PayloadUserConfig + '\alfresco.local.json', UserConfigRoot + '\alfresco.local.json', LogPath, True);
  CopyFileChecked(PayloadUserConfig + '\edocat.local.json', UserConfigRoot + '\edocat.local.json', LogPath, True);
  CopyFileChecked(PayloadUserConfig + '\fso.local.json', UserConfigRoot + '\fso.local.json', LogPath, True);

  WriteLog(LogPath, '[STEP] Setting user environment: DMS_PROVIDER_USER_CONFIG_DIR=' + UserConfigRoot);
  if not RegWriteStringValue(HKEY_CURRENT_USER, 'Environment', 'DMS_PROVIDER_USER_CONFIG_DIR', UserConfigRoot) then begin
    WriteLog(LogPath, '[FAIL] User environment was not written: DMS_PROVIDER_USER_CONFIG_DIR');
    RaiseException('User environment was not written: DMS_PROVIDER_USER_CONFIG_DIR');
  end;
  WriteLog(LogPath, '[ OK ] DMS_PROVIDER_USER_CONFIG_DIR');

  WriteLog(LogPath, '[INFO] User structure phase completed successfully');
end;

function Quote(Value: String): String;
begin
  Result := '"' + Value + '"';
end;

procedure WriteAdminStructureScript(ScriptPath: String; PayloadRoot: String; DefaultAppRoot: String; UserLogPath: String; UserConfigRoot: String);
var
  Script: String;
begin
  Script :=
    '$ErrorActionPreference = "Stop"' + #13#10 +
    '$payloadRoot = ' + Quote(PayloadRoot) + #13#10 +
    '$defaultAppRoot = ' + Quote(DefaultAppRoot) + #13#10 +
    'Add-Type -AssemblyName System.Windows.Forms' + #13#10 +
    '$dialog = New-Object System.Windows.Forms.FolderBrowserDialog' + #13#10 +
    '$dialog.Description = "Select parent folder for DMS Provider"' + #13#10 +
    '$dialog.SelectedPath = [System.IO.Path]::GetDirectoryName($defaultAppRoot)' + #13#10 +
    '$dialog.ShowNewFolderButton = $true' + #13#10 +
    '$dialogResult = $dialog.ShowDialog()' + #13#10 +
    'if ($dialogResult -ne [System.Windows.Forms.DialogResult]::OK -or [string]::IsNullOrWhiteSpace($dialog.SelectedPath)) { throw "Installation folder selection was cancelled." }' + #13#10 +
    '$selectedPath = $dialog.SelectedPath.TrimEnd("\")' + #13#10 +
    'if ([System.IO.Path]::GetFileName($selectedPath) -ieq "DMS Provider") { $appRoot = $selectedPath } else { $appRoot = Join-Path $selectedPath "DMS Provider" }' + #13#10 +
    '$logDir = Join-Path $appRoot "logs"' + #13#10 +
    'New-Item -ItemType Directory -Path $logDir -Force | Out-Null' + #13#10 +
    '$logPath = Join-Path $logDir "installer-structure-admin.log"' + #13#10 +
    'function Write-InstallLog([string]$Message) {' + #13#10 +
    '    $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $Message' + #13#10 +
    '    Add-Content -Path $logPath -Value $line -Encoding UTF8' + #13#10 +
    '    Write-Host $Message' + #13#10 +
    '}' + #13#10 +
    'function Ensure-Dir([string]$Path) {' + #13#10 +
    '    Write-InstallLog "[STEP] Creating directory: $Path"' + #13#10 +
    '    New-Item -ItemType Directory -Path $Path -Force | Out-Null' + #13#10 +
    '    Write-InstallLog "[ OK ] $Path"' + #13#10 +
    '}' + #13#10 +
    'function Copy-Checked([string]$Source, [string]$Target) {' + #13#10 +
    '    Write-InstallLog "[STEP] Copying file: $Source -> $Target"' + #13#10 +
    '    Copy-Item -Path $Source -Destination $Target -Force' + #13#10 +
    '    if (-not (Test-Path $Target)) { throw "File was not copied: $Target" }' + #13#10 +
    '    Write-InstallLog "[ OK ] $Target"' + #13#10 +
    '}' + #13#10 +
    'function Invoke-Nssm([string[]]$Arguments, [bool]$IgnoreFailure = $false) {' + #13#10 +
    '    $nssm = Join-Path $appRoot "nssm.exe"' + #13#10 +
    '    $commandText = "$nssm $($Arguments -join '' '')"' + #13#10 +
    '    Write-InstallLog "[INFO] NSSM: $commandText"' + #13#10 +
    '    $output = & $nssm @Arguments 2>&1' + #13#10 +
    '    $exitCode = $LASTEXITCODE' + #13#10 +
    '    foreach ($line in @($output)) { if (-not [string]::IsNullOrWhiteSpace([string]$line)) { Write-InstallLog "[INFO] NSSM output: $line" } }' + #13#10 +
    '    if ($exitCode -ne 0 -and -not $IgnoreFailure) { throw "NSSM command failed with exit code $exitCode`: $commandText" }' + #13#10 +
    '    if ($exitCode -ne 0) { Write-InstallLog "[WARN] NSSM command ignored exit code $exitCode`: $commandText" }' + #13#10 +
    '}' + #13#10 +
    'function Remove-ExistingService([string]$ServiceName) {' + #13#10 +
    '    $existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue' + #13#10 +
    '    if ($null -eq $existingService) {' + #13#10 +
    '        Write-InstallLog "[INFO] Existing service not found: $ServiceName"' + #13#10 +
    '        return' + #13#10 +
    '    }' + #13#10 +
    '    Write-InstallLog "[STEP] Removing existing Windows service"' + #13#10 +
    '    Write-InstallLog "[INFO] Existing service status: $($existingService.Status)"' + #13#10 +
    '    if ($existingService.Status -ne "Stopped") {' + #13#10 +
    '        Invoke-Nssm @("stop", $ServiceName) $true' + #13#10 +
    '        Start-Sleep -Seconds 2' + #13#10 +
    '    }' + #13#10 +
    '    Invoke-Nssm @("remove", $ServiceName, "confirm") $true' + #13#10 +
    '    Start-Sleep -Seconds 2' + #13#10 +
    '    $remainingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue' + #13#10 +
    '    if ($null -ne $remainingService) {' + #13#10 +
    '        Write-InstallLog "[WARN] NSSM remove did not remove service, trying sc.exe delete"' + #13#10 +
    '        $scOutput = & sc.exe delete $ServiceName 2>&1' + #13#10 +
    '        foreach ($line in @($scOutput)) { if (-not [string]::IsNullOrWhiteSpace([string]$line)) { Write-InstallLog "[INFO] sc.exe output: $line" } }' + #13#10 +
    '        Start-Sleep -Seconds 2' + #13#10 +
    '    }' + #13#10 +
    '    for ($attempt = 1; $attempt -le 10; $attempt++) {' + #13#10 +
    '        $remainingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue' + #13#10 +
    '        if ($null -eq $remainingService) {' + #13#10 +
    '            Write-InstallLog "[ OK ] Existing service removed: $ServiceName"' + #13#10 +
    '            return' + #13#10 +
    '        }' + #13#10 +
    '        Write-InstallLog "[INFO] Waiting for service removal attempt $attempt/10"' + #13#10 +
    '        Start-Sleep -Seconds 1' + #13#10 +
    '    }' + #13#10 +
    '    throw "Existing service could not be removed: $ServiceName"' + #13#10 +
    '}' + #13#10 +
    'function Write-ServiceControlScript([string]$FileBase, [string]$Action) {' + #13#10 +
    '    $psPath = Join-Path $appRoot "$FileBase.ps1"' + #13#10 +
    '    $cmdPath = Join-Path $appRoot "$FileBase.cmd"' + #13#10 +
    '    $psContent = @(' + #13#10 +
    '        ''$ErrorActionPreference = "Stop"''' + #13#10 +
    '        ''$serviceName = "DMSProviderBridge"''' + #13#10 +
    '        ''$action = "ActionPlaceholder"''' + #13#10 +
    '        ''$appRoot = Split-Path -Parent $PSCommandPath''' + #13#10 +
    '        ''$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())''' + #13#10 +
    '        ''if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {''' + #13#10 +
    '        ''    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath)''' + #13#10 +
    '        ''    exit''' + #13#10 +
    '        ''}''' + #13#10 +
    '        ''try {''' + #13#10 +
    '        ''    Write-Host "Service action: $action"''' + #13#10 +
    '        ''    if ($action -eq "start") { Start-Service -Name $serviceName -ErrorAction Stop; Start-Sleep -Seconds 2 }''' + #13#10 +
    '        ''    elseif ($action -eq "stop") { Stop-Service -Name $serviceName -ErrorAction Stop; Start-Sleep -Seconds 2 }''' + #13#10 +
    '        ''    elseif ($action -ne "status") { throw "Unsupported action: $action" }''' + #13#10 +
    '        ''    Get-Service -Name $serviceName | Format-List Name, DisplayName, Status, StartType''' + #13#10 +
    '        ''    Write-Host ""''' + #13#10 +
    '        ''    Write-Host "SCM query:"''' + #13#10 +
    '        ''    sc.exe queryex $serviceName''' + #13#10 +
    '        ''    $nssm = Join-Path $appRoot "nssm.exe"''' + #13#10 +
    '        ''    if (Test-Path $nssm) { Write-Host ""; Write-Host "NSSM dump:"; & $nssm dump $serviceName }''' + #13#10 +
    '        ''    $stdout = Join-Path $appRoot "logs\bridge-stdout.log"''' + #13#10 +
    '        ''    $stderr = Join-Path $appRoot "logs\bridge-stderr.log"''' + #13#10 +
    '        ''    if (Test-Path $stdout) { Write-Host ""; Write-Host "bridge-stdout.log tail:"; Get-Content $stdout -Tail 40 }''' + #13#10 +
    '        ''    if (Test-Path $stderr) { Write-Host ""; Write-Host "bridge-stderr.log tail:"; Get-Content $stderr -Tail 80 }''' + #13#10 +
    '        ''    Write-Host ""; Write-Host "Service Control Manager events:"''' + #13#10 +
    '        ''    Get-WinEvent -FilterHashtable @{LogName="System"; ProviderName="Service Control Manager"} -MaxEvents 30 -ErrorAction SilentlyContinue | Where-Object { $_.Message -like "*$serviceName*" } | Select-Object -First 8 TimeCreated, Id, Message | Format-List''' + #13#10 +
    '        ''}''' + #13#10 +
    '        ''catch {''' + #13#10 +
    '        ''    Write-Host $_.Exception.Message -ForegroundColor Red''' + #13#10 +
    '        ''    Write-Host ""''' + #13#10 +
    '        ''    Write-Host "Service state after failure:"''' + #13#10 +
    '        ''    sc.exe queryex $serviceName''' + #13#10 +
    '        ''    exit 1''' + #13#10 +
    '        ''}''' + #13#10 +
    '        ''Read-Host "Press Enter to close"''' + #13#10 +
    '    )' + #13#10 +
    '    $psContent = $psContent -replace "ActionPlaceholder", $Action' + #13#10 +
    '    Set-Content -Path $psPath -Value $psContent -Encoding UTF8' + #13#10 +
    '    $cmdContent = @("@echo off", "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""%~dp0$FileBase.ps1""")' + #13#10 +
    '    Set-Content -Path $cmdPath -Value $cmdContent -Encoding ASCII' + #13#10 +
    '    Write-InstallLog "[ OK ] Service control script: $cmdPath"' + #13#10 +
    '}' + #13#10 +
    'function Write-ServiceControlShortcut([string]$FileBase, [string]$Title) {' + #13#10 +
    '    $programs = [Environment]::GetFolderPath("CommonPrograms")' + #13#10 +
    '    if ([string]::IsNullOrWhiteSpace($programs)) { $programs = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs" }' + #13#10 +
    '    $shortcutDir = Join-Path $programs "DMS Provider"' + #13#10 +
    '    Ensure-Dir $shortcutDir' + #13#10 +
    '    $shortcutPath = Join-Path $shortcutDir "$Title.lnk"' + #13#10 +
    '    $shell = New-Object -ComObject WScript.Shell' + #13#10 +
    '    $shortcut = $shell.CreateShortcut($shortcutPath)' + #13#10 +
    '    $shortcut.TargetPath = Join-Path $appRoot "$FileBase.cmd"' + #13#10 +
    '    $shortcut.WorkingDirectory = $appRoot' + #13#10 +
    '    $shortcut.Description = $Title' + #13#10 +
    '    $shortcut.Save()' + #13#10 +
    '    Write-InstallLog "[ OK ] Service control shortcut: $shortcutPath"' + #13#10 +
    '}' + #13#10 +
    'Ensure-Dir $appRoot' + #13#10 +
    'Ensure-Dir (Join-Path $appRoot "config")' + #13#10 +
    'Ensure-Dir (Join-Path $appRoot "logs")' + #13#10 +
    'Write-InstallLog "[INFO] Admin structure phase started"' + #13#10 +
    'Write-InstallLog "[INFO] Install path: $appRoot"' + #13#10 +
    'Write-InstallLog "[INFO] User phase log: ' + UserLogPath + '"' + #13#10 +
    'Copy-Checked (Join-Path $payloadRoot "app\dms-provider-bridge.exe") (Join-Path $appRoot "dms-provider-bridge.exe")' + #13#10 +
    'Copy-Checked (Join-Path $payloadRoot "app\nssm.exe") (Join-Path $appRoot "nssm.exe")' + #13#10 +
    'Copy-Checked (Join-Path $payloadRoot "app\install-bridge-service.ps1") (Join-Path $appRoot "install-bridge-service.ps1")' + #13#10 +
    'Copy-Checked (Join-Path $payloadRoot "app\uninstall-bridge-service.ps1") (Join-Path $appRoot "uninstall-bridge-service.ps1")' + #13#10 +
    'Copy-Checked (Join-Path $payloadRoot "config\bridge.json") (Join-Path $appRoot "config\bridge.json")' + #13#10 +
    'Copy-Checked (Join-Path $payloadRoot "config\alfresco.json") (Join-Path $appRoot "config\alfresco.json")' + #13#10 +
    'Copy-Checked (Join-Path $payloadRoot "config\edocat.json") (Join-Path $appRoot "config\edocat.json")' + #13#10 +
    'Copy-Checked (Join-Path $payloadRoot "config\fso.json") (Join-Path $appRoot "config\fso.json")' + #13#10 +
    'Write-InstallLog "[STEP] Setting machine environment: DMS_PROVIDER_MACHINE_CONFIG_DIR=$appRoot\config"' + #13#10 +
    '[Environment]::SetEnvironmentVariable("DMS_PROVIDER_MACHINE_CONFIG_DIR", (Join-Path $appRoot "config"), "Machine")' + #13#10 +
    'Write-InstallLog "[ OK ] DMS_PROVIDER_MACHINE_CONFIG_DIR"' + #13#10 +
    '$serviceName = "DMSProviderBridge"' + #13#10 +
    '$serviceDisplayName = "DMS Provider Bridge"' + #13#10 +
    '$bridgeExe = Join-Path $appRoot "dms-provider-bridge.exe"' + #13#10 +
    '$machineConfigRoot = Join-Path $appRoot "config"' + #13#10 +
    '$userConfigRoot = ' + Quote(UserConfigRoot) + #13#10 +
    '$stdoutLog = Join-Path $appRoot "logs\bridge-stdout.log"' + #13#10 +
    '$stderrLog = Join-Path $appRoot "logs\bridge-stderr.log"' + #13#10 +
    'Write-InstallLog "[STEP] Registering Windows service"' + #13#10 +
    'Write-InstallLog "[INFO] Service name: $serviceName"' + #13#10 +
    'Write-InstallLog "[INFO] Display name: $serviceDisplayName"' + #13#10 +
    'Write-InstallLog "[INFO] Account: LocalSystem"' + #13#10 +
    'Write-InstallLog "[INFO] App: $bridgeExe"' + #13#10 +
    'Write-InstallLog "[INFO] AppDirectory: $appRoot"' + #13#10 +
    'Write-InstallLog "[INFO] Machine config: $machineConfigRoot"' + #13#10 +
    'Write-InstallLog "[INFO] User config: $userConfigRoot"' + #13#10 +
    'Remove-ExistingService $serviceName' + #13#10 +
    'Invoke-Nssm @("install", $serviceName, $bridgeExe)' + #13#10 +
    'Invoke-Nssm @("set", $serviceName, "AppDirectory", $appRoot)' + #13#10 +
    'Invoke-Nssm @("set", $serviceName, "DisplayName", $serviceDisplayName)' + #13#10 +
    'Invoke-Nssm @("set", $serviceName, "AppStdout", $stdoutLog)' + #13#10 +
    'Invoke-Nssm @("set", $serviceName, "AppStderr", $stderrLog)' + #13#10 +
    'Invoke-Nssm @("set", $serviceName, "AppEnvironmentExtra", "DMS_PROVIDER_MACHINE_CONFIG_DIR=$machineConfigRoot", "DMS_PROVIDER_USER_CONFIG_DIR=$userConfigRoot")' + #13#10 +
    'Invoke-Nssm @("set", $serviceName, "ObjectName", "LocalSystem")' + #13#10 +
    'Invoke-Nssm @("set", $serviceName, "Start", "SERVICE_AUTO_START")' + #13#10 +
    '$registeredService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue' + #13#10 +
    'if ($null -eq $registeredService) { throw "Service was not found after registration: $serviceName" }' + #13#10 +
    'Write-InstallLog "[ OK ] Service registered: $serviceName"' + #13#10 +
    'Write-InstallLog "[STEP] Writing service control scripts"' + #13#10 +
    'Write-ServiceControlScript "start-bridge-service" "start"' + #13#10 +
    'Write-ServiceControlScript "stop-bridge-service" "stop"' + #13#10 +
    'Write-ServiceControlScript "status-bridge-service" "status"' + #13#10 +
    'Write-ServiceControlShortcut "start-bridge-service" "DMS Provider Bridge - Start Service"' + #13#10 +
    'Write-ServiceControlShortcut "stop-bridge-service" "DMS Provider Bridge - Stop Service"' + #13#10 +
    'Write-ServiceControlShortcut "status-bridge-service" "DMS Provider Bridge - Service Status"' + #13#10 +
    'Write-InstallLog "[STEP] Starting Windows service"' + #13#10 +
    'try {' + #13#10 +
    '    Write-InstallLog "[INFO] Start-Service: $serviceName"' + #13#10 +
    '    $startWarnings = @()' + #13#10 +
    '    Start-Service -Name $serviceName -ErrorAction Stop -WarningAction Continue -WarningVariable startWarnings' + #13#10 +
    '    foreach ($warning in @($startWarnings)) { if (-not [string]::IsNullOrWhiteSpace([string]$warning)) { Write-InstallLog "[WARN] Start-Service warning: $warning" } }' + #13#10 +
    '    Write-InstallLog "[INFO] Start-Service returned"' + #13#10 +
    '}' + #13#10 +
    'catch {' + #13#10 +
    '    Write-InstallLog "[WARN] Start-Service reported: $($_.Exception.Message)"' + #13#10 +
    '}' + #13#10 +
    'for ($attempt = 1; $attempt -le 15; $attempt++) {' + #13#10 +
    '    $serviceState = Get-Service -Name $serviceName -ErrorAction SilentlyContinue' + #13#10 +
    '    if ($null -ne $serviceState) { Write-InstallLog "[INFO] Service status attempt $attempt/15: $($serviceState.Status)" }' + #13#10 +
    '    if ($null -ne $serviceState -and $serviceState.Status -eq "Running") {' + #13#10 +
    '        Write-InstallLog "[ OK ] Service started: $serviceName"' + #13#10 +
    '        break' + #13#10 +
    '    }' + #13#10 +
    '    Start-Sleep -Seconds 1' + #13#10 +
    '}' + #13#10 +
    '$serviceState = Get-Service -Name $serviceName -ErrorAction SilentlyContinue' + #13#10 +
    'if ($null -eq $serviceState -or $serviceState.Status -ne "Running") {' + #13#10 +
    '    Write-InstallLog "[FAIL] Service did not reach Running state: $serviceName"' + #13#10 +
    '    foreach ($logPathToRead in @($stdoutLog, $stderrLog)) {' + #13#10 +
    '        if (Test-Path $logPathToRead) {' + #13#10 +
    '            Write-InstallLog "[INFO] Tail: $logPathToRead"' + #13#10 +
    '            foreach ($line in @(Get-Content -Path $logPathToRead -Tail 80 -ErrorAction SilentlyContinue)) { Write-InstallLog "[INFO] $line" }' + #13#10 +
    '        }' + #13#10 +
    '        else { Write-InstallLog "[INFO] Log file not found: $logPathToRead" }' + #13#10 +
    '    }' + #13#10 +
    '    $nssmDump = & $nssm dump $serviceName 2>&1' + #13#10 +
    '    foreach ($line in @($nssmDump)) { if (-not [string]::IsNullOrWhiteSpace([string]$line)) { Write-InstallLog "[INFO] NSSM dump: $line" } }' + #13#10 +
    '    throw "Service did not start: $serviceName"' + #13#10 +
    '}' + #13#10 +
    'Write-InstallLog "[INFO] Admin structure phase completed successfully"' + #13#10;

  SaveStringToFile(ScriptPath, Script, False);
end;

procedure RunAdminStructurePhase();
var
  ResultCode: Integer;
  PayloadRoot: String;
  DefaultAppRoot: String;
  ScriptPath: String;
  Params: String;
  UserLogPath: String;
  UserConfigRoot: String;
begin
  PayloadRoot := ExpandConstant('{tmp}\dms-provider-payload');
  DefaultAppRoot := ExpandConstant('{commonpf}\DMS Provider');
  ScriptPath := ExpandConstant('{tmp}\dms-provider-admin-structure.ps1');
  UserLogPath := ExpandConstant('{userappdata}\DMS provider\installer-structure.log');
  UserConfigRoot := ExpandConstant('{userappdata}\DMS provider\config');

  WizardForm.StatusLabel.Caption := 'Requesting administrator rights for app structure...';
  WriteAdminStructureScript(ScriptPath, PayloadRoot, DefaultAppRoot, UserLogPath, UserConfigRoot);

  Params := '-STA -NoProfile -ExecutionPolicy Bypass -File ' + Quote(ScriptPath);
  if not ShellExec('runas', ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Params, '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then begin
    RaiseException('Admin structure phase was not started.');
  end;
  if ResultCode <> 0 then begin
    RaiseException('Admin structure phase failed with exit code: ' + IntToStr(ResultCode));
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    RunUserStructurePhase();
    RunAdminStructurePhase();
  end;
end;
