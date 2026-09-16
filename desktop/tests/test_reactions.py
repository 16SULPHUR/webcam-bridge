import os

from webcam_bridge import paths
from webcam_bridge.reactions import DEFAULT_MAPPINGS, catalog_payload
from webcam_bridge.reactions.animations import ANIMATIONS
from webcam_bridge.reactions.common import bundled_emoji, emoji_filename, emoji_from_filename
from webcam_bridge.reactions.triggers import TRIGGERS


def test_emoji_filename_roundtrip():
    for char in ("👍", "❤", "🫶", "☝"):
        assert emoji_from_filename(emoji_filename(char)) == char
    assert emoji_filename("❤️") == emoji_filename("❤")


def test_default_mappings_reference_known_ids():
    for m in DEFAULT_MAPPINGS:
        assert m["trigger"] in TRIGGERS, m
        assert m["animation"] in ANIMATIONS, m


def test_default_emoji_are_bundled():
    bundled = set(bundled_emoji(paths.BUNDLED_EMOJI_DIR))
    missing = [m["value"] for m in DEFAULT_MAPPINGS if m["type"] == "emoji" and m["value"] not in bundled]
    assert not missing, f"add these to tools/emoji/build.mjs and rebuild: {missing}"


def test_catalog_payload(tmp_path):
    (tmp_path / "meme.gif").write_bytes(b"GIF89a")
    (tmp_path / "emoji").mkdir()
    (tmp_path / "emoji" / "ignored.png").write_bytes(b"")
    (tmp_path / "notes.txt").write_text("x")

    payload = catalog_payload(str(tmp_path), paths.BUNDLED_EMOJI_DIR)
    assert payload["images"] == ["meme.gif"]
    assert "👍" in payload["bundledEmoji"]
    assert {t["id"] for t in payload["triggers"]} == set(TRIGGERS)


def test_bundled_emoji_are_192px_png():
    from PIL import Image

    for name in os.listdir(paths.BUNDLED_EMOJI_DIR):
        with Image.open(os.path.join(paths.BUNDLED_EMOJI_DIR, name)) as im:
            assert im.format == "PNG" and im.mode == "RGBA", name
            assert max(im.size) == 192, name
