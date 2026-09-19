"""
setup_state.py — What the first-run wizard checks, and what it can fix itself.

The packaged build already carries Python, FFmpeg and the virtual camera, so
the only things left are machine- and phone-specific: registering the camera,
fetching platform-tools, and getting the phone plugged in with the app running.
Each step reports one of:

    ok       nothing to do
    todo     the user (or an action below) has to do something
    blocked  an earlier step has to pass first
    working  an action is running right now
    error    the last action failed

Actions run in a background thread so a slow download never blocks the HTTP
handler; the dashboard polls /api/setup and re-renders.
"""

import os
import shutil
import sys
import threading
import time
from typing import Callable, Optional

from . import adb, paths

RELEASES_PAGE = "https://github.com/16SULPHUR/webcam-bridge/releases/latest"
USB_DEBUG_HELP = "https://developer.android.com/studio/debug/dev-options"

# Each snapshot shells out to adb a few times, and the dashboard polls while
# the page is open. Share one result between pollers for this long.
SNAPSHOT_TTL = 2.0


# ── Background action runner ──────────────────────────────────────────────────

class ActionRunner:
    """Runs one wizard action at a time and remembers how it went."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running: Optional[str] = None
        self._message = ""
        self._error = ""

    def state(self) -> dict:
        with self._lock:
            return {"running": self._running, "message": self._message, "error": self._error}

    def start(self, name: str, work: Callable[[], str]) -> tuple[bool, str]:
        with self._lock:
            if self._running:
                return False, f"“{self._running}” is still running"
            self._running = name
            self._message = ""
            self._error = ""
        threading.Thread(target=self._run, args=(name, work), daemon=True,
                         name=f"Setup-{name}").start()
        return True, "started"

    def _run(self, name: str, work: Callable[[], str]) -> None:
        try:
            message = work()
            error = ""
        except Exception as exc:
            message = ""
            error = str(exc) or exc.__class__.__name__
        invalidate()
        with self._lock:
            if self._running == name:
                self._running = None
            self._message = message
            self._error = error


_runner = ActionRunner()


# ── Individual checks ─────────────────────────────────────────────────────────

def _ffmpeg_step() -> dict:
    ffmpeg = paths.resolve_ffmpeg()
    present = os.path.isfile(ffmpeg) or bool(shutil.which(ffmpeg))
    return {
        "id": "ffmpeg",
        "title": "Video decoder",
        "state": "ok" if present else "error",
        "detail": (f"FFmpeg ready ({os.path.basename(ffmpeg)})." if present else
                   "FFmpeg is missing. Reinstall Webcam Bridge, or set WEBCAM_BRIDGE_FFMPEG."),
    }


def _camera_step() -> dict:
    from . import vcam

    if not vcam.IS_WINDOWS:
        return {
            "id": "camera",
            "title": "Virtual camera",
            "state": "ok",
            "detail": "On this platform the bridge uses OBS / v4l2loopback instead.",
        }
    info = vcam.status()
    if info["installed"]:
        return {"id": "camera", "title": "Virtual camera", "state": "ok",
                "detail": f"“{info['name']}” is registered and ready to pick in Zoom, Teams or Meet."}
    if not info["available"]:
        return {"id": "camera", "title": "Virtual camera", "state": "error",
                "detail": "Camera files are missing from this install — reinstall Webcam Bridge."}
    return {
        "id": "camera",
        "title": "Virtual camera",
        "state": "todo",
        "detail": f"Install the “{info['name']}” camera so meeting apps can see this stream.",
        "action": "camera-install",
        "actionLabel": "Install camera",
        "actionNote": "Windows will ask for administrator permission.",
    }


def _adb_step() -> dict:
    exe = adb.path()
    if exe:
        where = "downloaded copy" if exe == paths.ADB_EXE else exe
        return {"id": "adb", "title": "Phone connection tools", "state": "ok",
                "detail": f"Android platform-tools ready ({where})."}
    return {
        "id": "adb",
        "title": "Phone connection tools",
        "state": "todo",
        "detail": "Android platform-tools (about 13 MB) talks to the phone over USB.",
        "action": "adb-download",
        "actionLabel": "Download platform-tools",
        "actionNote": "Downloaded from dl.google.com; needs internet once.",
    }


def _phone_step(blocked: bool) -> dict:
    step = {"id": "phone", "title": "Phone connected",
            "link": USB_DEBUG_HELP, "linkLabel": "How to enable USB debugging"}
    if blocked:
        return {**step, "state": "blocked", "detail": "Waiting for the connection tools."}
    state = adb.device_state()
    if state == "ready":
        return {**step, "state": "ok", "detail": "Phone is connected over USB and authorised."}
    if state == "unauthorized":
        return {**step, "state": "todo",
                "detail": "Phone found, but USB debugging is not authorised yet — tap "
                          "“Allow USB debugging” on the phone screen."}
    if state == "offline":
        return {**step, "state": "todo",
                "detail": "Phone is not responding. Unplug it, plug it back in, and unlock the screen."}
    return {**step, "state": "todo",
            "detail": "Plug the phone in over USB and turn on USB debugging in Developer options."}


def _app_step(blocked: bool) -> dict:
    step = {"id": "app", "title": "Phone app",
            "link": RELEASES_PAGE, "linkLabel": "Download the APK"}
    if blocked:
        return {**step, "state": "blocked", "detail": "Waiting for the phone."}
    if not adb.package_installed():
        return {**step, "state": "todo",
                "detail": "Install the Webcam Bridge APK on the phone, then press Re-check. "
                          "Open the release page, download the .apk and run it on the phone."}
    return {**step, "state": "ok", "detail": "Webcam Bridge is installed on the phone.",
            "action": "app-launch", "actionLabel": "Open it on the phone"}


def _stream_step(blocked: bool, connected: bool) -> dict:
    step = {"id": "stream", "title": "Video stream"}
    if blocked:
        return {**step, "state": "blocked", "detail": "Waiting for the phone app."}
    if connected:
        return {**step, "state": "ok", "detail": "Frames are arriving from the phone."}
    return {**step, "state": "todo",
            "detail": "Open Webcam Bridge on the phone and tap Start Streaming.",
            "action": "connect", "actionLabel": "Retry connection"}


# ── Snapshot ──────────────────────────────────────────────────────────────────

_snapshot_lock = threading.Lock()
_snapshot_cache: tuple[float, bool, dict] | None = None


def snapshot(android_connected: bool = False) -> dict:
    """Every step plus whether the bridge is good to go.

    The checks shell out to adb and the dashboard polls them, so their result
    is shared between callers for a moment. The running job is always current.
    """
    job = _runner.state()
    cached = _cached_steps(android_connected)
    steps = [dict(step) for step in cached["steps"]]
    for step in steps:
        if step.get("action") and step["action"] == job["running"]:
            step["state"] = "working"
    return {
        "steps": steps,
        "ready": cached["ready"],
        "job": job,
        "platform": sys.platform,
        "releases": RELEASES_PAGE,
    }


def _cached_steps(android_connected: bool) -> dict:
    global _snapshot_cache
    with _snapshot_lock:
        cached = _snapshot_cache
        if (cached is not None and cached[1] == android_connected
                and time.monotonic() - cached[0] < SNAPSHOT_TTL):
            return cached[2]
        data = _build_steps(android_connected)
        _snapshot_cache = (time.monotonic(), android_connected, data)
        return data


def _build_steps(android_connected: bool) -> dict:
    ffmpeg = _ffmpeg_step()
    camera = _camera_step()
    adb_step = _adb_step()
    phone = _phone_step(adb_step["state"] != "ok")
    app = _app_step(phone["state"] != "ok")
    stream = _stream_step(app["state"] != "ok", android_connected)
    steps = [ffmpeg, camera, adb_step, phone, app, stream]
    return {"steps": steps, "ready": all(s["state"] == "ok" for s in steps)}


# ── Actions ───────────────────────────────────────────────────────────────────

def _do_camera_install() -> str:
    from . import vcam
    return vcam.install()


def _do_adb_download() -> str:
    from .fetch import fetch_adb
    fetch_adb()
    if not adb.available():
        raise OSError("platform-tools was downloaded but adb still is not usable")
    return "Android platform-tools installed."


def _do_app_launch() -> str:
    if not adb.launch_app():
        raise OSError("Could not start the app — open Webcam Bridge on the phone yourself.")
    return "Opened Webcam Bridge on the phone."


def _do_connect(port: int) -> str:
    """Re-run the port forwards and nudge the app, the way the launcher does."""
    if not adb.forward_stream():
        raise OSError("adb forward failed — check that the phone is still plugged in.")
    adb.reverse_dashboard(port)
    adb.launch_app()
    return "Reconnected to the phone."


# Each action takes the dashboard port; most have no use for it.
ACTIONS: dict[str, Callable[[int], str]] = {
    "camera-install": lambda port: _do_camera_install(),
    "adb-download": lambda port: _do_adb_download(),
    "app-launch": lambda port: _do_app_launch(),
    "connect": _do_connect,
}


def start_action(name: str, port: int = 5134) -> tuple[bool, str]:
    work = ACTIONS.get(name)
    if work is None:
        return False, f"unknown action “{name}”"
    # A fix changes what the checks see, so do not serve a stale snapshot after it.
    invalidate()
    return _runner.start(name, lambda: work(port))


def invalidate() -> None:
    global _snapshot_cache
    with _snapshot_lock:
        _snapshot_cache = None
