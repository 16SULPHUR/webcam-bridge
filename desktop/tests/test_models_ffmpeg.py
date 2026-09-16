import os
import subprocess

from webcam_bridge import models, paths


def test_ensure_model_uses_existing_file(monkeypatch, tmp_path):
    (tmp_path / "face_landmarker.task").write_bytes(b"x")
    monkeypatch.setenv("MEDIAPIPE_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(models.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no download expected")))
    assert models.ensure_model("face_landmarker.task") == str(tmp_path / "face_landmarker.task")


def test_ensure_model_downloads_once(monkeypatch, tmp_path):
    monkeypatch.delenv("MEDIAPIPE_MODELS_DIR", raising=False)
    monkeypatch.setattr(paths, "MODELS_DIR", str(tmp_path))
    calls = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"model-bytes"

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        return Resp()

    monkeypatch.setattr(models.urllib.request, "urlopen", fake_urlopen)
    name = "selfie_segmenter_landscape.tflite"
    path = models.ensure_model(name, log=lambda m: None)
    assert open(path, "rb").read() == b"model-bytes"
    assert models.ensure_model(name, log=lambda m: None) == path
    assert calls == [models.MODEL_URLS[name]]


def test_ffmpeg_falls_back_to_bundled_build(monkeypatch):
    monkeypatch.delenv("WEBCAM_BRIDGE_FFMPEG", raising=False)
    monkeypatch.setattr(paths.shutil, "which", lambda name: None)
    exe = paths.resolve_ffmpeg()
    assert os.path.isfile(exe)
    out = subprocess.run([exe, "-hide_banner", "-decoders"], capture_output=True, text=True).stdout
    assert " h264 " in out


def test_ffmpeg_env_override(monkeypatch):
    monkeypatch.setenv("WEBCAM_BRIDGE_FFMPEG", r"C:\custom\ffmpeg.exe")
    assert paths.resolve_ffmpeg() == r"C:\custom\ffmpeg.exe"
