; webcam-bridge.iss — Inno Setup script for the one-click Windows installer.
;
;   iscc /DAppVersion=0.1.1 packaging\windows\webcam-bridge.iss
;
; Expects desktop\dist\WebcamBridge\ to exist (see desktop\packaging\webcam-bridge.spec).
; The installer runs elevated, so the virtual camera is registered here and the
; user never sees a second administrator prompt.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "Webcam Bridge"
#define AppExe "WebcamBridge.exe"
#define AppPublisher "Webcam Bridge contributors"
#define AppUrl "https://github.com/16SULPHUR/webcam-bridge"

[Setup]
AppId={{9C4B5E21-7F3A-4D68-9A1C-6B2E0D5F7A31}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=..\..\dist
OutputBaseFilename=WebcamBridge-Setup-{#AppVersion}
LicenseFile=..\..\LICENSE
SetupIconFile=..\..\desktop\packaging\webcam-bridge.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Registering the DirectShow camera writes to HKLM.
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
MinVersion=10.0
DisableDirPage=auto
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\..\desktop\dist\WebcamBridge\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; The app registers its own camera, so installer and dashboard share one code path.
Filename: "{app}\{#AppExe}"; Parameters: "camera install"; \
    StatusMsg: "Installing the Webcam Bridge virtual camera..."; \
    Flags: runhidden waituntilterminated
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#AppExe}"; Parameters: "camera uninstall"; \
    RunOnceId: "UnregisterCamera"; Flags: runhidden waituntilterminated

[UninstallDelete]
; Copies the camera install made outside {app}; settings and recordings stay put.
Type: filesandordirs; Name: "{commonappdata}\WebcamBridge\vcam"

[Messages]
WelcomeLabel2=This installs {#AppName} {#AppVersion} — the desktop bridge, FFmpeg and the Webcam Bridge virtual camera.%n%nAfterwards, plug in your phone and the app walks you through the rest.
