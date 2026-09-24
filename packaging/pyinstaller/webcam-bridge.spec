# Standalone build: pyinstaller packaging/pyinstaller/webcam-bridge.spec
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
ICON = os.path.join(ROOT, "packaging", "windows", "webcam-bridge.ico")

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
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="webcam-bridge",
    console=True,
    icon=ICON if sys.platform == "win32" and os.path.isfile(ICON) else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="webcam-bridge")
