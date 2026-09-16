import os
import sys
import tempfile

# Isolate every test run from the developer's real data directory. This must
# happen before webcam_bridge.paths is imported anywhere.
_HOME = tempfile.mkdtemp(prefix="webcam-bridge-test-")
os.environ["WEBCAM_BRIDGE_HOME"] = _HOME
os.environ["WEBCAM_BRIDGE_RECORDINGS"] = os.path.join(_HOME, "recordings")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
