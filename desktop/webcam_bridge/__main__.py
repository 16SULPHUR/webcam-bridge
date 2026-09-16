"""
__main__.py — Entry point for the Webcam Bridge desktop stack.

Usage:
    webcam-bridge [--host HOST] [--port PORT] [--no-tui]
    python -m webcam_bridge ...

Starts:
  1. ConfigManager  — loads config.json from the user data directory
  2. EventBroadcaster  — SSE + video hub
  3. RecordingManager  — H.264 → MP4 recording
  4. BridgeServer  — HTTP dashboard
  5. Pipeline  — FFmpeg VCam + Web + Python frame_sender
  6. AndroidTcpClient  — connects to Android over ADB
"""

import argparse
import os
import shutil
import sys
import signal
import threading

from . import __version__, paths
from .config      import DASHBOARD_HOST, DASHBOARD_PORT, ConfigManager
from .broadcaster import EventBroadcaster
from .recorder    import RecordingManager
from .pipeline    import Pipeline
from .tcp_client  import AndroidTcpClient
from .web_server    import BridgeServer
from .phone_stats  import PhoneStatsCollector


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="webcam-bridge",
        description="Use an Android phone as a USB webcam (desktop bridge).",
    )
    parser.add_argument("--host", default=os.environ.get("WEBCAM_BRIDGE_HOST", DASHBOARD_HOST),
                        help="dashboard bind address (default: %(default)s; "
                             "use 0.0.0.0 to allow other devices on your network)")
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("WEBCAM_BRIDGE_PORT", DASHBOARD_PORT)),
                        help="dashboard port (default: %(default)s)")
    parser.add_argument("--no-tui", action="store_true", help="plain log output instead of the terminal UI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    cam = sub.add_parser("camera", help="manage the built-in 'Webcam Bridge' virtual camera (Windows)")
    cam.add_argument("action", choices=("install", "uninstall", "status"))
    return parser.parse_args(argv)


def camera_command(action: str) -> int:
    from . import vcam

    try:
        if action == "install":
            print(vcam.install())
        elif action == "uninstall":
            print(vcam.uninstall())
        else:
            info = vcam.status()
            if not info["supported"]:
                print("The built-in camera is Windows-only; OBS / v4l2loopback is used on this platform.")
                return 0
            print(f'"{info["name"]}" camera: {"installed" if info["installed"] else "not installed"}')
            for arch, state in info["arches"].items():
                where = state["path"] or "-"
                print(f"  {arch}: bundled={'yes' if state['bundled'] else 'no'}  "
                      f"registered={'yes' if state['registered'] else 'no'}  {where}")
    except vcam.VirtualCameraError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv=None) -> None:
    args = parse_args(argv)
    if args.command == "camera":
        sys.exit(camera_command(args.action))
    paths.ensure_user_dirs()
    ffmpeg_path = paths.resolve_ffmpeg()
    if not (os.path.isfile(ffmpeg_path) or shutil.which(ffmpeg_path)):
        print(f"Error: FFmpeg not found ({ffmpeg_path}).\n"
              "Reinstall the bridge (scripts\\setup.bat), install FFmpeg on PATH, "
              "or set WEBCAM_BRIDGE_FFMPEG to ffmpeg.exe.", file=sys.stderr)
        sys.exit(1)

    print("=" * 56)
    print(f"  Webcam Bridge v{__version__}")
    print("=" * 56)
    print(f"  Data:       {paths.DATA_DIR}")
    print(f"  Recordings: {paths.RECORDINGS_DIR}")
    print(f"  FFmpeg:     {ffmpeg_path}")
    print(f"  Python:     {sys.executable}")
    print()

    # ── 1. Core services ──────────────────────────────────────────────────────
    config      = ConfigManager(paths.CONFIG_PATH)
    broadcaster = EventBroadcaster()
    recorder    = RecordingManager(ffmpeg_path, paths.RECORDINGS_DIR, broadcaster)

    # Initialize TUI
    from .tui import TuiManager, run_tui_loop
    use_tui = sys.stdout.isatty() and not args.no_tui
    tui = TuiManager(broadcaster, config, port=args.port) if use_tui else None

    # ── 2. HTTP server ────────────────────────────────────────────────────────
    server = BridgeServer(config, broadcaster, recorder, host=args.host, port=args.port)

    # ── 3. Pipeline ───────────────────────────────────────────────────────────
    pipeline = Pipeline(
        config      = config,
        broadcaster = broadcaster,
        recorder    = recorder,
        ffmpeg_path = ffmpeg_path,
        python_path = sys.executable,
        script_path = paths.FRAME_SENDER,
    )
    server.set_pipeline(pipeline)

    # ── 3b. Phone stats collector (ADB-based) ────────────────────────────────
    phone_stats = PhoneStatsCollector(broadcaster)

    # ── 4. TCP client (connects to Android) ───────────────────────────────────
    def on_disconnect():
        broadcaster.update_stats(androidConnected=False)
        broadcaster.broadcast_status()
        recorder.clear_codec_config()
        pipeline.restart("Android disconnected - pipeline reset")

    tcp_client = AndroidTcpClient(
        broadcaster   = broadcaster,
        data_callback = pipeline.feed,
        on_connect    = None,
        on_disconnect = on_disconnect,
    )
    pipeline.set_on_stop(lambda: tcp_client.disconnect())
    server.set_tcp_client(tcp_client)

    # ── 5. Shutdown handler ───────────────────────────────────────────────────
    def shutdown(sig=None, frame=None):
        print("\n[Bridge] Shutting down...")
        phone_stats.stop()
        tcp_client.stop()
        pipeline.stop("Shutdown")
        recorder.kill()
        server.stop()
        if use_tui and tui:
            tui.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # ── 6. Start everything ───────────────────────────────────────────────────
    if use_tui and tui:
        with tui:
            # Spawn TUI rendering update thread
            tui_thread = threading.Thread(target=run_tui_loop, args=(tui,), daemon=True, name="TuiLoop")
            tui_thread.start()

            # HTTP server in a daemon thread
            threading.Thread(target=server.start, daemon=True, name="WebServer").start()

            # Pipeline starts immediately (waits for Android data via feed())
            pipeline.start()

            # TCP client starts connecting in background
            tcp_client.start()

            # Phone stats collector starts polling via ADB
            phone_stats.start()

            # Block main thread
            try:
                threading.Event().wait()
            except KeyboardInterrupt:
                shutdown()
    else:
        # Fallback raw terminal layout
        threading.Thread(target=server.start, daemon=True, name="WebServer").start()
        pipeline.start()
        tcp_client.start()
        phone_stats.start()

        print(f"\nDashboard -> http://localhost:{args.port}")
        print("Press Ctrl+C to stop.\n")

        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            shutdown()


if __name__ == "__main__":
    main()
