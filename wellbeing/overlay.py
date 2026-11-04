"""The see-through layers the pictures live on, one per monitor.

Animating dozens of real windows is slow on Windows: every move and resize
of a native window costs about a millisecond, so 53 of them crawl along at
under 10 frames a second. Drawing every picture on one transparent,
always-on-top layer per monitor runs at a smooth 60. Clicks on the empty,
see-through parts fall through to whatever is underneath; clicks on a
picture reach it.

Pictures live in one coordinate space shared by every monitor (Qt's global
screen coordinates), so a picture can sit across the edge between two
monitors and each layer draws its own half. The ``Stage`` holds the pictures
and the mouse state; each ``Overlay`` is a window that draws its part of the
stage and passes the mouse on to it.
"""

from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import QObject, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QCloseEvent, QFont, QFontMetrics, QMouseEvent, QPainter, QPaintEvent, QRegion
from PySide6.QtWidgets import QWidget

from .picture import Picture

THROW_WINDOW = 0.1  # seconds of mouse movement used to work out a throw


class Stage(QObject):
    """Every picture (bottom to top), in global screen coordinates, and the mouse.

    Emits ``close_requested(picture)`` when the user closes a picture with its
    close button, or with Alt+F4 after clicking it.
    """

    close_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.pictures: list[Picture] = []
        self.now = 0.0
        self.font = QFont("Segoe UI", 9)
        self.metrics = QFontMetrics(self.font)
        self._held: Picture | None = None
        self._focused: Picture | None = None
        self._grab_offset = QPointF()
        self._trail: deque[tuple[float, float, float]] = deque(maxlen=16)

    # --- finding pictures ------------------------------------------------------
    def picture_at(self, point: QPointF) -> Picture | None:
        for picture in reversed(self.pictures):
            if picture.contains(point):
                return picture
        return None

    def update_hover(self, point: QPointF | None) -> None:
        """Light up the close button under *point* (None: the cursor is elsewhere)."""
        hovered = self.picture_at(point) if point is not None else None
        for picture in self.pictures:
            picture.hover_close = picture is hovered and picture.on_close_button(point)

    def forget(self, picture: Picture) -> None:
        """Stop tracking *picture* for input (it is closing)."""
        if self._held is picture:
            self._held = None
        if self._focused is picture:
            self._focused = None

    # --- mouse, in global coordinates -------------------------------------------
    def press(self, point: QPointF) -> None:
        picture = self.picture_at(point)
        if picture is None:
            return
        self._focused = picture
        # Pictures keep moving, so close on press: waiting for the release
        # would often miss the button.
        if picture.on_close_button(point):
            self.close_requested.emit(picture)
            return
        self.pictures.remove(picture)  # clicked one comes to the front
        self.pictures.append(picture)
        self._held = picture
        picture.body.grab()
        self._grab_offset = QPointF(point.x() - picture.body.x, point.y() - picture.body.y)
        self._trail.clear()
        self._trail.append((time.perf_counter(), point.x(), point.y()))

    def move(self, point: QPointF) -> None:
        if self._held is not None:
            self._held.body.move_to(point.x() - self._grab_offset.x(), point.y() - self._grab_offset.y())
            self._trail.append((time.perf_counter(), point.x(), point.y()))
        self.update_hover(point)

    def release(self) -> None:
        if self._held is not None:
            self._held.body.throw(*self._throw_velocity())
            self._held = None

    def _throw_velocity(self) -> tuple[float, float]:
        if len(self._trail) < 2:
            return 0.0, 0.0
        newest = self._trail[-1]
        oldest = next(s for s in self._trail if newest[0] - s[0] <= THROW_WINDOW)
        elapsed = newest[0] - oldest[0]
        if elapsed < 0.005:
            return 0.0, 0.0
        return (newest[1] - oldest[1]) / elapsed, (newest[2] - oldest[2]) / elapsed

    def alt_f4_target(self) -> Picture | None:
        """The picture Alt+F4 closes: the one last clicked, else the top one."""
        target = self._focused
        if target is None or target.closing:
            target = next((p for p in reversed(self.pictures) if not p.closing), None)
        return target


class Overlay(QWidget):
    """A transparent window over one monitor that shows its part of the stage."""

    def __init__(self, stage: Stage) -> None:
        flags = (
            Qt.WindowType.Tool  # no taskbar button
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setWindowTitle("Snow Leopards")
        self.stage = stage
        self.allow_close = False
        self._dirty = QRegion()  # where pictures were drawn last frame (local)

    @property
    def area(self) -> QRect:
        """The part of the global coordinate space this layer covers."""
        return self.geometry()

    # --- drawing ---------------------------------------------------------------
    def refresh(self, boxes: list[QRect]) -> None:
        """Repaint where pictures were last frame and where they are now (global boxes)."""
        area = self.area
        origin = area.topLeft()
        now = QRegion()
        for box in boxes:
            if box.intersects(area):
                now += box.translated(-origin)
        changed = now + self._dirty
        self._dirty = now
        if not changed.isEmpty():
            self.update(changed)

    def paintEvent(self, event: QPaintEvent) -> None:
        stage = self.stage
        origin = self.area.topLeft()
        visible = event.rect().translated(origin)  # global
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setFont(stage.font)
        painter.translate(-origin.x(), -origin.y())
        for picture in stage.pictures:
            if picture.paint_box(stage.now).intersects(visible):
                picture.draw(painter, stage.now, stage.metrics)

    # --- mouse -----------------------------------------------------------------
    def _global(self, event: QMouseEvent) -> QPointF:
        return event.position() + QPointF(self.area.topLeft())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.stage.press(self._global(event))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        # While a picture is held, moves keep coming here even when the mouse
        # is over another monitor, so a picture can be dragged across.
        self.stage.move(self._global(event))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.stage.release()

    def leaveEvent(self, _event) -> None:
        self.stage.update_hover(None)

    # --- closing ---------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:
        """Alt+F4 closes the picture last clicked, never the whole layer."""
        if self.allow_close:
            event.accept()
            return
        event.ignore()
        target = self.stage.alt_f4_target()
        if target is not None:
            self.stage.close_requested.emit(target)
