#ifndef AppVersion
  #error AppVersion must be supplied by build-installer.ps1
#endif
#define ProjectRoot SourcePath + ".."

[Setup]
AppId={{07BD152E-EBD3-4763-B00B-4049E485BB53}
AppName=HDR Screen Share
AppVersion={#AppVersion}
AppPublisher=HDR Screen Share contributors
AppPublisherURL=https://github.com/Axli5c/hdr-screen-share
AppSupportURL=https://github.com/Axli5c/hdr-screen-share/issues
DefaultDirName={localappdata}\Programs\HDRScreenShare
DefaultGroupName=HDR Screen Share
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.22000
LicenseFile={#ProjectRoot}\LICENSE
OutputDir={#ProjectRoot}\dist\releases
OutputBaseFilename=HDRScreenShare-Setup-v{#AppVersion}-windows-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\HDRScreenShare.exe
CloseApplications=yes
CloseApplicationsFilter=HDRScreenShare.exe
RestartApplications=no
SetupLogging=yes
ShowLanguageDialog=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[CustomMessages]
english.ChooseComponents=Choose components
russian.ChooseComponents=Выберите компоненты
english.AppComponent=HDR Screen Share (includes Python and all application libraries)
russian.AppComponent=HDR Screen Share (Python и все библиотеки уже включены)
english.VddComponent=Virtual Display Driver - for Virtual screen mode (download, UAC)
russian.VddComponent=Драйвер виртуального дисплея — режим Virtual screen (загрузка, UAC)
english.CableComponent=VB-CABLE by VB-Audio - audio in Application window mode (download, UAC)
russian.CableComponent=VB-CABLE от VB-Audio — звук в Application window (загрузка, UAC)
english.DesktopShortcut=Create a desktop shortcut
russian.DesktopShortcut=Создать ярлык на рабочем столе
english.OpenApp=Open HDR Screen Share
russian.OpenApp=Открыть HDR Screen Share
english.CableNotice=VB-CABLE is donationware by VB-Audio: https://vb-audio.com/Cable/%nSupport the author if you find it useful. Selected drivers require internet access.
russian.CableNotice=VB-CABLE — Donationware от VB-Audio: https://vb-audio.com/Cable/%nПоддержите автора, если программа полезна. Для загрузки драйверов нужен интернет.
english.AppInstalled=HDR Screen Share is installed. Choose a monitor and press Start.
russian.AppInstalled=HDR Screen Share установлен. Выберите монитор и нажмите Start.
english.InstallingDrivers=Installing selected drivers...
russian.InstallingDrivers=Установка выбранных драйверов...
english.DriverCancelled=HDR Screen Share is installed. Driver setup was cancelled or could not start. Run Setup again to install the drivers.
russian.DriverCancelled=HDR Screen Share установлен. Установка драйверов отменена или не запустилась. Для установки драйверов запустите установщик ещё раз.
english.DriverIncomplete=HDR Screen Share is installed. Driver setup did not finish. Run Setup again to retry.
russian.DriverIncomplete=HDR Screen Share установлен. Установка драйверов не завершилась. Запустите установщик ещё раз.
english.DriverFailed=Some drivers could not be installed. Run Setup again to retry.
russian.DriverFailed=Не все драйверы удалось установить. Для повторной попытки запустите установщик ещё раз.

[Types]
Name: "custom"; Description: "{cm:ChooseComponents}"; Flags: iscustom

[Components]
Name: "app"; Description: "{cm:AppComponent}"; Types: custom; Flags: fixed
Name: "vdd"; Description: "{cm:VddComponent}"
Name: "vbcable"; Description: "{cm:CableComponent}"

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"; Flags: unchecked

[Files]
Source: "{#ProjectRoot}\dist\HDRScreenShare\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "setup-components.ps1"; Flags: dontcopy
Source: "install-devices.ps1"; Flags: dontcopy
Source: "vdd-config.ps1"; Flags: dontcopy
Source: "device-packages.json"; Flags: dontcopy

[Icons]
Name: "{group}\HDR Screen Share"; Filename: "{app}\HDRScreenShare.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\HDR Screen Share"; Filename: "{app}\HDRScreenShare.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\HDRScreenShare.exe"; Description: "{cm:OpenApp}"; WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent unchecked

[UninstallDelete]
Type: files; Name: "{app}\setup-result.txt"

[Code]
var
  ComponentResult: String;
  DriverSetupFailed: Boolean;

procedure SaveComponentResult;
begin
  Log(ComponentResult);
  SaveStringToFile(ExpandConstant('{app}\setup-result.txt'), UTF8Encode(ComponentResult), False);
end;

function GetCustomSetupExitCode: Integer;
begin
  if DriverSetupFailed then Result := 10 else Result := 0;
end;

procedure InitializeWizard;
var
  Notice: TNewStaticText;
begin
  Notice := TNewStaticText.Create(WizardForm);
  Notice.Parent := WizardForm.SelectComponentsPage;
  Notice.SetBounds(WizardForm.ComponentsList.Left, WizardForm.ComponentsList.Top + WizardForm.ComponentsList.Height - ScaleY(45), WizardForm.ComponentsList.Width, ScaleY(45));
  Notice.WordWrap := True;
  Notice.Caption := CustomMessage('CableNotice');
  WizardForm.ComponentsList.Height := WizardForm.ComponentsList.Height - ScaleY(55);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Selected, Params, ReportFile: String;
  ReportText, StatusText: AnsiString;
  Code: Integer;
begin
  if CurStep <> ssPostInstall then Exit;
  Selected := '';
  if WizardIsComponentSelected('vdd') then Selected := 'vdd';
  if WizardIsComponentSelected('vbcable') then begin
    if Selected <> '' then Selected := Selected + ',';
    Selected := Selected + 'vbcable';
  end;
  ComponentResult := CustomMessage('AppInstalled');
  if Selected = '' then begin
    SaveComponentResult;
    Exit;
  end;
  ExtractTemporaryFile('setup-components.ps1');
  ExtractTemporaryFile('install-devices.ps1');
  ExtractTemporaryFile('vdd-config.ps1');
  ExtractTemporaryFile('device-packages.json');
  ReportFile := ExpandConstant('{tmp}\component-result.txt');
  Params := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{tmp}\setup-components.ps1') + '" -Selected "' + Selected + '" -ReportPath "' + ReportFile + '"';
  if ActiveLanguage = 'russian' then Params := Params + ' -Language ru';
  WizardForm.StatusLabel.Caption := CustomMessage('InstallingDrivers');
  if not ShellExec('runas', ExpandConstant('{sysnative}\WindowsPowerShell\v1.0\powershell.exe'), Params, ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, Code) then begin
    ComponentResult := CustomMessage('DriverCancelled');
    DriverSetupFailed := True;
    SaveComponentResult;
    Exit;
  end;
  if LoadStringFromFile(ReportFile, ReportText) then
    ComponentResult := UTF8Decode(ReportText)
  else begin
    ComponentResult := CustomMessage('DriverIncomplete');
    DriverSetupFailed := True;
  end;
  if not LoadStringFromFile(ReportFile + '.status', StatusText) then
    DriverSetupFailed := True
  else if StatusText <> 'ok' then
    DriverSetupFailed := True;
  if DriverSetupFailed then begin
    ComponentResult := ComponentResult + #13#10 + CustomMessage('DriverFailed');
  end;
  SaveComponentResult;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then begin
    WizardForm.FinishedLabel.Caption := ComponentResult;
    WizardForm.FinishedLabel.Height := ScaleY(150);
    WizardForm.RunList.Top := WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height + ScaleY(8);
  end;
end;
