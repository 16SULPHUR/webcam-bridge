"""
__main__.py — Entry point for the Webcam Bridge desktop stack.

Usage:
    webcam-bridge [--host HOST] [--port PORT] [--no-tui] [--no-browser] [--no-adb]
    webcam-bridge camera install | uninstall | status
    webcam-bridge doctor
    python -m webcam_bridge ...

Starts:
  1. ConfigManager  — loads config.json from the user data directory
  2. EventBroadcaster  — SSE + video hub
  3. RecordingManager  — H.264 → MP4 recording
  4. BridgeServer  — HTTP dashboard
  5. Pipeline  — FFmpeg VCam + Web + Python frame_sender
  6. DeviceManager  — sets up the phone over USB (adb, app install, forwarding)
  7. AndroidTcpClient  — connects to Android over ADB
"""

import argparse
import os
import runpy
import shutil
import sys
import signal
import threading
import webbrowser

from . import __version__, adb, paths, updates
from .config      import DASHBOARD_HOST, DASHBOARD_PORT, ConfigManager
from .broadcaster import EventBroadcaster
from .recorder    import RecordingManager
from .pipeline    import Pipeline
from .tcp_client  import AndroidTcpClient
from .web_server    import BridgeServer
from .phone_stats  import PhoneStatsCollector
from .device       import DeviceManager


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


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
    parser.add_argument("--no-browser", action="store_true", default=_env_flag("WEBCAM_BRIDGE_NO_BROWSER"),
                        help="don't open the dashboard in a browser on start")
    parser.add_argument("--no-adb", action="store_true", default=_env_flag("WEBCAM_BRIDGE_NO_ADB"),
                        help="don't manage the phone over USB (you run adb forward yourself)")
    parser.add_argument("--no-update-check", action="store_true",
                        default=_env_flag("WEBCAM_BRIDGE_NO_UPDATE_CHECK"),
                        help="don't check GitHub for a newer release")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    cam = sub.add_parser("camera", help="manage the built-in 'Webcam Bridge' virtual camera (Windows)")
    cam.add_argument("action", choices=("install", "uninstall", "status"))
    sub.add_parser("doctor", help="check the setup and print a report to paste into bug reports")
    fetch = sub.add_parser("fetch", help="download optional data (models, skins, vcam, apk, adb)")
    fetch.add_argument("fetch_args", nargs=argparse.REMAINDER)
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


def doctor() -> int:
    from . import device, vcam

    ok = True

    def row(label: str, value: str, good: bool = True) -> None:
        nonlocal ok
        ok &= good
        print(f"  [{'OK' if good else '!!'}] {label:<15} {value}")

    print(f"Webcam Bridge {__version__} ({'standalone' if paths.FROZEN else 'Python ' + sys.version.split()[0]})")
    print(f"  platform        {sys.platform}")
    print(f"  data            {paths.DATA_DIR}")
    ffmpeg = paths.resolve_ffmpeg()
    row("FFmpeg", ffmpeg, bool(os.path.isfile(ffmpeg) or shutil.which(ffmpeg)))

    adb_path = adb.find_adb()
    row("adb", adb_path or "not found (downloaded automatically on start)", bool(adb_path))
    if adb_path:
        adb.start_server(adb_path)
        devices = adb.list_devices(adb_path)
        row("phone", ", ".join(f"{s} ({st})" for s, st in devices) or "none connected",
            any(st == "device" for _, st in devices))
        for serial, state in devices:
            if state == "device":
                app = device.installed_app_version(adb_path, serial)
                row("phone app", f"{serial}: " + ("not installed" if app is None else app or "installed"),
                    app is not None)
    apk = device.find_apk()
    print(f"  apk             {apk or 'not bundled (downloaded from the release when needed)'}")

    info = vcam.status()
    if info["supported"]:
        row("virtual camera", "installed" if info["installed"] else "not installed: webcam-bridge camera install",
            info["installed"])
    else:
        print("  virtual camera  OBS / v4l2loopback via pyvirtualcam")

    latest = updates.latest_version()
    if updates.is_newer(latest):
        print(f"  update          {latest} available: {updates.RELEASES_URL}")
    return 0 if ok else 1


def run_frame_sender(argv: list[str]) -> None:
    """Standalone builds have no python.exe, so the exe re-runs itself for the frame processor."""
    sys.argv = [paths.FRAME_SENDER, *argv]
    runpy.run_module("webcam_bridge.frame_sender", run_name="__main__", alter_sys=True)


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["_frame-sender"]:
        run_frame_sender(argv[1:])
        return
    args = parse_args(argv)
    if args.command == "camera":
        sys.exit(camera_command(args.action))
    if args.command == "doctor":
        sys.exit(doctor())
    if args.command == "fetch":
        from .fetch import main as fetch_main
        sys.exit(fetch_main(args.fetch_args))
    paths.ensure_user_dirs()
    ffmpeg_path = paths.resolve_ffmpeg()
    if not (os.path.isfile(ffmpeg_path) or shutil.which(ffmpeg_path)):
        print(f"Error: FFmpeg not found ({ffmpeg_path}).\n"
              "Reinstall Webcam Bridge, install FFmpeg on PATH, "
              "or set WEBCAM_BRIDGE_FFMPEG to ffmpeg.exe.", file=sys.stderr)
        sys.exit(1)

    print("=" * 56)
    print(f"  Webcam Bridge v{__version__}")
    print("=" * 56)
    print(f"  Data:       {paths.DATA_DIR}")
    print(f"  Recordings: {paths.RECORDINGS_DIR}")
    print(f"  FFmpeg:     {ffmpeg_path}")
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
        sender_cmd  = paths.frame_sender_command(),
    )
    server.set_pipeline(pipeline)

    # ── 3b. Phone setup over USB + stats ─────────────────────────────────────
    device = None if args.no_adb else DeviceManager(broadcaster, dashboard_port=args.port)
    if device:
        adb_command = device.adb_command
    else:
        def adb_command():
            found = adb.find_adb()
            return [found] if found else None
    phone_stats = PhoneStatsCollector(broadcaster, adb_command)

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
        if device:
            device.stop()
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
    dashboard_url = f"http://localhost:{args.port}"

    def start_services() -> None:
        threading.Thread(target=server.start, daemon=True, name="WebServer").start()
        pipeline.start()
        tcp_client.start()
        if device:
            device.start()
        phone_stats.start()
        if not args.no_update_check:
            updates.check_in_background(broadcaster)
        if not args.no_browser:
            threading.Timer(1.0, webbrowser.open, args=(dashboard_url,)).start()

    def wait_forever() -> None:
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            shutdown()

    if use_tui and tui:
        with tui:
            threading.Thread(target=run_tui_loop, args=(tui,), daemon=True, name="TuiLoop").start()
            start_services()
            wait_forever()
    else:
        start_services()
        print(f"\nDashboard -> {dashboard_url}")
        print("Press Ctrl+C to stop.\n")
        wait_forever()


if __name__ == "__main__":
    main()
