[Setup]
AppId={{CFD8BDCC-B59A-4CB3-93D7-530BB5283773}
AppName=DMS Provider Bridge Setup
AppVersion=0.2.8-alpha
AppPublisher=mergi72
DefaultDirName={autopf}\DMS Provider
DefaultGroupName=DMS Provider Bridge
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=artifacts\installer
OutputBaseFilename=DmsProviderBridgeSetup-v0.2.8-alpha
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "artifacts\bridge-installer-payload\dms-provider-bridge.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\nssm.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\install-bridge-service.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\uninstall-bridge-service.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\config\default.json"; DestDir: "{commonappdata}\DMSProvider\config"; Flags: ignoreversion onlyifdoesntexist
Source: "artifacts\bridge-installer-payload\config\alfresco.json"; DestDir: "{commonappdata}\DMSProvider\config"; Flags: ignoreversion onlyifdoesntexist
Source: "artifacts\bridge-installer-payload\config\edocat.json"; DestDir: "{commonappdata}\DMSProvider\config"; Flags: ignoreversion onlyifdoesntexist
Source: "artifacts\bridge-installer-payload\config\fso.json"; DestDir: "{commonappdata}\DMSProvider\config"; Flags: ignoreversion onlyifdoesntexist
Source: "artifacts\bridge-installer-payload\config\user.json"; DestDir: "{app}\config"; Flags: ignoreversion

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install-bridge-service.ps1"" -RuntimeMode User -TaskName ""DmsProviderBridgeUser"" -StartImmediately -BridgeExePath ""{app}\dms-provider-bridge.exe"" -BridgeConfigDirPath ""{commonappdata}\DMSProvider\config"" -UserConfigTemplatePath ""{app}\config\user.json"" -NssmExePath ""{app}\nssm.exe"""; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\uninstall-bridge-service.ps1"" -NssmExePath ""{app}\nssm.exe"""; Flags: runhidden waituntilterminated; RunOnceId: "DMSProviderBridgeUninstallCleanup"
