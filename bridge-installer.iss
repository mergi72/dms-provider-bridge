[Setup]
AppId={{CFD8BDCC-B59A-4CB3-93D7-530BB5283773}
AppName=DMS Provider Bridge Setup
AppVersion=0.3.1
AppPublisher=mergi72
DefaultDirName={autopf}\DMS Provider
DefaultGroupName=DMS Provider Bridge
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=artifacts\installer
OutputBaseFilename=DmsProviderBridgeSetup-v0.3.1
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Dirs]
Name: "{commonappdata}\DMS Provider\config"; Flags: uninsneveruninstall
Name: "{userappdata}\DMS Provider\config"; Flags: uninsneveruninstall

[Files]
Source: "artifacts\bridge-installer-payload\dms-provider-bridge.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\nssm.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\install-bridge-service.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\uninstall-bridge-service.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\config\bridge.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\config\alfresco.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\config\edocat.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\config\fso.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\user-config\alfresco.local.json"; DestDir: "{userappdata}\DMS Provider\config"; Flags: ignoreversion onlyifdoesntexist
Source: "artifacts\bridge-installer-payload\user-config\edocat.local.json"; DestDir: "{userappdata}\DMS Provider\config"; Flags: ignoreversion onlyifdoesntexist
Source: "artifacts\bridge-installer-payload\user-config\fso.local.json"; DestDir: "{userappdata}\DMS Provider\config"; Flags: ignoreversion onlyifdoesntexist

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install-bridge-service.ps1"" -RuntimeMode Service -ServiceName ""DMSProviderBridge"" -ServiceDisplayName ""DMS Provider Bridge"" -ServiceAccount LocalSystem -StartImmediately -BridgeExePath ""{app}\dms-provider-bridge.exe"" -BridgeConfigDirPath ""{app}\config"" -ConfigRoot ""{userappdata}\DMS Provider\config"" -UserConfigSourceDirPath ""{userappdata}\DMS Provider\config"" -NssmExePath ""{app}\nssm.exe"""; Flags: waituntilterminated logoutput

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\uninstall-bridge-service.ps1"" -ServiceName ""DMSProviderBridge"" -KeepConfigFiles -NssmExePath ""{app}\nssm.exe"""; Flags: runhidden waituntilterminated; RunOnceId: "DMSProviderBridgeUninstallCleanup"
