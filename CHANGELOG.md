# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
