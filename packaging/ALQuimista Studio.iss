; Inno Setup configuration for the installed Windows distribution.
#define AppName "ALQuimista Studio"
#ifndef AppVersion
  #define AppVersion "5.0.0"
#endif
#ifndef AppExeSource
  #define AppExeSource "..\\.tmp\\pyinstaller-dist\\ALQuimista Studio.exe"
#endif
#define AppExeName "ALQuimista Studio.exe"

[Setup]
AppId={{8E8DDBE4-AD5F-4F55-9D9F-5A1C0B6D4E20}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\ALQuimista Studio
DefaultGroupName={#AppName}
OutputDir=..\dist\releases
OutputBaseFilename=ALQuimista-Studio-windows-installer-{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "{#AppExeSource}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\distribuicao\LEIA-ME-PORTATIL.txt"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{userappdata}\ALQuimista Studio"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  LanguageCode: String;
begin
  if CurStep = ssPostInstall then begin
    if ActiveLanguage = 'english' then
      LanguageCode := 'en'
    else if ActiveLanguage = 'spanish' then
      LanguageCode := 'es'
    else
      LanguageCode := 'pt-BR';
    SetIniString('preferences', 'language', LanguageCode,
      ExpandConstant('{userappdata}\ALQuimista Studio\settings.ini'));
  end;
end;
