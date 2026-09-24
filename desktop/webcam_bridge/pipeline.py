"""
pipeline.py — Manages FFmpeg VCam and Python frame_sender.

Responsibilities:
  - Spawn and kill FFmpeg VCam (h264 → BGR24)
  - Spawn and kill Python frame_sender.py
  - Fan incoming H.264 data to FFmpeg stdin pipe
  - Track decoded frame count for stats
  - Implement VCam failure circuit-breaker (disable after N fast failures)
  - Expose restart() for config changes and reconnect
"""

import json
import subprocess
import threading
import time
from typing import Optional, Callable

from .broadcaster import EventBroadcaster
from .config import ConfigManager
from .ffmpeg_utils import build_vcam_args
from .recorder import RecordingManager


# ── Tuning constants ──────────────────────────────────────────────────────────
RX_STATUS_PREFIX        = "@@RX "   # frame_sender → bridge status channel
PIPELINE_RESTART_DELAY  = 1.5    # seconds before pipeline respawns
VCAM_MAX_FAILURES       = 3      # max fast VCam failures before disabling
VCAM_FAILURE_WINDOW     = 15.0   # seconds — failures within this window count


class Pipeline:
    """
    Lifecycle:
        pipeline.start()   → spawn FFmpeg + Python, connect TCP fan-out
        pipeline.stop()    → kill all subprocesses gracefully
        pipeline.restart() → stop + start (after a delay)
        pipeline.feed(b)   → send H.264 bytes to FFmpeg stdin pipe
    """

    def __init__(
        self,
        config:      ConfigManager,
        broadcaster: EventBroadcaster,
        recorder:    RecordingManager,
        ffmpeg_path: str,
        sender_cmd:  list[str],
    ) -> None:
        self._cfg     = config
        self._bc      = broadcaster
        self._rec     = recorder
        self._ffmpeg  = ffmpeg_path
        self._sender_cmd = sender_cmd

        self._on_stop: Optional[Callable[[], None]] = None

        self._lock          = threading.Lock()
        self._vcam_proc: Optional[subprocess.Popen] = None
        self._py_proc:   Optional[subprocess.Popen] = None

        self._running   = False
        self._restarting = False

        # Frame counting
        self._stdout_bytes  = 0
        self._frame_size    = 1280 * 720 * 3  # updated on start
        self._decoded_frames = 0
        self._latest_jpeg: Optional[bytes] = None

        # VCam circuit-breaker
        self._vcam_failures      = 0
        self._vcam_last_fail_ts  = 0.0
        self._vcam_disabled      = False

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn all subprocesses."""
        with self._lock:
            if self._running:
                return
            self._running = True
        self._spawn()

    def stop(self, reason: str = "Requested") -> None:
        """Kill all subprocesses and mark as stopped."""
        with self._lock:
            self._running = False
        self._kill_all(reason)

    def restart(self, reason: str = "Config change") -> None:
        """Stop → wait → start. Safe to call from any thread."""
        if self._restarting:
            return
        self._restarting = True
        self._bc.broadcast_log("node", f"[Pipeline] Restarting: {reason}")
        self._kill_all(reason)
        time.sleep(PIPELINE_RESTART_DELAY)
        self._restarting = False
        if self._running:
            self._spawn()

    def feed(self, chunk: bytes) -> None:
        """Pipe an H.264 chunk to FFmpeg stdin pipe and optional recorder."""
        # VCam FFmpeg
        proc = self._vcam_proc
        if proc and proc.poll() is None:
            try:
                proc.stdin.write(chunk)
                proc.stdin.flush()
            except Exception:
                pass

        # Recorder
        self._rec.feed(chunk)

        # Frame counting (based on VCam BGR24 output bytes)
        self._stdout_bytes = 0  # reset handled in stdout reader

    @property
    def vcam_active(self) -> bool:
        p = self._py_proc
        return p is not None and p.poll() is None

    @property
    def decoded_frames(self) -> int:
        return self._decoded_frames

    @property
    def latest_jpeg(self) -> Optional[bytes]:
        return self._latest_jpeg

    def set_on_stop(self, callback: Callable[[], None]) -> None:
        self._on_stop = callback

    # ── Internal spawn / kill ──────────────────────────────────────────────────

    def _spawn(self) -> None:
        cfg = self._cfg.to_dict()
        width, height     = self._cfg.get_dimensions()
        vcam_enabled      = bool(cfg.get("vcamEnabled", True)) and not self._vcam_disabled
        target_fps        = int(cfg.get("targetFps", 30))

        # FFmpeg outputs a stable raw BGR24 stream of size width x height
        self._frame_size = width * height * 3
        self._decoded_frames = 0
        self._stdout_bytes   = 0

        print(f"[Pipeline] Starting - VCam={width}x{height}, FPS={target_fps}")

        # ── 1. FFmpeg Decoder ──────────────────────────────────────────────
        vcam_args = build_vcam_args(
            self._ffmpeg, width, height, target_fps
        )
        self._vcam_proc = subprocess.Popen(
            vcam_args,
            bufsize=0,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        threading.Thread(
            target=self._drain_vcam_stdout,
            args=(self._vcam_proc, width, height),
            daemon=True, name="VcamStdout",
        ).start()
        threading.Thread(
            target=self._drain_stderr,
            args=(self._vcam_proc, "FFmpeg-VCam"),
            daemon=True, name="VcamStderr",
        ).start()
        threading.Thread(
            target=self._watch_vcam_proc,
            args=(self._vcam_proc,),
            daemon=True, name="VcamWatch",
        ).start()

        # ── 2. Python frame_sender (Unified Filter Processor & VCam/Preview Output) ──
        # We pass only the path to config.json. The Python process reads settings dynamically from it.
        self._py_proc = subprocess.Popen(
            [*self._sender_cmd, self._cfg._path],
            bufsize=0,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        threading.Thread(
            target=self._drain_py_stdout,
            args=(self._py_proc,),
            daemon=True, name="PyStdout",
        ).start()
        threading.Thread(
            target=self._drain_stderr,
            args=(self._py_proc, "python"),
            daemon=True, name="PyStderr",
        ).start()
        threading.Thread(
            target=self._watch_py_proc,
            args=(self._py_proc,),
            daemon=True, name="PyWatch",
        ).start()

        self._bc.update_stats(vcamActive=vcam_enabled)
        self._bc.broadcast_status()
        print("[Pipeline] Ready - waiting for frames from Android...")

    def _kill_all(self, reason: str = "") -> None:
        if reason:
            print(f"[Pipeline] Stopping: {reason}")

        if self._on_stop:
            try:
                self._on_stop()
            except Exception:
                pass

        # Kill VCam FFmpeg
        proc = self._vcam_proc
        self._vcam_proc = None
        if proc:
            try:
                proc.stdin.close()
            except Exception:
                pass
            try:
                proc.kill()
            except Exception:
                pass

        # Kill Python
        proc = self._py_proc
        self._py_proc = None
        if proc:
            try:
                proc.stdin.close()
            except Exception:
                pass
            try:
                proc.kill()
            except Exception:
                pass

        self._bc.update_stats(vcamActive=False)

    # ── Stdout drains ──────────────────────────────────────────────────────────

    def _drain_vcam_stdout(
        self, proc: subprocess.Popen, w: int, h: int
    ) -> None:
        """
        Read BGR24 frames from VCam FFmpeg stdout and forward to Python frame_sender.
        Also counts decoded frames for the dashboard stats.
        """
        frame_size  = w * h * 3
        local_bytes = 0

        while proc.poll() is None:
            try:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
            except Exception:
                break

            # Forward to Python frame_sender
            py = self._py_proc
            if py and py.poll() is None:
                try:
                    py.stdin.write(chunk)
                    py.stdin.flush()
                except Exception:
                    pass

            # Frame count
            local_bytes += len(chunk)
            frames_done  = local_bytes // frame_size
            if frames_done > 0:
                self._decoded_frames += frames_done
                local_bytes = local_bytes % frame_size
                self._bc.update_stats(decodedFrames=self._decoded_frames)
                self._bc.broadcast_status()

    def _drain_py_stdout(self, proc: subprocess.Popen) -> None:
        """Read binary JPEG preview frames from Python and broadcast to clients.
        
        NOTE: proc.stdout from subprocess.PIPE is already a binary BufferedReader.
        We use proc.stdout directly.
        """
        stdout_buf = proc.stdout  # already a binary BufferedReader
        try:
            while True:
                # Read 4-byte length header
                len_bytes = b""
                while len(len_bytes) < 4:
                    chunk = stdout_buf.read(4 - len(len_bytes))
                    if not chunk:
                        # EOF — process exited and pipe drained
                        return
                    len_bytes += chunk

                length = int.from_bytes(len_bytes, byteorder="big")
                if length <= 0 or length > 10_000_000:  # sanity check (<10 MB)
                    # Corrupt framing — stop reading
                    print(f"[Pipeline] _drain_py_stdout: bad frame length {length}, stopping.",
                          file=__import__('sys').stderr)
                    return

                # Read frame payload
                jpeg_bytes = b""
                while len(jpeg_bytes) < length:
                    chunk = stdout_buf.read(length - len(jpeg_bytes))
                    if not chunk:
                        return  # truncated frame at EOF
                    jpeg_bytes += chunk

                self._latest_jpeg = jpeg_bytes

                # Construct MJPEG boundary chunk
                boundary = (
                    b"\r\n--ffmpeg\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(length).encode("ascii") + b"\r\n\r\n"
                    + jpeg_bytes + b"\r\n"
                )
                self._bc.send_video_chunk(boundary)
        except Exception as exc:
            import sys as _sys
            print(f"[Pipeline] _drain_py_stdout error: {exc}", file=_sys.stderr)

    def _drain_stderr(self, proc: subprocess.Popen, label: str) -> None:
        """Forward FFmpeg/Python stderr to dashboard log (line by line)."""
        try:
            for raw in proc.stderr:
                msg = raw.decode(errors="replace").strip()
                if not msg:
                    continue
                if msg.startswith(RX_STATUS_PREFIX):
                    self._handle_reaction_status(msg[len(RX_STATUS_PREFIX):])
                    continue
                self._bc.broadcast_log("node", f"[{label}] {msg}")
        except Exception:
            pass

    def _handle_reaction_status(self, payload: str) -> None:
        """Reaction detector state, emitted by frame_sender once per ~0.5 s."""
        try:
            self._bc.update_stats(reactions=json.loads(payload))
        except Exception:
            pass

    # ── Process watchers ──────────────────────────────────────────────────────

    def _watch_vcam_proc(self, proc: subprocess.Popen) -> None:
        code = proc.wait()
        if proc is not self._vcam_proc:
            return  # stale reference — we've already restarted
        if self._running and not self._restarting:
            self._trigger_restart(f"FFmpeg VCam exited (code {code})")

    def _watch_py_proc(self, proc: subprocess.Popen) -> None:
        code = proc.wait()
        if proc is not self._py_proc:
            return  # stale reference
        if self._running and not self._restarting:
            self._handle_vcam_failure(code)

    # ── VCam circuit-breaker ──────────────────────────────────────────────────

    def _handle_vcam_failure(self, code: int) -> None:
        if code == 0:
            self._vcam_failures = 0
            return

        now = time.monotonic()
        if now - self._vcam_last_fail_ts < VCAM_FAILURE_WINDOW:
            self._vcam_failures += 1
        else:
            self._vcam_failures = 1
        self._vcam_last_fail_ts = now

        print(f"[Python] [WARN] VCam failure {self._vcam_failures}/{VCAM_MAX_FAILURES} - code {code}")

        if self._vcam_failures >= VCAM_MAX_FAILURES:
            self._vcam_disabled = True
            self._cfg.update({"vcamEnabled": False})
            msg = ("[ERROR] VCam disabled - OBS Virtual Camera not available. "
                   "Make sure OBS -> Virtual Camera is STARTED before launching. "
                   "Web preview still running. Restart bridge to retry.")
            print(f"[Python] {msg}")
            self._bc.broadcast_log("node", msg)
            self._bc.update_stats(vcamActive=False)
            self._bc.broadcast_status()
            return

        # Trigger full restart for transient failures
        self._trigger_restart(f"Python VCam exited (code {code})")

    def _trigger_restart(self, reason: str) -> None:
        threading.Thread(
            target=self.restart,
            args=(reason,),
            daemon=True,
            name="PipelineRestart",
        ).start()
