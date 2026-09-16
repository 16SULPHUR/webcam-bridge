"""
catalog.py — Built-in reaction pack and config defaults.

DEFAULT_MAPPINGS is what a fresh install (and the dialog's "Restore defaults")
starts from. Anything the user adds in the dashboard lives in config.json under
"reactions" and overrides this list wholesale.
"""

DEFAULTS = {
    "enabled": False,
    "detectionFps": 12,
    "sensitivity": 1.0,
    "holdFrames": 2,
    "cooldownMs": 1800,
    "maxConcurrent": 4,
    "globalScale": 1.0,
    "showLabel": False,
    "showTracking": False,
    "mappings": [],
}

PLACEMENTS = [
    {"id": "anchor", "label": "Follow hand / face"},
    {"id": "top_left", "label": "Top left"},
    {"id": "top_center", "label": "Top center"},
    {"id": "top_right", "label": "Top right"},
    {"id": "center", "label": "Center"},
    {"id": "bottom_left", "label": "Bottom left"},
    {"id": "bottom_center", "label": "Bottom center"},
    {"id": "bottom_right", "label": "Bottom right"},
]


def _m(trigger, value, animation, size=0.20, duration=1.4,
       placement="anchor", enabled=True, kind="emoji"):
    return {
        "id": f"default_{trigger}",
        "trigger": trigger,
        "enabled": enabled,
        "type": kind,
        "value": value,
        "animation": animation,
        "placement": placement,
        "size": size,
        "duration": duration,
        "cooldownMs": None,
    }


DEFAULT_MAPPINGS = [
    _m("thumbs_up",     "👍", "pop",       size=0.22, duration=1.3),
    _m("thumbs_down",   "👎", "pop",       size=0.22, duration=1.3),
    _m("victory",       "✌",  "float_up",  size=0.20, duration=1.6),
    _m("open_palm",     "👋", "shake",     size=0.22, duration=1.4),
    _m("fist",          "✊", "pulse",     size=0.20, duration=1.3),
    _m("ok_sign",       "👌", "pop",       size=0.20, duration=1.3),
    _m("rock_on",       "🤘", "burst",     size=0.16, duration=1.6),
    _m("call_me",       "🤙", "float_up",  size=0.20, duration=1.5),
    _m("point_up",      "☝",  "float_up",  size=0.18, duration=1.5),
    _m("heart_hands",   "❤",  "burst",     size=0.16, duration=1.8),
    _m("both_hands_up", "🎉", "confetti",  size=0.16, duration=2.4, placement="center"),
    _m("smile",         "😄", "pop",       size=0.20, duration=1.4),
    _m("mouth_open",    "😮", "pop",       size=0.20, duration=1.4),
    _m("wink",          "😉", "pop",       size=0.18, duration=1.2, enabled=False),
    _m("brow_raise",    "🤨", "slide_up",  size=0.18, duration=1.2, enabled=False),
]


def default_config() -> dict:
    cfg = dict(DEFAULTS)
    cfg["mappings"] = [dict(m) for m in DEFAULT_MAPPINGS]
    return cfg
