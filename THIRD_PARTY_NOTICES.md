# Third-party notices

Webcam Bridge is MIT-licensed (see [LICENSE](LICENSE)). It bundles or uses the
following third-party material.

## Bundled

| Material | Where | License |
|---|---|---|
| [softcam](https://github.com/tshino/softcam) — Copyright (c) 2020 tshino, including Microsoft DirectShow BaseClasses | `vcam/windows/third_party/softcam/` and the `webcam_bridge_cam.dll` built from it | [MIT](vcam/windows/third_party/softcam/LICENSE) |
| [FFmpeg](https://ffmpeg.org) — LGPL build from [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds), in the Windows installer only | `ffmpeg\ffmpeg.exe` beside the app, with its `LICENSE.txt` | [LGPL-2.1-or-later](https://www.ffmpeg.org/legal.html) |
| [Twemoji](https://github.com/jdecked/twemoji) graphics — Copyright 2019 Twitter, Inc and other contributors | `desktop/webcam_bridge/assets/emoji/` (rasterized from SVG) | [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `oneko.gif` sprite sheet from [oneko.js](https://github.com/adryd325/oneko.js) by adryd325 | `desktop/webcam_bridge/web/img/oneko.gif` | [MIT](https://github.com/adryd325/oneko.js/blob/main/LICENSE) |
| Gradle Wrapper | `android/gradle/wrapper/` | [Apache-2.0](https://github.com/gradle/gradle/blob/master/LICENSE) |

## Downloaded at runtime (not bundled)

| Material | When | License |
|---|---|---|
| [MediaPipe](https://github.com/google-ai-edge/mediapipe) and its selfie segmenter / hand / face landmarker models | `pip install`; models on first use | Apache-2.0 |
| FFmpeg static build via [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | `pip install`, for source checkouts — the installer bundles an LGPL build instead | FFmpeg: GPL/LGPL depending on the build; wrapper: BSD-2-Clause |
| [Android platform-tools](https://developer.android.com/tools/releases/platform-tools) (`adb`) | The setup wizard, or `python -m webcam_bridge.fetch adb` | [Android Software Development Kit License Agreement](https://developer.android.com/studio/terms) — not redistributed by this project |
| [RobustVideoMatting](https://github.com/PeterL1n/RobustVideoMatting) model | Fetched through `torch.hub` only when you choose the RVM segmentation engine | GPL-3.0 |
| Neko skin library from [eliot-akira/neko](https://github.com/eliot-akira/neko) | `python -m webcam_bridge.fetch skins` | No license stated — personal use only; not redistributed by this project |
| Inter and JetBrains Mono fonts | Loaded by the dashboard from Google Fonts | SIL Open Font License 1.1 |

FFmpeg is invoked as a separate executable over pipes, never linked into the
bridge. The Windows installer ships an LGPL build (the bridge only decodes
H.264 and stream-copies to MP4, so no GPL-only component is needed) together
with its licence text; its source is available from the
[build project](https://github.com/BtbN/FFmpeg-Builds) and
[ffmpeg.org](https://ffmpeg.org/download.html).

Python and Android dependencies are listed in `desktop/pyproject.toml` and
`android/app/build.gradle` and keep their own licenses.
