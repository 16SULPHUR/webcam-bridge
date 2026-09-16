import http.client
import json
import threading

import pytest

from webcam_bridge.broadcaster import EventBroadcaster
from webcam_bridge.config import ConfigManager
from webcam_bridge.web_server import BridgeServer, ThreadingBridgeHTTPServer, BridgeHandler


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    cfg = ConfigManager(str(tmp_path_factory.mktemp("cfg") / "config.json"))
    BridgeServer(cfg, EventBroadcaster(), recorder=None, host="127.0.0.1", port=0)
    httpd = ThreadingBridgeHTTPServer(("127.0.0.1", 0), BridgeHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def request(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp, data


def test_index_served(server):
    resp, data = request(server, "GET", "/")
    assert resp.status == 200
    assert b"<html" in data.lower()


def test_no_wildcard_cors(server):
    resp, _ = request(server, "GET", "/api/config")
    assert resp.status == 200
    assert resp.getheader("Access-Control-Allow-Origin") is None


def test_static_traversal_blocked(server):
    resp, _ = request(server, "GET", "/css/../../config.py")
    assert resp.status in (403, 404)


def test_backgrounds_listed(server):
    resp, data = request(server, "GET", "/api/backgrounds")
    names = [b["filename"] for b in json.loads(data)["backgrounds"]]
    assert "green_screen.png" in names
    resp, _ = request(server, "GET", "/backgrounds/green_screen.png")
    assert resp.status == 200


def test_bundled_emoji_served(server):
    resp, data = request(server, "GET", "/reactions/assets/emoji/u1f44d.png")
    assert resp.status == 200
    assert data.startswith(b"\x89PNG")


def test_cross_origin_post_rejected(server):
    body = json.dumps({"mirror": True})
    resp, _ = request(server, "POST", "/api/config", body,
                      {"Origin": "https://evil.example", "Content-Type": "application/json"})
    assert resp.status == 403


def test_same_origin_post_allowed(server):
    body = json.dumps({"mirror": True})
    resp, data = request(server, "POST", "/api/config", body,
                         {"Origin": f"http://127.0.0.1:{server}", "Content-Type": "application/json"})
    assert resp.status == 200
    assert json.loads(data)["config"]["mirror"] is True


def test_upload_rejects_non_images(server):
    resp, _ = request(server, "POST", "/api/upload_background?filename=evil.py", b"print(1)")
    assert resp.status == 400


def test_vcam_status(server):
    resp, data = request(server, "GET", "/api/vcam")
    info = json.loads(data)
    assert resp.status == 200
    assert info["backend"] in ("builtin", "obs")
    assert "installed" in info


def test_vcam_install_uses_vcam_module(server, monkeypatch):
    from webcam_bridge import vcam
    calls = []
    monkeypatch.setattr(vcam, "install", lambda: calls.append("install") or "ok")
    resp, data = request(server, "POST", "/api/vcam/install")
    assert resp.status == 200
    assert json.loads(data)["message"] == "ok"
    assert calls == ["install"]
