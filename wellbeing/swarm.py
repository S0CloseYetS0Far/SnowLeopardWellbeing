"""All the pictures together: popping them up, the shared clock, closing.

Closing a picture opens another one straight away, so there are never
fewer on screen. That keeps going until the script itself is stopped.

Every monitor gets its own see-through layer, and the pictures share one
world spanning all of them, so they jump, walk and get thrown from one
monitor to the next.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QObject, QPointF, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication, QImageReader, QPixmap, QScreen

from . import config
from .overlay import Overlay, Stage
from .physics import Body, Bounds, World
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
    """Owns every picture, steps their physics and redraws them each frame.

    *pictures* are all the pictures this swarm may show; *first* (default:
    all of them) are the ones it opens at the start. Replacements for
    closed pictures come from all of *pictures*.
    """

    def __init__(
        self,
        pictures: list[Path],
        rng: random.Random | None = None,
        first: list[Path] | None = None,
    ) -> None:
        super().__init__()
        self.sources = list(pictures)
        self.first = list(self.sources if first is None else first)
        self.rng = rng or random.Random()
        self.quitting = False
        self.started = False
        self.now = 0.0  # seconds since start(); drives every animation
        self._numbers = {source: n for n, source in enumerate(self.sources, 1)}
        self._pixmaps: dict[Path, QPixmap | None] = {}
        self._queue: list[Path] = []

        self.stage = Stage()
        self.stage.close_requested.connect(self.close_picture)
        self.overlays: dict[QScreen, Overlay] = {}
        self.world = World([Bounds(0, 0, 1, 1)])
        self._layout()
        app = QGuiApplication.instance()
        app.screenAdded.connect(self._screen_added)
        app.screenRemoved.connect(self._layout)

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
        return self.stage.pictures

    @property
    def overlay(self) -> Overlay:
        """The layer on the main monitor."""
        primary = QGuiApplication.primaryScreen()
        return self.overlays.get(primary) or next(iter(self.overlays.values()))

    @property
    def open_count(self) -> int:
        """Pictures on screen and not on their way out."""
        return sum(1 for p in self.pictures if not p.closing)

    def all_closed(self) -> bool:
        """True only when no picture is open or still waiting to pop up."""
        if not self.first:
            return True
        return self.started and not self._queue and self.open_count == 0

    # --- starting and stopping -------------------------------------------------
    def start(self) -> None:
        """Pop the first pictures up, one after another, and start the clock."""
        self._queue = self.first[:]
        self.rng.shuffle(self._queue)
        self.started = True
        for overlay in self.overlays.values():
            overlay.show()
        self._clock.start()
        self._frame_timer.start()
        self._spawn_timer.start()

    def raise_(self) -> None:
        """Bring every layer above other always-on-top windows (the video)."""
        for overlay in self.overlays.values():
            overlay.raise_()

    def shutdown(self) -> None:
        self.quitting = True
        self._spawn_timer.stop()
        self._frame_timer.stop()
        self._queue.clear()
        self.pictures.clear()
        for overlay in self.overlays.values():
            overlay.allow_close = True
            overlay.close()

    # --- pictures --------------------------------------------------------------
    def spawn(self, source: Path) -> Picture | None:
        """Open *source* as a new picture in the top part of a random monitor."""
        pixmap = self._pixmap(source)
        if pixmap is None:
            return None
        b = self.rng.choice(self.world.areas)
        longest = self.rng.uniform(*config.PICTURE_SIZE) * (b.bottom - b.top)
        aspect = pixmap.width() / pixmap.height()
        width, height = (longest, longest / aspect) if aspect >= 1 else (longest * aspect, longest)

        x = self.rng.uniform(b.left + width / 2, max(b.left + width / 2, b.right - width / 2))
        y = b.top + height + self.rng.uniform(0, 0.35) * (b.bottom - b.top - height)
        body = Body(
            width, height, x, y, self.world,
            vx=self.rng.uniform(-350, 350), vy=self.rng.uniform(-500, 150),
            rng=random.Random(self.rng.random()),  # each picture gets its own dice
        )
        body.bounds = b
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
        self.stage.forget(picture)
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
            # Big enough for the largest picture at its widest squash, on the
            # tallest and sharpest monitor.
            longest = max(
                (s.availableGeometry().height() * s.devicePixelRatio() for s in self.overlays),
                default=1080,
            )
            longest = math.ceil(config.PICTURE_SIZE[1] * longest / (1 - config.MAX_SQUASH))
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

        cursor = QPointF(QCursor.pos())
        over_us = any(o.area.contains(cursor.toPoint()) for o in self.overlays.values())
        self.stage.update_hover(cursor if over_us else None)
        self.stage.now = self.now
        boxes = [p.paint_box(self.now) for p in self.pictures]
        for overlay in self.overlays.values():
            overlay.refresh(boxes)

    # --- monitors --------------------------------------------------------------
    def _screen_added(self, screen: QScreen) -> None:
        self._layout()
        if self.started and not self.quitting:
            self.overlays[screen].show()

    def _layout(self, *_args) -> None:
        """One layer per monitor, covering it above the taskbar; each monitor's
        free area becomes a room of the world, its bottom edge the floor."""
        screens = QGuiApplication.screens()
        for screen in list(self.overlays):
            if screen not in screens:
                overlay = self.overlays.pop(screen)
                overlay.allow_close = True
                overlay.close()
                overlay.deleteLater()
        areas = []
        for screen in screens:
            overlay = self.overlays.get(screen)
            if overlay is None:
                overlay = self.overlays[screen] = Overlay(self.stage)
                overlay.setScreen(screen)
                screen.availableGeometryChanged.connect(self._layout)
            area = screen.availableGeometry()
            overlay.setGeometry(area)
            areas.append(Bounds(area.left(), area.top(), area.left() + area.width(), area.top() + area.height()))
        if areas:
            self.world.areas[:] = areas  # bodies notice and find their new room
