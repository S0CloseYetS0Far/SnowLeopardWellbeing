"""Entry point: read the options, find the media, start everything."""

from __future__ import annotations

import argparse
import os
import signal
import sys
from pathlib import Path

from . import media


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="wellbeing",
        description="Plays the snow leopard video and lets every picture loose on the screen.",
    )
    parser.add_argument("--pictures", type=Path, help="folder of pictures (default: snowleopard/)")
    parser.add_argument("--video", type=Path, help="video file (default: first video in the project folder)")
    parser.add_argument("--mute", action="store_true", help="play the video without sound")
    parser.add_argument(
        "--workers", type=int, metavar="N",
        help="processes to spread the pictures over, for several CPU cores "
             "(default: half the logical cores, at most 4; 0 = all in one process)",
    )
    parser.add_argument("--duration", type=float, metavar="SECONDS", help="quit by itself after this many seconds")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    found = media.discover(args.pictures, args.video)
    print("Snow Leopard Wellbeing")
    print(f"  video    : {found.video.name if found.video else '(none found)'}")
    print(f"  pictures : {len(found.pictures)}")

    # Qt's FFmpeg backend prints a stream dump for every file it opens.
    os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia*=false")
    # Ctrl+C in the console ends the script at once, even inside Qt's loop.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    if sys.platform == "win32":
        # A parent program can start us with Ctrl+C switched off, and that
        # setting is inherited. Switch it back on so Ctrl+C always works.
        import ctypes

        ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QKeySequence, QShortcut
    from PySide6.QtWidgets import QApplication

    from . import config
    from .killswitch import HOTKEY_TEXT, KillSwitch
    from .swarm import Swarm
    from .video_window import VideoWindow

    if not found.video and not found.pictures:
        print("Nothing to show.")
        return 1

    from .workers import WorkerPool, default_count

    app = QApplication(sys.argv[:1])
    workers = default_count() if args.workers is None else max(0, args.workers)
    workers = min(workers, len(found.pictures))
    if workers:
        swarm = WorkerPool(found.pictures, workers)  # several processes, several cores
    else:
        swarm = Swarm(found.pictures)
    print(f"  processes: {workers or 1} for the pictures" + (" (plus this one for the video)" if workers else ""))

    video = None
    if found.video:
        # The video only closes once every picture is closed, and closing a
        # picture opens another, so in practice it never closes.
        video = VideoWindow(
            found.video,
            muted=args.mute,
            may_close=swarm.all_closed,
            refusal=lambda: f"Nope. {swarm.open_count} snow leopards are still out there.",
        )
        video.activated.connect(swarm.raise_)  # pictures stay in front
        video.start()
    if workers:
        swarm.start()  # workers take about a second to start up anyway
    else:
        QTimer.singleShot(config.PICTURES_DELAY_MS, swarm.start)

    stopping = False

    def shutdown() -> None:
        # app.quit() asks every window to close and gives up when one refuses,
        # which the video window always does. exit() cannot be refused.
        nonlocal stopping
        if stopping:
            return
        stopping = True
        killswitch.stop()
        swarm.shutdown()
        if video is not None:
            video.force_close()
        app.exit(0)

    killswitch = KillSwitch()
    killswitch.triggered.connect(shutdown)
    how = killswitch.start()
    # While one of our windows has focus the shortcut works on any system.
    if workers:
        swarm.stop_requested.connect(shutdown)
    for window in [video, *([] if workers else swarm.overlays.values())]:
        if window is not None:
            shortcut = QShortcut(QKeySequence(HOTKEY_TEXT), window)
            shortcut.activated.connect(shutdown)

    print()
    print("To stop it:")
    if how != "off":
        print(f"  - press {HOTKEY_TEXT} (works from any window)")
    else:
        print(f"  - press {HOTKEY_TEXT} while a snow leopard window is active")
    print("  - or press Ctrl+C in this window, or close this window")

    if args.duration:
        QTimer.singleShot(round(args.duration * 1000), shutdown)
    return app.exec()
