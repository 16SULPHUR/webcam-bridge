# Third-party notices

Webcam Bridge is MIT-licensed (see [LICENSE](LICENSE)). It bundles or uses the
following third-party material.

## Bundled

| Material | Where | License |
|---|---|---|
| [Twemoji](https://github.com/jdecked/twemoji) graphics — Copyright 2019 Twitter, Inc and other contributors | `desktop/webcam_bridge/assets/emoji/` (rasterized from SVG) | [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `oneko.gif` sprite sheet from [oneko.js](https://github.com/adryd325/oneko.js) by adryd325 | `desktop/webcam_bridge/web/img/oneko.gif` | [MIT](https://github.com/adryd325/oneko.js/blob/main/LICENSE) |
| Gradle Wrapper | `android/gradle/wrapper/` | [Apache-2.0](https://github.com/gradle/gradle/blob/master/LICENSE) |

## Downloaded at runtime (not bundled)

| Material | When | License |
|---|---|---|
| [MediaPipe](https://github.com/google-ai-edge/mediapipe) and its hand / face landmarker models | `pip install`; `python -m webcam_bridge.fetch models` | Apache-2.0 |
| [RobustVideoMatting](https://github.com/PeterL1n/RobustVideoMatting) model | Fetched through `torch.hub` only when you choose the RVM segmentation engine | GPL-3.0 |
| Neko skin library from [eliot-akira/neko](https://github.com/eliot-akira/neko) | `python -m webcam_bridge.fetch skins` | No license stated — personal use only; not redistributed by this project |
| Inter and JetBrains Mono fonts | Loaded by the dashboard from Google Fonts | SIL Open Font License 1.1 |

Python and Android dependencies are listed in `desktop/pyproject.toml` and
`android/app/build.gradle` and keep their own licenses.
