"""Check standalone builds: python packaging/smoke_test.py <webcam-bridge executable>..."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time

W, H, FRAMES = 320, 180, 150


def check(exe: str) -> int:
    print(f"== {exe}")
    home = tempfile.mkdtemp(prefix="wb-smoke-")
    env = {**os.environ, "WEBCAM_BRIDGE_HOME": home, "WEBCAM_BRIDGE_NO_UPDATE_CHECK": "1"}

    version = subprocess.run([exe, "--version"], capture_output=True, text=True, env=env, check=True)
    print(version.stdout.strip())
    doctor = subprocess.run([exe, "doctor"], capture_output=True, text=True, env=env)
    print(doctor.stdout)
    if "Traceback" in doctor.stderr:
        print(doctor.stderr)
        return 1

    subprocess.run([exe, "fetch", "models"], env=env, check=True)

    if sys.platform == "win32":
        window = subprocess.run([exe, "_window-test"], capture_output=True, text=True, env=env, timeout=120)
        print(window.stdout.strip())
        if window.returncode:
            print(f"FAILED: the app window did not open\n{window.stderr}")
            return 1

    cfg = os.path.join(home, "config.json")
    with open(cfg, "w") as fh:
        json.dump({"resolution": f"{W}x{H}", "vcamEnabled": False, "bgMode": "blur",
                   "faceTouchupEnabled": True}, fh)

    proc = subprocess.Popen([exe, "_frame-sender", cfg], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    out, errb = bytearray(), bytearray()
    readers = [threading.Thread(target=lambda: out.extend(proc.stdout.read())),
               threading.Thread(target=lambda: errb.extend(proc.stderr.read()))]
    for t in readers:
        t.start()
    frame = bytes(W * H * 3)
    for _ in range(FRAMES):
        proc.stdin.write(frame)
        proc.stdin.flush()
        time.sleep(0.03)
    proc.stdin.close()
    proc.wait(timeout=180)
    for t in readers:
        t.join()
    err = errb.decode("utf-8", "replace")

    lines = [line for line in err.splitlines() if "PySender" in line or "Touchup" in line]
    print("\n".join(lines[-15:]))
    failures = [line for line in err.splitlines() if "Traceback" in line or "ERROR loading" in line]
    if "Segmentation loaded" not in err:
        failures.append("background segmentation never loaded")
    if not out or failures:
        print(f"FAILED: {len(out)} bytes of preview output; errors: {failures}")
        return 1
    print(f"OK: {len(out)} bytes of preview output")
    return 0


if __name__ == "__main__":
    sys.exit(max(check(exe) for exe in sys.argv[1:]))
