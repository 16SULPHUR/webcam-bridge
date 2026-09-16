# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- Android: Gradle 9.7, Android Gradle Plugin 9.4 (built-in Kotlin), compileSdk 37 / targetSdk 36, current AndroidX and
  Material libraries. **Minimum Android version is now 6.0 (API 23).**

## [0.1.0] - 2026-09-16

First public release.

### Added
- Android app streaming the phone camera as H.264 over USB, with remote-control screen and home-screen widget.
- Desktop bridge: virtual camera output, web dashboard, colour/zoom/sharpness controls, background blur/replace
  (MediaPipe or Robust Video Matting), face touch-up, recording and snapshots.
- Gesture and expression reaction overlays with a bundled Twemoji pack.
- Desktop pets (oneko) with optional downloadable skins.
- `webcam-bridge` CLI with `--host`, `--port` and `--no-tui`; `python -m webcam_bridge.fetch` for optional downloads.

### Security
- Dashboard binds to localhost by default, rejects cross-origin POSTs and no longer sends wildcard CORS headers.
