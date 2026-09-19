#!/usr/bin/env sh
# start.sh — start the desktop bridge from a source checkout (Linux/macOS).
# Linux needs v4l2loopback for the virtual camera; macOS needs OBS installed.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/desktop/.venv/bin/python"

if [ ! -x "$PY" ]; then
    echo "Creating virtual environment in desktop/.venv ..."
    python3 -m venv "$ROOT/desktop/.venv"
    "$PY" -m pip install --upgrade pip
    "$PY" -m pip install -e "$ROOT/desktop"
fi

# launcher.py downloads adb if needed, sets up the USB forwards, starts the
# phone app and opens the dashboard. Anything it cannot do shows up on the
# dashboard's Setup page with a button to fix it.
exec "$PY" -m webcam_bridge.launcher "$@"
