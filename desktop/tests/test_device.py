import hashlib
import socket
import subprocess
import sys
import threading
import time

import pytest

from webcam_bridge import __version__, adb, device, fetch, paths, tcp_client, updates


class FakeBroadcaster:
    def __init__(self):
        self.stats = {}
        self.logs = []

    def update_stats(self, **kw):
        self.stats.update(kw)

    def broadcast_status(self):
        pass

    def broadcast_log(self, source, msg):
        self.logs.append(msg)


class FakePhone:
    """Stands in for adb: records commands and answers like a phone would."""

    def __init__(self, state="device", app_version=None, install_output="Success"):
        self.state = state
        self.app_version = app_version
        self.install_output = install_output
        self.commands = []

    def run(self, adb_path, args, serial=None, timeout=10.0):
        self.commands.append(args)
        out, code = "", 0
        if args[:3] == ["shell", "dumpsys", "package"] and self.app_version is not None:
            out = f"Packages:\n  Package [{device.APP_ID}] (abc):\n    versionName={self.app_version}\n"
        elif args[0] == "install":
            out = self.install_output
            code = 0 if out == "Success" else 1
            if code == 0:
                self.app_version = __version__
        elif args[:2] == ["shell", "getprop"]:
            out = "Pixel 7\n"
        return subprocess.CompletedProcess(args, code, out, "")

    def list_devices(self, adb_path):
        return [("SERIAL1", self.state)] if self.state else []


@pytest.fixture
def phone(monkeypatch, tmp_path):
    def make(**kw):
        fake = FakePhone(**kw)
        monkeypatch.setattr(adb, "run", fake.run)
        monkeypatch.setattr(adb, "list_devices", fake.list_devices)
        return fake
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"apk")
    monkeypatch.setenv("WEBCAM_BRIDGE_APK", str(apk))
    return make


def manager():
    bc = FakeBroadcaster()
    mgr = device.DeviceManager(bc, dashboard_port=5134)
    mgr._adb = "adb"
    return mgr, bc


def test_installs_app_forwards_and_launches(phone):
    fake = phone(app_version=None)
    mgr, bc = manager()
    mgr._poll()

    assert ["install", "-r", device.find_apk()] in fake.commands
    assert ["forward", "tcp:8080", "tcp:8080"] in fake.commands
    assert ["reverse", "tcp:5134", "tcp:5134"] in fake.commands
    assert any(c[:3] == ["shell", "am", "start"] and "stream" in c for c in fake.commands)
    assert bc.stats["deviceState"] == "ready"
    assert mgr.adb_command() == ["adb", "-s", "SERIAL1"]


def test_current_app_is_not_reinstalled(phone):
    fake = phone(app_version=__version__)
    mgr, bc = manager()
    mgr._poll()
    assert not any(c[0] == "install" for c in fake.commands)
    assert bc.stats["deviceState"] == "ready"


def test_outdated_app_with_other_signature_still_streams(phone):
    fake = phone(app_version="0.0.1", install_output="Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: ...]")
    mgr, bc = manager()
    mgr._poll()
    assert bc.stats["deviceState"] == "ready"
    assert any("Uninstall the old" in log for log in bc.logs)
    assert ["forward", "tcp:8080", "tcp:8080"] in fake.commands


def test_failed_install_is_not_retried_every_poll(phone):
    fake = phone(app_version=None, install_output="Failure [INSTALL_FAILED_INSUFFICIENT_STORAGE]")
    mgr, bc = manager()
    mgr._poll()
    mgr._poll()
    assert sum(c[0] == "install" for c in fake.commands) == 1
    assert bc.stats["deviceState"] == "no-app"
    assert "INSUFFICIENT_STORAGE" in bc.stats["deviceHint"]


@pytest.mark.parametrize("state, expected", [(None, "no-device"), ("unauthorized", "unauthorized"),
                                             ("offline", "offline")])
def test_waiting_states(phone, state, expected):
    phone(state=state)
    mgr, bc = manager()
    mgr._poll()
    assert bc.stats["deviceState"] == expected
    assert mgr.adb_command() is None


def test_replug_sets_up_forwarding_again(phone):
    fake = phone(app_version=__version__)
    mgr, _ = manager()
    mgr._poll()
    fake.state = None
    mgr._poll()
    assert mgr.serial is None
    fake.state = "device"
    mgr._poll()
    assert fake.commands.count(["forward", "tcp:8080", "tcp:8080"]) == 2


def test_list_devices_parsing(monkeypatch):
    out = ("* daemon started successfully\nList of devices attached\n"
           "R58M123\tdevice\nemulator-5554\tunauthorized\n\n")
    monkeypatch.setattr(adb, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, out, ""))
    assert adb.list_devices("adb") == [("R58M123", "device"), ("emulator-5554", "unauthorized")]


def test_adb_env_override_wins(monkeypatch, tmp_path):
    exe = tmp_path / adb.EXE
    exe.write_bytes(b"")
    monkeypatch.setenv("WEBCAM_BRIDGE_ADB", str(exe))
    assert adb.find_adb() == str(exe)


def test_platform_tools_url_is_pinned():
    url, sha = adb.platform_tools_url()
    assert adb.PLATFORM_TOOLS_VERSION in url and len(sha) == 64


@pytest.mark.parametrize("candidate, current, newer", [
    ("0.2.0", "0.1.1", True), ("v0.1.10", "0.1.9", True), ("0.1.1", "0.1.1", False),
    ("0.1.0", "0.1.1", False), (None, "0.1.1", False), ("garbage", "0.1.1", False),
])
def test_is_newer(candidate, current, newer):
    assert updates.is_newer(candidate, current) is newer


def test_verified_download_checks_sums(monkeypatch):
    blob = b"apk-bytes"
    good = hashlib.sha256(blob).hexdigest()
    sums = {"SHA256SUMS.txt": f"{good}  webcam-bridge-1.0.0.apk\n{'0' * 64}  other.zip\n"}

    def fake_download(url, log=print):
        name = url.rsplit("/", 1)[1]
        return sums[name].encode() if name in sums else blob

    monkeypatch.setattr(fetch, "_download", fake_download)
    assert fetch._download_verified("https://x", "webcam-bridge-1.0.0.apk") == blob
    sums["SHA256SUMS.txt"] = f"{'f' * 64}  webcam-bridge-1.0.0.apk\n"
    with pytest.raises(OSError):
        fetch._download_verified("https://x", "webcam-bridge-1.0.0.apk")


def test_frame_sender_command_from_source():
    assert paths.frame_sender_command() == [sys.executable, "-u", paths.FRAME_SENDER]


def test_tcp_client_ignores_forwards_without_app(monkeypatch):
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    monkeypatch.setattr(tcp_client, "ADB_PORT", server.getsockname()[1])
    monkeypatch.setattr(tcp_client, "RECONNECT_DELAY", 0.05)

    def serve():
        conn, _ = server.accept()
        conn.close()                      # adb forward with nothing listening on the phone
        conn, _ = server.accept()
        conn.sendall(b"h264")
        time.sleep(0.2)
        conn.close()

    threading.Thread(target=serve, daemon=True).start()
    received, events = [], []
    client = tcp_client.AndroidTcpClient(
        FakeBroadcaster(), received.append,
        on_connect=lambda: events.append("connect"), on_disconnect=lambda: events.append("disconnect"))
    client.start()
    deadline = time.time() + 5
    while "disconnect" not in events and time.time() < deadline:
        time.sleep(0.02)
    client.stop()
    server.close()
    assert b"".join(received) == b"h264"
    assert events[:2] == ["connect", "disconnect"]
