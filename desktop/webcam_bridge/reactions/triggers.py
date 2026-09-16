"""
triggers.py — Gesture / expression rules.

Each rule is registered in TRIGGERS and returns True when the pose matches.
Add a new trigger by writing a function and decorating it with @hand_trigger,
@hands_trigger (two-handed) or @face_trigger — it shows up in the dashboard
settings dialog automatically.
"""

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

# landmark indices: (mcp, pip, dip, tip)
FINGERS = {
    "thumb":  (1, 2, 3, 4),
    "index":  (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring":   (13, 14, 15, 16),
    "pinky":  (17, 18, 19, 20),
}


def _dist(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a[:2]) - np.asarray(b[:2])))


class Hand:
    """One detected hand, landmarks normalised to 0..1 of the frame."""

    def __init__(self, lm: np.ndarray, handedness: str = "Right", sensitivity: float = 1.0):
        self.lm = lm
        self.handedness = handedness
        self.scale = max(_dist(lm[0], lm[9]), 1e-4)
        self.center = (float(np.mean(lm[[0, 5, 9, 13, 17], 0])),
                       float(np.mean(lm[[0, 5, 9, 13, 17], 1])))
        self.top = (float(np.mean(lm[:, 0])), float(np.min(lm[:, 1])))
        margin = 1.0 + 0.15 / max(sensitivity, 0.2)
        self._ext = {name: self._is_extended(name, margin) for name in FINGERS}

    def _is_extended(self, name: str, margin: float) -> bool:
        mcp, pip, dip, tip = FINGERS[name]
        if name == "thumb":
            # A curled thumb bends at the IP joint; a raised one stays straight and
            # reaches further from the wrist than its own knuckle.
            reach = _dist(self.lm[tip], self.lm[0]) > _dist(self.lm[mcp], self.lm[0]) * (margin - 0.05)
            a = self.lm[dip][:2] - self.lm[pip][:2]
            b = self.lm[tip][:2] - self.lm[dip][:2]
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            straight = na < 1e-6 or nb < 1e-6 or float(np.dot(a, b) / (na * nb)) > 0.55
            return reach and straight
        return _dist(self.lm[tip], self.lm[0]) > _dist(self.lm[pip], self.lm[0]) * margin

    def extended(self, *names: str) -> bool:
        return all(self._ext[n] for n in names)

    def folded(self, *names: str) -> bool:
        return not any(self._ext[n] for n in names)

    def only(self, *names: str) -> bool:
        return self.extended(*names) and self.folded(*[f for f in FINGERS if f not in names])

    def tip(self, name: str) -> np.ndarray:
        return self.lm[FINGERS[name][3]]

    def direction(self, name: str) -> np.ndarray:
        mcp, _, _, tip = FINGERS[name]
        v = self.lm[tip][:2] - self.lm[mcp][:2]
        n = np.linalg.norm(v)
        return v / n if n > 1e-6 else v

    def gap(self, a: str, b: str) -> float:
        return _dist(self.tip(a), self.tip(b)) / self.scale

    def spread(self) -> float:
        return _dist(self.lm[8], self.lm[20]) / self.scale


class Face:
    """One detected face, landmarks normalised to 0..1 of the frame."""

    def __init__(self, lm: np.ndarray, sensitivity: float = 1.0):
        self.lm = lm
        self.sensitivity = sensitivity
        self.width = max(_dist(lm[234], lm[454]), 1e-4)
        self.center = (float(np.mean(lm[:, 0])), float(np.mean(lm[:, 1])))
        self.top = (self.center[0], float(np.min(lm[:, 1])))

    def _ear(self, top, bottom, left, right) -> float:
        return _dist(self.lm[top], self.lm[bottom]) / max(_dist(self.lm[left], self.lm[right]), 1e-4)

    @property
    def mouth_open_ratio(self) -> float:
        return _dist(self.lm[13], self.lm[14]) / max(_dist(self.lm[61], self.lm[291]), 1e-4)

    @property
    def mouth_width_ratio(self) -> float:
        return _dist(self.lm[61], self.lm[291]) / self.width

    @property
    def smile_curve(self) -> float:
        corners_y = (self.lm[61][1] + self.lm[291][1]) / 2.0
        return float((self.lm[14][1] - corners_y) / self.width)

    @property
    def left_ear(self) -> float:
        return self._ear(386, 374, 362, 263)

    @property
    def right_ear(self) -> float:
        return self._ear(159, 145, 33, 133)

    @property
    def brow_lift(self) -> float:
        left = _dist(self.lm[334], self.lm[386])
        right = _dist(self.lm[105], self.lm[159])
        return float((left + right) / 2.0 / self.width)


@dataclass
class TriggerDef:
    id: str
    label: str
    kind: str                 # "hand" | "hands" | "face"
    emoji: str                # suggested default artwork
    suppresses: tuple = ()    # triggers this one outranks when both match
    fn: Callable = field(repr=False, default=None)


TRIGGERS: dict[str, TriggerDef] = {}


def _register(kind):
    def outer(tid: str, label: str, emoji: str = "", suppresses: tuple = ()):
        def inner(fn):
            TRIGGERS[tid] = TriggerDef(tid, label, kind, emoji, suppresses, fn)
            return fn
        return inner
    return outer


hand_trigger = _register("hand")
hands_trigger = _register("hands")
face_trigger = _register("face")


# ── One-handed gestures ───────────────────────────────────────────────────────

@hand_trigger("thumbs_up", "Thumbs Up", "👍")
def _thumbs_up(hand: Hand, ctx) -> bool:
    return (hand.only("thumb")
            and hand.direction("thumb")[1] < -0.45)


@hand_trigger("thumbs_down", "Thumbs Down", "👎")
def _thumbs_down(hand: Hand, ctx) -> bool:
    return (hand.only("thumb")
            and hand.direction("thumb")[1] > 0.45)


@hand_trigger("victory", "Peace / Victory", "✌")
def _victory(hand: Hand, ctx) -> bool:
    return hand.only("index", "middle") and hand.gap("index", "middle") > 0.45


@hand_trigger("open_palm", "Open Palm / Wave", "👋")
def _open_palm(hand: Hand, ctx) -> bool:
    return (hand.extended("index", "middle", "ring", "pinky")
            and hand.spread() > 0.9)


@hand_trigger("fist", "Fist", "✊")
def _fist(hand: Hand, ctx) -> bool:
    return hand.folded("index", "middle", "ring", "pinky", "thumb")


@hand_trigger("ok_sign", "OK Sign", "👌")
def _ok_sign(hand: Hand, ctx) -> bool:
    return (hand.gap("thumb", "index") < 0.35
            and hand.extended("middle", "ring")
            and not hand.extended("index"))


@hand_trigger("rock_on", "Rock Horns", "🤘")
def _rock_on(hand: Hand, ctx) -> bool:
    return hand.only("index", "pinky") or hand.only("thumb", "index", "pinky")


@hand_trigger("call_me", "Call Me / Shaka", "🤙")
def _call_me(hand: Hand, ctx) -> bool:
    return hand.only("thumb", "pinky")


@hand_trigger("point_up", "Pointing Up", "☝")
def _point_up(hand: Hand, ctx) -> bool:
    return hand.only("index") and hand.direction("index")[1] < -0.55


# ── Two-handed gestures ───────────────────────────────────────────────────────

@hands_trigger("heart_hands", "Heart Hands", "❤",
               suppresses=("fist", "ok_sign", "point_up", "thumbs_up", "victory"))
def _heart_hands(hands: list[Hand], ctx) -> bool:
    if len(hands) < 2:
        return False
    a, b = hands[0], hands[1]
    scale = (a.scale + b.scale) / 2.0
    thumbs = _dist(a.tip("thumb"), b.tip("thumb")) / scale
    index = _dist(a.tip("index"), b.tip("index")) / scale
    # index fingertips form the top of the heart, thumb tips the point below
    lift = ((a.tip("thumb")[1] + b.tip("thumb")[1]) - (a.tip("index")[1] + b.tip("index")[1])) / 2.0
    return thumbs < 0.6 and index < 0.65 and lift > 0.3 * scale


@hands_trigger("both_hands_up", "Both Hands Up", "🎉",
               suppresses=("open_palm", "victory"))
def _both_hands_up(hands: list[Hand], ctx) -> bool:
    if len(hands) < 2:
        return False
    return all(h.extended("index", "middle", "ring", "pinky") for h in hands[:2])


# ── Facial expressions ────────────────────────────────────────────────────────

@face_trigger("smile", "Big Smile", "😄")
def _smile(face: Face, ctx) -> bool:
    s = face.sensitivity
    return face.mouth_width_ratio > 0.47 / s and face.smile_curve > 0.012 / s


@face_trigger("mouth_open", "Surprise / Mouth Open", "😮")
def _mouth_open(face: Face, ctx) -> bool:
    return face.mouth_open_ratio > 0.55 / face.sensitivity


@face_trigger("wink", "Wink", "😉")
def _wink(face: Face, ctx) -> bool:
    left, right = face.left_ear, face.right_ear
    closed, open_ = min(left, right), max(left, right)
    return closed < 0.13 * face.sensitivity and open_ > 0.24


@face_trigger("brow_raise", "Eyebrow Raise", "🤨")
def _brow_raise(face: Face, ctx) -> bool:
    return face.brow_lift > 0.175 / face.sensitivity


def anchor_for(kind: str, subject) -> tuple[float, float]:
    """Normalised point the artwork should pop out of."""
    if kind == "hands":
        xs = [s.top[0] for s in subject[:2]]
        ys = [s.top[1] for s in subject[:2]]
        return float(np.mean(xs)), float(np.mean(ys)) - 0.06
    x, y = subject.top
    return x, max(0.0, y - 0.08)


def catalog() -> list[dict]:
    return [
        {"id": t.id, "label": t.label, "kind": t.kind, "emoji": t.emoji}
        for t in TRIGGERS.values()
    ]


def resolve_conflicts(hits: dict) -> dict:
    """Drop one-handed matches that a richer two-handed gesture already covers."""
    for tid in list(hits):
        for sub in TRIGGERS[tid].suppresses:
            hits.pop(sub, None)
    return hits
