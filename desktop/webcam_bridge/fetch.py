"""
fetch.py — Download optional third-party data into the user data directory.

    python -m webcam_bridge.fetch models   # MediaPipe models (also downloaded on first use)
    python -m webcam_bridge.fetch skins    # Neko skin library for custom pets
    python -m webcam_bridge.fetch vcam     # prebuilt virtual camera DLLs (source checkouts)
    python -m webcam_bridge.fetch adb      # Android platform-tools (the setup wizard does this)
    python -m webcam_bridge.fetch all

The models are Google's (Apache-2.0) and the Neko skins are a community
collection without a stated license, so neither is bundled. Android
platform-tools is Google's too, and its SDK terms do not allow us to
redistribute it, so it is fetched from dl.google.com on demand. The virtual
camera DLLs are this project's own, built by CI and attached to each GitHub
release; pip/zip installs from a release already contain them.
"""

import argparse
import hashlib
import io
import os
import shutil
import stat
import sys
import tarfile
import urllib.request
import zipfile

from . import paths
from .models import MODEL_URLS

SKINS_TARBALL = "https://codeload.github.com/eliot-akira/neko/tar.gz/refs/heads/main"
SKINS_SUBDIR = "2023-icon-library"

RELEASES = "https://github.com/16SULPHUR/webcam-bridge/releases/latest/download"
VCAM_ZIP = "webcam-bridge-vcam.zip"

# Google publishes only a moving "latest" build, with no checksum alongside it,
# so the download is trusted on HTTPS and then sanity-checked for adb itself.
PLATFORM_TOOLS_URLS = {
    "win32":  "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
    "darwin": "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip",
    "linux":  "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
}
PLATFORM_TOOLS_PREFIX = "platform-tools/"


def _download(url: str) -> bytes:
    print(f"  downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "webcam-bridge"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def fetch_models(force: bool = False) -> None:
    os.makedirs(paths.MODELS_DIR, exist_ok=True)
    for name, url in MODEL_URLS.items():
        dest = os.path.join(paths.MODELS_DIR, name)
        if os.path.isfile(dest) and not force:
            print(f"  {name} already present")
            continue
        data = _download(url)
        with open(dest, "wb") as fh:
            fh.write(data)
        print(f"  saved {dest} ({len(data) // 1024} KiB)")


def fetch_skins(force: bool = False) -> None:
    os.makedirs(paths.SKINS_DIR, exist_ok=True)
    if os.listdir(paths.SKINS_DIR) and not force:
        print(f"  skins already present in {paths.SKINS_DIR} (use --force to refresh)")
        return
    print("  Neko skins come from https://github.com/eliot-akira/neko — a community")
    print("  collection with no stated license, downloaded here for personal use only.")
    data = _download(SKINS_TARBALL)
    count = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            parts = member.name.split("/")
            # <repo>-main/2023-icon-library/<skin>/<frame>.png
            if len(parts) != 4 or parts[1] != SKINS_SUBDIR or not member.isfile():
                continue
            if not parts[3].lower().endswith(".png"):
                continue
            dest = paths.safe_join(paths.SKINS_DIR, os.path.join(parts[2], parts[3]))
            if dest is None:
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with tar.extractfile(member) as src, open(dest, "wb") as out:
                out.write(src.read())
            count += 1
    print(f"  extracted {count} frames into {paths.SKINS_DIR}")


def fetch_vcam(force: bool = False) -> None:
    from .vcam import DLL_NAME

    target = os.path.join(paths.VCAM_BUNDLED_DIR, "x64", DLL_NAME)
    if os.path.isfile(target) and not force:
        print(f"  already present in {paths.VCAM_BUNDLED_DIR}")
        return
    data = _download(f"{RELEASES}/{VCAM_ZIP}")
    sums = _download(f"{RELEASES}/SHA256SUMS.txt").decode("utf-8", "replace")
    expected = next((line.split()[0] for line in sums.splitlines()
                     if line.strip().endswith(VCAM_ZIP)), None)
    actual = hashlib.sha256(data).hexdigest()
    if expected != actual:
        raise OSError(f"checksum mismatch for {VCAM_ZIP} (expected {expected}, got {actual})")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            arch, _, fname = name.partition("/")
            if arch not in ("x64", "x86") or fname != DLL_NAME:
                continue
            dest = os.path.join(paths.VCAM_BUNDLED_DIR, arch, DLL_NAME)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as out:
                out.write(zf.read(name))
            print(f"  saved {dest}")
    print("  next: webcam-bridge camera install")


def fetch_adb(force: bool = False) -> None:
    """Install Android platform-tools into the user data directory."""
    if os.path.isfile(paths.ADB_EXE) and not force:
        print(f"  adb already present at {paths.ADB_EXE}")
        return
    url = PLATFORM_TOOLS_URLS.get(sys.platform)
    if url is None:
        raise OSError(f"no platform-tools build for {sys.platform} — install adb yourself")

    data = _download(url)
    staging = paths.ADB_DIR + ".new"
    shutil.rmtree(staging, ignore_errors=True)
    exe_name = os.path.basename(paths.ADB_EXE)
    found_adb = False
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for member in zf.infolist():
            if member.is_dir() or not member.filename.startswith(PLATFORM_TOOLS_PREFIX):
                continue
            rel = member.filename[len(PLATFORM_TOOLS_PREFIX):]
            dest = paths.safe_join(staging, rel)
            if dest is None:
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(member) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            if os.path.basename(dest) == exe_name:
                found_adb = True
            if not sys.platform.startswith("win"):
                os.chmod(dest, os.stat(dest).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    if not found_adb:
        shutil.rmtree(staging, ignore_errors=True)
        raise OSError(f"{url} did not contain {exe_name}")

    # Swap in atomically-ish: a half-extracted platform-tools is worse than none.
    shutil.rmtree(paths.ADB_DIR, ignore_errors=True)
    os.replace(staging, paths.ADB_DIR)
    print(f"  installed adb into {paths.ADB_DIR}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m webcam_bridge.fetch", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("what", choices=("models", "skins", "vcam", "adb", "all"))
    parser.add_argument("--force", action="store_true", help="download again even if present")
    args = parser.parse_args(argv)

    try:
        if args.what in ("models", "all"):
            print("MediaPipe models:")
            fetch_models(args.force)
        if args.what in ("vcam", "all") and sys.platform == "win32":
            print("Virtual camera:")
            fetch_vcam(args.force)
        if args.what in ("adb", "all"):
            print("Android platform-tools:")
            fetch_adb(args.force)
        if args.what in ("skins", "all"):
            print("Neko skins:")
            fetch_skins(args.force)
    except OSError as exc:
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
