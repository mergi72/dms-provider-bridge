[Setup]
AppId={{CFD8BDCC-B59A-4CB3-93D7-530BB5283773}
AppName=DMS Provider Bridge Setup
AppVersion=0.3.0
AppPublisher=mergi72
DefaultDirName={autopf}\DMS Provider
DefaultGroupName=DMS Provider Bridge
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=artifacts\installer
OutputBaseFilename=DmsProviderBridgeSetup-v0.3.0
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "artifacts\bridge-installer-payload\dms-provider-bridge.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\nssm.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\install-bridge-service.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\uninstall-bridge-service.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\config\default.json"; DestDir: "{commonappdata}\DMS Provider\config"; Flags: ignoreversion onlyifdoesntexist
Source: "artifacts\bridge-installer-payload\config\alfresco.json"; DestDir: "{commonappdata}\DMS Provider\config"; Flags: ignoreversion onlyifdoesntexist
Source: "artifacts\bridge-installer-payload\config\edocat.json"; DestDir: "{commonappdata}\DMS Provider\config"; Flags: ignoreversion onlyifdoesntexist
Source: "artifacts\bridge-installer-payload\config\fso.json"; DestDir: "{commonappdata}\DMS Provider\config"; Flags: ignoreversion onlyifdoesntexist
Source: "artifacts\bridge-installer-payload\user-config\user.json"; DestDir: "{userappdata}\DMS Provider\config"; Flags: ignoreversion onlyifdoesntexist

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install-bridge-service.ps1"" -RuntimeMode User -TaskName ""DmsProviderBridgeUser"" -StartImmediately -BridgeExePath ""{app}\dms-provider-bridge.exe"" -BridgeConfigDirPath ""{commonappdata}\DMS Provider\config"" -UserConfigSourceDirPath ""{userappdata}\DMS Provider\config"" -NssmExePath ""{app}\nssm.exe"""; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\uninstall-bridge-service.ps1"" -KeepConfigFiles -NssmExePath ""{app}\nssm.exe"""; Flags: runhidden waituntilterminated; RunOnceId: "DMSProviderBridgeUninstallCleanup"
