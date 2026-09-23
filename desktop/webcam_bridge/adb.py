"""
adb.py — Locate adb, downloading Google's platform-tools on first use if needed.

Search order: WEBCAM_BRIDGE_ADB, PATH, next to the installed exe, the user data
directory, then a pinned download (the same approach scrcpy uses).
"""

import hashlib
import io
import os
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile

from . import paths

PLATFORM_TOOLS_VERSION = "37.0.0"
PLATFORM_TOOLS = {
    "win32": ("win", "4fe305812db074cea32903a489d061eb4454cbc90a49e8fea677f4b7af764918"),
    "linux": ("linux", "198ae156ab285fa555987219af237b31102fefe8b9d2bc274708a8d4f2865a07"),
    "darwin": ("darwin", "094a1395683c509fd4d48667da0d8b5ef4d42b2abfcd29f2e8149e2f989357c7"),
}
WINDOWS_FILES = ("adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll")
EXE = "adb.exe" if sys.platform == "win32" else "adb"

# Keep adb from flashing a console window when the bridge runs without one.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class AdbError(RuntimeError):
    pass


def _candidates() -> list[str]:
    found = []
    explicit = os.environ.get("WEBCAM_BRIDGE_ADB")
    if explicit:
        found.append(explicit)
    on_path = shutil.which("adb")
    if on_path:
        found.append(on_path)
    if paths.INSTALL_DIR:
        found.append(os.path.join(paths.INSTALL_DIR, "platform-tools", EXE))
    found.append(os.path.join(paths.TOOLS_DIR, EXE))
    return found


def find_adb() -> str | None:
    return next((p for p in _candidates() if os.path.isfile(p)), None)


def platform_tools_url() -> tuple[str, str]:
    key = "linux" if sys.platform.startswith("linux") else sys.platform
    if key not in PLATFORM_TOOLS:
        raise AdbError(f"No platform-tools build for {sys.platform}; install adb and put it on PATH.")
    name, sha256 = PLATFORM_TOOLS[key]
    return (f"https://dl.google.com/android/repository/platform-tools_r{PLATFORM_TOOLS_VERSION}-{name}.zip",
            sha256)


def download_adb(log=print) -> str:
    url, expected = platform_tools_url()
    log(f"Downloading Android platform-tools {PLATFORM_TOOLS_VERSION} (adb) ...")
    req = urllib.request.Request(url, headers={"User-Agent": "webcam-bridge"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except OSError as exc:
        raise AdbError(f"Could not download adb: {exc}") from exc
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise AdbError(f"platform-tools checksum mismatch (expected {expected}, got {actual})")

    wanted = WINDOWS_FILES if sys.platform == "win32" else (EXE,)
    os.makedirs(paths.TOOLS_DIR, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in wanted:
            dest = os.path.join(paths.TOOLS_DIR, name)
            with zf.open(f"platform-tools/{name}") as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            if sys.platform != "win32":
                os.chmod(dest, os.stat(dest).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    log(f"adb installed in {paths.TOOLS_DIR}")
    return os.path.join(paths.TOOLS_DIR, EXE)


def ensure_adb(log=print) -> str:
    return find_adb() or download_adb(log)


def run(adb: str, args: list[str], serial: str | None = None, timeout: float = 10.0) -> subprocess.CompletedProcess:
    cmd = [adb, *(["-s", serial] if serial else []), *args]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=NO_WINDOW)


def start_server(adb: str) -> None:
    """Start the adb daemon without pipes: a daemon inheriting ours would keep later calls waiting."""
    subprocess.run([adb, "start-server"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=30, creationflags=NO_WINDOW)


def list_devices(adb: str) -> list[tuple[str, str]]:
    """[(serial, state)] where state is device / unauthorized / offline / ..."""
    out = run(adb, ["devices"], timeout=15).stdout
    _, _, listing = out.partition("List of devices attached")
    return [tuple(line.split("\t")[:2]) for line in listing.splitlines() if line.count("\t") == 1]
