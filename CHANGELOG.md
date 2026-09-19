# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **One-click Windows installer** (`WebcamBridge-Setup-<version>.exe`): bundles Python, FFmpeg and the
  virtual camera, registers the camera during installation and adds Start-menu and desktop shortcuts.
  Nothing else has to be installed by hand.
- The desktop shortcut now does what `scripts\start.bat` did — connect to the phone, set up the USB port
  forwards, start the bridge and open the dashboard — so there is a single thing to open.
- **Setup page** in the dashboard: a live checklist of FFmpeg, the virtual camera, `adb`, the phone, the
  phone app and the video stream, with one-click fixes. It opens automatically until you have been through it.
- Android platform-tools is downloaded on demand (`python -m webcam_bridge.fetch adb` or the Setup page)
  instead of having to be installed and put on `PATH` by hand.
- `WEBCAM_BRIDGE_ADB` overrides which `adb` is used.

### Changed
- The bundled FFmpeg is preferred over one on `PATH`, so a stale system build cannot break decoding.
- The installer ships an LGPL FFmpeg build rather than the GPL one `pip` installs; see
  [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

### Fixed
- `adb devices` daemon-startup output was parsed as if it were a connected device.

## [0.1.1] - 2026-09-17

### Fixed
- `start.bat` crashed when FFmpeg was not on `PATH`: FFmpeg is now installed with the bridge (imageio-ffmpeg),
  and a missing FFmpeg gives a clear message instead of a traceback.
- Background blur/replace and face touch-up did nothing with mediapipe 1.x (the default on new installs and
  Python 3.13+); they now use the MediaPipe Tasks API when the legacy API is unavailable.
- MediaPipe model files are downloaded automatically on first use.

## [0.1.0] - 2026-09-17

First public release.

### Added
- Android app (Android 6.0+) streaming the phone camera as H.264 over USB, with remote-control screen and
  home-screen widget.
- Desktop bridge: web dashboard, colour/zoom/sharpness controls, background blur/replace
  (MediaPipe or Robust Video Matting), face touch-up, recording and snapshots.
- Built-in **Webcam Bridge** virtual camera for Windows (DirectShow, based on softcam) — OBS is optional.
  Manage it with `webcam-bridge camera install|uninstall|status` or from the dashboard's Camera page;
  the `vcamBackend` setting chooses between Automatic, Webcam Bridge and OBS.
- Gesture and expression reaction overlays with a bundled Twemoji pack.
- Desktop pets (oneko) with optional downloadable skins.
- `webcam-bridge` CLI with `--host`, `--port` and `--no-tui`; `python -m webcam_bridge.fetch` for optional
  downloads (models, skins, camera DLLs).

### Security
- Dashboard binds to localhost by default, rejects cross-origin POSTs and no longer sends wildcard CORS headers.
