# Contributing to Webcam Bridge

Thanks for helping out! Bug reports, docs fixes, new gestures, and support for
more platforms are all welcome.

## Ways to help

- **Report a bug** — open an issue using the bug template. Include your OS,
  phone model, Android version and the bridge log (`--no-tui` output is easiest to copy).
- **Suggest a feature** — open a feature request and describe the use case first.
- **Pick an issue** — look for [`good first issue`](https://github.com/16SULPHUR/webcam-bridge/labels/good%20first%20issue)
  or [`help wanted`](https://github.com/16SULPHUR/webcam-bridge/labels/help%20wanted).
  Comment on it so nobody duplicates the work.

## Repository layout

```
android/            Android app (Kotlin, Camera2 + MediaCodec)
desktop/            Desktop bridge (Python package `webcam_bridge`)
  webcam_bridge/    source; web/ is the dashboard, assets/ bundled media
  tests/            pytest suite
  tools/emoji/      rebuilds the bundled Twemoji pack (Node.js)
vcam/windows/       built-in virtual camera DLL (C++, CMake, vendored softcam)
docs/               architecture and feature docs
scripts/            setup / start helpers
```

See [docs/architecture.md](docs/architecture.md) for how the pieces fit.

## Desktop development

```bash
cd desktop
python -m venv .venv
.venv\Scripts\activate          # source .venv/bin/activate on Linux/macOS
pip install -e ".[dev]"

pytest                          # tests
ruff check .                    # lint
python -m webcam_bridge --no-tui
```

Tips:

- Use `WEBCAM_BRIDGE_HOME=<temp dir>` so development runs don't touch your real settings.
- The dashboard is plain HTML/CSS/JS in `webcam_bridge/web/` — no build step.
  Keep it dependency-free.
- `frame_sender.py` runs in a separate process. Never `print()` to stdout
  there, because stdout carries video frames. Use `log()` instead.
- New config keys must be added to `_DEFAULTS` in `config.py`, or they won't be saved.

## Virtual camera development

The DLL in `vcam/windows/` needs Visual Studio 2019+ — see
[vcam/windows/README.md](vcam/windows/README.md). If you only work on Python,
`python -m webcam_bridge.fetch vcam` downloads a prebuilt copy, and CI builds it
for every pull request.

## Android development

Open `android/` in Android Studio, or run
`./gradlew assembleDebug` (JDK 17, SDK 37). Keep `minSdk` at 23 unless there is a strong reason to raise it.

## Pull requests

1. Fork the repo and create a branch: `git checkout -b fix/short-description`.
2. Keep each PR focused on one change. Add or update tests where it makes sense.
3. Make sure `pytest` and `ruff check .` pass, and the Android app builds.
4. Update docs or the README if behaviour changes, and add a line to
   `CHANGELOG.md` under **Unreleased**.
5. Open the PR and fill in the template. CI must be green before merge.

Commit messages: short imperative summary (`Add wink trigger sensitivity`),
with detail in the body if needed.

## Assets and licensing

Only contribute images, sounds or models that you created yourself or that are
under a license compatible with MIT redistribution (e.g. CC0, CC-BY, MIT,
Apache-2.0). Add an entry to [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
for anything you didn't create. Don't commit logos, trademarks or photos of people.

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
