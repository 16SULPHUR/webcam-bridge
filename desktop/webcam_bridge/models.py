"""
models.py — MediaPipe model files, downloaded on first use.

mediapipe >= 1.0 dropped the bundled `mp.solutions` graphs, so the Tasks API
needs these files. They are Google's (Apache-2.0) and are cached in the user
data directory (or MEDIAPIPE_MODELS_DIR).
"""

import os
import sys
import threading
import urllib.request

from . import paths

_BASE = "https://storage.googleapis.com/mediapipe-models"

MODEL_URLS = {
    "hand_landmarker.task":
        f"{_BASE}/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
    "face_landmarker.task":
        f"{_BASE}/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
    "selfie_segmenter_landscape.tflite":
        f"{_BASE}/image_segmenter/selfie_segmenter_landscape/float16/1/selfie_segmenter_landscape.tflite",
}

_lock = threading.Lock()


def model_dirs() -> list[str]:
    return [d for d in (os.environ.get("MEDIAPIPE_MODELS_DIR", ""), paths.MODELS_DIR) if d]


def find_model(name: str) -> str | None:
    for directory in model_dirs():
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return path
    return None


def ensure_model(name: str, log=None) -> str:
    """Return a local path to the model, downloading it once if needed."""
    log = log or (lambda msg: sys.stderr.write(msg + "\n"))
    with _lock:
        path = find_model(name)
        if path:
            return path
        url = MODEL_URLS[name]
        dest = os.path.join(paths.MODELS_DIR, name)
        os.makedirs(paths.MODELS_DIR, exist_ok=True)
        log(f"[Models] Downloading {name} (first use)...")
        tmp = dest + ".part"
        req = urllib.request.Request(url, headers={"User-Agent": "webcam-bridge"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
            out.write(resp.read())
        os.replace(tmp, dest)
        log(f"[Models] Saved {dest}")
        return dest
