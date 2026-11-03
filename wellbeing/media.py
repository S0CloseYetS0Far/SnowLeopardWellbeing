"""Find the pictures and the video on disk."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PICTURE_EXTENSIONS = {".jpg", ".jpeg", ".jfif", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".wmv"}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PICTURES_DIR = PROJECT_ROOT / "snowleopard"


def _files_with(folder: Path, extensions: set[str]) -> list[Path]:
    if not folder.is_dir():
        return []
    found = (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in extensions)
    return sorted(found, key=lambda p: p.name.lower())


def find_pictures(folder: Path) -> list[Path]:
    """Every picture file directly inside *folder*, sorted by name."""
    return _files_with(folder, PICTURE_EXTENSIONS)


def find_video(*folders: Path) -> Path | None:
    """The first video file in *folders*, searched in the order given."""
    for folder in folders:
        videos = _files_with(folder, VIDEO_EXTENSIONS)
        if videos:
            return videos[0]
    return None


@dataclass(frozen=True)
class Media:
    pictures: list[Path]
    video: Path | None


def discover(pictures_dir: Path | None = None, video: Path | None = None) -> Media:
    """Pictures from *pictures_dir* (default ``snowleopard/``) and a video.

    Without an explicit *video*, the first video file in the project folder
    is used, then the first one in the pictures folder.
    """
    pictures_dir = pictures_dir or DEFAULT_PICTURES_DIR
    if video is None:
        video = find_video(PROJECT_ROOT, pictures_dir)
    return Media(find_pictures(pictures_dir), video)
