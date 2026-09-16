"""
recorder.py — Recording manager.

Spawns an FFmpeg process that reads the raw H.264 TCP stream and writes it
to an MP4 file. The caller must call feed(chunk) for each data chunk received
from Android.
"""

import os
import subprocess
import threading
import time
from typing import Optional


class RecordingManager:
    """
    Manages a single FFmpeg recording subprocess.

    Usage:
        rec = RecordingManager(ffmpeg_path, output_dir, broadcaster)
        filepath = rec.start()          # begin recording
        rec.feed(h264_chunk)            # call from TCP data handler
        saved   = rec.stop()            # end recording, returns file path
    """

    def __init__(self, ffmpeg_path: str, output_dir: str, broadcaster) -> None:
        self._ffmpeg   = ffmpeg_path
        self._out_dir  = output_dir
        self._bc       = broadcaster
        self._proc: Optional[subprocess.Popen] = None
        self._filepath: Optional[str]          = None
        self._lock     = threading.Lock()
        self._sps_pps  = b""

    def clear_codec_config(self) -> None:
        with self._lock:
            self._sps_pps = b""

    # ── Public ───────────────────────────────────────────────────────────────

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    @property
    def filepath(self) -> Optional[str]:
        return self._filepath

    def start(self, fps: int = 30) -> str:
        """Start recording. Returns the output file path."""
        with self._lock:
            if self._proc and self._proc.poll() is None:
                raise RuntimeError("Already recording")
            ts   = time.strftime("%Y-%m-%dT%H-%M-%S")
            path = os.path.join(self._out_dir, f"recording-{ts}.mp4")
            self._filepath = path
            self._proc = subprocess.Popen(
                [
                    self._ffmpeg,
                    "-hide_banner", "-loglevel", "warning",
                    "-f", "h264", "-i", "pipe:0",
                    "-bsf:v", f"setts=ts=N/{fps}/TB",
                    "-c:v", "copy",
                    "-movflags", "+faststart",
                    path,
                ],
                bufsize=0,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            # Log stderr from recording FFmpeg in background
            threading.Thread(
                target=self._read_stderr, args=(self._proc,),
                daemon=True, name="RecorderStderr",
            ).start()
            if self._sps_pps:
                try:
                    self._proc.stdin.write(self._sps_pps)
                    self._proc.stdin.flush()
                except Exception:
                    pass
            print(f"[Record] Started -> {path}")
            self._bc.update_stats(recording=True)
            self._bc.broadcast_status()
            return path

    def stop(self) -> str:
        """Stop recording. Returns the saved file path."""
        with self._lock:
            if not self._proc:
                raise RuntimeError("Not recording")
            saved = self._filepath
            try:
                self._proc.stdin.close()
            except Exception:
                pass
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc    = None
            self._filepath = None
        print(f"[Record] Stopped. File: {saved}")
        self._bc.update_stats(recording=False)
        self._bc.broadcast_status()
        return saved or ""

    def feed(self, chunk: bytes) -> None:
        """Write a raw H.264 chunk to the recording process stdin."""
        with self._lock:
            if not self._sps_pps:
                self._sps_pps = self._extract_sps_pps(chunk)
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.stdin.write(chunk)
                    self._proc.stdin.flush()
                except Exception:
                    pass

    def _extract_sps_pps(self, chunk: bytes) -> bytes:
        sps = b""
        pps = b""
        pos = 0
        offsets = []
        while True:
            idx = chunk.find(b'\x00\x00\x01', pos)
            if idx == -1:
                break
            offsets.append(idx)
            pos = idx + 3
            
        for idx_arr, start_idx in enumerate(offsets):
            end_idx = offsets[idx_arr + 1] if idx_arr + 1 < len(offsets) else len(chunk)
            nal = chunk[start_idx:end_idx]
            
            header_offset = 3
            if len(nal) > 3 and nal[0] == 0 and nal[1] == 0 and nal[2] == 1:
                header_offset = 3
            elif len(nal) > 4 and nal[0] == 0 and nal[1] == 0 and nal[2] == 0 and nal[3] == 1:
                header_offset = 4
            else:
                continue
                
            if len(nal) > header_offset:
                nal_type = nal[header_offset] & 0x1F
                if nal_type == 7:
                    sps = nal
                elif nal_type == 8:
                    pps = nal
                    
        return sps + pps

    def kill(self) -> None:
        """Forcefully terminate any in-progress recording."""
        with self._lock:
            if self._proc:
                try:
                    self._proc.kill()
                except Exception:
                    pass
                self._proc    = None
                self._filepath = None
        self._bc.update_stats(recording=False)

    # ── Private ──────────────────────────────────────────────────────────────

    def _read_stderr(self, proc: subprocess.Popen) -> None:
        try:
            for line in proc.stderr:
                msg = line.decode(errors="replace").strip()
                if msg:
                    self._bc.broadcast_log("node", f"[Record] {msg}")
        except Exception:
            pass
