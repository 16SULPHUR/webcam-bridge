# Releasing

Releases are cut from a tag. CI builds everything and publishes it.

```bash
# 1. Describe the release under "## [Unreleased]" in CHANGELOG.md and merge it.
# 2. Bump every version, date the changelog, commit and tag:
python scripts/release.py bump 0.2.0
# 3. Publish:
git push --follow-tags
```

`scripts/release.py bump` updates `desktop/webcam_bridge/__init__.py`, the
Android `versionName` and `versionCode`, and `CHANGELOG.md`. CI runs
`scripts/release.py check` on every push so the versions can't drift.

## What the release workflow publishes

| Asset | Used by |
|---|---|
| `WebcamBridge-Setup-<v>.exe` | Windows users, winget |
| `WebcamBridge-<v>-windows-x64.zip` | Portable Windows copy |
| `webcam-bridge-<v>.apk` | The bridge's automatic phone install, sideloading, Obtainium |
| `webcam_bridge-<v>-py3-none-any.whl`, `.tar.gz` | pip / pipx, PyPI |
| `webcam-bridge-vcam.zip` | `webcam-bridge fetch vcam` in source checkouts |
| `SHA256SUMS.txt` | Checked by every in-app download |

The release notes are the changelog section plus install instructions. Each pull
request also builds the installer (the **Windows installer** CI artifact) so
packaging problems show up before a release.

## One-time setup

All of these are optional; without them the release still works.

### APK signing

Without a key, the APK is signed with a throwaway debug key and users must
uninstall the app before each update. Create a key once and keep it safe:

```bash
keytool -genkeypair -v -keystore release.jks -alias webcam-bridge -keyalg RSA -keysize 4096 -validity 10000
base64 -w0 release.jks   # macOS: base64 -i release.jks
```

Add repository secrets `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`,
`ANDROID_KEY_ALIAS` and `ANDROID_KEY_PASSWORD`.

### PyPI (`pipx install webcam-bridge`)

1. On PyPI, add a [trusted publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
   for project `webcam-bridge`: owner `16SULPHUR`, repository `webcam-bridge`,
   workflow `release.yml`, environment `pypi`.
2. In the repository settings, create an environment named `pypi` and a
   repository variable `PYPI_PUBLISH` = `true`.

### winget (`winget install ...`)

1. Submit the first version by hand, e.g. with
   [Komac](https://github.com/russellbanks/Komac):
   `komac new WebcamBridge.WebcamBridge --urls <installer URL>`.
2. Fork [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs) to the
   account that owns the token below.
3. Add a classic personal access token with `public_repo` scope as the
   `WINGET_TOKEN` secret, and a repository variable `WINGET_IDENTIFIER` =
   `WebcamBridge.WebcamBridge`.

From then on every release opens the winget update automatically.

### Code signing the installer

The installer is unsigned, so Windows SmartScreen warns on first run. Free
signing for open-source projects is available from
[SignPath Foundation](https://signpath.org/); it plugs into the `windows` job.
