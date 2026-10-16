; PokeBrawl Windows installer (Inno Setup 6). Built by the release workflow:
;   iscc /DAppVersion=1.0.0 /DSrc=dist\PokeBrawl-windows /DOut=dist /DIcon=build\PokeBrawl.ico tools\PokeBrawl.iss
; Installs for the current user only (no admin prompt), adds Start menu + Desktop shortcuts. The game's own updater
; runs it silently (/VERYSILENT) and it reopens the game afterwards.
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{7E1C2B6A-4F0B-4C7E-9B7D-5A1B0C9E8D21}
AppName=PokeBrawl
AppVersion={#AppVersion}
AppPublisher=PokeBrawl
DefaultDirName={localappdata}\Programs\PokeBrawl
DefaultGroupName=PokeBrawl
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir={#Out}
OutputBaseFilename=PokeBrawl-windows-setup
SetupIconFile={#Icon}
UninstallDisplayIcon={app}\PokeBrawl.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; Flags: checkedonce

[Files]
Source: "{#Src}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\*"

[Icons]
Name: "{group}\PokeBrawl"; Filename: "{app}\PokeBrawl.exe"
Name: "{userdesktop}\PokeBrawl"; Filename: "{app}\PokeBrawl.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PokeBrawl.exe"; Description: "Play PokeBrawl"; Flags: nowait postinstall
