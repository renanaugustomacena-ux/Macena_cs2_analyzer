; =====================================================================
; MACENA CS2 ANALYZER - INNO SETUP SCRIPT
; =====================================================================

[Setup]
AppId={{D3B3E1A2-5678-4CDE-9012-3456789ABCDE}
AppName=Macena CS2 Analyzer
; P10-02: Must match pyproject.toml [project].version on every release
AppVersion=1.0.0
AppPublisher=Macena
DefaultDirName={autopf}\Macena_CS2_Analyzer
DefaultGroupName=Macena CS2 Analyzer
AllowNoIcons=yes
; Output location
OutputDir=..\dist
OutputBaseFilename=Macena_CS2_Installer
Compression=lzma
SolidCompression=yes
WizardStyle=modern
DiskSpanning=yes
DiskClusterSize=512

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copy all files from the PyInstaller dist folder
Source: "..\dist\Macena_CS2_Analyzer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Macena CS2 Analyzer"; Filename: "{app}\Macena_CS2_Analyzer.exe"
Name: "{group}\{cm:UninstallProgram,Macena CS2 Analyzer}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Macena CS2 Analyzer"; Filename: "{app}\Macena_CS2_Analyzer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Macena_CS2_Analyzer.exe"; Description: "{cm:LaunchProgram,Macena CS2 Analyzer}"; Flags: nowait postinstall skipifsilent
