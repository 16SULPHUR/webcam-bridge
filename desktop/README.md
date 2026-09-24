# webcam-bridge

Desktop half of [Webcam Bridge](https://github.com/16SULPHUR/webcam-bridge):
use your Android phone as a USB webcam. The bridge finds your phone over USB,
installs the companion app on it, decodes the camera stream, applies effects
(backgrounds, touch-up, reactions, pets) and feeds a virtual camera, with a
web dashboard at <http://localhost:5134>.

```bash
pipx install webcam-bridge
webcam-bridge            # plug in your phone with USB debugging on
webcam-bridge doctor     # check the setup
```

On Windows, the [installer](https://github.com/16SULPHUR/webcam-bridge/releases/latest)
is the easiest way in: it needs no Python and sets up the virtual camera.
See the [main README](https://github.com/16SULPHUR/webcam-bridge#readme) for
details and troubleshooting.
