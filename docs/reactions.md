# Reaction Overlays

Gestures and facial expressions drop emoji / meme artwork onto the live video —
burned into the OBS virtual camera, so Zoom, Teams and OBS all see it.

Everything is configured on the dashboard's **Reactions** page
(<http://localhost:5134/#reactions>). The switch at the top turns the whole
feature on and off; nothing is loaded — no MediaPipe models, no detection
thread — while it is off.

**Show tracking on preview** draws the hand skeleton, face landmarks and a HUD
listing whatever rules match right now. It is the fastest way to tell whether a
gesture is being recognised (rule matches) or just not firing yet (hold frames /
cooldown). The overlay is drawn on the dashboard preview only — never on the
virtual camera, so nobody in your call sees it. The same numbers appear live on
the Reactions page and in the terminal UI.

```
desktop/
├── tools/emoji/                ← rebuilds the bundled Twemoji pack
└── webcam_bridge/
    ├── assets/emoji/           ← bundled emoji sprites (generated, Twemoji)
    └── reactions/
    ├── triggers.py     ← gesture / expression rules
    ├── animations.py   ← motion presets
    ├── detector.py     ← MediaPipe hand + face landmarks
    ├── assets.py       ← artwork loading, emoji rendering, caching
    ├── engine.py       ← detection thread, overlay lifecycle, compositing
    ├── catalog.py      ← the built-in pack + config defaults
    └── common.py       ← shared paths / naming helpers
```

Your own files live in the user data directory (printed when the bridge
starts; `%LOCALAPPDATA%\WebcamBridge` on Windows):

```
WebcamBridge/
├── reactions/      ← your memes (png / jpg / webp / gif)
├── emoji-cache/    ← emoji rendered from the system font on first use
└── models/         ← MediaPipe .task files (only for mediapipe ≥ 1.0)
```

## Adding artwork

**A meme image** — drop a PNG/JPG/WEBP/GIF into the `reactions/` data folder (or use
*Upload artwork* in the dialog), then set a reaction's type to **Image** and pick
the file. Transparent PNGs look best; animated GIFs loop while on screen
(needs Pillow).

**An emoji** — type it into the reaction's emoji box. If it isn't in the bundled
pack it is rendered from the system emoji font (Segoe UI Emoji on Windows) the
first time it fires and cached in `emoji-cache/`.

To add emoji to the bundled Twemoji pack (so they work everywhere, without
Pillow or a system font), rebuild it — this needs Node.js 18+:

```bash
cd desktop/tools/emoji
npm install
npm run build -- 🦄 🫠 🥹
```

Add them to the `BUNDLED` list in `build.mjs` as well so the next full rebuild
keeps them.

## Adding a gesture

Write a rule in `webcam_bridge/reactions/triggers.py` — it appears in the settings
dialog automatically, no other file needs touching:

```python
@hand_trigger("spock", "Vulcan Salute", "🖖")
def _spock(hand, ctx):
    return (hand.extended("index", "middle", "ring", "pinky")
            and hand.gap("middle", "ring") > 0.8
            and hand.gap("index", "middle") < 0.4)
```

`Hand` helpers: `extended(*fingers)`, `folded(*fingers)`, `only(*fingers)`,
`tip(finger)`, `direction(finger)` (unit vector, y is negative upwards),
`gap(a, b)` and `spread()` — both normalised by hand size.

`@hands_trigger` receives the list of hands (two-handed poses, and can list
`suppresses=(...)` to outrank one-handed rules it contains). `@face_trigger`
receives a `Face` with `mouth_open_ratio`, `mouth_width_ratio`, `smile_curve`,
`left_ear` / `right_ear` (eye openness) and `brow_lift`.

## Adding an animation

Same idea in `animations.py` — return where the artwork sits at progress `t`
(0→1). Offsets are fractions of the frame height, `spread=True` scatters
particles across the whole frame instead of at the hand:

```python
@animation("drop", "Drop In", particles=1)
def _drop(t, i, n, seed):
    return Transform(dy=-0.4 * (1 - _ease_out(min(1, t * 3))), alpha=_fade_tail(t))
```

## Tuning

| Setting | What it does |
|---|---|
| Detection rate | Landmark inference per second (own thread; 8–15 is plenty) |
| Sensitivity | Loosens/tightens every rule's thresholds at once |
| Hold frames | Consecutive detections needed before firing — raise it if things trigger by accident |
| Cooldown | Minimum gap between two firings of the same reaction |
| Max on screen | Overlay cap; oldest is dropped |
| Overall size | Multiplies every reaction's size |
| Burn trigger name | Draws the trigger label into the frame — handy while tuning |
| Show tracking | Skeleton + live matches on the dashboard preview (not the virtual camera) |

Per reaction you can override the artwork, animation, placement (follow the
hand/face, or a fixed corner), size and duration, and the **▶** button fires one
into the live feed without gesturing.

## Requirements

MediaPipe does the landmark work — already required by the background
segmentation and face touch-up features:

Both `mediapipe` and `pillow` are installed with the desktop bridge
(Pillow provides custom emoji and animated GIF support).

On MediaPipe **1.0+** the legacy `mp.solutions` graphs are gone, so the detector
falls back to the Tasks API and needs the model files in the `models/` data
folder (or a directory named by `MEDIAPIPE_MODELS_DIR`). Download them with
`webcam-bridge fetch models`, or manually:

- [hand_landmarker.task](https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task)
- [face_landmarker.task](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task)

If anything is missing the reason is printed once to the bridge log and the
video pipeline carries on untouched.
