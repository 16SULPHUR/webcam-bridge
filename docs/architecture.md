# Architecture

Webcam Bridge has two halves that talk over an `adb` USB connection.

```
┌──────────────── Android (android/) ────────────────┐
│ MainActivity ── CameraStreamer                     │
│                  Camera2 → MediaCodec (H.264)      │
│                  TCP server :8080 ─────────────────┼──┐  adb forward tcp:8080
│                  ◄── JSON commands (switch camera) │  │
│ ControlActivity / ControlWidgetProvider            │  │
│   └─ NetworkHelper → HTTP 127.0.0.1:5134 ──────────┼──┼─┐  adb reverse tcp:5134
└────────────────────────────────────────────────────┘  │ │
                                                        │ │
┌──────────────── Desktop (desktop/webcam_bridge/) ─────▼─▼──────────────────┐
│ tcp_client ──► pipeline.feed ──► FFmpeg (h264 → raw BGR24)                 │
│                    │                 │                                     │
│                    │                 ▼                                     │
│                    │           frame_sender.py  (separate process)         │
│                    │             zoom · colour · background · touch-up     │
│                    │             pets · reactions                          │
│                    │                 ├──► vcam → "Webcam Bridge" camera    │
│                    │                 └──► JPEG frames → dashboard preview  │
│                    └──► recorder (H.264 → MP4, no re-encode)               │
│                                                                            │
│ web_server  ── dashboard (web/), REST API, SSE logs, MJPEG preview         │
│ broadcaster ── fan-out hub for logs, stats and video                       │
│ config      ── config.json (read live by frame_sender)                     │
│ phone_stats ── battery / model via adb shell                               │
│ tui         ── rich terminal UI                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

## Desktop modules

| Module | Responsibility |
|---|---|
| `__main__.py` | CLI, wiring, shutdown |
| `launcher.py` | What the Windows shortcut runs: adb, USB forwards, browser, then `__main__` |
| `paths.py` | Every filesystem location; env-var overrides; source vs. packaged layout |
| `adb.py` | Finding and running `adb`; device, package and port-forward helpers |
| `setup_state.py` | The dashboard's Setup checklist and its one-click fixes |
| `config.py` | Thread-safe `config.json` with defaults |
| `tcp_client.py` | Connects to the phone, reconnects, sends commands |
| `pipeline.py` | Spawns FFmpeg and `frame_sender.py`, restarts on failure |
| `frame_sender.py` | Per-frame processing; re-reads `config.json` so changes apply live |
| `rvm_matting.py`, `face_touchup.py` | Optional heavy effects, loaded lazily |
| `reactions/` | Gesture/expression detection and overlay animation — see [reactions.md](reactions.md) |
| `vcam.py` | Virtual camera output (built-in DirectShow camera or pyvirtualcam) and its installer |
| `recorder.py` | Remuxes the raw H.264 stream to MP4 |
| `web_server.py` | Standard-library HTTP server for the dashboard |
| `fetch.py` | Optional downloads (MediaPipe models, Neko skins, platform-tools) |
| `procs.py` | Subprocess flags — keeps helper consoles hidden in the packaged app |

`frame_sender.py` runs as its own process. It communicates with the bridge
through pipes: stdin carries raw frames, stdout carries length-prefixed JPEGs,
and stderr carries logs (lines beginning with `@@RX ` are reaction status).
C libraries that print to stdout are redirected so they can't corrupt the frame
protocol.

## Virtual camera

`vcam/windows/` builds `webcam_bridge_cam.dll`, a DirectShow source filter
(vendored softcam). The bridge loads it with `ctypes` and writes frames to
shared memory; camera apps load the same DLL, registered once with `regsvr32`,
and read from that memory. See [vcam/windows/README.md](../vcam/windows/README.md).

## Files on disk

Bundled resources ship inside the package (`web/`, `assets/`). Anything a user
creates goes to the data directory (`WEBCAM_BRIDGE_HOME`, default
`%LOCALAPPDATA%\WebcamBridge`), and recordings go to
`WEBCAM_BRIDGE_RECORDINGS` (default `~/Videos/WebcamBridge`).

## Packaging

`desktop/packaging/webcam-bridge.spec` freezes the bridge with PyInstaller into
a self-contained folder — CPython, every wheel, an LGPL FFmpeg
(`packaging/fetch_ffmpeg.py`) and the camera DLLs.
`packaging/windows/webcam-bridge.iss` wraps that in an Inno Setup installer,
which registers the camera by calling the app's own `camera install`.

The frozen build has no `python.exe`, so `pipeline.py` starts the frame
processor by re-running the app as `WebcamBridge.exe --frame-sender <config>`;
`packaging/entry.py` routes that back into `frame_sender.main()`. It also has
no console, so `launcher.py` sends output to `webcam-bridge.log` in the data
directory. Android platform-tools is never bundled — Google's SDK terms do not
allow redistributing it — so the Setup page downloads it on first run.

## Security model

The dashboard has no authentication. It binds to `127.0.0.1` by default,
sends no permissive CORS headers, rejects cross-origin `POST`s, and confines
file serving to known directories. Binding to `0.0.0.0` exposes the camera to
the local network; the bridge prints a warning when you do.
