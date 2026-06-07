[Setup]
AppId={{CFD8BDCC-B59A-4CB3-93D7-530BB5283773}
AppName=DMS Provider Bridge Setup
AppVersion=0.3.4
AppPublisher=mergi72
DefaultDirName={autopf}\DMS Provider
DefaultGroupName=DMS Provider Bridge
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=artifacts\installer
OutputBaseFilename=DmsProviderBridgeSetup-v0.3.4-debug
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Dirs]
Name: "{app}"; Flags: uninsneveruninstall
Name: "{app}\config"; Flags: uninsneveruninstall
Name: "{app}\logs"; Flags: uninsneveruninstall
Name: "{userappdata}\DMS bridge"; Flags: uninsneveruninstall
Name: "{userappdata}\DMS bridge\config"; Flags: uninsneveruninstall

[Files]
Source: "artifacts\bridge-installer-payload\dms-provider-bridge.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\nssm.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\install-bridge-service.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\uninstall-bridge-service.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\config\bridge.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\config\alfresco.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\config\edocat.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\config\fso.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "artifacts\bridge-installer-payload\user-config\alfresco.local.json"; DestDir: "{userappdata}\DMS bridge\config"; Flags: ignoreversion onlyifdoesntexist
Source: "artifacts\bridge-installer-payload\user-config\edocat.local.json"; DestDir: "{userappdata}\DMS bridge\config"; Flags: ignoreversion onlyifdoesntexist
Source: "artifacts\bridge-installer-payload\user-config\fso.local.json"; DestDir: "{userappdata}\DMS bridge\config"; Flags: ignoreversion onlyifdoesntexist

[Code]
procedure WriteBlockLog(Message: String);
var
  LogPath: String;
  Line: String;
begin
  LogPath := ExpandConstant('{app}\logs\installer-block2.log');
  Line := GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':') + ' ' + Message + #13#10;
  SaveStringToFile(LogPath, Line, True);
  Log(Message);
end;

procedure VerifyDir(Path: String);
begin
  WriteBlockLog('[STEP] Verify directory: ' + Path);
  if DirExists(Path) then begin
    WriteBlockLog('[ OK ] ' + Path);
  end else begin
    WriteBlockLog('[FAIL] Missing directory: ' + Path);
    RaiseException('Missing directory: ' + Path);
  end;
end;

procedure VerifyFile(Path: String);
begin
  WriteBlockLog('[STEP] Verify file: ' + Path);
  if FileExists(Path) then begin
    WriteBlockLog('[ OK ] ' + Path);
  end else begin
    WriteBlockLog('[FAIL] Missing file: ' + Path);
    RaiseException('Missing file: ' + Path);
  end;
end;

procedure VerifyBlock2Install();
begin
  WizardForm.StatusLabel.Caption := 'Verifying DMS Provider Bridge files...';
  WriteBlockLog('[INFO] Block 2 verification started');

  WriteBlockLog('[STEP] Verifying application directories');
  VerifyDir(ExpandConstant('{app}'));
  VerifyDir(ExpandConstant('{app}\config'));
  VerifyDir(ExpandConstant('{app}\logs'));

  WriteBlockLog('[STEP] Verifying user AppData directories');
  VerifyDir(ExpandConstant('{userappdata}\DMS bridge'));
  VerifyDir(ExpandConstant('{userappdata}\DMS bridge\config'));

  WriteBlockLog('[STEP] Verifying application files');
  VerifyFile(ExpandConstant('{app}\dms-provider-bridge.exe'));
  VerifyFile(ExpandConstant('{app}\nssm.exe'));
  VerifyFile(ExpandConstant('{app}\install-bridge-service.ps1'));
  VerifyFile(ExpandConstant('{app}\uninstall-bridge-service.ps1'));

  WriteBlockLog('[STEP] Verifying application config files');
  VerifyFile(ExpandConstant('{app}\config\bridge.json'));
  VerifyFile(ExpandConstant('{app}\config\alfresco.json'));
  VerifyFile(ExpandConstant('{app}\config\edocat.json'));
  VerifyFile(ExpandConstant('{app}\config\fso.json'));

  WriteBlockLog('[STEP] Verifying user local config files');
  VerifyFile(ExpandConstant('{userappdata}\DMS bridge\config\alfresco.local.json'));
  VerifyFile(ExpandConstant('{userappdata}\DMS bridge\config\edocat.local.json'));
  VerifyFile(ExpandConstant('{userappdata}\DMS bridge\config\fso.local.json'));

  WriteBlockLog('[INFO] Block 2 verification completed successfully');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    VerifyBlock2Install();
  end;
end;
