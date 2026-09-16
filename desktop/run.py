"""Run the bridge from a source checkout without installing it: python run.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webcam_bridge.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
