"""All the pictures together: popping them up, the shared clock, closing.

Closing a picture opens another one straight away, so there are never
fewer on screen. That keeps going until the script itself is stopped.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QObject, QPointF, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication, QImageReader, QPixmap

from . import config
from .overlay import Overlay
from .physics import Body, Bounds
from .picture import Picture


def load_pixmap(path: Path, longest: int) -> QPixmap | None:
    """Read a picture, shrunk so its longest side is at most *longest* px."""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)  # respect the camera's rotation flag
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > longest:
        reader.setScaledSize(size.scaled(longest, longest, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    return None if image.isNull() else QPixmap.fromImage(image)


class Swarm(QObject):
    """Owns every picture, steps their physics and redraws them each frame."""

    def __init__(self, pictures: list[Path], rng: random.Random | None = None) -> None:
        super().__init__()
        self.sources = list(pictures)
        self.rng = rng or random.Random()
        self.quitting = False
        self.started = False
        self.now = 0.0  # seconds since start(); drives every animation
        self._numbers = {source: n for n, source in enumerate(self.sources, 1)}
        self._pixmaps: dict[Path, QPixmap | None] = {}
        self._queue: list[Path] = []

        self.overlay = Overlay()
        self.overlay.close_requested.connect(self.close_picture)
        self._screen = QGuiApplication.primaryScreen()
        self.bounds = Bounds(0, 0, 1, 1)  # overlay coordinates; bottom is the floor
        self._fit_screen()
        self._screen.availableGeometryChanged.connect(self._fit_screen)

        self._clock = QElapsedTimer()
        self._frame_timer = QTimer(self)
        self._frame_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._frame_timer.setInterval(round(1000 / config.FPS))
        self._frame_timer.timeout.connect(self._tick)
        self._spawn_timer = QTimer(self)
        self._spawn_timer.setInterval(config.SPAWN_INTERVAL_MS)
        self._spawn_timer.timeout.connect(self._spawn_next)

    @property
    def pictures(self) -> list[Picture]:
        return self.overlay.pictures

    @property
    def open_count(self) -> int:
        """Pictures on screen and not on their way out."""
        return sum(1 for p in self.pictures if not p.closing)

    def all_closed(self) -> bool:
        """True only when no picture is open or still waiting to pop up."""
        if not self.sources:
            return True
        return self.started and not self._queue and self.open_count == 0

    # --- starting and stopping -------------------------------------------------
    def start(self) -> None:
        """Pop every picture up, one after another, and start the clock."""
        self._queue = self.sources[:]
        self.rng.shuffle(self._queue)
        self.started = True
        self.overlay.show()
        self._clock.start()
        self._frame_timer.start()
        self._spawn_timer.start()

    def shutdown(self) -> None:
        self.quitting = True
        self._spawn_timer.stop()
        self._frame_timer.stop()
        self._queue.clear()
        self.pictures.clear()
        self.overlay.allow_close = True
        self.overlay.close()

    # --- pictures --------------------------------------------------------------
    def spawn(self, source: Path) -> Picture | None:
        """Open *source* as a new picture somewhere in the top part of the screen."""
        pixmap = self._pixmap(source)
        if pixmap is None:
            return None
        b = self.bounds
        longest = self.rng.uniform(*config.PICTURE_SIZE) * (b.bottom - b.top)
        aspect = pixmap.width() / pixmap.height()
        width, height = (longest, longest / aspect) if aspect >= 1 else (longest * aspect, longest)

        x = self.rng.uniform(b.left + width / 2, max(b.left + width / 2, b.right - width / 2))
        y = b.top + height + self.rng.uniform(0, 0.35) * (b.bottom - b.top - height)
        body = Body(
            width, height, x, y, b,
            vx=self.rng.uniform(-350, 350), vy=self.rng.uniform(-500, 150),
            rng=random.Random(self.rng.random()),  # each picture gets its own dice
        )
        title = f"Snow Leopard #{self._numbers.get(source, 0)}"
        picture = Picture(pixmap, title, body, source, born=self.now)
        self.pictures.append(picture)
        return picture

    def close_picture(self, picture: Picture) -> None:
        """Close *picture*, and open another one in its place."""
        if picture.closing or picture not in self.pictures:
            return
        picture.closed_at = self.now
        if picture.body.held:
            picture.body.throw(0, 0)
        self.overlay.forget(picture)
        if not self.quitting:
            for _ in range(config.RESPAWN_PER_CLOSE):
                self.spawn(self._replacement_for(picture.source))

    def _replacement_for(self, closed: Path) -> Path:
        """A different picture, preferably one that is not on screen yet."""
        showing = {p.source for p in self.pictures if not p.closing} | set(self._queue)
        unseen = [s for s in self.sources if s not in showing and s != closed]
        others = [s for s in self.sources if s != closed]
        return self.rng.choice(unseen or others or self.sources)

    def _spawn_next(self) -> None:
        if self.quitting or not self._queue:
            self._spawn_timer.stop()
            return
        self.spawn(self._queue.pop())

    def _pixmap(self, source: Path) -> QPixmap | None:
        if source not in self._pixmaps:
            # Big enough for the largest picture at its widest squash.
            dpr = self._screen.devicePixelRatio()
            longest = config.PICTURE_SIZE[1] * (self.bounds.bottom - self.bounds.top)
            longest = math.ceil(longest / (1 - config.MAX_SQUASH) * dpr)
            self._pixmaps[source] = load_pixmap(source, longest)
        return self._pixmaps[source]

    # --- the clock -------------------------------------------------------------
    def _tick(self) -> None:
        dt = min(self._clock.restart() / 1000.0, config.MAX_FRAME_TIME)
        self.now += dt
        for picture in self.pictures:
            if not picture.closing:
                picture.body.step(dt)
        self.pictures[:] = [p for p in self.pictures if not p.gone(self.now)]

        cursor = QPointF(self.overlay.mapFromGlobal(QCursor.pos()))
        inside = self.overlay.rect().contains(cursor.toPoint())
        self.overlay.update_hover(cursor if inside else None)
        self.overlay.now = self.now
        self.overlay.update()

    def _fit_screen(self, *_args) -> None:
        """Cover the screen above the taskbar; its bottom edge is the floor."""
        area = self._screen.availableGeometry()
        self.overlay.setGeometry(area)
        self.bounds.left, self.bounds.top = 0, 0
        self.bounds.right, self.bounds.bottom = area.width(), area.height()
