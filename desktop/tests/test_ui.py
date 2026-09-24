import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from webcam_bridge import ui
from webcam_bridge.__main__ import is_cli


@pytest.mark.parametrize("argv, cli", [
    ([], False), (["--port", "5000"], False), (["--browser"], False), (["doctor"], True),
    (["camera", "status"], True), (["--version"], True), (["-h"], True),
])
def test_is_cli(argv, cli):
    assert is_cli(argv) is cli


def serve(body: dict) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_running_instance_is_recognised():
    ours, other = serve({"app": "webcam-bridge"}), serve({"hello": "world"})
    try:
        assert ui.running_instance(f"http://127.0.0.1:{ours.server_port}")
        assert not ui.running_instance(f"http://127.0.0.1:{other.server_port}")
    finally:
        ours.shutdown()
        other.shutdown()


def test_no_instance_when_port_is_free():
    server = serve({})
    port = server.server_port
    server.shutdown()
    server.server_close()
    assert not ui.running_instance(f"http://127.0.0.1:{port}")
