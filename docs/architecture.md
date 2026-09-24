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
│ device      ── finds the phone, installs the app, adb forward / reverse    │
│ phone_stats ── battery / model via adb shell                               │
│ tui         ── rich terminal UI                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

## Desktop modules

| Module | Responsibility |
|---|---|
| `__main__.py` | CLI, wiring, shutdown |
| `paths.py` | Every filesystem location; env-var overrides |
| `config.py` | Thread-safe `config.json` with defaults |
| `device.py` | Watches `adb devices`; installs/updates the app, sets up forwarding, launches streaming |
| `adb.py` | Finds adb, or downloads a pinned platform-tools build on first use |
| `tcp_client.py` | Connects to the phone, reconnects, sends commands |
| `pipeline.py` | Spawns FFmpeg and `frame_sender.py`, restarts on failure |
| `frame_sender.py` | Per-frame processing; re-reads `config.json` so changes apply live |
| `rvm_matting.py`, `face_touchup.py` | Optional heavy effects, loaded lazily |
| `reactions/` | Gesture/expression detection and overlay animation — see [reactions.md](reactions.md) |
| `vcam.py` | Virtual camera output (built-in DirectShow camera or pyvirtualcam) and its installer |
| `recorder.py` | Remuxes the raw H.264 stream to MP4 |
| `web_server.py` | Standard-library HTTP server for the dashboard |
| `fetch.py` | Optional downloads (MediaPipe models, Neko skins, camera DLLs, APK, adb) |
| `updates.py` | Checks GitHub for a newer release |

`frame_sender.py` runs as its own process. It communicates with the bridge
through pipes: stdin carries raw frames, stdout carries length-prefixed JPEGs,
and stderr carries logs (lines beginning with `@@RX ` are reaction status).
C libraries that print to stdout are redirected so they can't corrupt the frame
protocol.

## Phone setup over USB

`device.py` polls `adb devices` every two seconds. When a phone becomes
available it installs the Webcam Bridge app if it is missing or older than the
bridge (APK bundled by the installer, else downloaded from the matching GitHub
release and checked against `SHA256SUMS.txt`), runs `adb forward tcp:8080` and
`adb reverse tcp:5134`, and starts `MainActivity` with `--ez stream true` so
the app skips its mode picker. Unplugging resets the state, so replugging sets
everything up again. Its progress is shown on the dashboard as `deviceState` /
`deviceHint`. `--no-adb` turns all of this off.

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

| Channel | Built by | Contents |
|---|---|---|
| `WebcamBridge-Setup-<v>.exe` | `packaging/windows/` (PyInstaller + Inno Setup) | Standalone bridge (no Python needed), adb, the APK, the registered camera |
| `WebcamBridge-<v>-windows-x64.zip` | same | Portable copy of the above; run `webcam-bridge camera install` once |
| `webcam_bridge-<v>-py3-none-any.whl` | `python -m build desktop` | pip / pipx install, camera DLLs included |
| `webcam-bridge-<v>.apk` | Gradle | The Android app |

Standalone builds have no `python.exe`, so the exe starts the frame processor
by re-running itself as `webcam-bridge _frame-sender <config>`
(`paths.frame_sender_command()`). `packaging/smoke_test.py` checks a build end
to end, including MediaPipe. Releases are described in [releasing.md](releasing.md).

## Security model

The dashboard has no authentication. It binds to `127.0.0.1` by default,
sends no permissive CORS headers, rejects cross-origin `POST`s, and confines
file serving to known directories. Binding to `0.0.0.0` exposes the camera to
the local network; the bridge prints a warning when you do.
