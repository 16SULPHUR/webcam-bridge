"""
config.py — Thread-safe configuration manager.

Loads/saves config.json. Provides defaults including the new
video-processing fields (brightness, contrast, saturation, sharpness, targetFps).
"""

import copy
import json
import os
import threading
from typing import Any

from .reactions.catalog import default_config as _default_reactions

# Dashboard address — the one place the defaults are defined. Localhost only by
# default: the dashboard has no authentication.
DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 5134

# ── Defaults ──────────────────────────────────────────────────────────────────
_DEFAULTS: dict[str, Any] = {
    # Set once the first-run wizard has been seen; until then the dashboard
    # opens on the Setup page instead of Live.
    "setupCompleted": False,
    "resolution":  "auto",
    "mirror":      False,
    "orientation": 0,
    "vcamEnabled": True,
    "vcamBackend": "auto",  # "auto" | "builtin" | "obs" — see vcam.py
    "zoom":        1.0,
    # Video-processing (applied via FFmpeg eq / unsharp filters)
    "brightness":  0.0,    # -1.0 → +1.0  (FFmpeg eq=brightness)
    "contrast":    1.0,    # 0.5  → 2.0   (FFmpeg eq=contrast)
    "saturation":  1.0,    # 0.0  → 2.0   (FFmpeg eq=saturation)
    "sharpness":   0.0,    # 0.0  → 2.0   (FFmpeg unsharp luma amount)
    "targetFps":   30,     # 10 / 15 / 20 / 24 / 30
    "blur":        0,      # Background blur intensity (0 to 25)
    "cameraFacing": "back", # "back" or "front"
    # Virtual background
    "bgMode":      "none", # "none" | "blur" | "replace"
    "bgImage":     "",     # filename within backgrounds/ folder
    # Segmentation
    "segmentationEngine": "mediapipe",  # "mediapipe" | "rvm"
    "rvmDownsampleRatio": 0.25,          # RVM internal compute scale (0.1=fast, 0.5=quality)
    # Face touch-up
    "faceTouchupEnabled":  False,
    "faceTouchupStrength": 35,           # 0–100 (percentage)
    # Desktop pets (oneko)
    "onekoEnabled":       False,
    "onekoSize":          2.0,
    "customOnekoEnabled": False,
    "customOnekoSkin":    "socks",
    "customPets":         [],
    # Reaction overlays — see webcam_bridge/reactions/
    "reactions": _default_reactions(),
}
# ─────────────────────────────────────────────────────────────────────────────


class ConfigManager:
    """Thread-safe wrapper around config.json."""

    def __init__(self, path: str) -> None:
        self._path  = path
        self._lock  = threading.RLock()
        self._data: dict[str, Any] = copy.deepcopy(_DEFAULTS)
        self._load()

    # ── Private ──────────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as fh:
                    saved = json.load(fh)
                with self._lock:
                    self._data.update(saved)
                print(f"[Config] Loaded: res={self._data.get('resolution')}, "
                      f"mirror={self._data.get('mirror')}, "
                      f"orientation={self._data.get('orientation')} deg")
            else:
                # frame_sender reads the file directly — make sure it exists.
                self._save()
        except Exception as exc:
            print(f"[Config] Failed to load - using defaults: {exc}")

    def _save(self) -> None:
        try:
            with self._lock:
                snapshot = dict(self._data)
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(snapshot, fh, indent=2)
        except Exception as exc:
            print(f"[Config] Failed to save: {exc}")

    # ── Public ───────────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def update(self, new_data: dict) -> None:
        """Merge new_data into config and persist to disk."""
        with self._lock:
            for k, v in new_data.items():
                if k in _DEFAULTS or k in self._data:
                    self._data[k] = v
        self._save()

    def to_dict(self) -> dict:
        with self._lock:
            return dict(self._data)

    def get_dimensions(self) -> tuple[int, int]:
        """Return (width, height) from the resolution string."""
        res = self.get("resolution", "auto")
        if not res or res == "auto":
            return 1280, 720
        try:
            w, h = res.split("x")
            return int(w), int(h)
        except Exception:
            return 1280, 720
