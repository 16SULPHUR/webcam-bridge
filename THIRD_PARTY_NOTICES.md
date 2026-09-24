# Third-party notices

Webcam Bridge is MIT-licensed (see [LICENSE](LICENSE)). It bundles or uses the
following third-party material.

## Bundled

| Material | Where | License |
|---|---|---|
| [softcam](https://github.com/tshino/softcam) — Copyright (c) 2020 tshino, including Microsoft DirectShow BaseClasses | `vcam/windows/third_party/softcam/` and the `webcam_bridge_cam.dll` built from it | [MIT](vcam/windows/third_party/softcam/LICENSE) |
| [Twemoji](https://github.com/jdecked/twemoji) graphics — Copyright 2019 Twitter, Inc and other contributors | `desktop/webcam_bridge/assets/emoji/` (rasterized from SVG) | [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `oneko.gif` sprite sheet from [oneko.js](https://github.com/adryd325/oneko.js) by adryd325 | `desktop/webcam_bridge/web/img/oneko.gif` | [MIT](https://github.com/adryd325/oneko.js/blob/main/LICENSE) |
| Gradle Wrapper | `android/gradle/wrapper/` | [Apache-2.0](https://github.com/gradle/gradle/blob/master/LICENSE) |

## Standalone Windows builds

The installer and portable zip also contain a Python runtime, the Python
dependencies from `desktop/pyproject.toml`, and:

| Material | License |
|---|---|
| `adb.exe`, `AdbWinApi.dll`, `AdbWinUsbApi.dll` from [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools) (pinned in `desktop/webcam_bridge/adb.py`) | [Android SDK License](https://developer.android.com/studio/terms); adb source is Apache-2.0 |
| [PyInstaller](https://pyinstaller.org) bootloader | GPL-2.0 with an exception that allows bundling any program |
| [pyvirtualcam](https://github.com/letmaik/pyvirtualcam) | GPL-2.0 |
| FFmpeg via imageio-ffmpeg | GPL |

Because they include GPL components, those binary builds as a whole are
distributed under the GPL; the source code of this project remains MIT. When
adb is not bundled, the bridge downloads the same pinned platform-tools build
from Google on first use and verifies its checksum.

## Downloaded at runtime (not bundled)

| Material | When | License |
|---|---|---|
| [MediaPipe](https://github.com/google-ai-edge/mediapipe) and its selfie segmenter / hand / face landmarker models | `pip install`; models on first use | Apache-2.0 |
| FFmpeg static build via [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | `pip install` | FFmpeg: GPL/LGPL; wrapper: BSD-2-Clause |
| [RobustVideoMatting](https://github.com/PeterL1n/RobustVideoMatting) model | Fetched through `torch.hub` only when you choose the RVM segmentation engine | GPL-3.0 |
| Neko skin library from [eliot-akira/neko](https://github.com/eliot-akira/neko) | `webcam-bridge fetch skins` | No license stated — personal use only; not redistributed by this project |
| Inter and JetBrains Mono fonts | Loaded by the dashboard from Google Fonts | SIL Open Font License 1.1 |

Python and Android dependencies are listed in `desktop/pyproject.toml` and
`android/app/build.gradle` and keep their own licenses.
