"""
updates.py — Tell the user when a newer release is on GitHub.

Disable with --no-update-check or WEBCAM_BRIDGE_NO_UPDATE_CHECK=1.
"""

import json
import re
import threading
import urllib.request

from . import __version__

REPO = "16SULPHUR/webcam-bridge"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"


def parse_version(text: str | None) -> tuple[int, ...]:
    """'v0.2.1' / '0.2.1-beta' -> (0, 2, 1); unparseable -> ()."""
    m = re.match(r"v?(\d+(?:\.\d+)*)", (text or "").strip())
    return tuple(int(p) for p in m.group(1).split(".")) if m else ()


def is_newer(candidate: str | None, current: str = __version__) -> bool:
    new, cur = parse_version(candidate), parse_version(current)
    return bool(new) and bool(cur) and new > cur


def latest_version(timeout: float = 5.0) -> str | None:
    req = urllib.request.Request(API_URL, headers={
        "User-Agent": f"webcam-bridge/{__version__}",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            tag = json.load(resp).get("tag_name")
    except Exception:
        return None
    return tag.lstrip("v") if isinstance(tag, str) else None


def check_in_background(broadcaster) -> None:
    def run():
        latest = latest_version()
        if is_newer(latest):
            broadcaster.update_stats(updateAvailable=latest)
            broadcaster.broadcast_status()
            broadcaster.broadcast_log("system", f"[Update] Webcam Bridge {latest} is available: {RELEASES_URL}")

    threading.Thread(target=run, daemon=True, name="UpdateCheck").start()
