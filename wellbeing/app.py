"""Entry point: read the options, find the media, start everything."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import media


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="wellbeing",
        description="Plays the snow leopard video and lets every picture loose on the screen.",
    )
    parser.add_argument("--pictures", type=Path, help="folder of pictures (default: snowleopard/)")
    parser.add_argument("--video", type=Path, help="video file (default: first video in the project folder)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    found = media.discover(args.pictures, args.video)
    print("Snow Leopard Wellbeing")
    print(f"  video    : {found.video.name if found.video else '(none found)'}")
    print(f"  pictures : {len(found.pictures)}")
    return 0
