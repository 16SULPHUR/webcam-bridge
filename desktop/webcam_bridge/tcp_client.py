"""
tcp_client.py — Connects to the Android camera server via ADB port forward.

The Android app runs a TCP server on port 8080.
ADB port forward maps localhost:8080 → phone:8080.

This client:
  1. Connects to localhost:8080
  2. Reads H.264 data and calls data_callback(chunk) for each chunk
  3. Reconnects on disconnect (unless stopped)
  4. Updates the broadcaster with connection state
"""

import socket
import threading
import time
from typing import Callable, Optional

from .broadcaster import EventBroadcaster


# ── Tuning constants ──────────────────────────────────────────────────────────
ADB_HOST        = "127.0.0.1"
ADB_PORT        = 8080
RECONNECT_DELAY = 2.0   # seconds between reconnect attempts
READ_CHUNK_SIZE = 65536  # bytes per read()


class AndroidTcpClient:
    """
    Connects and reconnects to the Android camera TCP server.

    The data_callback is called with each received bytes chunk.
    The on_connect / on_disconnect callbacks update pipeline state.
    """

    def __init__(
        self,
        broadcaster:     EventBroadcaster,
        data_callback:   Callable[[bytes], None],
        on_connect:      Optional[Callable[[], None]] = None,
        on_disconnect:   Optional[Callable[[], None]] = None,
    ) -> None:
        self._bc             = broadcaster
        self._data_cb        = data_callback
        self._on_connect     = on_connect
        self._on_disconnect  = on_disconnect

        self._sock: Optional[socket.socket] = None
        self._pending: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Stats
        self._total_bytes    = 0
        self._bytes_this_sec = 0
        self._last_log_ts    = time.monotonic()

    # ── Public ───────────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._sock is not None

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    def start(self) -> None:
        """Begin connecting (runs in background thread)."""
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="TcpClient",
        )
        self._thread.start()

    def stop(self) -> None:
        """Disconnect and stop the reconnect loop."""
        self._running = False
        self._close_socket()

    def disconnect(self) -> None:
        """Force close the current connection, triggering a reconnect."""
        self._close_socket()

    def send_command(self, payload: str) -> None:
        """Send a string payload (e.g., newline-terminated JSON command) to the connected Android client."""
        sock = self._sock
        if sock:
            try:
                # Add newline separator for easy reading on Android (readLine)
                data = (payload + "\n").encode("utf-8")
                sock.sendall(data)
            except Exception as exc:
                self._bc.broadcast_log("node", f"[Bridge] Failed to send command to Android: {exc}")

    # ── Internal ─────────────────────────────────────────────────────────────

    def _run(self) -> None:
        while self._running:
            try:
                self._connect_and_read()
            except Exception as exc:
                if self._running:
                    self._bc.broadcast_log(
                        "node", f"[Bridge] TCP error: {exc}"
                    )
            if self._running:
                self._close_socket()
                self._bc.update_stats(androidConnected=False)
                self._bc.broadcast_status()
                if self._on_disconnect:
                    self._on_disconnect()
                time.sleep(RECONNECT_DELAY)

    def _connect_and_read(self) -> None:
        first = b""
        while self._running:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.settimeout(3.0)
                sock.connect((ADB_HOST, ADB_PORT))
                sock.settimeout(None)
                # adb accepts the forward even when the app isn't listening yet and then
                # closes it; only a connection that delivers data counts as connected.
                self._pending = sock
                first = sock.recv(READ_CHUNK_SIZE)
                self._pending = None
                if not first:
                    sock.close()
                    time.sleep(RECONNECT_DELAY)
                    continue
                self._sock = sock
                break
            except (ConnectionRefusedError, TimeoutError, OSError):
                # Android app not streaming yet — retry silently
                if self._running:
                    time.sleep(RECONNECT_DELAY)
            except Exception as exc:
                self._bc.broadcast_log("node", f"[Bridge] Connect error: {exc}")
                time.sleep(RECONNECT_DELAY)

        if not self._running or self._sock is None:
            return

        self._bc.update_stats(androidConnected=True, h264ReceivedBytes=self._total_bytes)
        self._bc.broadcast_status()
        self._bc.broadcast_log("node", "[Bridge] [OK] Connected to Android stream!")
        print("[Bridge] [OK] Connected to Android stream!")

        if self._on_connect:
            self._on_connect()

        # Read loop
        buf_log = 0
        chunk = first
        while self._running:
            if not chunk:
                try:
                    chunk = self._sock.recv(READ_CHUNK_SIZE)
                except Exception:
                    break
            if not chunk:
                break

            self._total_bytes    += len(chunk)
            self._bytes_this_sec += len(chunk)

            # Periodic data-flow log every 100 KB
            buf_log += len(chunk)
            if buf_log >= 100_000:
                self._bc.update_stats(
                    h264ReceivedBytes=self._total_bytes,
                    androidConnected=True,
                )
                buf_log = 0

            self._data_cb(chunk)
            chunk = b""

        self._bc.broadcast_log("node", "[Bridge] TCP connection closed")
        print("[Bridge] TCP connection closed")

    def _close_socket(self) -> None:
        pending, self._pending = self._pending, None
        if pending:
            try:
                pending.close()
            except Exception:
                pass
        sock, self._sock = self._sock, None
        if sock:
            try:
                sock.close()
            except Exception:
                pass
