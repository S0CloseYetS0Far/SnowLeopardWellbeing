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
    parser.add_argument("--duration", type=float, metavar="SECONDS", help="quit by itself after this many seconds")
    return parser.parse_args(argv)


def _quiet_ffmpeg() -> None:
    """Keep FFmpeg's codec-probing chatter out of the console.

    Qt's video backend is FFmpeg, which logs straight to stderr. Its DLL ships
    inside PySide6; loading it here gives the same instance Qt uses. Playback
    errors still reach us through QMediaPlayer.errorOccurred.
    """
    import ctypes

    import PySide6

    for dll in Path(PySide6.__file__).parent.glob("avutil*.dll"):
        try:
            ctypes.CDLL(str(dll)).av_log_set_level(8)  # AV_LOG_FATAL
        except (OSError, AttributeError):
            pass


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    found = media.discover(args.pictures, args.video)
    print("Snow Leopard Wellbeing")
    print(f"  video    : {found.video.name if found.video else '(none found)'}")
    print(f"  pictures : {len(found.pictures)}")
    print("To stop: press Ctrl+C in this window, or close this window.")

    # Qt's FFmpeg backend prints a stream dump for every file it opens.
    os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia*=false")
    _quiet_ffmpeg()
    # Ctrl+C in the console ends the script at once, even inside Qt's loop.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from . import config
    from .swarm import Swarm
    from .video_window import VideoWindow

    if not found.video and not found.pictures:
        print("Nothing to show.")
        return 1

    app = QApplication(sys.argv[:1])
    swarm = Swarm(found.pictures)

    video = None
    if found.video:
        video = VideoWindow(found.video, muted=args.mute, may_close=lambda: False)
        video.start()
    QTimer.singleShot(config.PICTURES_DELAY_MS, swarm.start)

    def shutdown() -> None:
        # app.quit() asks every window to close and gives up when one refuses,
        # which the video window always does. exit() cannot be refused.
        swarm.shutdown()
        if video is not None:
            video.force_close()
        app.exit(0)

    if args.duration:
        QTimer.singleShot(round(args.duration * 1000), shutdown)
    return app.exec()
