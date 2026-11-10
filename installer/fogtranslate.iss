; Inno Setup script for Fog Translate (built in CI, .github/workflows/build.yml):
;     ISCC.exe /DAppVersion=<version> installer\fogtranslate.iss
; Per-user install without admin rights (%LOCALAPPDATA%\Programs\Fog Translate); settings and keys stay in
; %LOCALAPPDATA%\FogTranslate and are kept when uninstalling. Unsigned.
#ifndef AppVersion
  #define AppVersion "0.0"
#endif

[Setup]
AppId={{6B0C3E2A-5D0B-4C61-9E9A-2F7A6B1D4E77}
AppName=Fog Translate
AppVersion={#AppVersion}
AppPublisher=senisinx
AppPublisherURL=https://github.com/senisinx/fog-translate
DefaultDirName={localappdata}\Programs\Fog Translate
DefaultGroupName=Fog Translate
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=FogTranslate-Setup-{#AppVersion}
SetupIconFile=..\build\fogtranslate\fogtranslate.ico
UninstallDisplayIcon={app}\FogTranslate.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; the terms of use come in the language chosen at the start (UTF-8 with BOM; en/de are the two halves of LICENSE,
; the others translations that name the English text as the one that applies)
[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"; LicenseFile: "terms\terms_en.txt"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"; LicenseFile: "terms\terms_de.txt"
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"; LicenseFile: "terms\terms_it.txt"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"; LicenseFile: "terms\terms_ru.txt"
Name: "zh"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"; LicenseFile: "terms\terms_zh.txt"
Name: "ja"; MessagesFile: "compiler:Languages\Japanese.isl"; LicenseFile: "terms\terms_ja.txt"
Name: "ko"; MessagesFile: "compiler:Languages\Korean.isl"; LicenseFile: "terms\terms_ko.txt"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\FogTranslate\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Fog Translate"; Filename: "{app}\FogTranslate.exe"
Name: "{userdesktop}\Fog Translate"; Filename: "{app}\FogTranslate.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FogTranslate.exe"; Description: "{cm:LaunchProgram,Fog Translate}"; Flags: nowait postinstall skipifsilent
; an update from the program (/update=1, fogtranslate/relupdate.py install_args) runs silently: start it again
Filename: "{app}\FogTranslate.exe"; Flags: nowait; Check: IsUpdate

[Code]
const
  MutexName = 'Local\FogTranslate.Running';   { fogtranslate/relupdate.py MUTEX_NAME }
  UpdateWaitMs = 60000;

var
  Installed: Boolean;

function IsUpdate: Boolean;
begin
  Result := ExpandConstant('{param:update|0}') = '1';
end;

{ An update from the program: the program ends right after starting this setup - wait for it (at most a minute).
  An installation by hand is left to CloseApplications above. }
function InitializeSetup(): Boolean;
var
  Waited: Integer;
begin
  Installed := False;
  Result := True;
  if not IsUpdate then
    Exit;
  Waited := 0;
  while CheckForMutexes(MutexName) do
  begin
    if Waited >= UpdateWaitMs then
    begin
      Result := False;
      Exit;
    end;
    Sleep(250);
    Waited := Waited + 250;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    Installed := True;
end;

{ An update that did not finish starts the program that is still there again }
procedure DeinitializeSetup();
var
  Code: Integer;
  Dir: String;
begin
  if IsUpdate and (not Installed) then
  begin
    if not RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6B0C3E2A-5D0B-4C61-9E9A-2F7A6B1D4E77}_is1',
                               'Inno Setup: App Path', Dir) then
      Dir := ExpandConstant('{localappdata}\Programs\Fog Translate');
    if FileExists(Dir + '\FogTranslate.exe') then
      Exec(Dir + '\FogTranslate.exe', '', Dir, SW_SHOWNORMAL, ewNoWait, Code);
  end;
end;
