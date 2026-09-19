import io
import os
import zipfile

import pytest

from webcam_bridge import adb, fetch, launcher, paths, setup_state


@pytest.fixture(autouse=True)
def _fresh_snapshot():
    """The wizard caches its checks for a couple of seconds; tests must not."""
    setup_state.invalidate()
    yield
    setup_state.invalidate()


# ── adb helpers ───────────────────────────────────────────────────────────────

DEVICES_OUTPUT = """List of devices attached
ZY3298ABCD\tdevice
emulator-5554\toffline
"""


@pytest.mark.parametrize("output, expected", [
    ("List of devices attached\n", "none"),
    ("List of devices attached\nZY32\tdevice\n", "ready"),
    ("List of devices attached\nZY32\tunauthorized\n", "unauthorized"),
    ("List of devices attached\nZY32\toffline\n", "offline"),
    # A ready phone wins over a stale offline entry.
    (DEVICES_OUTPUT, "ready"),
])
def test_device_state(monkeypatch, output, expected):
    monkeypatch.setattr(adb, "available", lambda: True)
    monkeypatch.setattr(adb, "run", lambda args, timeout=5.0: output)
    assert adb.device_state() == expected


def test_device_state_without_adb(monkeypatch):
    monkeypatch.setattr(adb, "path", lambda: None)
    assert adb.device_state() == "none"
    assert adb.run(["devices"]) is None


def test_devices_ignores_malformed_lines(monkeypatch):
    monkeypatch.setattr(adb, "run", lambda args, timeout=5.0:
                        "List of devices attached\nZY32\tdevice\n\n* daemon started *\n")
    assert adb.devices() == [("ZY32", "device")]


def test_package_installed(monkeypatch):
    monkeypatch.setattr(adb, "run", lambda args, timeout=5.0: "package:/data/app/base.apk")
    assert adb.package_installed() is True
    monkeypatch.setattr(adb, "run", lambda args, timeout=5.0: "")
    assert adb.package_installed() is False


# ── platform-tools download ───────────────────────────────────────────────────

def _zip(names: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in names:
            zf.writestr(name, b"binary")
    return buf.getvalue()


def test_fetch_adb_extracts_platform_tools(monkeypatch):
    exe = os.path.basename(paths.ADB_EXE)
    monkeypatch.setattr(fetch, "_download", lambda url: _zip([
        f"platform-tools/{exe}", "platform-tools/NOTICE.txt", "unrelated.txt",
    ]))
    fetch.fetch_adb(force=True)
    assert os.path.isfile(paths.ADB_EXE)
    assert os.path.isfile(os.path.join(paths.ADB_DIR, "NOTICE.txt"))
    assert not os.path.exists(os.path.join(paths.ADB_DIR, "unrelated.txt"))


def test_fetch_adb_keeps_previous_install_when_zip_has_no_adb(monkeypatch):
    exe = os.path.basename(paths.ADB_EXE)
    monkeypatch.setattr(fetch, "_download", lambda url: _zip([f"platform-tools/{exe}"]))
    fetch.fetch_adb(force=True)

    monkeypatch.setattr(fetch, "_download", lambda url: _zip(["platform-tools/fastboot"]))
    with pytest.raises(OSError):
        fetch.fetch_adb(force=True)
    assert os.path.isfile(paths.ADB_EXE)
    assert not os.path.exists(paths.ADB_DIR + ".new")


def test_fetch_adb_refuses_paths_escaping_the_directory(monkeypatch):
    exe = os.path.basename(paths.ADB_EXE)
    monkeypatch.setattr(fetch, "_download", lambda url: _zip([
        f"platform-tools/{exe}", "platform-tools/../../escaped.txt",
    ]))
    fetch.fetch_adb(force=True)
    escaped = os.path.abspath(os.path.join(paths.DATA_DIR, "..", "..", "escaped.txt"))
    assert not os.path.exists(escaped)


# ── wizard snapshot ───────────────────────────────────────────────────────────

def test_snapshot_shape():
    data = setup_state.snapshot(False)
    ids = [s["id"] for s in data["steps"]]
    assert ids == ["ffmpeg", "camera", "adb", "phone", "app", "stream"]
    assert all(s["state"] in ("ok", "todo", "blocked", "working", "error") for s in data["steps"])
    assert isinstance(data["ready"], bool)


def test_later_steps_are_blocked_without_adb(monkeypatch):
    monkeypatch.setattr(adb, "path", lambda: None)
    steps = {s["id"]: s for s in setup_state.snapshot(False)["steps"]}
    assert steps["adb"]["state"] == "todo"
    assert steps["phone"]["state"] == "blocked"
    assert steps["app"]["state"] == "blocked"
    assert steps["stream"]["state"] == "blocked"
    assert not setup_state.snapshot(False)["ready"]


def test_stream_step_follows_the_android_connection(monkeypatch):
    monkeypatch.setattr(adb, "path", lambda: "/usr/bin/adb")
    monkeypatch.setattr(adb, "device_state", lambda: "ready")
    monkeypatch.setattr(adb, "package_installed", lambda app_id=adb.APP_ID: True)
    connected = {s["id"]: s for s in setup_state.snapshot(True)["steps"]}
    assert connected["stream"]["state"] == "ok"
    idle = {s["id"]: s for s in setup_state.snapshot(False)["steps"]}
    assert idle["stream"]["state"] == "todo"
    assert idle["stream"]["action"] == "connect"


def test_snapshot_is_cached_but_the_job_state_is_not(monkeypatch):
    calls = []
    real = setup_state._adb_step
    monkeypatch.setattr(setup_state, "_adb_step", lambda: calls.append(1) or real())
    setup_state.snapshot(False)
    setup_state.snapshot(False)
    assert len(calls) == 1, "the checks should be shared between pollers"
    assert setup_state.snapshot(False)["job"] == setup_state._runner.state()

    setup_state.invalidate()
    setup_state.snapshot(False)
    assert len(calls) == 2


def test_callers_cannot_mutate_the_cached_snapshot():
    first = setup_state.snapshot(False)
    first["steps"][0]["state"] = "error"
    assert setup_state.snapshot(False)["steps"][0]["state"] != "error"


def test_unknown_action_is_rejected():
    started, message = setup_state.start_action("rm -rf")
    assert not started
    assert "unknown action" in message


def test_every_advertised_action_exists():
    """A step must never offer a button the runner cannot dispatch."""
    for step in setup_state.snapshot(False)["steps"]:
        if step.get("action"):
            assert step["action"] in setup_state.ACTIONS, step["id"]


# ── launcher ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("argv, expected", [
    ([], 5134),
    (["--port", "9000"], 9000),
    (["--port=7001"], 7001),
    (["--no-tui", "--port", "8123"], 8123),
    (["--port", "not-a-number"], 5134),
])
def test_port_for(monkeypatch, argv, expected):
    monkeypatch.delenv("WEBCAM_BRIDGE_PORT", raising=False)
    assert launcher._port_for(argv) == expected


def test_port_for_reads_the_environment(monkeypatch):
    monkeypatch.setenv("WEBCAM_BRIDGE_PORT", "6000")
    assert launcher._port_for([]) == 6000
    assert launcher._port_for(["--port", "7000"]) == 7000


def test_prepare_phone_survives_a_missing_adb(monkeypatch):
    monkeypatch.setattr(adb, "available", lambda: False)
    monkeypatch.setattr("webcam_bridge.fetch.fetch_adb",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    launcher.prepare_phone(5134)  # must not raise — the wizard reports it instead
