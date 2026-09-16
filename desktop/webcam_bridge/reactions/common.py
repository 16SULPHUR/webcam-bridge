"""
common.py — Dependency-free helpers shared by the engine and the web server.

Kept free of cv2/numpy so the dashboard process can list assets without
pulling in the vision stack.
"""

import os

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
EMOJI_DIRNAME = "emoji"

FONT_CANDIDATES = (
    os.environ.get("WEBCAM_BRIDGE_EMOJI_FONT", ""),
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "seguiemj.ttf"),
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/System/Library/Fonts/Apple Color Emoji.ttc",
)


def emoji_filename(char: str) -> str:
    parts = [f"u{ord(c):x}" for c in char if c not in ("\ufe0f", "\ufe0e", "\u200d")]
    return ("_".join(parts) or "unknown") + ".png"


def emoji_from_filename(name: str) -> str:
    stem = os.path.splitext(os.path.basename(name))[0]
    try:
        return "".join(chr(int(p[1:], 16)) for p in stem.split("_") if p.startswith("u"))
    except ValueError:
        return ""


def list_images(assets_dir: str) -> list[str]:
    """Meme/image assets, relative to assets_dir (any emoji/ folder is excluded)."""
    out: list[str] = []
    for root, dirs, files in os.walk(assets_dir):
        dirs[:] = [d for d in dirs if d != EMOJI_DIRNAME and not d.startswith(".")]
        for name in sorted(files):
            if name.lower().endswith(IMAGE_EXTS):
                rel = os.path.relpath(os.path.join(root, name), assets_dir)
                out.append(rel.replace(os.sep, "/"))
    return out


def bundled_emoji(emoji_dir: str) -> list[str]:
    if not os.path.isdir(emoji_dir):
        return []
    chars = [emoji_from_filename(n) for n in sorted(os.listdir(emoji_dir))
             if n.lower().endswith(".png")]
    return [c for c in chars if c]


def emoji_font_path() -> str | None:
    return next((p for p in FONT_CANDIDATES if p and os.path.isfile(p)), None)


def renderer_status() -> dict:
    """Can unbundled emoji be rendered on demand?"""
    try:
        import PIL  # noqa: F401
    except ImportError:
        return {"available": False, "reason": "Pillow is not installed (pip install pillow)"}
    font = emoji_font_path()
    if not font:
        return {"available": False, "reason": "no colour emoji font found"}
    return {"available": True, "reason": "", "font": os.path.basename(font)}


# MediaPipe Tasks models (mediapipe >= 1.0) live in models.py.
from ..models import MODEL_URLS, find_model  # noqa: E402,F401
