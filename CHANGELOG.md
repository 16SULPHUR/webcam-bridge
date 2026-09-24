# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `WebcamBridge-<version>-portable.exe`: the whole app (adb and the Android app included) in one file.
  It replaces the portable zip.
- The dashboard opens in its own app window (WebView2 on Windows, WebKit on macOS) instead of a
  terminal plus a browser tab; closing the window quits. `--browser` keeps the old behaviour.
- Starting the app while it is already running opens the running dashboard instead of failing.
- Windows builds write their output to `webcam-bridge.log` in the data folder; startup errors show a message box.

### Changed
- Depends on `opencv-contrib-python` (what MediaPipe uses) instead of `opencv-python`, so only one
  OpenCV is installed.

## [0.2.0] - 2026-09-24

### Added
- Windows installer (`WebcamBridge-Setup-<version>.exe`) and portable zip that need no Python, adb or OBS:
  they bundle the bridge, adb and the Android app, and register the Webcam Bridge camera.
- Plug and play: the bridge finds the phone over USB, installs or updates the Android app, sets up
  `adb forward` / `adb reverse`, and opens the app straight into streaming. Replugging the phone works.
- adb is downloaded automatically (pinned, checksum-verified platform-tools) when it isn't installed.
- The dashboard explains what to do next (enable USB debugging, tap Allow, installing the app) and
  shows when a new release is available.
- `webcam-bridge doctor` checks FFmpeg, adb, the phone, the app and the camera.
- `webcam-bridge fetch` replaces `python -m webcam_bridge.fetch` and can also fetch `apk` and `adb`.
- `--no-browser`, `--no-adb` and `--no-update-check` options. The dashboard opens in the browser on start.
- Release automation: one command bumps every version; tagged releases publish the installer, portable
  zip, APK, Python wheel and checksums, plus optional PyPI and winget publishing.
- Every pull request builds and smoke-tests the Windows installer.

### Changed
- `scripts\start.bat` and `scripts/start.sh` just run the bridge; adb handling moved into the bridge.

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
