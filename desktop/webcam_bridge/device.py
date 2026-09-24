"""
device.py — Plug-and-play phone handling over USB.

Watches `adb devices` and, for each phone that shows up:
  1. installs or updates the Webcam Bridge app (bundled or downloaded APK)
  2. forwards the camera stream (tcp:8080) and reverses the dashboard port
  3. launches the app straight into streaming

State is published to the dashboard as deviceState / deviceHint.
"""

import os
import re
import subprocess
import threading
import time
from typing import Optional

from . import __version__, adb, paths
from .updates import parse_version

APP_ID = "io.github.sulphur16.webcambridge"
STREAM_PORT = 8080
POLL_INTERVAL = 2.0
ADB_RETRY_INTERVAL = 60.0

HINTS = {
    "no-adb": "adb could not be set up. Install Android platform-tools, or set WEBCAM_BRIDGE_ADB.",
    "no-device": "Plug your phone in with a USB cable and turn on USB debugging.",
    "unauthorized": "Unlock your phone and tap Allow on the USB debugging prompt.",
    "offline": "The phone is not responding to adb. Unplug it and plug it back in.",
    "installing": "Installing the Webcam Bridge app on your phone...",
    "no-app": "Install the Webcam Bridge app on your phone (see the Releases page).",
    "ready": "Phone connected. Waiting for the camera stream...",
}


def find_apk() -> Optional[str]:
    candidates = [os.environ.get("WEBCAM_BRIDGE_APK")]
    if paths.INSTALL_DIR:
        candidates.append(os.path.join(paths.INSTALL_DIR, "android", "webcam-bridge.apk"))
    candidates.append(os.path.join(paths.APK_CACHE_DIR, f"webcam-bridge-{__version__}.apk"))
    return next((p for p in candidates if p and os.path.isfile(p)), None)


def installed_app_version(adb_path: str, serial: str) -> Optional[str]:
    """versionName of the app on the phone, '' if installed without one, None if absent."""
    out = adb.run(adb_path, ["shell", "dumpsys", "package", APP_ID], serial).stdout
    if f"Package [{APP_ID}]" not in out:
        return None
    m = re.search(r"versionName=(\S+)", out)
    return m.group(1) if m else ""


class DeviceManager:
    def __init__(self, broadcaster, dashboard_port: int, auto_install: bool = True) -> None:
        self._bc = broadcaster
        self._dashboard_port = dashboard_port
        self._auto_install = auto_install
        self._running = False
        self._adb: Optional[str] = None
        self._serial: Optional[str] = None
        self._state: Optional[str] = None
        self._install_failed: set[str] = set()
        self._announced: set[str] = set()

    @property
    def serial(self) -> Optional[str]:
        return self._serial

    def adb_command(self) -> Optional[list[str]]:
        """Base command for talking to the active phone, or None when there isn't one."""
        if not (self._adb and self._serial):
            return None
        return [self._adb, "-s", self._serial]

    def start(self) -> None:
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="DeviceManager").start()

    def stop(self) -> None:
        self._running = False

    def _log(self, msg: str) -> None:
        self._bc.broadcast_log("system", f"[Phone] {msg}")

    def _set_state(self, state: str, hint: Optional[str] = None) -> None:
        if state == self._state:
            return
        self._state = state
        self._bc.update_stats(deviceState=state, deviceHint=hint or HINTS.get(state, ""))
        self._bc.broadcast_status()
        if state in ("no-device", "unauthorized", "offline", "no-app", "no-adb"):
            self._log(hint or HINTS[state])

    def _loop(self) -> None:
        while self._running and not self._adb:
            try:
                self._adb = adb.ensure_adb(self._log)
            except adb.AdbError as exc:
                self._set_state("no-adb", f"{HINTS['no-adb']} ({exc})")
                time.sleep(ADB_RETRY_INTERVAL)
        if not self._adb:
            return
        self._log(f"Using {self._adb}")
        try:
            adb.start_server(self._adb)
        except (OSError, subprocess.SubprocessError) as exc:
            self._log(f"Could not start adb: {exc}")

        while self._running:
            try:
                self._poll()
            except Exception as exc:
                self._log(f"adb error: {exc}")
            time.sleep(POLL_INTERVAL)

    def _poll(self) -> None:
        devices = adb.list_devices(self._adb)
        ready = [s for s, state in devices if state == "device"]
        self._announced &= set(ready)
        self._install_failed &= {s for s, _ in devices}

        if self._serial and self._serial not in ready:
            self._log(f"{self._serial} disconnected")
            self._serial = None

        if not self._serial:
            if ready:
                if len(ready) > 1:
                    self._log(f"Several phones connected; using {ready[0]}")
                self._prepare(ready[0])
            elif any(state == "unauthorized" for _, state in devices):
                self._set_state("unauthorized")
            elif devices:
                self._set_state("offline")
            else:
                self._set_state("no-device")

    def _prepare(self, serial: str) -> None:
        if serial not in self._announced:
            self._announced.add(serial)
            model = adb.run(self._adb, ["shell", "getprop", "ro.product.model"], serial).stdout.strip()
            self._log(f"Found {model or serial}")

        if not self._ensure_app(serial):
            return

        if adb.run(self._adb, ["forward", f"tcp:{STREAM_PORT}", f"tcp:{STREAM_PORT}"], serial).returncode:
            self._log("adb forward failed; will retry")
            return
        port = self._dashboard_port
        if adb.run(self._adb, ["reverse", f"tcp:{port}", f"tcp:{port}"], serial).returncode:
            self._log("adb reverse failed; phone remote control needs Wi-Fi mode")
        adb.run(self._adb, ["shell", "am", "start", "-n", f"{APP_ID}/.MainActivity",
                            "--ez", "stream", "true"], serial)
        self._serial = serial
        self._set_state("ready")
        self._log("Ready. The app was opened on your phone.")

    def _ensure_app(self, serial: str) -> bool:
        current = installed_app_version(self._adb, serial)
        outdated = current is not None and parse_version(current) < parse_version(__version__)
        if current is not None and not outdated:
            return True
        if not self._auto_install or serial in self._install_failed:
            if current is None:
                self._set_state("no-app")
            return current is not None

        apk = find_apk() or self._download_apk()
        if not apk:
            if current is None:
                self._set_state("no-app")
                self._install_failed.add(serial)
            return current is not None

        self._set_state("installing")
        self._log(f"{'Updating' if outdated else 'Installing'} the app from {apk}")
        result = adb.run(self._adb, ["install", "-r", apk], serial, timeout=180)
        if result.returncode == 0:
            self._log("App installed")
            return True

        detail = (result.stdout + result.stderr).strip().splitlines()[-1:] or ["unknown error"]
        self._install_failed.add(serial)
        if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in detail[0]:
            hint = "Uninstall the old Webcam Bridge app from your phone, then reconnect it."
        else:
            hint = f"Could not install the app: {detail[0]}"
        if current is None:
            self._set_state("no-app", hint)
            return False
        self._log(hint)
        return True

    def _download_apk(self) -> Optional[str]:
        from .fetch import fetch_apk
        try:
            return fetch_apk(log=self._log)
        except OSError as exc:
            self._log(f"Could not download the Android app: {exc}")
            return None
