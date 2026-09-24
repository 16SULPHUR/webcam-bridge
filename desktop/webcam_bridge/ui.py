"""
ui.py — The dashboard in its own app window (WebView2 on Windows, WebKit on macOS),
and console handling for the windowed Windows build, which starts without stdout.
"""

import ctypes
import json
import os
import sys
import threading
import time
import urllib.request

from . import paths

TITLE = "Webcam Bridge"
IS_WINDOWS = sys.platform == "win32"


def window_supported() -> bool:
    if sys.platform not in ("win32", "darwin"):
        return False
    try:
        import webview  # noqa: F401
    except Exception:
        return False
    return True


def show_window(url: str) -> bool:
    """Blocks until the window is closed. False if no window could be shown."""
    import webview

    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.create_window(TITLE, url, width=1360, height=860, min_size=(960, 640))
    try:
        webview.start(private_mode=False, storage_path=os.path.join(paths.DATA_DIR, "webview"))
    except Exception as exc:
        print(f"[Window] Could not open the app window: {exc}", file=sys.stderr)
        return False
    return True


def window_test(timeout: float = 60.0) -> int:
    """Used by the build smoke test: load a page in a hidden window."""
    import webview

    loaded = threading.Event()
    window = webview.create_window(TITLE, html="<p>ok</p>", hidden=True)
    window.events.loaded += lambda *_: loaded.set()

    def close() -> None:
        loaded.wait(timeout)
        window.destroy()

    webview.start(close)
    print("Window loaded" if loaded.is_set() else "Window did not load")
    return 0 if loaded.is_set() else 1


def running_instance(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/status", timeout=1) as resp:
            return json.load(resp).get("app") == "webcam-bridge"
    except (OSError, ValueError):
        return False


def wait_for_server(url: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline and not running_instance(url):
        time.sleep(0.2)


def ensure_console() -> bool:
    """Borrow the terminal we were started from, or open one. True if a new console was opened."""
    if not IS_WINDOWS or sys.stdout is not None:
        return False
    kernel32 = ctypes.windll.kernel32
    opened = False
    if not kernel32.AttachConsole(-1):
        if not kernel32.AllocConsole():
            return False
        opened = True
    sys.stdout = sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
    sys.stdin = open("CONIN$", encoding="utf-8", errors="replace")
    return opened


def log_to_file() -> None:
    if sys.stdout is None or sys.stderr is None:
        os.makedirs(paths.DATA_DIR, exist_ok=True)
        log = open(paths.LOG_PATH, "w", encoding="utf-8", errors="replace", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log


def show_error(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    if IS_WINDOWS and paths.FROZEN:
        ctypes.windll.user32.MessageBoxW(None, message, TITLE, 0x10)
