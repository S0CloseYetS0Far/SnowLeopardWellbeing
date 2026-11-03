"""The see-through layer over the whole screen that all the pictures live on.

Animating dozens of real windows is slow on Windows: every move and resize
of a native window costs about a millisecond, so 53 of them crawl along at
under 10 frames a second. Drawing every picture on one transparent,
always-on-top layer runs at a smooth 60. Clicks on the empty, see-through
parts fall through to whatever is underneath; clicks on a picture reach it.
"""

from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QCloseEvent, QFont, QFontMetrics, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from .picture import Picture

THROW_WINDOW = 0.1  # seconds of mouse movement used to work out a throw


class Overlay(QWidget):
    """Draws ``pictures`` (bottom to top) and turns mouse input into actions.

    Emits ``close_requested(picture)`` when the user closes a picture with its
    close button, or with Alt+F4 after clicking it.
    """

    close_requested = Signal(object)

    def __init__(self) -> None:
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

        self.pictures: list[Picture] = []
        self.now = 0.0
        self.allow_close = False
        self._font = QFont("Segoe UI", 9)
        self._metrics = QFontMetrics(self._font)
        self._held: Picture | None = None
        self._focused: Picture | None = None
        self._grab_offset = QPointF()
        self._trail: deque[tuple[float, float, float]] = deque(maxlen=16)

    # --- drawing ---------------------------------------------------------------
    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setFont(self._font)
        for picture in self.pictures:
            picture.draw(painter, self.now, self._metrics)

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

    # --- mouse -----------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position()
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

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position()
        if self._held is not None:
            self._held.body.move_to(point.x() - self._grab_offset.x(), point.y() - self._grab_offset.y())
            self._trail.append((time.perf_counter(), point.x(), point.y()))
        self.update_hover(point)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._held is not None:
            self._held.body.throw(*self._throw_velocity())
            self._held = None

    def leaveEvent(self, _event) -> None:
        self.update_hover(None)

    def _throw_velocity(self) -> tuple[float, float]:
        if len(self._trail) < 2:
            return 0.0, 0.0
        newest = self._trail[-1]
        oldest = next(s for s in self._trail if newest[0] - s[0] <= THROW_WINDOW)
        elapsed = newest[0] - oldest[0]
        if elapsed < 0.005:
            return 0.0, 0.0
        return (newest[1] - oldest[1]) / elapsed, (newest[2] - oldest[2]) / elapsed

    # --- closing ---------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:
        """Alt+F4 closes the picture last clicked, never the whole layer."""
        if self.allow_close:
            event.accept()
            return
        event.ignore()
        target = self._focused
        if target is None or target.closing:
            target = next((p for p in reversed(self.pictures) if not p.closing), None)
        if target is not None:
            self.close_requested.emit(target)
