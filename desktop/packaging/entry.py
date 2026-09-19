"""
entry.py — The single executable's entry point.

Two jobs, picked apart by the first argument:

  --frame-sender <config.json>   the frame processor Pipeline spawns. There is
                                 no python.exe in a packaged build, so the app
                                 re-runs itself in this mode instead.
  anything else                  the normal launcher (prepare the phone, start
                                 the bridge, open the dashboard).
"""

import multiprocessing
import sys


def _run_frame_sender() -> None:
    # frame_sender.py reads its config path from sys.argv[1] while importing,
    # so hand it the argv shape it expects before the import happens.
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    from webcam_bridge import frame_sender

    frame_sender.main()


def main() -> None:
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == "--frame-sender":
        _run_frame_sender()
        return
    from webcam_bridge.launcher import main as launch

    launch()


if __name__ == "__main__":
    main()
