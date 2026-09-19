"""
adb.py — One place to find and drive the Android Debug Bridge.

The packaged build does not ship platform-tools (Google's SDK terms restrict
redistributing it), so the setup wizard downloads it into the user data
directory on first run. A system adb on PATH is used when there is one.

Every helper is failure-tolerant: a missing phone, a missing adb or a denied
USB-debugging prompt returns a falsy result instead of raising, because the
wizard turns those into the next thing for the user to do.
"""

import os
import shutil
import subprocess
import sys
from typing import List, Optional, Tuple

from . import paths

APP_ID = "io.github.sulphur16.webcambridge"
MAIN_ACTIVITY = ".MainActivity"
STREAM_PORT = 8080

# The states `adb devices` can report for a line that really is a device.
DEVICE_STATES = ("device", "unauthorized", "offline", "recovery",
                 "sideload", "bootloader", "authorizing", "connecting")

# Keep adb's console window from flashing up in front of the packaged app.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def path() -> Optional[str]:
    """The adb executable to use, or None when there is none."""
    explicit = os.environ.get("WEBCAM_BRIDGE_ADB")
    if explicit and os.path.isfile(explicit):
        return explicit
    if os.path.isfile(paths.ADB_EXE):
        return paths.ADB_EXE
    return shutil.which("adb")


def available() -> bool:
    return path() is not None


def run(args: List[str], timeout: float = 5.0) -> Optional[str]:
    """Run an adb command and return its stdout, or None if it failed."""
    exe = path()
    if exe is None:
        return None
    try:
        result = subprocess.run([exe] + list(args), capture_output=True, text=True,
                                timeout=timeout, creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def devices() -> List[Tuple[str, str]]:
    """[(serial, state)] as reported by `adb devices`.

    Starting the adb daemon prints its own chatter into this listing, so only
    lines ending in a state adb actually reports are taken.
    """
    out = run(["devices"], timeout=15.0)
    if out is None:
        return []
    found = []
    for line in out.splitlines()[1:]:
        serial, tab, state = line.partition("\t")
        if tab and state.strip() in DEVICE_STATES:
            found.append((serial.strip(), state.strip()))
    return found


def device_state() -> str:
    """'ready', 'unauthorized', 'offline' or 'none' — what the wizard shows."""
    if not available():
        return "none"
    states = [state for _, state in devices()]
    for wanted in ("device", "unauthorized"):
        if wanted in states:
            return "ready" if wanted == "device" else "unauthorized"
    return "offline" if states else "none"


def package_installed(app_id: str = APP_ID) -> bool:
    out = run(["shell", "pm", "path", app_id], timeout=15.0)
    return bool(out and out.startswith("package:"))


def launch_app(app_id: str = APP_ID) -> bool:
    return run(["shell", "am", "start", "-n", f"{app_id}/{MAIN_ACTIVITY}"], timeout=15.0) is not None


def forward_stream() -> bool:
    """Phone's H.264 server → this PC. Required for the video stream."""
    return run(["forward", f"tcp:{STREAM_PORT}", f"tcp:{STREAM_PORT}"], timeout=15.0) is not None


def reverse_dashboard(port: int) -> bool:
    """Dashboard → phone, so the app's remote control can use 127.0.0.1."""
    return run(["reverse", f"tcp:{port}", f"tcp:{port}"], timeout=15.0) is not None


def wait_for_device(timeout: float = 10.0) -> bool:
    return run(["wait-for-device"], timeout=timeout) is not None
