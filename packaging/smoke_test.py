"""Check standalone builds: python packaging/smoke_test.py <webcam-bridge executable> [--portable <exe>]

The single-file exe loses piped stdio (its windowed bootloader has none to hand on),
so it is only checked the way people use it: start the app and watch it come up.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

W, H, FRAMES = 320, 180, 150


def kill_tree(proc: subprocess.Popen) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
    else:
        proc.terminate()  # the single-file bootloader passes SIGTERM on to the app, which stops its children
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


def run(cmd: list[str], env: dict, timeout: float = 300) -> subprocess.CompletedProcess:
    """Like subprocess.run, but a hang kills the whole process tree and fails the check."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        raise SystemExit(f"FAILED: {' '.join(cmd[1:])} did not finish in {timeout:.0f} s")
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def new_env() -> tuple[str, dict]:
    home = tempfile.mkdtemp(prefix="wb-smoke-")
    return home, {**os.environ, "WEBCAM_BRIDGE_HOME": home, "WEBCAM_BRIDGE_NO_UPDATE_CHECK": "1"}


def check_window(exe: str, env: dict) -> bool:
    if sys.platform != "win32":
        return True
    window = run([exe, "_window-test"], env, timeout=180)
    print(f"window test: exit {window.returncode} {window.stdout.strip()}")
    return window.returncode == 0


def check_app(exe: str, home: str, env: dict) -> bool:
    """Start the app without a window; it must serve the dashboard and start the frame processor."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    out_path = os.path.join(home, "stdout.txt")
    with open(out_path, "w") as out:
        proc = subprocess.Popen([exe, "--no-browser", "--no-adb", "--port", str(port)],
                                stdout=out, stderr=subprocess.STDOUT, env=env)

    def output() -> str:
        text = ""
        for path in (out_path, os.path.join(home, "webcam-bridge.log")):
            if os.path.isfile(path):
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text += fh.read()
        return text

    status, deadline = None, time.time() + 180
    try:
        while time.time() < deadline and proc.poll() is None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=2) as resp:
                    status = json.load(resp)
            except (OSError, ValueError):
                pass
            if status and "[PySender] Starting" in output():
                break
            time.sleep(1)
    finally:
        kill_tree(proc)
    log = output()
    ok = bool(status and status.get("app") == "webcam-bridge" and "[PySender] Starting" in log)
    print(f"app: {'OK' if ok else 'FAILED'} (dashboard {'up' if status else 'down'})")
    if not ok:
        print(log[-4000:])
    return ok


def check_frame_sender(exe: str, home: str, env: dict) -> bool:
    cfg = os.path.join(home, "config.json")
    with open(cfg, "w") as fh:
        json.dump({"resolution": f"{W}x{H}", "vcamEnabled": False, "bgMode": "blur",
                   "faceTouchupEnabled": True}, fh)

    proc = subprocess.Popen([exe, "_frame-sender", cfg], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    out, errb = bytearray(), bytearray()
    readers = [threading.Thread(target=lambda: out.extend(proc.stdout.read()), daemon=True),
               threading.Thread(target=lambda: errb.extend(proc.stderr.read()), daemon=True)]
    for t in readers:
        t.start()
    frame = bytes(W * H * 3)
    try:
        for _ in range(FRAMES):
            proc.stdin.write(frame)
            proc.stdin.flush()
            time.sleep(0.03)
        proc.stdin.close()
        proc.wait(timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        kill_tree(proc)
        print(f"FAILED: frame processor: {exc!r}")
        return False
    for t in readers:
        t.join(timeout=30)
    err = errb.decode("utf-8", "replace")

    lines = [line for line in err.splitlines() if "PySender" in line or "Touchup" in line]
    print("\n".join(lines[-15:]))
    failures = [line for line in err.splitlines() if "Traceback" in line or "ERROR loading" in line]
    if "Segmentation loaded" not in err:
        failures.append("background segmentation never loaded")
    if not out or failures:
        print(f"FAILED: {len(out)} bytes of preview output; errors: {failures}")
        return False
    print(f"frame processor: OK, {len(out)} bytes of preview output")
    return True


def check_installed(exe: str) -> bool:
    print(f"== {exe}", flush=True)
    home, env = new_env()
    version = run([exe, "--version"], env, timeout=120)
    print(version.stdout.strip())
    if version.returncode or not version.stdout.strip():
        print(f"FAILED: --version printed nothing\n{version.stderr}")
        return False
    doctor = run([exe, "doctor"], env)
    print(doctor.stdout)
    if "Traceback" in doctor.stderr:
        print(doctor.stderr)
        return False
    if run([exe, "fetch", "models"], env).returncode:
        print("FAILED: fetch models")
        return False
    return check_window(exe, env) and check_frame_sender(exe, home, env) and check_app(exe, home, env)


def check_portable(exe: str) -> bool:
    print(f"== {exe}", flush=True)
    home, env = new_env()
    return check_window(exe, env) and check_app(exe, home, env)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("exe")
    parser.add_argument("--portable")
    args = parser.parse_args()
    ok = check_installed(args.exe)
    if args.portable:
        ok = check_portable(args.portable) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
