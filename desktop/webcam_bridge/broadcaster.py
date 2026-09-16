"""
broadcaster.py — Thread-safe event broadcaster for SSE log events and MJPEG video.

Architecture:
  - One Queue per connected SSE client → handler thread blocks on queue.get()
  - One Queue per connected video client → handler thread blocks on queue.get()
  - Pipeline threads call broadcast_log() / broadcast_status() / send_video_chunk()
  - Dead clients are auto-pruned on next broadcast attempt
"""

import json
import queue
import threading
import time
from typing import Set


# ── Client wrappers ───────────────────────────────────────────────────────────

class SseClient:
    """Holds a per-client queue for Server-Sent Events."""
    def __init__(self) -> None:
        self.q:     queue.Queue[bytes] = queue.Queue(maxsize=300)
        self.alive: bool               = True

    def put(self, data: bytes) -> None:
        if self.alive:
            try:
                self.q.put_nowait(data)
            except queue.Full:
                pass  # drop oldest SSE event if client is slow


class VideoClient:
    """Holds a per-client queue for MJPEG video chunks."""
    def __init__(self) -> None:
        self.q:     queue.Queue[bytes] = queue.Queue(maxsize=0)
        self.alive: bool               = True

    def put(self, data: bytes) -> None:
        if self.alive:
            try:
                self.q.put_nowait(data)
            except queue.Full:
                pass


# ── Broadcaster ───────────────────────────────────────────────────────────────

class EventBroadcaster:
    """Central hub that fans out logs, status, and video to all web clients."""

    def __init__(self) -> None:
        self._sse_lock:   threading.Lock    = threading.Lock()
        self._sse_set:    Set[SseClient]    = set()
        self._video_lock: threading.Lock    = threading.Lock()
        self._video_set:  Set[VideoClient]  = set()

        # Live stats (updated by Pipeline / TcpClient / PhoneStatsCollector)
        self._stats: dict = {
            "androidConnected":  False,
            "h264ReceivedBytes": 0,
            "decodedFrames":     0,
            "vcamActive":        False,
            "bitrateKBs":        0.0,
            "recording":         False,
            "reactions":         {},
            # Phone stats (populated by PhoneStatsCollector)
            "phoneModel":          None,
            "phoneAndroidVersion": None,
            "phoneDeviceName":     None,
            "phoneBattery":        None,
            "phoneBatteryStatus":  None,
            "phoneBatteryPlugged": None,
            "phoneBatteryHealth":  None,
            "phoneTemperature":    None,
            "phoneUptime":         None,
        }
        self._last_bytes: int   = 0
        self._last_ts:    float = time.monotonic()

    # ── SSE ───────────────────────────────────────────────────────────────────

    def add_sse_client(self) -> SseClient:
        client = SseClient()
        with self._sse_lock:
            self._sse_set.add(client)
        return client

    def remove_sse_client(self, client: SseClient) -> None:
        client.alive = False
        with self._sse_lock:
            self._sse_set.discard(client)

    def _broadcast_sse(self, data: dict) -> None:
        payload = ("data: " + json.dumps(data) + "\n\n").encode("utf-8")
        with self._sse_lock:
            clients = set(self._sse_set)
        for c in clients:
            c.put(payload)

    def broadcast_log(self, source: str, message: str) -> None:
        msg = message.strip()
        if msg:
            import sys
            # Replace old "node" stack label with "system"
            display_source = "system" if source == "node" else source
            
            # Check if TUI is active, and forward logs to it instead of standard stdout printing
            from .tui import TuiManager
            tui = TuiManager.get_instance()
            if tui and tui.running:
                tui.log(display_source, msg)
            else:
                # Print to server terminal console safely (fallback)
                try:
                    print(f"[{display_source.upper()}] {msg}", flush=True)
                except Exception:
                    try:
                        enc = sys.stdout.encoding or "utf-8"
                        safe_msg = msg.encode(enc, errors="replace").decode(enc)
                        print(f"[{display_source.upper()}] {safe_msg}", flush=True)
                    except Exception:
                        pass
            
            self._broadcast_sse({"type": "log", "source": display_source, "message": msg})

    def broadcast_status(self) -> None:
        now = time.monotonic()
        dt  = now - self._last_ts
        bitrate = (
            (self._stats["h264ReceivedBytes"] - self._last_bytes) / 1024.0 / dt
            if dt > 0 else 0.0
        )
        self._last_bytes = self._stats["h264ReceivedBytes"]
        self._last_ts    = now
        self._stats["bitrateKBs"] = max(0.0, round(bitrate, 1))
        self._broadcast_sse({
            "type": "status",
            **self._stats,
        })

    def update_stats(self, **kwargs) -> None:
        self._stats.update(kwargs)

    def get_stats(self) -> dict:
        return dict(self._stats)

    # ── Video ─────────────────────────────────────────────────────────────────

    def add_video_client(self) -> VideoClient:
        client = VideoClient()
        with self._video_lock:
            self._video_set.add(client)
        return client

    def remove_video_client(self, client: VideoClient) -> None:
        client.alive = False
        with self._video_lock:
            self._video_set.discard(client)

    def send_video_chunk(self, chunk: bytes) -> None:
        with self._video_lock:
            clients = set(self._video_set)
        for c in clients:
            c.put(chunk)

    @property
    def has_video_clients(self) -> bool:
        with self._video_lock:
            return bool(self._video_set)
