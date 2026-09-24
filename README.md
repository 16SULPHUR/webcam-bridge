# Webcam Bridge

**Use your Android phone as a USB webcam.** Install it, plug your phone in, and
pick **Webcam Bridge** as the camera in Zoom, Teams, Meet, Discord or OBS. The
bridge installs the phone app for you, and there's nothing else to set up.

[![CI](https://github.com/16SULPHUR/webcam-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/16SULPHUR/webcam-bridge/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/16SULPHUR/webcam-bridge)](https://github.com/16SULPHUR/webcam-bridge/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/16SULPHUR/webcam-bridge/total)](https://github.com/16SULPHUR/webcam-bridge/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

- 📱 **Phone camera over USB**: low latency, no Wi-Fi needed
- 🔌 **Plug and play**: finds the phone, installs and updates the app, starts streaming
- 🎛️ **Web dashboard**: live preview, resolution / FPS, zoom, colour, sharpness
- 🌄 **Virtual backgrounds**: blur or replace, with MediaPipe or Robust Video Matting
- ✨ **Face touch-up**, recording and snapshots
- 🎭 **Reaction overlays**: thumbs-up, peace sign, heart hands or a smile trigger animated emoji and memes
- 🐈 **Desktop pets** for your video feed
- 🕹️ **Remote control** from the phone app and a home-screen widget

## Get started

### 1. Install

**Windows 10/11:** download **`WebcamBridge-Setup-<version>.exe`** from the
[latest release](https://github.com/16SULPHUR/webcam-bridge/releases/latest)
and run it. It includes everything: no Python, adb or OBS needed, and it sets up
the **Webcam Bridge** camera. Prefer no installer? Download the single-file
**`WebcamBridge-<version>-portable.exe`** and double-click it (it takes a few
seconds longer to start, because it unpacks itself each time).

**Linux / macOS:**

```bash
pipx install webcam-bridge
```

The virtual camera uses [v4l2loopback](https://github.com/umlaeute/v4l2loopback)
on Linux (`sudo apt install v4l2loopback-dkms`) and
[OBS](https://obsproject.com) on macOS.

### 2. Turn on USB debugging on the phone

Settings → About phone → tap **Build number** seven times, then turn on
**Developer options → USB debugging**. [Step-by-step guide and phone-specific notes](docs/phone-setup.md).

### 3. Plug in and start

Open **Webcam Bridge** from the Start menu (or run `webcam-bridge`), plug the
phone in and tap **Allow** on the phone. The bridge installs the app, opens it
and starts streaming; the dashboard opens in its own window (on Linux, in your
browser at <http://localhost:5134>).

Then choose **Webcam Bridge** as the camera in your video app. Apps that were
already open need a restart to see it.

Something not working? Run **Webcam Bridge (troubleshoot)** from the Start menu
or `webcam-bridge doctor`; it checks every piece and says what's missing.

## How it works

```
Android phone                                   Desktop
┌─────────────────────────┐   USB (adb)   ┌───────────────────────────────────────────┐
│ Camera2 → MediaCodec    │ ────────────► │ TCP client (localhost:8080)               │
│ H.264 → TCP server :8080│               │   → FFmpeg decode → Python effects        │
│                         │ ◄──────────── │   → "Webcam Bridge" virtual camera        │
│ Remote control / widget │  adb reverse  │ Dashboard  http://localhost:5134          │
└─────────────────────────┘               └───────────────────────────────────────────┘
```

More detail in [docs/architecture.md](docs/architecture.md).

## Command line

```
webcam-bridge [--host HOST] [--port PORT] [--no-tui] [--no-browser] [--no-adb] [--no-update-check]
webcam-bridge doctor
webcam-bridge camera install | uninstall | status
webcam-bridge fetch models | skins | vcam | apk | adb | all
```

| Option / variable | Default | Purpose |
|---|---|---|
| `--host` / `WEBCAM_BRIDGE_HOST` | `127.0.0.1` | Dashboard bind address. Use `0.0.0.0` to control it from other devices over Wi-Fi. The dashboard has **no password**, so only do this on a trusted network. |
| `--port` / `WEBCAM_BRIDGE_PORT` | `5134` | Dashboard port |
| `--browser` / `WEBCAM_BRIDGE_BROWSER` | off | Open the dashboard in your web browser instead of its own window |
| `--no-browser` / `WEBCAM_BRIDGE_NO_BROWSER` | off | Don't open the dashboard at all |
| `--no-tui` | off | Plain log output instead of the terminal UI (when started from a terminal) |
| `--no-adb` / `WEBCAM_BRIDGE_NO_ADB` | off | Don't manage the phone; run `adb forward tcp:8080 tcp:8080` yourself |
| `--no-update-check` / `WEBCAM_BRIDGE_NO_UPDATE_CHECK` | off | Don't check GitHub for new releases |
| `WEBCAM_BRIDGE_HOME` | `%LOCALAPPDATA%\WebcamBridge` | Settings, uploads, models, downloaded adb and APK |
| `WEBCAM_BRIDGE_RECORDINGS` | `~\Videos\WebcamBridge` | Recordings and snapshots |
| `WEBCAM_BRIDGE_FFMPEG` | `ffmpeg` on `PATH`, else the bundled build | FFmpeg executable |
| `WEBCAM_BRIDGE_ADB` | `adb` on `PATH`, else bundled or downloaded | adb executable |
| `WEBCAM_BRIDGE_APK` | bundled, else downloaded from the release | Android app to install on the phone |

## Virtual camera

On Windows the bridge ships its own DirectShow camera, **Webcam Bridge**
(built from [softcam](https://github.com/tshino/softcam)). The installer
registers it; with the portable exe or pip, run `webcam-bridge camera install`
or use the dashboard's **Camera** page. The **Virtual camera** setting picks the
output: *Automatic* uses Webcam Bridge when installed and OBS Virtual Camera
otherwise. Details and limitations: [vcam/windows/README.md](vcam/windows/README.md).

## Phone remote control

The app's **Control** screen and home-screen widget talk to the dashboard. The
bridge runs `adb reverse`, so the default address `127.0.0.1:5134` works over
the USB cable. For Wi-Fi control, start the bridge with `--host 0.0.0.0` and
enter your PC's LAN address (e.g. `192.168.1.5:5134`).

## Reaction overlays 🎭

Throw a thumbs-up, a peace sign, heart hands or a big smile at the camera and
the matching emoji (or your own meme) animates onto the stream. Everything
lives on the dashboard's **Reactions** page. Adding gestures, animations and
artwork is documented in [docs/reactions.md](docs/reactions.md).

## Troubleshooting

| Problem | Fix |
|---|---|
| Dashboard says *Plug your phone in* | Check the cable carries data, USB debugging is on, and see [phone setup](docs/phone-setup.md) |
| Dashboard says *tap Allow* | Unlock the phone and accept the USB debugging prompt |
| *Could not install the app* | Xiaomi and some other phones need **Install via USB** turned on ([details](docs/phone-setup.md#phone-specific-notes)), or sideload the APK |
| *Uninstall the old Webcam Bridge app* | The installed app was signed with a different key; uninstall it once and reconnect |
| No "Webcam Bridge" camera in apps | Run `webcam-bridge camera install`, restart the app, and start the bridge before selecting the camera |
| Camera shows a dark frozen image | The bridge stopped; start it again |
| Windows SmartScreen warns about the installer | Click **More info → Run anyway**; the installer isn't code-signed yet |
| Background removal is slow | Use the MediaPipe engine or a lower resolution. The RVM engine needs the pip install with the `rvm` extra |
| Camera permission denied | Android Settings → Apps → Webcam Bridge → Permissions |

Still stuck? [Open an issue](https://github.com/16SULPHUR/webcam-bridge/issues/new/choose)
and paste the output of `webcam-bridge doctor`.

## Building from source

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, and
[docs/releasing.md](docs/releasing.md) for how releases are built.

## Contributing

Contributions are very welcome: bug reports, docs, new gestures, platform
support. Read [CONTRIBUTING.md](CONTRIBUTING.md) to get started, and please
follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

[MIT](LICENSE). Bundled third-party material (softcam, Twemoji, oneko, Android
platform-tools in the Windows builds) is listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
