# Builds the standalone app, the portable zip and the installer into dist\.
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
$Portable = "WebcamBridge-$Version-windows-x64"
Write-Host "Building Webcam Bridge $Version"

Remove-Item -Recurse -Force $Stage, "build\pyi", "dist\$Portable" -ErrorAction SilentlyContinue
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

python -m PyInstaller --noconfirm --distpath build\pyi\dist --workpath build\pyi\work packaging\pyinstaller\webcam-bridge.spec
if ($LASTEXITCODE) { throw "PyInstaller failed" }
Move-Item build\pyi\dist\webcam-bridge "$Stage\app"

$env:WEBCAM_BRIDGE_HOME = Join-Path $Root "build\adb-home"
& "$Stage\app\webcam-bridge.exe" fetch adb --force
if ($LASTEXITCODE) { throw "adb download failed" }
Copy-Item "build\adb-home\platform-tools\*" "$Stage\platform-tools\"
Remove-Item Env:\WEBCAM_BRIDGE_HOME

if ($Apk) {
    Copy-Item $Apk "$Stage\android\webcam-bridge.apk"
} else {
    Write-Warning "No -Apk given; the app will be downloaded from the release on first use."
}

# Portable zip: same layout as the installed folder.
New-Item -ItemType Directory -Force "dist\$Portable" | Out-Null
Copy-Item -Recurse "$Stage\app\*" "dist\$Portable\"
Copy-Item -Recurse "$Stage\platform-tools" "dist\$Portable\"
if ($Apk) { Copy-Item -Recurse "$Stage\android" "dist\$Portable\" }
Compress-Archive -Force "dist\$Portable" "dist\$Portable.zip"
Remove-Item -Recurse -Force "dist\$Portable"

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
