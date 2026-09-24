# Standalone build: pyinstaller packaging/pyinstaller/webcam-bridge.spec
# Produces dist/webcam-bridge/ (the folder the installer ships) and, with
# WEBCAM_BRIDGE_ONEFILE=1, dist/webcam-bridge-portable(.exe): the same app in one file.
# WEBCAM_BRIDGE_BUNDLE_ADB (a platform-tools folder) and WEBCAM_BRIDGE_BUNDLE_APK go inside the single file.
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
ICON = os.path.join(ROOT, "packaging", "windows", "webcam-bridge.ico")
ICON = ICON if sys.platform == "win32" and os.path.isfile(ICON) else None

# mediapipe loads its native library and models by path, so ship the whole package.
mp_datas, mp_binaries, mp_hidden = collect_all("mediapipe")

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[os.path.join(ROOT, "desktop")],
    datas=collect_data_files("webcam_bridge") + mp_datas,
    binaries=mp_binaries,
    hiddenimports=collect_submodules("webcam_bridge") + mp_hidden,
    excludes=["torch", "torchvision", "pytest"],
)
pyz = PYZ(a.pure)

# Windowed: the dashboard opens in its own window; CLI commands attach to the terminal (see ui.py).
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="webcam-bridge",
    console=False,
    icon=ICON,
)
coll = COLLECT(exe, a.binaries, a.datas, name="webcam-bridge")

if os.environ.get("WEBCAM_BRIDGE_ONEFILE") == "1":
    bundled = []
    adb_dir = os.environ.get("WEBCAM_BRIDGE_BUNDLE_ADB")
    if adb_dir:
        bundled += [(os.path.join("platform-tools", f), os.path.join(adb_dir, f), "DATA") for f in os.listdir(adb_dir)]
    apk = os.environ.get("WEBCAM_BRIDGE_BUNDLE_APK")
    if apk:
        bundled.append((os.path.join("android", "webcam-bridge.apk"), apk, "DATA"))
    EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas + bundled,
        name="webcam-bridge-portable",
        console=False,
        icon=ICON,
    )
