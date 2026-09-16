"""
phone_stats.py — Periodically collects phone stats via ADB shell commands.

Stats collected:
  - Device model
  - Android version
  - Battery level, status (charging/discharging), temperature
  - Uptime

Results are pushed into the EventBroadcaster so SSE clients receive them.
"""

import subprocess
import threading
import time
from typing import List, Optional

from .broadcaster import EventBroadcaster


# Interval between ADB stat polls (seconds)
POLL_INTERVAL = 10.0

# ADB binary — assumes it's on PATH
ADB = "adb"


def _run_adb(args: List[str], timeout: float = 5.0) -> Optional[str]:
    """Run an adb command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            [ADB] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    return None


def _parse_battery_dump(dump: str) -> dict:
    """Parse output of `adb shell dumpsys battery` into a dict."""
    info = {}
    if not dump:
        return info

    for line in dump.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip()

        if key == "level":
            try:
                info["level"] = int(val)
            except ValueError:
                pass
        elif key == "status":
            # 1=Unknown, 2=Charging, 3=Discharging, 4=Not charging, 5=Full
            status_map = {"1": "unknown", "2": "charging", "3": "discharging",
                          "4": "not_charging", "5": "full"}
            info["status"] = status_map.get(val, val)
        elif key == "temperature":
            try:
                info["temperature"] = int(val) / 10.0  # reported in tenths of °C
            except ValueError:
                pass
        elif key == "plugged":
            # 0=unplugged, 1=AC, 2=USB, 4=Wireless
            plug_map = {"0": "unplugged", "1": "ac", "2": "usb", "4": "wireless"}
            info["plugged"] = plug_map.get(val, val)
        elif key == "ac powered" and val.lower() == "true":
            info["plugged"] = "ac"
        elif key == "usb powered" and val.lower() == "true":
            info["plugged"] = "usb"
        elif key == "wireless powered" and val.lower() == "true":
            info["plugged"] = "wireless"
        elif key == "health":
            # 1=Unknown, 2=Good, 3=Overheat, 4=Dead, 5=Over voltage, 6=Unspecified failure
            health_map = {"1": "unknown", "2": "good", "3": "overheat",
                          "4": "dead", "5": "over_voltage", "6": "failure"}
            info["health"] = health_map.get(val, val)

    if "plugged" not in info:
        info["plugged"] = "unplugged"

    return info


class PhoneStatsCollector:
    """
    Background thread that polls phone stats via ADB and pushes them
    into the EventBroadcaster.
    """

    def __init__(self, broadcaster: EventBroadcaster) -> None:
        self._bc = broadcaster
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Cached static props (fetched once)
        self._model: Optional[str] = None
        self._android_version: Optional[str] = None
        self._device_name: Optional[str] = None

    def start(self) -> None:
        """Begin polling in a background daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="PhoneStats",
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _fetch_static_props(self) -> None:
        """Fetch device model and Android version (these don't change)."""
        if self._model is None:
            self._model = _run_adb(["shell", "getprop", "ro.product.model"])
        if self._android_version is None:
            self._android_version = _run_adb(["shell", "getprop", "ro.build.version.release"])
        if self._device_name is None:
            self._device_name = _run_adb(["shell", "getprop", "ro.product.device"])

    def _poll_loop(self) -> None:
        self._bc.broadcast_log("system", "[PhoneStats] Phone stats collector started.")

        # Short initial delay to let the bridge settle
        time.sleep(2.0)

        while self._running:
            try:
                self._fetch_static_props()

                # Battery info
                battery_dump = _run_adb(["shell", "dumpsys", "battery"])
                battery = _parse_battery_dump(battery_dump) if battery_dump else {}

                # Uptime
                uptime_raw = _run_adb(["shell", "cat", "/proc/uptime"])
                uptime_secs = None
                if uptime_raw:
                    try:
                        uptime_secs = int(float(uptime_raw.split()[0]))
                    except (ValueError, IndexError):
                        pass

                # Push into broadcaster stats
                self._bc.update_stats(
                    phoneModel=self._model or "Unknown",
                    phoneAndroidVersion=self._android_version or "?",
                    phoneDeviceName=self._device_name or "",
                    phoneBattery=battery.get("level"),
                    phoneBatteryStatus=battery.get("status", "unknown"),
                    phoneBatteryPlugged=battery.get("plugged", "unplugged"),
                    phoneBatteryHealth=battery.get("health", "unknown"),
                    phoneTemperature=battery.get("temperature"),
                    phoneUptime=uptime_secs,
                )

            except Exception as exc:
                # Don't crash the thread on unexpected errors
                self._bc.broadcast_log(
                    "system",
                    f"[PhoneStats] Error collecting stats: {exc}",
                )

            # Wait for next poll (check running flag frequently for fast shutdown)
            for _ in range(int(POLL_INTERVAL * 10)):
                if not self._running:
                    return
                time.sleep(0.1)

        self._bc.broadcast_log("system", "[PhoneStats] Phone stats collector stopped.")
