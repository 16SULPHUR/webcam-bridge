"""
animations.py — Overlay motion presets.

An animation maps progress t (0..1) for particle i to a Transform.
Offsets are fractions of the frame height so motion is resolution independent.
Register a new one with @animation(...) and it appears in the settings dialog.
"""

import math
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Transform:
    dx: float = 0.0
    dy: float = 0.0
    scale: float = 1.0
    alpha: float = 1.0
    rot: float = 0.0


@dataclass
class AnimationDef:
    id: str
    label: str
    particles: int
    spread: bool                 # True → particles ignore the anchor and use the full frame
    fn: Callable = field(repr=False, default=None)


ANIMATIONS: dict[str, AnimationDef] = {}


def animation(aid: str, label: str, particles: int = 1, spread: bool = False):
    def inner(fn):
        ANIMATIONS[aid] = AnimationDef(aid, label, particles, spread, fn)
        return fn
    return inner


def _ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def _fade_tail(t: float, start: float = 0.7) -> float:
    return 1.0 if t < start else max(0.0, 1.0 - (t - start) / (1.0 - start))


def _stagger(t: float, i: int, n: int, overlap: float = 0.55) -> float:
    if n <= 1:
        return t
    delay = (i / n) * (1.0 - overlap)
    return min(1.0, max(0.0, (t - delay) / max(overlap, 1e-3)))


@animation("pop", "Pop", particles=1)
def _pop(t, i, n, seed):
    if t < 0.25:
        s = 1.25 * _ease_out(t / 0.25)
    elif t < 0.4:
        s = 1.25 - 0.25 * ((t - 0.25) / 0.15)
    else:
        s = 1.0
    return Transform(dy=-0.04 * _ease_out(t), scale=s, alpha=_fade_tail(t, 0.75))


@animation("float_up", "Float Up", particles=1)
def _float_up(t, i, n, seed):
    return Transform(
        dx=0.03 * math.sin(t * math.pi * 2.0),
        dy=-0.40 * _ease_out(t),
        scale=0.6 + 0.4 * _ease_out(min(1.0, t * 4)),
        alpha=_fade_tail(t, 0.45),
    )


@animation("shake", "Wiggle", particles=1)
def _shake(t, i, n, seed):
    return Transform(
        dx=0.025 * math.sin(t * math.pi * 8.0),
        scale=min(1.0, t * 6),
        alpha=_fade_tail(t, 0.7),
        rot=14.0 * math.sin(t * math.pi * 8.0),
    )


@animation("pulse", "Heartbeat", particles=1)
def _pulse(t, i, n, seed):
    return Transform(
        scale=(1.0 + 0.18 * math.sin(t * math.pi * 6.0)) * min(1.0, t * 8),
        alpha=_fade_tail(t, 0.7),
    )


@animation("spin", "Spin", particles=1)
def _spin(t, i, n, seed):
    return Transform(
        dy=-0.12 * _ease_out(t),
        scale=min(1.0, t * 5),
        alpha=_fade_tail(t, 0.65),
        rot=360.0 * _ease_out(t),
    )


@animation("slide_up", "Slide In", particles=1)
def _slide_up(t, i, n, seed):
    rise = _ease_out(min(1.0, t * 3))
    return Transform(dy=0.25 * (1.0 - rise), alpha=_fade_tail(t, 0.7))


@animation("burst", "Burst", particles=8)
def _burst(t, i, n, seed):
    angle = (i / n) * math.tau + seed[0] * 0.6
    reach = 0.28 + seed[1] * 0.18
    e = _ease_out(t)
    return Transform(
        dx=math.cos(angle) * reach * e,
        dy=math.sin(angle) * reach * e - 0.05 * e,
        scale=(0.55 + seed[2] * 0.45) * min(1.0, t * 5),
        alpha=_fade_tail(t, 0.45),
        rot=(seed[3] - 0.5) * 180.0 * t,
    )


@animation("rain", "Rain", particles=10, spread=True)
def _rain(t, i, n, seed):
    p = _stagger(t, i, n, 0.6)
    if p <= 0.0:
        return Transform(alpha=0.0)
    return Transform(
        dx=(seed[0] - 0.5) * 0.92 + 0.03 * math.sin(p * math.pi * 3),
        dy=-0.62 + 1.4 * p,
        scale=0.45 + seed[1] * 0.4,
        alpha=_fade_tail(p, 0.75),
        rot=(seed[2] - 0.5) * 60.0 * p,
    )


@animation("confetti", "Confetti", particles=12, spread=True)
def _confetti(t, i, n, seed):
    p = _stagger(t, i, n, 0.7)
    if p <= 0.0:
        return Transform(alpha=0.0)
    return Transform(
        dx=(seed[0] - 0.5) * 0.92 + 0.05 * math.sin(p * math.pi * 2 + seed[3] * 6),
        dy=-0.62 + 1.4 * p,
        scale=0.42 + seed[1] * 0.38,
        alpha=_fade_tail(p, 0.7),
        rot=360.0 * p * (1.0 if seed[2] > 0.5 else -1.0),
    )


def catalog() -> list[dict]:
    return [
        {"id": a.id, "label": a.label, "particles": a.particles, "spread": a.spread}
        for a in ANIMATIONS.values()
    ]
