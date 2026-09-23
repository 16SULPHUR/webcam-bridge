#!/usr/bin/env sh
# start.sh — run the bridge from a source checkout (Linux/macOS).
# Linux needs v4l2loopback for the virtual camera; macOS needs OBS installed.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/desktop/.venv"

if [ ! -x "$VENV/bin/webcam-bridge" ]; then
    echo "Creating virtual environment in desktop/.venv ..."
    python3 -m venv "$VENV"
    "$VENV/bin/python" -m pip install --upgrade pip
    "$VENV/bin/python" -m pip install -e "$ROOT/desktop"
fi

exec "$VENV/bin/webcam-bridge" "$@"
