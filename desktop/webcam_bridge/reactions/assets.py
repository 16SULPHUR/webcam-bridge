"""
assets.py — Artwork loading for reaction overlays.

Resolves a mapping to an RGBA Sprite:
  type "emoji" → assets/emoji/<codepoints>.png (bundled Twemoji); anything else
                 is rendered from the system emoji font (Pillow) into the
                 user's emoji cache
  type "image" → any PNG / JPG / WEBP / GIF inside the user reactions folder
"""

import os
import sys
import threading

import cv2
import numpy as np

from .. import paths
from ..image_io import imread, imwrite
from .common import bundled_emoji, emoji_filename, emoji_font_path, list_images

RENDER_PX = 192


def _log(msg: str) -> None:
    sys.stderr.write(f"[Reactions] {msg}\n")


class Sprite:
    """One or more RGBA frames with playback timing."""

    def __init__(self, frames: list[np.ndarray], durations: list[float] | None = None):
        self.frames = frames
        self.durations = durations or [0.1] * len(frames)
        self.total = max(sum(self.durations), 1e-3)

    def frame_at(self, elapsed: float) -> np.ndarray:
        if len(self.frames) == 1:
            return self.frames[0]
        t = elapsed % self.total
        for frame, dur in zip(self.frames, self.durations):
            t -= dur
            if t <= 0:
                return frame
        return self.frames[-1]


def _to_rgba(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    elif img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    rgba = img.copy()
    rgba[:, :, :3] = img[:, :, 2::-1]
    return rgba


def _fit(img: np.ndarray, max_px: int = 256) -> np.ndarray:
    h, w = img.shape[:2]
    if max(h, w) <= max_px:
        return img
    s = max_px / float(max(h, w))
    return cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)


class EmojiRenderer:
    """Renders an emoji glyph to a transparent PNG using the system emoji font."""

    def __init__(self):
        self._font_path = emoji_font_path()
        self._pil_ok = False
        try:
            import PIL  # noqa: F401
            self._pil_ok = True
        except ImportError:
            pass

    @property
    def available(self) -> bool:
        return self._pil_ok and self._font_path is not None

    @property
    def reason(self) -> str:
        if not self._pil_ok:
            return "Pillow is not installed (pip install pillow)"
        if not self._font_path:
            return "no colour emoji font found"
        return ""

    def render(self, char: str, px: int = RENDER_PX) -> np.ndarray | None:
        if not self.available:
            return None
        from PIL import Image, ImageDraw, ImageFont

        font = None
        for size in (px, 109, 96, 64):
            try:
                font = ImageFont.truetype(self._font_path, size)
                break
            except OSError:
                continue
        if font is None:
            return None

        canvas = px * 3
        img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        try:
            draw.text((canvas // 2, canvas // 2), char, font=font,
                      embedded_color=True, anchor="mm")
        except Exception as exc:
            _log(f"emoji render failed for {char!r}: {exc}")
            return None

        bbox = img.getbbox()
        if not bbox:
            return None
        img = img.crop(bbox)
        scale = px / float(max(img.size))
        if scale < 1.0 or scale > 1.5:
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                             Image.LANCZOS)
        return np.array(img, dtype=np.uint8)


class AssetLibrary:
    def __init__(self, images_dir: str = paths.REACTIONS_DIR,
                 emoji_dir: str = paths.BUNDLED_EMOJI_DIR,
                 emoji_cache_dir: str = paths.EMOJI_CACHE_DIR):
        self.dir = images_dir
        self.emoji_dir = emoji_dir
        self.emoji_cache_dir = emoji_cache_dir
        os.makedirs(self.emoji_cache_dir, exist_ok=True)
        self.renderer = EmojiRenderer()
        self._cache: dict[tuple[str, str], Sprite | None] = {}
        self._lock = threading.Lock()

    # ── Lookup ────────────────────────────────────────────────────────────

    def sprite(self, kind: str, value: str) -> Sprite | None:
        key = (kind, value)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        sprite = self._build(kind, value)
        with self._lock:
            self._cache[key] = sprite
        return sprite

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()

    def _build(self, kind: str, value: str) -> Sprite | None:
        if not value:
            return None
        if kind == "emoji":
            return self._emoji_sprite(value)
        path = self._safe_path(value)
        return self._load_file(path) if path else None

    def _safe_path(self, rel: str) -> str | None:
        candidate = paths.safe_join(self.dir, rel)
        if candidate is None:
            _log(f"rejected asset path outside assets dir: {rel}")
            return None
        if not os.path.isfile(candidate):
            _log(f"asset not found: {rel}")
            return None
        return candidate

    def _emoji_sprite(self, char: str) -> Sprite | None:
        name = emoji_filename(char)
        for folder in (self.emoji_dir, self.emoji_cache_dir):
            if os.path.isfile(os.path.join(folder, name)):
                return self._load_file(os.path.join(folder, name))
        path = os.path.join(self.emoji_cache_dir, name)
        rendered = self.renderer.render(char)
        if rendered is None:
            _log(f"no artwork for {char!r} — {self.renderer.reason or 'render failed'}")
            return None
        try:
            bgra = rendered.copy()
            bgra[:, :, :3] = rendered[:, :, 2::-1]
            imwrite(path, bgra)
            _log(f"rendered emoji {char} → {os.path.basename(path)}")
        except Exception as exc:
            _log(f"could not cache emoji {char}: {exc}")
        return Sprite([_fit(rendered)])

    # ── File loading ──────────────────────────────────────────────────────

    def _load_file(self, path: str) -> Sprite | None:
        if path.lower().endswith(".gif"):
            animated = self._load_animated(path)
            if animated:
                return animated
        img = imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            _log(f"could not read {os.path.basename(path)}")
            return None
        return Sprite([_fit(_to_rgba(img))])

    def _load_animated(self, path: str) -> Sprite | None:
        try:
            from PIL import Image, ImageSequence
        except ImportError:
            _log("animated GIF needs Pillow — using first frame only")
            return None
        try:
            frames, durations = [], []
            with Image.open(path) as im:
                for frame in ImageSequence.Iterator(im):
                    rgba = np.array(frame.convert("RGBA"), dtype=np.uint8)
                    frames.append(_fit(rgba))
                    durations.append(max(frame.info.get("duration", 80), 20) / 1000.0)
            return Sprite(frames, durations) if frames else None
        except Exception as exc:
            _log(f"GIF load failed for {os.path.basename(path)}: {exc}")
            return None

    # ── Listing (dashboard) ───────────────────────────────────────────────

    def list_images(self) -> list[str]:
        return list_images(self.dir)

    def bundled_emoji(self) -> list[str]:
        return bundled_emoji(self.emoji_dir)
