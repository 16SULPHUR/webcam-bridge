"""
tui.py — Live terminal dashboard for the Webcam Bridge.

Panels: stream health, pipeline effects, reaction detection state, GPU load,
and a de-duplicated log stream. Rendered with `rich`; falls back to plain
prints automatically when stdout is not a TTY (see __main__.py --no-tui).
"""

import queue
import re
import subprocess
import threading
import time
from typing import Optional

from rich.align import Align
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import DASHBOARD_PORT

# Log lines that carry no signal — dropped before they reach the stream.
NOISE = re.compile(
    r"(Processed frame #|frame=\s*\d+|"
    r"All log messages before absl::InitializeLog|"
    r"inference_feedback_manager|"
    r"TensorFlow Lite XNNPACK|"
    r"Created TensorFlow Lite|"
    r"feedback tensors|"
    r"gl_context|landmark_projection_calculator)", re.I)

SOURCES = {
    "system": ("SYSTEM", "green"),
    "node": ("SYSTEM", "green"),
    "python": ("PYTHON", "cyan"),
    "pysender": ("PYTHON", "cyan"),
    "ffmpeg": ("FFMPEG", "magenta"),
    "ffmpeg-vcam": ("FFMPEG", "magenta"),
    "phone": ("PHONE", "yellow"),
}

OK = "bold green"
DIM = "grey50"
WARN = "bold yellow"
BAD = "bold red"


def _bar(fraction: float, width: int = 14) -> str:
    fraction = max(0.0, min(1.0, fraction))
    filled = int(width * fraction)
    colour = "red" if fraction > 0.85 else ("yellow" if fraction > 0.5 else "green")
    return f"[{colour}]" + "█" * filled + "[grey30]" + "░" * (width - filled) + f"[/grey30][/{colour}]"


def _kv(table: Table, key: str, value: str, style: str = "white") -> None:
    table.add_row(Text(key, style=DIM), Text.from_markup(f"[{style}]{value}[/{style}]"))


class TuiManager:
    _instance: Optional["TuiManager"] = None

    def __init__(self, broadcaster, config=None, port: int = DASHBOARD_PORT) -> None:
        self.port = port
        self._bc = broadcaster
        self._cfg = config
        self._queue: queue.Queue = queue.Queue()
        self._logs: list = []           # [ts, source, message, level, count]
        self._max_logs = 200
        self._start = time.monotonic()

        self.gpu = {"name": "—", "util": 0, "mem_used": 0, "mem_total": 1,
                    "temp": 0, "available": False}

        self.running = False
        self._lock = threading.RLock()
        self._live: Optional[Live] = None
        self.layout: Optional[Layout] = None
        TuiManager._instance = self

    @classmethod
    def get_instance(cls) -> Optional["TuiManager"]:
        return cls._instance

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def __enter__(self) -> "TuiManager":
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.stop()

    def start(self) -> None:
        with self._lock:
            if self.running:
                return
            self.running = True

        self.log("system", f"Dashboard ready on http://localhost:{self.port}")
        threading.Thread(target=self._gpu_loop, name="TuiGpu", daemon=True).start()

        self.layout = Layout()
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        self.layout["body"].split_row(
            Layout(name="side", ratio=4, minimum_size=34),
            Layout(name="logs", ratio=8),
        )
        self._live = Live(self.layout, refresh_per_second=6, screen=True)
        self._live.start()

    def stop(self) -> None:
        with self._lock:
            if not self.running:
                return
            self.running = False
        if self._live:
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None
        TuiManager._instance = None
        print("\nBridge stopped.\n")

    # ── Log ingestion ─────────────────────────────────────────────────────────

    def log(self, source: str, message: str) -> None:
        if message and not NOISE.search(message):
            self._queue.put((time.strftime("%H:%M:%S"), source, message))

    @staticmethod
    def _level(msg: str) -> str:
        low = msg.lower()
        if "error" in low or "failed" in low or "traceback" in low:
            return "error"
        if "warn" in low:
            return "warn"
        if low.startswith("✓") or "ready" in low or "started" in low or "fired" in low:
            return "ok"
        return "info"

    def _drain(self) -> None:
        while True:
            try:
                ts, src, msg = self._queue.get_nowait()
            except queue.Empty:
                return
            msg = re.sub(r"^\[(FFmpeg-VCam|python|node)\]\s*", "", msg).strip()
            with self._lock:
                # collapse a repeat of the previous line into a counter
                if self._logs and self._logs[-1][2] == msg and self._logs[-1][1] == src:
                    self._logs[-1][0] = ts
                    self._logs[-1][4] += 1
                    continue
                self._logs.append([ts, src, msg, self._level(msg), 1])
                if len(self._logs) > self._max_logs:
                    self._logs.pop(0)

    # ── GPU polling ───────────────────────────────────────────────────────────

    def _gpu_loop(self) -> None:
        while self.running:
            stats = self._query_gpu()
            with self._lock:
                self.gpu.update(stats)
            time.sleep(1.0)

    @staticmethod
    def _query_gpu() -> dict:
        try:
            res = subprocess.run(
                ["nvidia-smi",
                 "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, check=True, timeout=0.8)
            parts = [p.strip() for p in res.stdout.strip().splitlines()[0].split(",")]
            return {"name": parts[0], "util": int(parts[1]), "mem_used": int(parts[2]),
                    "mem_total": max(1, int(parts[3])), "temp": int(parts[4]), "available": True}
        except Exception:
            return {"name": "no NVIDIA GPU", "util": 0, "mem_used": 0,
                    "mem_total": 1, "temp": 0, "available": False}

    # ── Rendering ─────────────────────────────────────────────────────────────

    def update_render(self) -> None:
        if not self.running or not self._live or not isinstance(self.layout, Layout):
            return
        self._drain()
        stats = self._bc.get_stats()
        cfg = self._cfg.to_dict() if self._cfg else {}
        self.layout["header"].update(self._header(stats, cfg))
        self.layout["side"].update(self._sidebar(stats, cfg))
        self.layout["logs"].update(self._log_panel())
        self.layout["footer"].update(self._footer())

    def _header(self, stats: dict, cfg: dict) -> Panel:
        up = int(time.monotonic() - self._start)
        connected = stats.get("androidConnected")
        vcam = stats.get("vcamActive")
        text = Text.assemble(
            (" WEBCAM BRIDGE ", "bold reverse cyan"),
            ("   ", ""),
            ("● ", OK if connected else BAD),
            ("Streaming" if connected else "Waiting for phone", OK if connected else BAD),
            ("   │   ", DIM),
            (f"{cfg.get('resolution', 'auto')} @ {cfg.get('targetFps', 30)}fps", "white"),
            ("   │   ", DIM),
            ("VCam ", DIM), ("ON" if vcam else "OFF", OK if vcam else DIM),
            ("   │   ", DIM),
            ("up ", DIM), (f"{up // 3600:02d}:{up // 60 % 60:02d}:{up % 60:02d}", "white"),
        )
        return Panel(Align.center(text), border_style="cyan", padding=(0, 1))

    def _sidebar(self, stats: dict, cfg: dict) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_row(self._stream_table(stats, cfg))
        grid.add_row(Text())
        grid.add_row(self._effects_table(cfg))
        grid.add_row(Text())
        grid.add_row(self._reactions_table(stats.get("reactions") or {}, cfg))
        grid.add_row(Text())
        grid.add_row(self._gpu_table())
        return Panel(grid, title="[bold]system[/bold]", border_style="grey35", padding=(0, 1))

    def _stream_table(self, stats: dict, cfg: dict) -> Table:
        t = Table.grid(expand=True, padding=(0, 1))
        t.add_column(ratio=2); t.add_column(ratio=3, justify="right")
        t.add_row(Text("STREAM", style="bold cyan"), Text())
        _kv(t, "bitrate", f"{stats.get('bitrateKBs', 0.0)} KB/s")
        _kv(t, "frames", f"{stats.get('decodedFrames', 0):,}")
        _kv(t, "h264 in", f"{stats.get('h264ReceivedBytes', 0) / 1048576:.1f} MB")
        rec = stats.get("recording")
        _kv(t, "recording", "● REC" if rec else "idle", "bold red" if rec else DIM)
        battery = stats.get("phoneBattery")
        if battery is not None:
            _kv(t, "phone", f"{battery}%  {stats.get('phoneTemperature') or 0:.0f}°C")
        return t

    def _effects_table(self, cfg: dict) -> Table:
        t = Table.grid(expand=True, padding=(0, 1))
        t.add_column(ratio=2); t.add_column(ratio=3, justify="right")
        t.add_row(Text("PIPELINE", style="bold cyan"), Text())
        bg = cfg.get("bgMode", "none")
        _kv(t, "background", bg if bg != "none" else "off", "white" if bg != "none" else DIM)
        if bg != "none":
            _kv(t, "engine", str(cfg.get("segmentationEngine", "mediapipe")).upper())
        touch = cfg.get("faceTouchupEnabled")
        _kv(t, "touch-up", f"{cfg.get('faceTouchupStrength', 0)}%" if touch else "off",
            "white" if touch else DIM)
        zoom = float(cfg.get("zoom", 1.0))
        _kv(t, "zoom/mirror", f"{zoom:.1f}x · {'on' if cfg.get('mirror') else 'off'}")
        return t

    def _reactions_table(self, rx: dict, cfg: dict) -> Table:
        t = Table.grid(expand=True, padding=(0, 1))
        t.add_column(ratio=2); t.add_column(ratio=3, justify="right")
        t.add_row(Text("REACTIONS", style="bold magenta"), Text())

        conf = cfg.get("reactions") or {}
        if not conf.get("enabled"):
            _kv(t, "status", "off", DIM)
            return t

        det_fps = rx.get("detectorFps", 0)
        _kv(t, "detector", f"{rx.get('backend') or '…'}  {det_fps}/s",
            OK if det_fps else WARN)
        _kv(t, "tracking", f"{rx.get('hands', 0)} hands · {rx.get('faces', 0)} faces")
        matched = ", ".join(rx.get("matched") or [])
        _kv(t, "matching", matched or "—", "bold yellow" if matched else DIM)
        _kv(t, "last fired", rx.get("lastFired") or "—",
            "bold green" if rx.get("lastFired") else DIM)
        _kv(t, "on screen", f"{rx.get('overlays', 0)} / {rx.get('mappings', 0)} mapped")
        if conf.get("showTracking"):
            _kv(t, "skeleton", "on preview", "bold cyan")
        return t

    def _gpu_table(self) -> Table:
        with self._lock:
            gpu = dict(self.gpu)
        t = Table.grid(expand=True, padding=(0, 1))
        t.add_column(ratio=2); t.add_column(ratio=3, justify="right")
        t.add_row(Text("GPU", style="bold cyan"), Text(gpu["name"][:22], style=DIM))
        if not gpu["available"]:
            _kv(t, "status", "CPU only", DIM)
            return t
        t.add_row(Text("load", style=DIM),
                  Text.from_markup(f"{_bar(gpu['util'] / 100)} {gpu['util']:>3}%"))
        mem = gpu["mem_used"] / gpu["mem_total"]
        t.add_row(Text("vram", style=DIM),
                  Text.from_markup(f"{_bar(mem)} {gpu['mem_used'] // 1024:.0f}G"))
        temp = gpu["temp"]
        colour = "green" if temp < 62 else ("yellow" if temp < 78 else "red")
        _kv(t, "temp", f"{temp}°C", colour)
        return t

    def _log_panel(self) -> Panel:
        with self._lock:
            logs = list(self._logs[-120:])
        body = Text(no_wrap=False)
        styles = {"error": BAD, "warn": WARN, "ok": "green", "info": "white"}
        for ts, src, msg, level, count in logs:
            label, colour = SOURCES.get(src.lower(), (src.upper()[:6], "white"))
            body.append(f"{ts} ", DIM)
            body.append(f"{label:<6} ", f"bold {colour}")
            body.append(msg, styles[level])
            if count > 1:
                body.append(f"  ×{count}", "bold grey62")
            body.append("\n")
        return Panel(body, title="[bold]logs[/bold]", border_style="grey35", padding=(0, 1))

    def _footer(self) -> Panel:
        text = Text.assemble(
            ("Ctrl+C", "bold white on grey30"), (" stop bridge", DIM),
            ("     ", ""),
            ("dashboard ", DIM),
            (f"http://localhost:{self.port}", "bold underline cyan"),
            ("     ", ""),
            ("--no-tui", "bold white on grey30"), (" plain logs", DIM),
        )
        return Panel(Align.center(text), border_style="grey35", padding=(0, 1))


def run_tui_loop(tui: TuiManager) -> None:
    try:
        while tui.running:
            tui.update_render()
            time.sleep(0.15)
    except KeyboardInterrupt:
        pass
