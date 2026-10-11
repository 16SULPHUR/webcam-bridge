import json
import subprocess
import socket
import threading

from webcam_bridge import adb, device, wifi
from webcam_bridge.config import ConfigManager

from test_device import FakeBroadcaster, FakePhone


def make_target(tmp_path, phones=(), **cfg):
    config = ConfigManager(str(tmp_path / "config.json"))
    config.update(cfg)
    calls = []

    def fake_discover():
        calls.append(1)
        return list(phones)

    return wifi.StreamTarget(config, FakeBroadcaster(), fake_discover), config, calls


def test_usb_mode_uses_adb_forward(tmp_path):
    target, _, calls = make_target(tmp_path)
    assert target.resolve() == wifi.USB_TARGET
    assert not calls


def test_wifi_mode_uses_saved_address(tmp_path):
    target, _, calls = make_target(tmp_path, connection="wifi", wifiHost="192.168.1.20")
    assert target.resolve() == ("192.168.1.20", 8080)
    assert not calls


def test_wifi_mode_discovers_and_remembers_phone(tmp_path):
    phone = {"host": "192.168.1.30", "port": 8080, "name": "Pixel 7"}
    target, config, calls = make_target(tmp_path, [phone], connection="wifi", wifiHost="")
    assert target.resolve() == ("192.168.1.30", 8080)
    assert config.get("wifiHost") == "192.168.1.30"


def test_rediscovers_after_repeated_failures(tmp_path):
    phone = {"host": "192.168.1.31", "port": 8080, "name": "Pixel 7"}
    target, config, calls = make_target(tmp_path, [phone], connection="wifi", wifiHost="192.168.1.20")
    for _ in range(wifi.MAX_FAILURES):
        target.resolve()
        target.failed()
    assert target.resolve() == ("192.168.1.31", 8080)
    assert calls and config.get("wifiHost") == "192.168.1.31"


def test_parse_reply_ignores_other_apps():
    assert wifi.parse_reply(b"hello") is None
    assert wifi.parse_reply(b'{"app": "other"}') is None
    assert wifi.parse_reply(b'{"app": "webcam-bridge", "name": "Pixel", "port": 8080}') == \
        {"port": 8080, "name": "Pixel"}


def test_discover_finds_responder(monkeypatch):
    responder = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    responder.bind(("127.0.0.1", 0))
    monkeypatch.setattr(wifi, "DISCOVERY_PORT", responder.getsockname()[1])
    monkeypatch.setattr(wifi, "_broadcast_targets", lambda: [("127.0.0.1", "127.0.0.1")])

    def serve():
        data, addr = responder.recvfrom(256)
        if data == wifi.PROBE:
            responder.sendto(json.dumps({"app": "webcam-bridge", "name": "Pixel 7", "port": 8080}).encode(), addr)

    threading.Thread(target=serve, daemon=True).start()
    try:
        assert wifi.discover(timeout=1.0) == [{"host": "127.0.0.1", "port": 8080, "name": "Pixel 7"}]
    finally:
        responder.close()


class WifiPhone(FakePhone):
    def run(self, adb_path, args, serial=None, timeout=10.0):
        if args[:3] == ["shell", "ip", "-f"]:
            self.commands.append(args)
            out = "30: wlan0: <BROADCAST,UP>\n    inet 192.168.1.42/24 brd 192.168.1.255 scope global wlan0\n"
            return subprocess.CompletedProcess(args, 0, out, "")
        return super().run(adb_path, args, serial, timeout)


def test_usb_connection_pairs_wifi(monkeypatch, tmp_path):
    fake = WifiPhone(app_version=device.__version__)
    monkeypatch.setattr(adb, "run", fake.run)
    monkeypatch.setattr(adb, "list_devices", fake.list_devices)
    config = ConfigManager(str(tmp_path / "config.json"))
    mgr = device.DeviceManager(FakeBroadcaster(), dashboard_port=5134, config=config)
    mgr._adb = "adb"
    mgr._poll()
    assert config.get("wifiHost") == "192.168.1.42"


def test_wifi_mode_without_usb_shows_wifi_hint(monkeypatch, tmp_path):
    fake = FakePhone(state=None)
    monkeypatch.setattr(adb, "list_devices", fake.list_devices)
    config = ConfigManager(str(tmp_path / "config.json"))
    config.update({"connection": "wifi"})
    bc = FakeBroadcaster()
    mgr = device.DeviceManager(bc, dashboard_port=5134, config=config)
    mgr._adb = "adb"
    mgr._poll()
    assert bc.stats["deviceState"] == "wifi"
    assert bc.stats["deviceHint"] == wifi.HINT
