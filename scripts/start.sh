#!/usr/bin/env sh
# start.sh — connect to the phone over USB and start the desktop bridge (Linux/macOS).
# Linux needs v4l2loopback for the virtual camera; macOS needs OBS installed.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/desktop/.venv/bin/python"
APP_ID="io.github.sulphur16.webcambridge"
PORT="${WEBCAM_BRIDGE_PORT:-5134}"

if [ ! -x "$PY" ]; then
    echo "Creating virtual environment in desktop/.venv ..."
    python3 -m venv "$ROOT/desktop/.venv"
    "$PY" -m pip install --upgrade pip
    "$PY" -m pip install -e "$ROOT/desktop"
fi

command -v adb >/dev/null || { echo "adb not found — install Android platform-tools"; exit 1; }

echo "Waiting for phone (USB debugging must be enabled)..."
adb wait-for-device
adb shell am start -n "$APP_ID/.MainActivity" >/dev/null 2>&1 || echo "Open the Webcam Bridge app manually."
adb forward tcp:8080 tcp:8080
adb reverse "tcp:$PORT" "tcp:$PORT" >/dev/null 2>&1 || echo "adb reverse failed — phone remote control needs Wi-Fi mode."

exec "$PY" -m webcam_bridge --port "$PORT" "$@"
