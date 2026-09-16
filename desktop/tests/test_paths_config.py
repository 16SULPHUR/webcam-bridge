import json
import os

from webcam_bridge import paths
from webcam_bridge.config import ConfigManager
from webcam_bridge.ffmpeg_utils import build_vf_filter


def test_data_dir_honours_env():
    assert paths.DATA_DIR == os.path.abspath(os.environ["WEBCAM_BRIDGE_HOME"])
    assert paths.CONFIG_PATH.startswith(paths.DATA_DIR)


def test_bundled_resources_exist():
    assert os.path.isfile(os.path.join(paths.WEB_DIR, "index.html"))
    assert os.path.isfile(paths.ONEKO_GIF)
    assert os.path.isfile(paths.FRAME_SENDER)
    assert os.listdir(paths.BUNDLED_EMOJI_DIR)
    assert os.listdir(paths.BUNDLED_BG_DIR)


def test_safe_join_blocks_traversal(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    (tmp_path / "base-evil").mkdir()
    assert paths.safe_join(str(base), "a/b.png") == os.path.join(os.path.realpath(base), "a", "b.png")
    assert paths.safe_join(str(base), "../secret.txt") is None
    assert paths.safe_join(str(base), "../base-evil/x.png") is None


def test_user_background_shadows_bundled(monkeypatch, tmp_path):
    bundled = sorted(os.listdir(paths.BUNDLED_BG_DIR))[0]
    assert paths.find_background(bundled) == os.path.join(paths.BUNDLED_BG_DIR, bundled)

    monkeypatch.setattr(paths, "USER_BG_DIR", str(tmp_path))
    (tmp_path / bundled).write_bytes(b"x")
    assert paths.find_background(bundled) == os.path.join(str(tmp_path), bundled)
    assert paths.find_background("../" + bundled) == os.path.join(str(tmp_path), bundled)
    assert paths.find_background("") is None
    assert paths.find_background("missing.png") is None


def test_config_persists_known_keys(tmp_path):
    path = tmp_path / "config.json"
    cfg = ConfigManager(str(path))
    cfg.update({"mirror": True, "customPets": [{"skin": "ace", "enabled": True}], "bogus": 1})

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["mirror"] is True
    assert saved["customPets"] == [{"skin": "ace", "enabled": True}]
    assert "bogus" not in saved
    assert ConfigManager(str(path)).get("mirror") is True


def test_config_dimensions(tmp_path):
    cfg = ConfigManager(str(tmp_path / "c.json"))
    assert cfg.get_dimensions() == (1280, 720)
    cfg.update({"resolution": "640x480"})
    assert cfg.get_dimensions() == (640, 480)
    cfg.update({"resolution": "garbage"})
    assert cfg.get_dimensions() == (1280, 720)


def test_vf_filter():
    assert build_vf_filter(1280, 720, 30) == "scale=1280:720"
    assert build_vf_filter(640, 360, 15) == "fps=15,scale=640:360"
