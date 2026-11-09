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
AppPublisher=sarujansa
AppPublisherURL=https://github.com/sarujansa/fog-translate
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
LicenseFile=..\LICENSE
CloseApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\FogTranslate\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Fog Translate"; Filename: "{app}\FogTranslate.exe"
Name: "{userdesktop}\Fog Translate"; Filename: "{app}\FogTranslate.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FogTranslate.exe"; Description: "{cm:LaunchProgram,Fog Translate}"; Flags: nowait postinstall skipifsilent
