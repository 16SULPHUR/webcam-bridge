"""
engine.py — Reaction overlay orchestrator.

Main loop contract (frame_sender.py):
    engine.configure(cfg["reactions"])   # cheap, every config poll
    engine.submit(frame_rgb)             # hands the detector thread a copy
    engine.render(frame_rgb)             # composites active overlays in place

Detection runs on a background thread at its own frame rate so the video
pipeline never blocks on inference.
"""

import json
import sys
import threading
import time
from collections import OrderedDict

import cv2
import numpy as np

from . import animations as anim_mod
from . import catalog
from .assets import AssetLibrary, Sprite
from .detector import LandmarkDetector
from .triggers import TRIGGERS, anchor_for, resolve_conflicts

DETECT_WIDTH = 480

# MediaPipe's 21-point hand skeleton
HAND_BONES = (
    (0, 1), (0, 5), (0, 17), (5, 9), (9, 13), (13, 17),
    (1, 2), (2, 3), (3, 4),
    (5, 6), (6, 7), (7, 8),
    (9, 10), (10, 11), (11, 12),
    (13, 14), (14, 15), (15, 16),
    (17, 18), (18, 19), (19, 20),
)

# Face landmarks the expression rules actually read
FACE_POINTS = (13, 14, 61, 291, 33, 133, 159, 145, 362, 263, 386, 374, 105, 334, 234, 454)


def _log(msg: str) -> None:
    sys.stderr.write(f"[Reactions] {msg}\n")


class Overlay:
    __slots__ = ("sprite", "anim", "start", "duration", "anchor",
                 "placement", "size", "seeds", "label")

    def __init__(self, sprite: Sprite, anim, duration: float, anchor, placement: str,
                 size: float, label: str):
        self.sprite = sprite
        self.anim = anim
        self.start = time.monotonic()
        self.duration = max(0.2, duration)
        self.anchor = anchor
        self.placement = placement
        self.size = size
        self.label = label
        self.seeds = np.random.random((max(1, anim.particles), 4)).astype(np.float32)


_RESIZE_CACHE: "OrderedDict[tuple, tuple]" = OrderedDict()
_RESIZE_CACHE_MAX = 64


def _scaled(sprite: np.ndarray, th: int) -> np.ndarray:
    """Resized sprite, memoised — the same few sizes recur every frame."""
    key = (id(sprite), th)
    hit = _RESIZE_CACHE.get(key)
    if hit is not None:
        _RESIZE_CACHE.move_to_end(key)
        return hit[1]
    sh, sw = sprite.shape[:2]
    tw = int(max(4, sw * th / float(sh)))
    interp = cv2.INTER_AREA if th < sh else cv2.INTER_LINEAR
    out = cv2.resize(sprite, (tw, th), interpolation=interp)
    _RESIZE_CACHE[key] = (sprite, out)   # keep the source alive so id() stays unique
    if len(_RESIZE_CACHE) > _RESIZE_CACHE_MAX:
        _RESIZE_CACHE.popitem(last=False)
    return out


def blit_rgba(dst_rgb: np.ndarray, sprite: np.ndarray, cx: float, cy: float,
              target_h: float, alpha: float = 1.0, rot: float = 0.0) -> None:
    spr = _scaled(sprite, int(max(4, target_h)) & ~1)
    th, tw = spr.shape[:2]

    if abs(rot) > 0.5:
        rad = np.deg2rad(rot)
        cos, sin = abs(np.cos(rad)), abs(np.sin(rad))
        nw, nh = int(tw * cos + th * sin), int(tw * sin + th * cos)
        m = cv2.getRotationMatrix2D((tw / 2.0, th / 2.0), rot, 1.0)
        m[0, 2] += nw / 2.0 - tw / 2.0
        m[1, 2] += nh / 2.0 - th / 2.0
        spr = cv2.warpAffine(spr, m, (nw, nh), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        th, tw = nh, nw

    x0, y0 = int(cx - tw / 2.0), int(cy - th / 2.0)
    sx, sy = max(0, -x0), max(0, -y0)
    dx, dy = max(0, x0), max(0, y0)
    w = min(tw - sx, dst_rgb.shape[1] - dx)
    h = min(th - sy, dst_rgb.shape[0] - dy)
    if w <= 0 or h <= 0:
        return

    patch = spr[sy:sy + h, sx:sx + w]
    a = patch[:, :, 3:4].astype(np.float32) * (alpha / 255.0)
    roi = dst_rgb[dy:dy + h, dx:dx + w]
    dst_rgb[dy:dy + h, dx:dx + w] = (
        patch[:, :, :3].astype(np.float32) * a + roi.astype(np.float32) * (1.0 - a)
    ).astype(np.uint8)


class ReactionEngine:
    def __init__(self, images_dir: str | None = None):
        self.assets = AssetLibrary(images_dir) if images_dir else AssetLibrary()
        self._lock = threading.Lock()
        self._cfg = catalog.default_config()
        self._cfg_key = None
        self._mappings: list[dict] = []
        self._overlays: list[Overlay] = []

        self._input = None
        self._input_lock = threading.Lock()
        self._last_submit = 0.0

        self._thread = None
        self._running = False
        self._detector = None
        self._detector_key = None
        self._state: dict[str, dict] = {}
        self._last_test = None
        self.last_fired = ""

        # Tracking / diagnostics
        self._track: dict = {"hands": [], "faces": [], "matched": [], "fps": 0.0}
        self._det_fps = 0.0
        self._det_last = 0.0

    # ── Configuration ─────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return bool(self._cfg.get("enabled"))

    def configure(self, cfg: dict | None) -> None:
        cfg = cfg if isinstance(cfg, dict) else {}
        key = json.dumps(cfg, sort_keys=True, ensure_ascii=False)
        if key == self._cfg_key:
            return
        self._cfg_key = key

        merged = dict(catalog.DEFAULTS)
        merged.update(cfg)
        mappings = [m for m in merged.get("mappings", [])
                    if isinstance(m, dict)
                    and m.get("enabled", True)
                    and m.get("trigger") in TRIGGERS
                    and m.get("animation") in anim_mod.ANIMATIONS]

        with self._lock:
            self._cfg = merged
            self._mappings = mappings
        self.assets.invalidate()
        _RESIZE_CACHE.clear()

        if merged.get("enabled") and mappings:
            self._ensure_thread()
        else:
            self.stop()

        self._handle_preview(merged.get("testFire"))

    def _handle_preview(self, test: dict | None) -> None:
        """Dashboard "preview" button — fire one overlay without gesturing."""
        if not isinstance(test, dict):
            return
        stamp = test.get("ts")
        if not stamp or stamp == self._last_test:
            return
        self._last_test = stamp
        mapping = test.get("mapping")
        if isinstance(mapping, dict):
            self._emit(mapping, (0.5, 0.35))

    def _needs(self) -> tuple[bool, bool]:
        kinds = {TRIGGERS[m["trigger"]].kind for m in self._mappings}
        return bool({"hand", "hands"} & kinds), "face" in kinds

    # ── Main-thread hooks ─────────────────────────────────────────────────

    def submit(self, frame_rgb: np.ndarray) -> None:
        if not self._running:
            return
        fps = max(1, int(self._cfg.get("detectionFps", 12)))
        now = time.monotonic()
        if now - self._last_submit < 1.0 / fps:
            return
        self._last_submit = now

        h, w = frame_rgb.shape[:2]
        scale = min(1.0, DETECT_WIDTH / float(w))
        small = (cv2.resize(frame_rgb, (int(w * scale), int(h * scale)),
                            interpolation=cv2.INTER_AREA)
                 if scale < 1.0 else frame_rgb)
        with self._input_lock:
            self._input = np.ascontiguousarray(small)

    def render(self, frame_rgb: np.ndarray) -> np.ndarray:
        with self._lock:
            overlays = list(self._overlays)
            scale_all = float(self._cfg.get("globalScale", 1.0))
            show_label = bool(self._cfg.get("showLabel"))
        if not overlays:
            return frame_rgb

        now = time.monotonic()
        h, w = frame_rgb.shape[:2]
        expired = []

        for ov in overlays:
            elapsed = now - ov.start
            t = elapsed / ov.duration
            if t >= 1.0:
                expired.append(ov)
                continue

            base_x, base_y = self._base_point(ov, w, h)
            sprite_frame = ov.sprite.frame_at(elapsed)
            count = max(1, ov.anim.particles)
            for i in range(count):
                tr = ov.anim.fn(t, i, count, ov.seeds[i])
                if tr.alpha <= 0.01 or tr.scale <= 0.01:
                    continue
                unit_x = w if ov.anim.spread else h
                cx = base_x + tr.dx * unit_x
                cy = base_y + tr.dy * h
                blit_rgba(frame_rgb, sprite_frame, cx, cy,
                          ov.size * h * scale_all * tr.scale,
                          min(1.0, tr.alpha), tr.rot)

            if show_label:
                self._draw_label(frame_rgb, ov.label, base_x, base_y, h)

        if expired:
            with self._lock:
                self._overlays = [o for o in self._overlays if o not in expired]
        return frame_rgb

    def _base_point(self, ov: Overlay, w: int, h: int) -> tuple[float, float]:
        if ov.anim.spread:
            return w / 2.0, h / 2.0
        if ov.placement == "anchor" and ov.anchor is not None:
            return ov.anchor[0] * w, ov.anchor[1] * h
        mx, my = 0.18 * h, 0.18 * h
        xs = {"left": mx, "center": w / 2.0, "right": w - mx}
        ys = {"top": my, "center": h / 2.0, "bottom": h - my}
        parts = (ov.placement or "center").split("_")
        if len(parts) == 1:
            return xs["center"], ys["center"]
        return xs.get(parts[1], w / 2.0), ys.get(parts[0], h / 2.0)

    @staticmethod
    def _draw_label(frame_rgb, text, x, y, h) -> None:
        scale = max(0.4, h / 900.0)
        pos = (int(x) - 40, int(min(h - 8, y + 0.16 * h)))
        cv2.putText(frame_rgb, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame_rgb, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (255, 255, 255), 1, cv2.LINE_AA)

    # ── Detection thread ──────────────────────────────────────────────────

    def _ensure_thread(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="ReactionDetect", daemon=True)
        self._thread.start()
        _log("detection thread started")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        with self._lock:
            self._overlays.clear()
            self._state.clear()
        _log("detection thread stopping")

    def _loop(self) -> None:
        while self._running:
            with self._lock:
                mappings = list(self._mappings)
                sensitivity = float(self._cfg.get("sensitivity", 1.0)) or 1.0
                fps = max(1, int(self._cfg.get("detectionFps", 12)))
            if not mappings:
                time.sleep(0.1)
                continue

            need_hands, need_face = self._needs()
            if self._detector_key != (need_hands, need_face):
                if self._detector is not None:
                    self._detector.close()
                self._detector = LandmarkDetector(need_hands, need_face)
                self._detector_key = (need_hands, need_face)
                if not self._detector.ready:
                    time.sleep(2.0)
                    continue

            with self._input_lock:
                frame = self._input
                self._input = None
            if frame is None:
                time.sleep(0.005)
                continue

            try:
                hands, faces = self._detector.process(frame, sensitivity)
                fired = self._evaluate(hands, faces, sensitivity)
                self._record_tracking(hands, faces, fired)
                self._spawn(fired, mappings)
            except Exception as exc:
                _log(f"detection error: {exc}")
                time.sleep(0.05)

            time.sleep(max(0.0, 1.0 / fps * 0.25))

        if self._detector is not None:
            self._detector.close()
            self._detector = None
            self._detector_key = None

    def _record_tracking(self, hands, faces, hits) -> None:
        now = time.monotonic()
        if self._det_last:
            dt = now - self._det_last
            if dt > 0:
                inst = 1.0 / dt
                self._det_fps = inst if not self._det_fps else self._det_fps * 0.8 + inst * 0.2
        self._det_last = now
        with self._lock:
            self._track = {
                "hands": [h.lm[:, :2].copy() for h in hands],
                "faces": [f.lm[:, :2].copy() for f in faces],
                "matched": sorted(hits.keys()),
                "fps": round(self._det_fps, 1),
            }

    def _evaluate(self, hands, faces, sensitivity) -> dict[str, tuple[float, float]]:
        """Return {trigger_id: anchor} for every rule matching this frame."""
        hits: dict[str, tuple[float, float]] = {}
        for tid, tdef in TRIGGERS.items():
            try:
                if tdef.kind == "hand":
                    for hand in hands:
                        if tdef.fn(hand, sensitivity):
                            hits[tid] = anchor_for("hand", hand)
                            break
                elif tdef.kind == "hands":
                    if len(hands) >= 2 and tdef.fn(hands, sensitivity):
                        hits[tid] = anchor_for("hands", hands)
                elif tdef.kind == "face":
                    for face in faces:
                        if tdef.fn(face, sensitivity):
                            hits[tid] = anchor_for("face", face)
                            break
            except Exception as exc:
                _log(f"trigger '{tid}' raised: {exc}")
        return resolve_conflicts(hits)

    def _spawn(self, hits: dict, mappings: list[dict]) -> None:
        now = time.monotonic()
        with self._lock:
            hold = max(1, int(self._cfg.get("holdFrames", 2)))
            default_cd = float(self._cfg.get("cooldownMs", 1800)) / 1000.0
            max_live = max(1, int(self._cfg.get("maxConcurrent", 4)))

        for m in mappings:
            mid = m.get("id") or m["trigger"]
            st = self._state.setdefault(mid, {"hits": 0, "last": 0.0})
            anchor = hits.get(m["trigger"])
            if anchor is None:
                st["hits"] = 0
                continue

            st["hits"] += 1
            cooldown = m.get("cooldownMs")
            cooldown = default_cd if cooldown in (None, "") else float(cooldown) / 1000.0
            if st["hits"] < hold or now - st["last"] < cooldown:
                continue
            st["last"] = now
            st["hits"] = 0

            self._emit(m, anchor, max_live)

    def _emit(self, m: dict, anchor, max_live: int = 6) -> None:
        anim = anim_mod.ANIMATIONS.get(m.get("animation", "pop"))
        sprite = self.assets.sprite(m.get("type", "emoji"), m.get("value", ""))
        if sprite is None or anim is None:
            return
        trigger = m.get("trigger", "")
        label = TRIGGERS[trigger].label if trigger in TRIGGERS else trigger
        overlay = Overlay(sprite, anim, float(m.get("duration", 1.4)), anchor,
                          m.get("placement", "anchor"), float(m.get("size", 0.2)), label)
        with self._lock:
            self._overlays.append(overlay)
            if len(self._overlays) > max_live:
                self._overlays = self._overlays[-max_live:]
        self.last_fired = trigger
        _log(f"fired: {trigger or 'preview'} → {m.get('value')}")

    # ── Tracking overlay (dashboard preview only) ─────────────────────────────

    def draw_tracking(self, frame_rgb: np.ndarray) -> np.ndarray:
        """Draw the landmark skeleton and a detection HUD onto a frame."""
        with self._lock:
            track = dict(self._track)
            enabled = bool(self._cfg.get("enabled"))
            overlays = len(self._overlays)

        h, w = frame_rgb.shape[:2]
        unit = max(1, int(round(h / 360.0)))

        for face in track.get("faces", []):
            xs = (face[:, 0] * w).astype(np.int32)
            ys = (face[:, 1] * h).astype(np.int32)
            cv2.rectangle(frame_rgb, (int(xs.min()), int(ys.min())),
                          (int(xs.max()), int(ys.max())), (244, 114, 182), unit)
            for idx in FACE_POINTS:
                if idx < len(face):
                    cv2.circle(frame_rgb, (int(xs[idx]), int(ys[idx])), unit + 1,
                               (249, 168, 212), -1)

        for hand in track.get("hands", []):
            pts = [(int(x * w), int(y * h)) for x, y in hand]
            for a, b in HAND_BONES:
                cv2.line(frame_rgb, pts[a], pts[b], (56, 189, 248), unit, cv2.LINE_AA)
            for i, pt in enumerate(pts):
                colour = (250, 204, 21) if i in (4, 8, 12, 16, 20) else (255, 255, 255)
                cv2.circle(frame_rgb, pt, unit + 1, colour, -1, cv2.LINE_AA)

        lines = [
            (f"hands {len(track.get('hands', []))}   faces {len(track.get('faces', []))}   "
             f"det {track.get('fps', 0)}/s   overlays {overlays}") if enabled else "reactions off",
            "match  " + (", ".join(track.get("matched", [])) or "-"),
        ]
        self._hud(frame_rgb, lines, unit)
        return frame_rgb

    @staticmethod
    def _hud(frame_rgb, lines: list[str], unit: int) -> None:
        scale = 0.42 * unit
        thick = max(1, unit)
        pad = 5 * unit
        step = int(17 * unit)
        widths = [cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)[0][0] for t in lines]
        box_w = max(widths) + pad * 2
        box_h = step * len(lines) + pad
        panel = frame_rgb[0:box_h, 0:box_w]
        panel[:] = (panel * 0.35).astype(np.uint8)
        for i, text in enumerate(lines):
            cv2.putText(frame_rgb, text, (pad, int(step * (i + 1) - 3 * unit)),
                        cv2.FONT_HERSHEY_SIMPLEX, scale,
                        (125, 211, 252) if i else (226, 232, 240), thick, cv2.LINE_AA)

    def stats(self) -> dict:
        """Compact detection state for the terminal UI and the dashboard."""
        with self._lock:
            track = dict(self._track)
            return {
                "enabled": bool(self._cfg.get("enabled")),
                "mappings": len(self._mappings),
                "overlays": len(self._overlays),
                "hands": len(track.get("hands", [])),
                "faces": len(track.get("faces", [])),
                "matched": track.get("matched", []),
                "detectorFps": track.get("fps", 0.0),
                "backend": (type(self._detector._backend).__name__.strip("_").replace("Backend", "").lower()
                            if self._detector is not None and self._detector.ready else ""),
                "lastFired": self.last_fired,
            }
