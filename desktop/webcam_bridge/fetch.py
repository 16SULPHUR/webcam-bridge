"""
fetch.py — Download optional third-party data into the user data directory.

    python -m webcam_bridge.fetch models   # MediaPipe models (also downloaded on first use)
    python -m webcam_bridge.fetch skins    # Neko skin library for custom pets
    python -m webcam_bridge.fetch vcam     # prebuilt virtual camera DLLs (source checkouts)
    python -m webcam_bridge.fetch all

The models are Google's (Apache-2.0) and the Neko skins are a community
collection without a stated license, so neither is bundled. The virtual camera
DLLs are this project's own, built by CI and attached to each GitHub release;
pip/zip installs from a release already contain them.
"""

import argparse
import hashlib
import io
import os
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m webcam_bridge.fetch", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("what", choices=("models", "skins", "vcam", "all"))
    parser.add_argument("--force", action="store_true", help="download again even if present")
    args = parser.parse_args(argv)

    try:
        if args.what in ("models", "all"):
            print("MediaPipe models:")
            fetch_models(args.force)
        if args.what in ("vcam", "all") and sys.platform == "win32":
            print("Virtual camera:")
            fetch_vcam(args.force)
        if args.what in ("skins", "all"):
            print("Neko skins:")
            fetch_skins(args.force)
    except OSError as exc:
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
