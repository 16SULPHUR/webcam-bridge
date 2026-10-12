"""
wifi.py — Find the phone on the local network and pick where the stream comes from.

The phone app answers a UDP broadcast on DISCOVERY_PORT; the bridge then
connects straight to its camera server instead of going through adb forward.
"""

import json
import socket
import time
from typing import Optional

DISCOVERY_PORT = 8081
PROBE = b"WEBCAM_BRIDGE_DISCOVER"
STREAM_PORT = 8080
USB_TARGET = ("127.0.0.1", STREAM_PORT)
MAX_FAILURES = 3
REDISCOVER_INTERVAL = 5.0

HINT = "Open Webcam Bridge on your phone and keep it on the same Wi-Fi as this computer."


def local_ipv4s() -> list[str]:
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def _broadcast_targets() -> list[tuple[str, str]]:
    """(bind address, broadcast address) per interface; /24 is assumed, which covers home networks."""
    targets = [("", "255.255.255.255")]
    targets += [(ip, ip.rsplit(".", 1)[0] + ".255") for ip in local_ipv4s()]
    return targets


def discover(timeout: float = 1.5) -> list[dict]:
    """Phones answering on the local network: [{host, port, name}]."""
    found: dict[str, dict] = {}
    socks = []
    for bind_ip, bcast in _broadcast_targets():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind((bind_ip, 0))
            s.sendto(PROBE, (bcast, DISCOVERY_PORT))
            s.setblocking(False)
            socks.append(s)
        except OSError:
            continue
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            for s in socks:
                try:
                    data, (host, _) = s.recvfrom(1024)
                except (BlockingIOError, OSError):
                    continue
                reply = parse_reply(data)
                if reply:
                    found[host] = {"host": host, **reply}
            time.sleep(0.05)
    finally:
        for s in socks:
            s.close()
    return list(found.values())


def parse_reply(data: bytes) -> Optional[dict]:
    try:
        msg = json.loads(data)
    except ValueError:
        return None
    if not isinstance(msg, dict) or msg.get("app") != "webcam-bridge":
        return None
    port = msg.get("port", STREAM_PORT)
    return {"port": port if isinstance(port, int) else STREAM_PORT, "name": str(msg.get("name", "Phone"))}


class StreamTarget:
    """Tells the TCP client where to connect: adb forward on USB, or the phone itself on Wi-Fi."""

    def __init__(self, config, broadcaster, discover_fn=discover) -> None:
        self._config = config
        self._bc = broadcaster
        self._discover = discover_fn
        self._failures = 0
        self._last_scan = 0.0
        self._last_host = None

    @property
    def wifi(self) -> bool:
        return self._config.get("connection") == "wifi"

    def resolve(self) -> Optional[tuple[str, int]]:
        if not self.wifi:
            return USB_TARGET
        host = self._config.get("wifiHost") or ""
        port = int(self._config.get("wifiPort") or STREAM_PORT)
        if host != self._last_host:
            self._last_host, self._failures = host, 0
        if host and self._failures < MAX_FAILURES:
            return host, port
        if time.monotonic() - self._last_scan < REDISCOVER_INTERVAL:
            return (host, port) if host else None
        self._last_scan = time.monotonic()
        phones = self._discover()
        if not phones:
            self._bc.update_stats(deviceHint=HINT)
            self._bc.broadcast_status()
            return (host, port) if host else None
        phone = next((p for p in phones if p["host"] == host), phones[0])
        self._failures = 0
        if phone["host"] != host or phone["port"] != port:
            self._config.update({"wifiHost": phone["host"], "wifiPort": phone["port"]})
            self._last_host = phone["host"]
            self._bc.update_stats(wifiHost=phone["host"])
            self._bc.broadcast_log("system", f"[Phone] Found {phone['name']} on Wi-Fi at {phone['host']}")
        return phone["host"], phone["port"]

    def failed(self) -> None:
        if self.wifi:
            self._failures += 1

    def connected(self) -> None:
        self._failures = 0
