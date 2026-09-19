"""
procs.py — Subprocess flags shared by everything that spawns a helper.

The packaged Windows app has no console of its own, so every console child it
starts (FFmpeg, adb, the frame processor) would pop up its own black window.
CREATE_NO_WINDOW suppresses that; on other platforms the flag is simply 0.
"""

import subprocess
import sys

NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
