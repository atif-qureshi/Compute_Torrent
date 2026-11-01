#ifndef AppVersion
  #define AppVersion "2026.11.01-update2"
#endif

[Setup]
AppId={{A50D8A04-BCBA-4B3A-9AB9-5D5CF80DDB86}
AppName=ComputeTorrent Provider
AppVersion={#AppVersion}
AppPublisher=ComputeTorrent
DefaultDirName={localappdata}\Programs\ComputeTorrent
DefaultGroupName=ComputeTorrent
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=ComputeTorrent-Provider-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\ComputeTorrent_Seeder.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\ComputeTorrent_Seeder.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
Type: files; Name: "{userprograms}\ComputeTorrent Seeder.lnk"

[Icons]
Name: "{group}\ComputeTorrent Provider"; Filename: "{app}\ComputeTorrent_Seeder.exe"; IconFilename: "{app}\icon.ico"
Name: "{autodesktop}\ComputeTorrent Provider"; Filename: "{app}\ComputeTorrent_Seeder.exe"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\ComputeTorrent_Seeder.exe"; Description: "Launch ComputeTorrent Provider"; Flags: nowait postinstall skipifsilent
