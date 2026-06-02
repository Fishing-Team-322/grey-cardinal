#define MyAppName "Grey Cardinal Agent"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Grey Cardinal"
#define MyAppExeName "grey-cardinal-agent.exe"

[Setup]
AppId={{8A9E0D93-AE63-4F54-AB86-1D447F18E928}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Grey Cardinal Agent
DefaultGroupName=Grey Cardinal Agent
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=GreyCardinalAgentSetup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "autostart"; Description: "Start Grey Cardinal Agent on login"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "..\..\build\Release\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\config.example.toml"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Grey Cardinal Agent"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--config ""{app}\config.example.toml"""
Name: "{autodesktop}\Grey Cardinal Agent"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--config ""{app}\config.example.toml"""; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "GreyCardinalAgent"; ValueData: """{app}\{#MyAppExeName}"" --config ""{app}\config.example.toml"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--help"; Description: "Show Grey Cardinal Agent help"; Flags: postinstall skipifsilent nowait unchecked
