[Setup]
AppId={{7E6B6817-B0C2-48B6-AF5D-B7F891E4B0AD}
AppName=DMS Provider Bridge Setup
AppVersion=0.8.9-beta
AppPublisher=mergi72
CreateAppDir=no
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
Uninstallable=no
DisableFinishedPage=yes
OutputDir=artifacts\installer
OutputBaseFilename=DmsProviderBridgeSetup-v0.8.9-beta
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "artifacts\installer\DmsProviderBridgeSetupCore-v0.8.9-beta.exe"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall

[Code]
function Quote(Value: String): String;
begin
  Result := '"' + Value + '"';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  CoreSetupPath: String;
  Params: String;
begin
  if CurStep = ssPostInstall then begin
    CoreSetupPath := ExpandConstant('{tmp}\DmsProviderBridgeSetupCore-v0.8.9-beta.exe');
    Params := '/SUPPRESSMSGBOXES /NORESTART /USERAPPDATA=' + Quote(ExpandConstant('{userappdata}'));

    WizardForm.StatusLabel.Caption := 'Starting elevated DMS Provider Bridge setup...';
    if not Exec(CoreSetupPath, Params, '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then begin
      RaiseException('DMS Provider Bridge setup was not started.');
    end;

    if ResultCode <> 0 then begin
      RaiseException('DMS Provider Bridge setup failed with exit code: ' + IntToStr(ResultCode));
    end;
  end;
end;
