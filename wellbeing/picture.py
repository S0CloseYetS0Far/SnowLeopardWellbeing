"""One snow leopard picture: its body, how it looks, where it can be clicked.

Each picture is drawn as a little window of its own, with a title strip and
a close button, stretched and squashed to the shape of its body.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen, QPixmap, QStaticText

from . import config
from .physics import Body

_BAR = QColor(18, 18, 22, 190)
_CLOSE_HOVER = QColor(196, 43, 28)
_TEXT = QColor(236, 236, 240)
_BORDER = QColor(0, 0, 0, 150)
_CROSS_SIZE = 11
_cross: QPixmap | None = None


def _cross_pixmap() -> QPixmap:
    """The close button's cross, drawn once and reused (strokes are slow)."""
    global _cross
    if _cross is None:
        _cross = QPixmap(_CROSS_SIZE, _CROSS_SIZE)
        _cross.fill(Qt.GlobalColor.transparent)
        painter = QPainter(_cross)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(255, 255, 255), 1.4))
        a, b = 1.0, _CROSS_SIZE - 1.0
        painter.drawLine(QPointF(a, a), QPointF(b, b))
        painter.drawLine(QPointF(a, b), QPointF(b, a))
        painter.end()
    return _cross


def _ease_out_back(t: float) -> float:
    """0 -> 1 with a little overshoot, for the pop when a picture opens."""
    c = 1.70158
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


class Picture:
    def __init__(self, pixmap: QPixmap, title: str, body: Body, source: Path, born: float) -> None:
        self.pixmap = pixmap
        self.title = title
        self.body = body
        self.source = source
        self.born = born
        self.closed_at: float | None = None
        self.hover_close = False
        self._source_rect = QRectF(pixmap.rect())
        self._labels: dict[int, QStaticText] = {}  # title elided to a width, by width

    # --- state ---------------------------------------------------------------
    @property
    def closing(self) -> bool:
        return self.closed_at is not None

    def gone(self, now: float) -> bool:
        """True once the closing animation has finished."""
        return self.closed_at is not None and now - self.closed_at >= config.CLOSE_TIME

    def presence(self, now: float) -> float:
        """Size factor for opening and closing: 0 -> ~1.1 -> 1 when born, 1 -> 0 when closed."""
        if self.closed_at is not None:
            return max(0.0, 1.0 - (now - self.closed_at) / config.CLOSE_TIME)
        t = (now - self.born) / config.POP_TIME
        return 1.0 if t >= 1 else max(0.0, _ease_out_back(t))

    # --- geometry --------------------------------------------------------------
    def rect(self) -> QRectF:
        sx, sy = self.body.scale
        width = self.body.width * sx
        height = self.body.height * sy
        return QRectF(self.body.x - width / 2, self.body.y - height, width, height)

    def paint_box(self, now: float) -> QRect:
        """Whole pixels covering everything ``draw`` paints right now."""
        r = self.rect()
        size = max(1.0, self.presence(now))  # the opening pop overshoots a little
        if size != 1.0:
            centre = r.center()
            r = QRectF(centre.x() - r.width() * size / 2, centre.y() - r.height() * size / 2,
                       r.width() * size, r.height() * size)
        return r.toAlignedRect().adjusted(-2, -2, 2, 2)

    def close_rect(self) -> QRectF:
        r = self.rect()
        width = min(config.CLOSE_BUTTON_WIDTH, r.width())
        return QRectF(r.right() - width, r.top(), width, config.TITLE_BAR_HEIGHT)

    def contains(self, point: QPointF) -> bool:
        return not self.closing and self.rect().contains(point)

    def on_close_button(self, point: QPointF) -> bool:
        return not self.closing and self.close_rect().contains(point)

    # --- drawing ---------------------------------------------------------------
    def draw(self, painter: QPainter, now: float, metrics: QFontMetrics) -> None:
        """Draw onto *painter*, which already has the title font and smooth scaling set."""
        size = self.presence(now)
        if size <= 0:
            return
        r = self.rect()
        animating = size != 1.0
        if animating:  # opening or closing: scale about the centre and fade
            painter.save()
            centre = r.center()
            painter.translate(centre)
            painter.scale(size, size)
            painter.translate(-centre)
            painter.setOpacity(min(1.0, size))

        painter.drawPixmap(r, self.pixmap, self._source_rect)

        bar_height = config.TITLE_BAR_HEIGHT
        painter.fillRect(QRectF(r.left(), r.top(), r.width(), bar_height), _BAR)
        close = self.close_rect()
        if self.hover_close:
            painter.fillRect(close, _CLOSE_HOVER)
        cross = close.center() - QPointF(_CROSS_SIZE / 2, _CROSS_SIZE / 2)
        painter.drawPixmap(QPoint(round(cross.x()), round(cross.y())), _cross_pixmap())

        text_width = int(r.width() - close.width() - 10)
        if text_width > 16:
            painter.setPen(_TEXT)
            top = r.top() + (bar_height - metrics.height()) / 2
            painter.drawStaticText(QPoint(round(r.left() + 8), round(top)), self._label(metrics, text_width))

        # A thin dark edge, drawn as fills: pen strokes are much slower.
        left, top, right, bottom = r.left(), r.top(), r.right(), r.bottom()
        painter.fillRect(QRectF(left, top, r.width(), 1), _BORDER)
        painter.fillRect(QRectF(left, bottom - 1, r.width(), 1), _BORDER)
        painter.fillRect(QRectF(left, top, 1, r.height()), _BORDER)
        painter.fillRect(QRectF(right - 1, top, 1, r.height()), _BORDER)

        if animating:
            painter.restore()

    def _label(self, metrics: QFontMetrics, width: int) -> QStaticText:
        key = width // 4
        label = self._labels.get(key)
        if label is None:
            label = QStaticText(metrics.elidedText(self.title, Qt.TextElideMode.ElideRight, key * 4))
            label.setTextFormat(Qt.TextFormat.PlainText)
            self._labels[key] = label
        return label
