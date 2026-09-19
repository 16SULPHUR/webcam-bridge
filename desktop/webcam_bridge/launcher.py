"""
launcher.py — The one thing the Windows shortcut runs.

Everything scripts/start.bat used to do, minus the terminal: create the user
directories, make sure adb is there, wire up the USB port forwards, nudge the
phone app and open the dashboard.

Nothing in the preparation step is fatal. Whatever could not be done shows up
in the dashboard's Setup page with a button to fix it, so the bridge always
comes up and the user always has somewhere to look.

    python -m webcam_bridge.launcher [--no-browser] [bridge options...]
"""

import os
import socket
import sys
import threading
import time
import webbrowser

from . import adb, paths
from .config import DASHBOARD_PORT

LOG_NAME = "webcam-bridge.log"
LOG_MAX_BYTES = 4 * 1024 * 1024
DASHBOARD_WAIT = 30.0


def _redirect_output_to_log() -> None:
    """A windowed build has no console; keep the prints instead of losing them."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_path = os.path.join(paths.DATA_DIR, LOG_NAME)
    try:
        if os.path.isfile(log_path) and os.path.getsize(log_path) > LOG_MAX_BYTES:
            os.replace(log_path, log_path + ".old")
        stream = open(log_path, "a", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        stream = open(os.devnull, "w")
    sys.stdout = sys.stdout or stream
    sys.stderr = sys.stderr or stream


def _port_for(argv: list) -> int:
    """The port the bridge will bind, matching __main__'s own precedence."""
    for i, arg in enumerate(argv):
        if arg == "--port" and i + 1 < len(argv):
            try:
                return int(argv[i + 1])
            except ValueError:
                break
        if arg.startswith("--port="):
            try:
                return int(arg.split("=", 1)[1])
            except ValueError:
                break
    try:
        return int(os.environ.get("WEBCAM_BRIDGE_PORT") or DASHBOARD_PORT)
    except ValueError:
        return DASHBOARD_PORT


def prepare_phone(port: int) -> None:
    """Get adb and the USB forwards in place. Best effort, never raises."""
    if not adb.available():
        print("[Launcher] Android platform-tools missing - downloading...")
        try:
            from .fetch import fetch_adb
            fetch_adb()
        except Exception as exc:
            print(f"[Launcher] Could not install platform-tools: {exc}")
            return

    if adb.device_state() != "ready":
        print("[Launcher] No phone yet - the Setup page will wait for it.")
        return

    if adb.forward_stream():
        print("[Launcher] USB stream forward ready")
    if not adb.reverse_dashboard(port):
        print("[Launcher] adb reverse failed - phone remote control needs Wi-Fi mode.")
    if adb.launch_app():
        print("[Launcher] Opened Webcam Bridge on the phone")


def _dashboard_is_up(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def open_dashboard(port: int) -> None:
    """Wait for the HTTP server to bind, then show it."""
    deadline = time.monotonic() + DASHBOARD_WAIT
    while time.monotonic() < deadline:
        if _dashboard_is_up(port):
            webbrowser.open(f"http://localhost:{port}")
            return
        time.sleep(0.25)
    print("[Launcher] Dashboard did not come up in time - not opening a browser.")


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    open_browser = "--no-browser" not in argv
    argv = [a for a in argv if a != "--no-browser"]

    from .__main__ import SUBCOMMANDS, main as run_bridge

    paths.ensure_user_dirs()
    _redirect_output_to_log()

    # `WebcamBridge.exe camera install` and friends are one-shot commands (the
    # installer uses them); they get none of the launcher's background work.
    if not any(a in SUBCOMMANDS for a in argv):
        port = _port_for(argv)
        threading.Thread(target=prepare_phone, args=(port,), daemon=True, name="Prepare").start()
        if open_browser:
            threading.Thread(target=open_dashboard, args=(port,), daemon=True, name="OpenBrowser").start()

    run_bridge(argv)


if __name__ == "__main__":
    main()
