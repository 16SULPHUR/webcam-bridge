# Webcam Bridge

**Use your Android phone as a USB webcam.** The phone streams H.264 over USB;
the desktop bridge decodes it, applies effects and feeds a virtual camera that
Zoom, Teams, Meet, Discord and OBS can use.

[![CI](https://github.com/16SULPHUR/webcam-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/16SULPHUR/webcam-bridge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

- 📱 **Phone camera over USB** — low latency, no Wi-Fi needed
- 🎛️ **Web dashboard** — live preview, resolution / FPS, zoom, colour, sharpness
- 🌄 **Virtual backgrounds** — blur or replace, with MediaPipe or Robust Video Matting
- ✨ **Face touch-up**, recording and snapshots
- 🎭 **Reaction overlays** — thumbs-up, peace sign, heart hands or a smile trigger animated emoji and memes
- 🐈 **Desktop pets** for your video feed
- 🕹️ **Remote control** from the phone app and a home-screen widget

## How it works

```
Android phone                                   Desktop (Windows)
┌─────────────────────────┐   USB (adb)   ┌───────────────────────────────────────────┐
│ Camera2 → MediaCodec    │ ────────────► │ TCP client (localhost:8080)               │
│ H.264 → TCP server :8080│               │   → FFmpeg decode → Python effects        │
│                         │ ◄──────────── │   → pyvirtualcam (OBS Virtual Camera)     │
│ Remote control / widget │  adb reverse  │ Dashboard  http://localhost:5134          │
└─────────────────────────┘               └───────────────────────────────────────────┘
```

More detail in [docs/architecture.md](docs/architecture.md).

## Requirements

| | |
|---|---|
| Phone | Android 6.0+ with [USB debugging](https://developer.android.com/studio/debug/dev-options) enabled |
| Desktop | Windows 10/11 (Linux/macOS may work — see [below](#linux--macos)) |
| Python | 3.10 – 3.12 ([python.org](https://www.python.org/downloads/)) |
| FFmpeg | On `PATH` ([ffmpeg.org](https://ffmpeg.org/download.html)), or set `WEBCAM_BRIDGE_FFMPEG` |
| ADB | [Android platform-tools](https://developer.android.com/tools/releases/platform-tools) on `PATH` |
| Virtual camera | [OBS Studio](https://obsproject.com) 26+ (provides the "OBS Virtual Camera" device) |

## Quick start

1. **Install the phone app.** Download `webcam-bridge-<version>.apk` from the
   [latest release](https://github.com/16SULPHUR/webcam-bridge/releases/latest)
   and install it, or build it yourself (see [Building the Android app](#building-the-android-app)).
2. **Get the desktop bridge.** Download the source zip from the same release
   (or `git clone https://github.com/16SULPHUR/webcam-bridge.git`), then run:
   ```bat
   scripts\setup.bat
   ```
   Add `rvm` (`scripts\setup.bat rvm`) to also install PyTorch for the
   higher-quality Robust Video Matting background engine.
3. **Connect.** Plug the phone in over USB, open the app and tap **Start Streaming**, then:
   ```bat
   scripts\start.bat
   ```
4. **Open the dashboard** at <http://localhost:5134>.
5. **Pick the camera.** In Zoom / Teams / OBS select **OBS Virtual Camera**.

### Command-line options

```
webcam-bridge [--host HOST] [--port PORT] [--no-tui] [--version]
```

| Option / variable | Default | Purpose |
|---|---|---|
| `--host` / `WEBCAM_BRIDGE_HOST` | `127.0.0.1` | Dashboard bind address. Use `0.0.0.0` to control it from other devices over Wi-Fi — the dashboard has **no password**, so only do this on a trusted network. |
| `--port` / `WEBCAM_BRIDGE_PORT` | `5134` | Dashboard port |
| `--no-tui` | off | Plain log output instead of the terminal UI |
| `WEBCAM_BRIDGE_HOME` | `%LOCALAPPDATA%\WebcamBridge` | Settings, uploaded backgrounds and memes, models, pet skins |
| `WEBCAM_BRIDGE_RECORDINGS` | `~\Videos\WebcamBridge` | Recordings and snapshots |
| `WEBCAM_BRIDGE_FFMPEG` | `ffmpeg` on `PATH` | Path to the FFmpeg executable |

### Optional downloads

```bat
desktop\.venv\Scripts\python -m webcam_bridge.fetch models   :: MediaPipe models (needed with mediapipe >= 1.0)
desktop\.venv\Scripts\python -m webcam_bridge.fetch skins    :: Neko skins for custom pets
```

## Phone remote control

The app's **Control** screen and home-screen widget talk to the dashboard.
`scripts\start.bat` runs `adb reverse`, so the default address
`127.0.0.1:5134` works over the USB cable. For Wi-Fi control, start the bridge
with `--host 0.0.0.0` and enter your PC's LAN address (e.g. `192.168.1.5:5134`).

## Reaction overlays 🎭

Throw a thumbs-up, a peace sign, heart hands or a big smile at the camera and
the matching emoji (or your own meme) animates onto the stream. Everything
lives on the dashboard's **Reactions** page. Adding gestures, animations and
artwork is documented in [docs/reactions.md](docs/reactions.md).

## Building the Android app

Requires JDK 17 and the Android SDK (API 37). Android Studio works out of the
box — open the `android/` folder. From the command line:

```bat
cd android
gradlew.bat assembleDebug
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

`scripts\install-android.bat` does both steps.

## Linux / macOS

The bridge is developed on Windows, but its dependencies are cross-platform.
`pyvirtualcam` needs [v4l2loopback](https://github.com/umlaeute/v4l2loopback)
on Linux and OBS on macOS. Use `scripts/start.sh`. Reports and fixes are welcome!

## Troubleshooting

| Problem | Fix |
|---|---|
| `adb` not found | Install platform-tools and add the folder to `PATH` |
| Dashboard says *Android disconnected* | Make sure the app is streaming and `adb forward tcp:8080 tcp:8080` ran (`scripts\start.bat` does this) |
| No "OBS Virtual Camera" device | Install OBS 26+ and start its virtual camera once |
| `ffmpeg` not found | Add FFmpeg's `bin` folder to `PATH` or set `WEBCAM_BRIDGE_FFMPEG` |
| Phone remote control can't connect | Re-run `scripts\start.bat` (sets up `adb reverse`) or use Wi-Fi mode |
| Background removal is slow | Use the MediaPipe engine, lower the resolution, or install the `rvm` extra on an NVIDIA GPU |
| Camera permission denied | Android Settings → Apps → Webcam Bridge → Permissions |

## Contributing

Contributions are very welcome — bug reports, docs, new gestures, platform
support. Read [CONTRIBUTING.md](CONTRIBUTING.md) to get started, and please
follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

[MIT](LICENSE). Bundled third-party material (Twemoji, oneko) is listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
