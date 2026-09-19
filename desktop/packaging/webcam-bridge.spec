# webcam-bridge.spec — PyInstaller recipe for the packaged Windows app.
#
#     cd desktop && pyinstaller packaging/webcam-bridge.spec --noconfirm
#
# Produces dist/WebcamBridge/, a self-contained folder: CPython, every wheel,
# a known-good FFmpeg and the virtual camera DLLs. Android platform-tools is
# deliberately *not* here — Google's SDK terms do not let us redistribute it,
# so the setup wizard downloads it on first run.

import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = os.path.dirname(SPECPATH)          # desktop/
PKG = os.path.join(ROOT, "webcam_bridge")

datas = [
    (os.path.join(PKG, "web"), "webcam_bridge/web"),
    (os.path.join(PKG, "assets"), "webcam_bridge/assets"),
]
# Built by the vcam CI job and dropped in before packaging.
if os.path.isdir(os.path.join(PKG, "bin")):
    datas.append((os.path.join(PKG, "bin"), "webcam_bridge/bin"))

# MediaPipe carries its graphs and .tflite models as package data.
datas += collect_data_files("mediapipe")
datas += collect_data_files("pyvirtualcam")

binaries = collect_dynamic_libs("mediapipe") + collect_dynamic_libs("pyvirtualcam")

# FFmpeg is bundled so a fresh install decodes video without touching the
# network. paths.py looks for it at exactly this spot. Prefer the LGPL build
# fetch_ffmpeg.py puts in packaging/ffmpeg — that is the one we may ship; the
# imageio-ffmpeg fallback is GPL and only for local test builds.
FFMPEG_DIR = os.path.join(SPECPATH, "ffmpeg")
if os.path.isfile(os.path.join(FFMPEG_DIR, "ffmpeg.exe")):
    binaries.append((os.path.join(FFMPEG_DIR, "ffmpeg.exe"), "ffmpeg"))
    datas.append((os.path.join(FFMPEG_DIR, "LICENSE.txt"), "ffmpeg"))
else:
    import imageio_ffmpeg

    print("WARNING: packaging a GPL FFmpeg — run packaging/fetch_ffmpeg.py before releasing.")
    binaries.append((imageio_ffmpeg.get_ffmpeg_exe(), "ffmpeg"))

hiddenimports = collect_submodules("webcam_bridge") + collect_submodules("mediapipe") + [
    "pyvirtualcam",
    "imageio_ffmpeg",
]

a = Analysis(
    [os.path.join(SPECPATH, "entry.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Torch is the optional RVM engine only; bundling it would add gigabytes.
    excludes=["torch", "torchvision", "tkinter", "pytest", "matplotlib"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WebcamBridge",
    debug=False,
    strip=False,
    upx=False,
    # No console: the dashboard is the UI, and launcher.py sends prints to
    # %LOCALAPPDATA%\WebcamBridge\webcam-bridge.log.
    console=False,
    icon=os.path.join(SPECPATH, "webcam-bridge.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="WebcamBridge",
)
