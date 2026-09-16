import os
import sys

import numpy as np
import pytest

from webcam_bridge import vcam
from webcam_bridge.__main__ import camera_command


def test_elevated_command_line_quotes_paths():
    line = vcam.elevated_command_line([
        [r"C:\Windows\System32\regsvr32.exe", "/s", r"C:\Program Data\x64\cam.dll"],
        [r"C:\Windows\SysWOW64\regsvr32.exe", "/s", r"C:\x86\cam.dll"],
    ])
    assert line == (
        '/s /c ""C:\\Windows\\System32\\regsvr32.exe" /s "C:\\Program Data\\x64\\cam.dll" && '
        '"C:\\Windows\\SysWOW64\\regsvr32.exe" /s "C:\\x86\\cam.dll""'
    )


@pytest.mark.parametrize("installed, requested, expected", [
    (True, "auto", "builtin"),
    (False, "auto", "obs"),
    (True, "obs", "obs"),
    (False, "builtin", "builtin"),
    (True, "nonsense", "builtin"),
])
def test_resolve_backend(monkeypatch, installed, requested, expected):
    monkeypatch.setattr(vcam, "IS_WINDOWS", True)
    monkeypatch.setattr(vcam, "status", lambda: {"installed": installed})
    assert vcam.resolve_backend(requested) == expected


def test_status_shape():
    info = vcam.status()
    assert info["name"] == vcam.DEVICE_NAME
    assert set(info["arches"]) == {"x64", "x86"}
    assert isinstance(info["installed"], bool)


def test_camera_status_command(capsys):
    assert camera_command("status") == 0
    assert "camera" in capsys.readouterr().out.lower()


def test_install_errors_are_reported(monkeypatch, capsys):
    def boom():
        raise vcam.VirtualCameraError("nope")
    monkeypatch.setattr(vcam, "install", boom)
    assert camera_command("install") == 1
    assert "nope" in capsys.readouterr().err


needs_dll = pytest.mark.skipif(
    sys.platform != "win32" or sys.maxsize <= 2**32 or not os.path.isfile(vcam.bundled_dll("x64")),
    reason="needs the 64-bit camera DLL (built in CI)",
)


@needs_dll
def test_builtin_camera_sends_frames():
    cam = vcam._BuiltinCamera(642, 362, 30)
    try:
        assert (cam.width, cam.height) == (640, 360)  # rounded down to multiples of 4
        frame = np.zeros((362, 642, 3), dtype=np.uint8)
        frame[:, :, 0] = 255
        for _ in range(3):
            cam.send(frame)
        assert cam.connected is False  # nothing is reading the camera in CI
    finally:
        cam.close()


@needs_dll
def test_builtin_camera_is_single_instance():
    first = vcam._BuiltinCamera(320, 240, 30)
    try:
        with pytest.raises(vcam.VirtualCameraError):
            vcam._BuiltinCamera(320, 240, 30)
    finally:
        first.close()
    vcam._BuiltinCamera(320, 240, 30).close()  # free again after close
