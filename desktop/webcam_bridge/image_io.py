"""
image_io.py — cv2.imread / cv2.imwrite that work with non-ASCII paths.

OpenCV's file functions use the ANSI code page on Windows, so a user profile
like C:\\Users\\Zoë\\... fails silently. Reading through numpy avoids that.
"""

import os

import cv2
import numpy as np


def imread(path: str, flags: int = cv2.IMREAD_COLOR):
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, flags)


def imwrite(path: str, img) -> bool:
    ok, buf = cv2.imencode(os.path.splitext(path)[1] or ".png", img)
    if not ok:
        return False
    buf.tofile(path)
    return True
