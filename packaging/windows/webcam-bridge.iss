; Windows installer. Built by .github/workflows/release.yml; locally:
;   iscc /DAppVersion=0.2.0 /DStage=..\..\build\stage packaging\windows\webcam-bridge.iss
; Stage layout: app\ (PyInstaller output), platform-tools\, android\webcam-bridge.apk, vcam\x64|x86\

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Stage
  #define Stage "..\..\build\stage"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist"
#endif

#define AppName "Webcam Bridge"
#define AppExe "webcam-bridge.exe"
#define AppUrl "https://github.com/16SULPHUR/webcam-bridge"

[Setup]
AppId={{6B1F3C0E-8E7A-4B63-9C1B-0F5D2B7A9E41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Webcam Bridge contributors
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
OutputDir={#OutputDir}
OutputBaseFilename=WebcamBridge-Setup-{#AppVersion}
SetupIconFile=webcam-bridge.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#Stage}\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Stage}\platform-tools\*"; DestDir: "{app}\platform-tools"; Flags: ignoreversion
Source: "{#Stage}\android\webcam-bridge.apk"; DestDir: "{app}\android"; Flags: ignoreversion
; The "Webcam Bridge" camera, registered where `webcam-bridge camera install` would put it.
Source: "{#Stage}\vcam\x64\webcam_bridge_cam.dll"; DestDir: "{commonappdata}\WebcamBridge\vcam\x64"; Flags: ignoreversion regserver 64bit restartreplace uninsrestartdelete
Source: "{#Stage}\vcam\x86\webcam_bridge_cam.dll"; DestDir: "{commonappdata}\WebcamBridge\vcam\x86"; Flags: ignoreversion regserver 32bit restartreplace uninsrestartdelete

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} (troubleshoot)"; Filename: "{app}\{#AppExe}"; Parameters: "doctor"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\platform-tools\adb.exe"; Parameters: "kill-server"; Flags: runhidden skipifdoesntexist; RunOnceId: "KillAdb"

[Code]
// A running adb server from a previous install would lock platform-tools\adb.exe.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  Exec(ExpandConstant('{app}\platform-tools\adb.exe'), 'kill-server', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Result := '';
end;
