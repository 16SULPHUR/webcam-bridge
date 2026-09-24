# Builds the installer and the single-file portable exe into dist\.
#   pwsh packaging\windows\build.ps1 -VcamDir <dir with x64\ and x86\ DLLs> -Apk <webcam-bridge.apk>
# Needs Python 3.12 (64-bit) and Inno Setup 6.
param(
    [string]$VcamDir = "build\vcam-dist",
    [string]$Apk = "",
    [switch]$SkipInstaller
)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $Root

$Version = (python -c "import sys; sys.path.insert(0, 'desktop'); import webcam_bridge; print(webcam_bridge.__version__)").Trim()
$Stage = "build\stage"
$Portable = "dist\WebcamBridge-$Version-portable.exe"
Write-Host "Building Webcam Bridge $Version"

Remove-Item -Recurse -Force $Stage, "build\pyi", "build\adb-home", $Portable -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$Stage\platform-tools", "$Stage\android", "dist" | Out-Null

foreach ($arch in "x64", "x86") {
    $dll = Join-Path $VcamDir "$arch\webcam_bridge_cam.dll"
    if (-not (Test-Path $dll)) { throw "Missing $dll" }
    New-Item -ItemType Directory -Force "desktop\webcam_bridge\bin\$arch", "$Stage\vcam\$arch" | Out-Null
    Copy-Item $dll "desktop\webcam_bridge\bin\$arch\"
    Copy-Item $dll "$Stage\vcam\$arch\"
}

python -m pip install --upgrade pip
python -m pip install -e ".\desktop" pyinstaller
if ($LASTEXITCODE) { throw "pip install failed" }

$env:WEBCAM_BRIDGE_HOME = Join-Path $Root "build\adb-home"
python -m webcam_bridge fetch adb --force
if ($LASTEXITCODE) { throw "adb download failed" }
Copy-Item "build\adb-home\platform-tools\*" "$Stage\platform-tools\"
Remove-Item Env:\WEBCAM_BRIDGE_HOME

if ($Apk) {
    Copy-Item $Apk "$Stage\android\webcam-bridge.apk"
    $env:WEBCAM_BRIDGE_BUNDLE_APK = Resolve-Path "$Stage\android\webcam-bridge.apk"
} else {
    Write-Warning "No -Apk given; the app will be downloaded from the release on first use."
}

# One analysis builds both the installer's folder and the single-file portable exe.
$env:WEBCAM_BRIDGE_ONEFILE = "1"
$env:WEBCAM_BRIDGE_BUNDLE_ADB = Resolve-Path "$Stage\platform-tools"
python -m PyInstaller --noconfirm --distpath build\pyi\dist --workpath build\pyi\work packaging\pyinstaller\webcam-bridge.spec
if ($LASTEXITCODE) { throw "PyInstaller failed" }
Remove-Item Env:\WEBCAM_BRIDGE_ONEFILE, Env:\WEBCAM_BRIDGE_BUNDLE_ADB, Env:\WEBCAM_BRIDGE_BUNDLE_APK -ErrorAction SilentlyContinue
Move-Item build\pyi\dist\webcam-bridge "$Stage\app"
Move-Item build\pyi\dist\webcam-bridge-portable.exe $Portable

if (-not $SkipInstaller) {
    if (-not $Apk) { throw "The installer needs -Apk" }
    $iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
    if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
    if (-not (Test-Path $iscc)) {
        choco install innosetup --no-progress -y
        $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    }
    & $iscc "/DAppVersion=$Version" "/DStage=$Root\$Stage" "/DOutputDir=$Root\dist" packaging\windows\webcam-bridge.iss
    if ($LASTEXITCODE) { throw "Inno Setup failed" }
}

Get-ChildItem dist
