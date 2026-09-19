# Webcam Bridge

**Use your Android phone as a USB webcam.** The phone streams H.264 over USB;
the desktop bridge decodes it, applies effects and feeds its own **Webcam
Bridge** virtual camera that Zoom, Teams, Meet, Discord and OBS can use — no
OBS install required.

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
│                         │ ◄──────────── │   → "Webcam Bridge" virtual camera        │
│ Remote control / widget │  adb reverse  │ Dashboard  http://localhost:5134          │
└─────────────────────────┘               └───────────────────────────────────────────┘
```

More detail in [docs/architecture.md](docs/architecture.md).

## Requirements

| | |
|---|---|
| Phone | Android 6.0+ with [USB debugging](https://developer.android.com/studio/debug/dev-options) enabled |
| Desktop | Windows 10/11 64-bit (Linux/macOS may work — see [below](#linux--macos)) |
| Everything else | Nothing to install. Python, FFmpeg and the virtual camera are in the installer; `adb` is downloaded on first run |

## Quick start

1. **Install the desktop app.** Download `WebcamBridge-Setup-<version>.exe` from the
   [latest release](https://github.com/16SULPHUR/webcam-bridge/releases/latest)
   and run it. It brings its own Python and FFmpeg and registers the **Webcam
   Bridge** virtual camera, so there is nothing else to set up.

   > The installer is not code-signed yet, so Windows SmartScreen shows a
   > warning — choose **More info → Run anyway**.
2. **Install the phone app.** Download `webcam-bridge-<version>.apk` from the same
   release and open it on the phone, or build it yourself
   (see [Building the Android app](#building-the-android-app)).
3. **Open Webcam Bridge** from the Start menu or the desktop shortcut. The
   dashboard opens in your browser on a **Setup** page that checks everything
   and walks you through what is left — mostly plugging the phone in and
   turning on USB debugging.
4. **Pick the camera.** In Zoom / Teams / Meet select **Webcam Bridge**
   (restart apps that were open during setup). Start the bridge first.

That is the whole installation. Afterwards the desktop shortcut is the only
thing you open: it connects to the phone, starts the bridge and opens the
dashboard by itself.

### Running from a source checkout

Contributors and Linux/macOS users run it from source instead. This needs
[Python 3.10+](https://www.python.org/downloads/) (tick **Add python.exe to
PATH**) and, on Windows:

```bat
git clone https://github.com/16SULPHUR/webcam-bridge.git
cd webcam-bridge
scripts\setup.bat
scripts\start.bat
```

`scripts\setup.bat rvm` also installs PyTorch for the higher-quality Robust
Video Matting background engine. On Linux/macOS use `scripts/start.sh`.

### Command-line options

```
webcam-bridge [--host HOST] [--port PORT] [--no-tui] [--version]
webcam-bridge camera install | uninstall | status
```

| Option / variable | Default | Purpose |
|---|---|---|
| `--host` / `WEBCAM_BRIDGE_HOST` | `127.0.0.1` | Dashboard bind address. Use `0.0.0.0` to control it from other devices over Wi-Fi — the dashboard has **no password**, so only do this on a trusted network. |
| `--port` / `WEBCAM_BRIDGE_PORT` | `5134` | Dashboard port |
| `--no-tui` | off | Plain log output instead of the terminal UI |
| `WEBCAM_BRIDGE_HOME` | `%LOCALAPPDATA%\WebcamBridge` | Settings, uploaded backgrounds and memes, models, pet skins |
| `WEBCAM_BRIDGE_RECORDINGS` | `~\Videos\WebcamBridge` | Recordings and snapshots |
| `WEBCAM_BRIDGE_FFMPEG` | the bundled build, else `ffmpeg` on `PATH` | Path to the FFmpeg executable |
| `WEBCAM_BRIDGE_ADB` | the downloaded platform-tools, else `adb` on `PATH` | Path to the adb executable |

### Optional downloads

```bat
desktop\.venv\Scripts\python -m webcam_bridge.fetch models   :: MediaPipe models (otherwise downloaded on first use)
desktop\.venv\Scripts\python -m webcam_bridge.fetch skins    :: Neko skins for custom pets
desktop\.venv\Scripts\python -m webcam_bridge.fetch adb      :: Android platform-tools (the Setup page does this for you)
```

## Virtual camera

On Windows the bridge ships its own DirectShow camera, **Webcam Bridge**
(built from [softcam](https://github.com/tshino/softcam)). The installer
registers it; from a source checkout `scripts\setup.bat` does. You can also
manage it from the dashboard's **Setup** or **Camera** page, or with
`webcam-bridge camera install|uninstall|status`. The **Virtual camera** setting
picks the output: *Automatic* uses Webcam Bridge when installed and OBS Virtual
Camera otherwise. Details and limitations: [vcam/windows/README.md](vcam/windows/README.md).

## Phone remote control

The app's **Control** screen and home-screen widget talk to the dashboard.
Webcam Bridge runs `adb reverse` when it starts, so the default address
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

The installer is Windows-only, but the bridge itself is cross-platform — run it
from a source checkout with `scripts/start.sh`. The built-in camera is
Windows-only; elsewhere `pyvirtualcam` is used instead and needs
[v4l2loopback](https://github.com/umlaeute/v4l2loopback) on Linux and OBS on
macOS. The Setup page works the same on every platform. Reports and fixes are
welcome!

## Troubleshooting

Start at the dashboard's **Setup** page — it checks each piece and offers a
one-click fix for most of what can go wrong.

| Problem | Fix |
|---|---|
| Windows SmartScreen blocks the installer | The build is not code-signed yet — **More info → Run anyway** |
| `adb` not found | Press **Download platform-tools** on the Setup page, or install it yourself and put it on `PATH` |
| Setup page says *USB debugging is not authorised* | Unlock the phone and tap **Allow USB debugging** (tick "always allow") |
| Dashboard says *Android disconnected* | Make sure the app is streaming, then press **Retry connection** on the Setup page |
| No "Webcam Bridge" camera in apps | Install it from the Setup page, restart the meeting app, and start the bridge before selecting the camera |
| Camera shows a dark frozen image | The bridge stopped — start it again |
| `FFmpeg not found` | Reinstall Webcam Bridge, or set `WEBCAM_BRIDGE_FFMPEG` |
| The app does not seem to start | It has no window of its own; look for the browser tab, and at `%LOCALAPPDATA%\WebcamBridge\webcam-bridge.log` |
| `setup.bat` says Python is required | Source checkouts only — install Python from python.org; the Microsoft Store `python` alias doesn't work |
| Phone remote control can't connect | Restart Webcam Bridge (it re-runs `adb reverse`) or use Wi-Fi mode |
| Background removal is slow | Use the MediaPipe engine, lower the resolution, or install the `rvm` extra on an NVIDIA GPU |
| Camera permission denied | Android Settings → Apps → Webcam Bridge → Permissions |

## Contributing

Contributions are very welcome — bug reports, docs, new gestures, platform
support. Read [CONTRIBUTING.md](CONTRIBUTING.md) to get started, and please
follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

[MIT](LICENSE). Bundled third-party material (softcam, Twemoji, oneko) is listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
