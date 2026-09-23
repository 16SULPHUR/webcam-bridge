"""
Version bookkeeping for releases.

    python scripts/release.py bump 0.2.0      # set every version, date the changelog, commit and tag
    python scripts/release.py check [v0.2.0]  # fail if versions disagree (CI)
    python scripts/release.py notes 0.2.0     # print that version's changelog section
"""

import datetime
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY_INIT = ROOT / "desktop" / "webcam_bridge" / "__init__.py"
GRADLE = ROOT / "android" / "app" / "build.gradle"
CHANGELOG = ROOT / "CHANGELOG.md"
REPO_URL = "https://github.com/16SULPHUR/webcam-bridge"


def read_versions() -> dict:
    py = re.search(r'__version__ = "([^"]+)"', PY_INIT.read_text()).group(1)
    gradle = GRADLE.read_text()
    return {
        "python": py,
        "android": re.search(r'versionName "([^"]+)"', gradle).group(1),
        "versionCode": int(re.search(r"versionCode (\d+)", gradle).group(1)),
    }


def notes(version: str) -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|^\[[^\]]+\]:|\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def check(tag: str | None) -> int:
    v = read_versions()
    errors = []
    if v["python"] != v["android"]:
        errors.append(f"desktop is {v['python']} but the Android app is {v['android']}")
    if tag and tag.lstrip("v") != v["python"]:
        errors.append(f"tag {tag} does not match version {v['python']}")
    if tag and not notes(v["python"]):
        errors.append(f"CHANGELOG.md has no section for {v['python']}")
    for e in errors:
        print(f"::error::{e}")
    if not errors:
        print(f"Versions agree: {v['python']} (versionCode {v['versionCode']})")
    return 1 if errors else 0


def bump(version: str) -> int:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        print("Version must look like 1.2.3")
        return 1
    if subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=ROOT).stdout.strip():
        print("Commit or stash your changes first.")
        return 1
    if not notes("Unreleased") and f"## [{version}]" not in CHANGELOG.read_text(encoding="utf-8"):
        print("CHANGELOG.md has nothing under Unreleased. Describe the release there first.")
        return 1
    old = read_versions()

    PY_INIT.write_text(re.sub(r'__version__ = "[^"]+"', f'__version__ = "{version}"', PY_INIT.read_text()))
    gradle = GRADLE.read_text()
    gradle = re.sub(r'versionName "[^"]+"', f'versionName "{version}"', gradle)
    gradle = re.sub(r"versionCode \d+", f"versionCode {old['versionCode'] + 1}", gradle)
    GRADLE.write_text(gradle)

    text = CHANGELOG.read_text(encoding="utf-8")
    today = datetime.date.today().isoformat()
    if f"## [{version}]" not in text:
        text = text.replace("## [Unreleased]", f"## [Unreleased]\n\n## [{version}] - {today}", 1)
    text = re.sub(r"^\[Unreleased\]: .*$", f"[Unreleased]: {REPO_URL}/compare/v{version}...HEAD", text, flags=re.M)
    CHANGELOG.write_text(text, encoding="utf-8")

    subprocess.run(["git", "commit", "-am", f"Release v{version}"], cwd=ROOT, check=True)
    subprocess.run(["git", "tag", "-a", f"v{version}", "-m", f"Webcam Bridge {version}"], cwd=ROOT, check=True)
    print(f"Tagged v{version}. Publish it with: git push --follow-tags")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 1 and argv[0] == "check":
        return check(argv[1] if len(argv) > 1 else None)
    if len(argv) == 2 and argv[0] == "bump":
        return bump(argv[1])
    if len(argv) == 2 and argv[0] == "notes":
        print(notes(argv[1]))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
