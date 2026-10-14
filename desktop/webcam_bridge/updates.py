"""
updates.py — Tell the user when a newer release is on GitHub.

Disable with --no-update-check or WEBCAM_BRIDGE_NO_UPDATE_CHECK=1.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import urllib.request

from . import __version__, paths

REPO = "16SULPHUR/webcam-bridge"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_URL = f"https://github.com/{REPO}/releases/download/v{{version}}"
SETUP_NAME = "WebcamBridge-Setup-{version}.exe"
PORTABLE_NAME = "WebcamBridge-{version}-portable.exe"
UPDATE_DIR = os.path.join(paths.DATA_DIR, "update")

exit_hook = None
_installing = threading.Lock()


def parse_version(text: str | None) -> tuple[int, ...]:
    """'v0.2.1' / '0.2.1-beta' -> (0, 2, 1); unparseable -> ()."""
    m = re.match(r"v?(\d+(?:\.\d+)*)", (text or "").strip())
    return tuple(int(p) for p in m.group(1).split(".")) if m else ()


def is_newer(candidate: str | None, current: str = __version__) -> bool:
    new, cur = parse_version(candidate), parse_version(current)
    return bool(new) and bool(cur) and new > cur


def latest_version(timeout: float = 5.0) -> str | None:
    req = urllib.request.Request(API_URL, headers={
        "User-Agent": f"webcam-bridge/{__version__}",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            tag = json.load(resp).get("tag_name")
    except Exception:
        return None
    return tag.lstrip("v") if isinstance(tag, str) else None


def install_kind() -> str | None:
    """How this copy can update itself: 'installer', 'portable', or None (pip / source)."""
    if sys.platform != "win32" or not paths.FROZEN:
        return None
    if paths.ONEFILE:
        return "portable"
    if os.path.isfile(os.path.join(paths.INSTALL_DIR, "unins000.exe")):
        return "installer"
    return None


def _download_verified(version: str, name: str, dest: str, progress) -> None:
    base = DOWNLOAD_URL.format(version=version)
    req = urllib.request.Request(f"{base}/SHA256SUMS.txt", headers={"User-Agent": f"webcam-bridge/{__version__}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        sums = resp.read().decode("utf-8", "replace")
    expected = next((line.split()[0] for line in sums.splitlines()
                     if line.split() and line.split()[-1].lstrip("*") == name), None)
    if not expected:
        raise OSError(f"{name} is not listed in SHA256SUMS.txt")

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    digest = hashlib.sha256()
    req = urllib.request.Request(f"{base}/{name}", headers={"User-Agent": f"webcam-bridge/{__version__}"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if total:
                progress(int(done * 100 / total))
    if digest.hexdigest() != expected:
        os.remove(dest)
        raise OSError(f"checksum mismatch for {name}")


def _apply_installer(path: str) -> None:
    subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS", "/UPDATE"],
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0), close_fds=True)


def _apply_portable(path: str) -> None:
    current = sys.executable
    old = current + ".old"
    if os.path.exists(old):
        os.remove(old)
    os.replace(current, old)
    try:
        os.replace(path, current)
    except OSError:
        os.replace(old, current)
        raise
    subprocess.Popen([current], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0), close_fds=True)


def cleanup_old_portable() -> None:
    if paths.ONEFILE:
        try:
            os.remove(sys.executable + ".old")
        except OSError:
            pass


def install_in_background(broadcaster, version: str) -> bool:
    """Download the release matching this install and hand over to it. False if one is already running."""
    kind = install_kind()
    if not kind or not _installing.acquire(blocking=False):
        return False

    def set_state(state: str, **extra) -> None:
        broadcaster.update_stats(updateState=state, **extra)
        broadcaster.broadcast_status()

    def run():
        try:
            name = (SETUP_NAME if kind == "installer" else PORTABLE_NAME).format(version=version)
            dest = os.path.join(UPDATE_DIR, name)
            set_state("downloading", updateProgress=0)
            last = [-1]

            def progress(pct: int) -> None:
                if pct != last[0]:
                    last[0] = pct
                    set_state("downloading", updateProgress=pct)

            _download_verified(version, name, dest, progress)
            set_state("installing")
            broadcaster.broadcast_log("system", f"[Update] Installing Webcam Bridge {version}")
            if kind == "installer":
                _apply_installer(dest)
            else:
                _apply_portable(dest)
        except Exception as exc:
            set_state("failed", updateError=str(exc))
            broadcaster.broadcast_log("system", f"[Update] Could not update: {exc}")
            _installing.release()
            return
        if exit_hook:
            try:
                exit_hook()
            except SystemExit:
                pass
        os._exit(0)

    threading.Thread(target=run, daemon=True, name="UpdateInstall").start()
    return True


def check_in_background(broadcaster) -> None:
    def run():
        latest = latest_version()
        if is_newer(latest):
            broadcaster.update_stats(updateAvailable=latest, updateInstallable=install_kind() is not None)
            broadcaster.broadcast_status()
            broadcaster.broadcast_log("system", f"[Update] Webcam Bridge {latest} is available: {RELEASES_URL}")

    threading.Thread(target=run, daemon=True, name="UpdateCheck").start()
