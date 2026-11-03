"""The video window: plays at once, loops forever, refuses to close."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QAbstractAnimation, QEvent, QPoint, QPropertyAnimation, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaMetaData, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QVBoxLayout, QWidget

from . import config

TITLE = "Snow Leopard Wellbeing"
_ffmpeg_quiet = False


def quiet_ffmpeg() -> None:
    """Keep FFmpeg's codec-probing chatter out of the console.

    Qt's video backend is FFmpeg, which logs straight to stderr. Its DLL ships
    inside PySide6; loading it here gives the same instance Qt uses. Playback
    errors still reach us through QMediaPlayer.errorOccurred.
    """
    global _ffmpeg_quiet
    if _ffmpeg_quiet:
        return
    _ffmpeg_quiet = True
    import ctypes

    import PySide6

    for dll in Path(PySide6.__file__).parent.glob("avutil*.dll"):
        try:
            ctypes.CDLL(str(dll)).av_log_set_level(8)  # AV_LOG_FATAL
        except (OSError, AttributeError):
            pass


class VideoWindow(QWidget):
    """Shows the video. Closing is refused while ``may_close()`` is False.

    ``refusal()`` gives the text flashed in the title bar when a close is
    refused. ``force_close()`` always works; the kill switch uses it.
    ``activated`` fires whenever the window becomes the active one.
    """

    activated = Signal()

    def __init__(
        self,
        video: Path,
        *,
        muted: bool = False,
        may_close: Callable[[], bool] = lambda: True,
        refusal: Callable[[], str] = lambda: "Nope.",
    ) -> None:
        # Title bar with only a close button: no minimize, no maximize.
        flags = (
            Qt.WindowType.Window
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        super().__init__(None, flags)
        quiet_ffmpeg()
        self.may_close = may_close
        self.refusal = refusal
        self._forced = False
        self._shown = False

        self.setWindowTitle(TITLE)
        self.setStyleSheet("background: black;")
        self.view = QVideoWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        self.audio = QAudioOutput(self)
        self.audio.setVolume(config.VIDEO_VOLUME)
        self.audio.setMuted(muted)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.view)
        self.player.setLoops(QMediaPlayer.Loops.Infinite)
        self.player.playbackStateChanged.connect(self._keep_playing)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.errorOccurred.connect(self._on_error)
        self.player.setSource(QUrl.fromLocalFile(str(video)))

        # If headphones are plugged in or out, follow the new default speaker.
        self._devices = QMediaDevices(self)
        self._devices.audioOutputsChanged.connect(
            lambda: self.audio.setDevice(QMediaDevices.defaultAudioOutput())
        )

        self._shake_anim = QPropertyAnimation(self, b"pos", self)
        self._shake_anim.setDuration(380)
        self._title_reset = QTimer(self, singleShot=True, interval=2500)
        self._title_reset.timeout.connect(lambda: self.setWindowTitle(TITLE))
        self._fit(QSize(16, 9))

    # --- starting --------------------------------------------------------
    def start(self) -> None:
        """Start playing now; the window appears once the video size is known."""
        self.player.play()
        QTimer.singleShot(1000, self._show_once)  # in case the size never arrives

    def _on_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if self._shown or status not in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferingMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            return
        size = self.player.metaData().value(QMediaMetaData.Key.Resolution)
        if isinstance(size, QSize) and size.isValid():
            self._fit(size)
        self._show_once()

    def _show_once(self) -> None:
        if not self._shown:
            self._shown = True
            self.show()
            self.raise_()

    def _fit(self, video_size: QSize) -> None:
        """Size the window to the video's shape and centre it on the screen."""
        screen = QGuiApplication.primaryScreen().availableGeometry()
        scale = min(
            screen.width() * config.VIDEO_MAX_WIDTH / video_size.width(),
            screen.height() * config.VIDEO_MAX_HEIGHT / video_size.height(),
        )
        width, height = round(video_size.width() * scale), round(video_size.height() * scale)
        self.resize(width, height)
        self.move(screen.center() - QPoint(width // 2, height // 2))

    # --- never stop ------------------------------------------------------
    def _keep_playing(self, state: QMediaPlayer.PlaybackState) -> None:
        if (
            state != QMediaPlayer.PlaybackState.PlayingState
            and not self._forced
            and self.player.error() == QMediaPlayer.Error.NoError
        ):
            QTimer.singleShot(0, self.player.play)

    def _on_error(self, _error: QMediaPlayer.Error, message: str) -> None:
        print(f"Video error: {message}", file=sys.stderr)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            QTimer.singleShot(0, self._unminimize)
        elif event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.activated.emit()

    def _unminimize(self) -> None:
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.show()
        self.raise_()

    # --- closing ---------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:
        if self._forced or self.may_close():
            self._forced = True
            self.player.stop()
            event.accept()
            return
        event.ignore()
        self._refuse()

    def force_close(self) -> None:
        self._forced = True
        self.close()

    def _refuse(self) -> None:
        self.raise_()
        self.activateWindow()
        self.setWindowTitle(self.refusal())
        self._title_reset.start()
        if self._shake_anim.state() == QAbstractAnimation.State.Running:
            return
        start = self.pos()
        offsets = (-24, 20, -16, 12, -8, 4)
        self._shake_anim.setStartValue(start)
        self._shake_anim.setEndValue(start)
        for i, dx in enumerate(offsets, 1):
            self._shake_anim.setKeyValueAt(i / (len(offsets) + 1), start + QPoint(dx, 0))
        self._shake_anim.start()
