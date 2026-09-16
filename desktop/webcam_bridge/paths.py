"""
paths.py — Every filesystem location the bridge uses, in one place.

Bundled, read-only resources ship inside the package. Anything the user creates
(settings, uploads, downloaded models, recordings) lives outside it so the
package directory can stay read-only and git-clean.

Environment overrides:
  WEBCAM_BRIDGE_HOME        user data directory (config, uploads, models, skins)
  WEBCAM_BRIDGE_RECORDINGS  where recordings and snapshots are written
  WEBCAM_BRIDGE_FFMPEG      explicit path to the ffmpeg executable
  MEDIAPIPE_MODELS_DIR      extra directory searched for MediaPipe .task models
"""

import os
import shutil
import sys

APP_NAME = "WebcamBridge"

# ── Bundled resources (read-only) ─────────────────────────────────────────────
PACKAGE_DIR      = os.path.dirname(os.path.abspath(__file__))
WEB_DIR          = os.path.join(PACKAGE_DIR, "web")
ASSETS_DIR       = os.path.join(PACKAGE_DIR, "assets")
BUNDLED_BG_DIR   = os.path.join(ASSETS_DIR, "backgrounds")
BUNDLED_EMOJI_DIR = os.path.join(ASSETS_DIR, "emoji")
ONEKO_GIF        = os.path.join(WEB_DIR, "img", "oneko.gif")
FRAME_SENDER     = os.path.join(PACKAGE_DIR, "frame_sender.py")
VCAM_BUNDLED_DIR = os.path.join(PACKAGE_DIR, "bin")   # <arch>/webcam_bridge_cam.dll (built in CI)


def _default_home() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
        return os.path.join(base, APP_NAME)
    if sys.platform == "darwin":
        return os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "webcam-bridge")


# ── User data (writable) ──────────────────────────────────────────────────────
DATA_DIR        = os.path.abspath(os.environ.get("WEBCAM_BRIDGE_HOME") or _default_home())
CONFIG_PATH     = os.path.join(DATA_DIR, "config.json")
USER_BG_DIR     = os.path.join(DATA_DIR, "backgrounds")
REACTIONS_DIR   = os.path.join(DATA_DIR, "reactions")        # uploaded meme artwork
EMOJI_CACHE_DIR = os.path.join(DATA_DIR, "emoji-cache")      # emoji rendered on demand
SKINS_DIR       = os.path.join(DATA_DIR, "skins")            # Neko skin folders
MODELS_DIR      = os.path.join(DATA_DIR, "models")           # MediaPipe .task files

RECORDINGS_DIR = os.path.abspath(
    os.environ.get("WEBCAM_BRIDGE_RECORDINGS")
    or os.path.join(os.path.expanduser("~"), "Videos", APP_NAME)
)


# Registered camera DLLs are loaded by other apps, possibly for other users, so
# they are copied to a stable machine-wide location before registration.
VCAM_INSTALL_DIR = os.path.join(
    os.environ.get("ProgramData") or r"C:\ProgramData", APP_NAME, "vcam")


def ensure_user_dirs() -> None:
    for d in (DATA_DIR, USER_BG_DIR, REACTIONS_DIR, EMOJI_CACHE_DIR,
              SKINS_DIR, MODELS_DIR, RECORDINGS_DIR):
        os.makedirs(d, exist_ok=True)


def background_dirs() -> list[str]:
    """User uploads first so they shadow a bundled file of the same name."""
    return [USER_BG_DIR, BUNDLED_BG_DIR]


def find_background(filename: str) -> str | None:
    name = os.path.basename(filename or "")
    if not name:
        return None
    for d in background_dirs():
        path = os.path.join(d, name)
        if os.path.isfile(path):
            return path
    return None


def resolve_ffmpeg() -> str:
    explicit = os.environ.get("WEBCAM_BRIDGE_FFMPEG")
    if explicit:
        return explicit
    local = os.path.join(DATA_DIR, "bin", "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if os.path.isfile(local):
        return local
    return shutil.which("ffmpeg") or "ffmpeg"


def safe_join(base: str, rel: str) -> str | None:
    """Join rel onto base, refusing anything that escapes base."""
    root = os.path.realpath(base)
    candidate = os.path.realpath(os.path.join(root, rel))
    if candidate != root and not candidate.startswith(root + os.sep):
        return None
    return candidate
