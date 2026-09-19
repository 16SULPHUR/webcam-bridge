"""
fetch_ffmpeg.py — Put a redistributable FFmpeg next to the packaging spec.

    python packaging/fetch_ffmpeg.py

The imageio-ffmpeg build the bridge uses from a source checkout is compiled
--enable-gpl --enable-version3. That is fine to *use*, but shipping it inside
the installer would put the whole download under the GPL, so the packaged app
carries an LGPL build instead. The bridge only decodes H.264 and stream-copies
to MP4 (-c:v copy), so nothing in the GPL-only feature set is needed.

The build and its licence text land in packaging/ffmpeg/, which
webcam-bridge.spec picks up automatically.
"""

import hashlib
import io
import os
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(HERE, "ffmpeg")

BASE = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"
ARCHIVE = "ffmpeg-master-latest-win64-lgpl.zip"
WANTED = ("ffmpeg.exe", "LICENSE.txt")


def _download(url: str) -> bytes:
    print(f"  downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "webcam-bridge"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def main() -> int:
    if os.path.isfile(os.path.join(DEST, "ffmpeg.exe")):
        print(f"  already present in {DEST}")
        return 0

    data = _download(f"{BASE}/{ARCHIVE}")
    expected = _download(f"{BASE}/{ARCHIVE}.sha256").decode("utf-8", "replace").split()[0]
    actual = hashlib.sha256(data).hexdigest()
    if expected != actual:
        print(f"checksum mismatch for {ARCHIVE} (expected {expected}, got {actual})", file=sys.stderr)
        return 1

    os.makedirs(DEST, exist_ok=True)
    found = set()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for member in zf.infolist():
            name = os.path.basename(member.filename)
            if member.is_dir() or name not in WANTED or name in found:
                continue
            with zf.open(member) as src, open(os.path.join(DEST, name), "wb") as out:
                out.write(src.read())
            found.add(name)
            print(f"  saved {os.path.join(DEST, name)}")

    missing = set(WANTED) - found
    if missing:
        print(f"{ARCHIVE} did not contain {', '.join(sorted(missing))}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
