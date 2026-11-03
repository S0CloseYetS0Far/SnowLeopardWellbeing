"""The way out: Ctrl+Shift+Q stops the whole script, from anywhere.

The pictures and the video refuse to go away by themselves, so the script
needs an exit that always works, even when the pictures cover the console.
On Windows the combination is registered as a system-wide hotkey, so it
works whichever window has focus, and the key press is not passed on to
that window. If another program already owns the combination, the keys
are checked a few times a second instead.

Ctrl+C in the console, or closing the console, also stop the script.
"""

from __future__ import annotations

import sys
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, QTimer, Signal

HOTKEY_TEXT = "Ctrl+Shift+Q"
_HOTKEY_ID = 0x5A1E  # any number in 0x0000-0xBFFF that is ours
_WM_HOTKEY = 0x0312
_MOD_CONTROL, _MOD_SHIFT, _MOD_NOREPEAT = 0x0002, 0x0004, 0x4000
_VK_SHIFT, _VK_CONTROL, _VK_Q = 0x10, 0x11, ord("Q")


class _HotkeyFilter(QAbstractNativeEventFilter):
    """Spots our WM_HOTKEY message in the stream of Windows messages."""

    def __init__(self, on_hotkey: Callable[[], None]) -> None:
        super().__init__()
        self._on_hotkey = on_hotkey

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                self._on_hotkey()
                return True, 0
        return False, 0


class KillSwitch(QObject):
    """Emits ``triggered`` (once) when Ctrl+Shift+Q is pressed.

    *key_down* tells whether a virtual key is held; it is only needed for
    the polling fallback and can be replaced in tests.
    """

    triggered = Signal()

    def __init__(self, key_down: Callable[[int], bool] | None = None) -> None:
        super().__init__()
        self.mode = "off"  # "hotkey", "polling" or "off"
        self._fired = False
        self._filter: _HotkeyFilter | None = None
        self._key_down = key_down
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(30)
        self._poll_timer.timeout.connect(self.poll)

    def start(self) -> str:
        """Start listening; returns how: "hotkey", "polling" or "off"."""
        if self._key_down is None and sys.platform == "win32":
            if self._register_hotkey():
                self.mode = "hotkey"
                return self.mode
            import ctypes

            get_state = ctypes.windll.user32.GetAsyncKeyState
            self._key_down = lambda vk: bool(get_state(vk) & 0x8000)
        if self._key_down is not None:
            self._poll_timer.start()
            self.mode = "polling"
        return self.mode

    def stop(self) -> None:
        self._poll_timer.stop()
        if self.mode == "hotkey":
            import ctypes

            ctypes.windll.user32.UnregisterHotKey(None, _HOTKEY_ID)
            QCoreApplication.instance().removeNativeEventFilter(self._filter)
        self.mode = "off"

    def poll(self) -> None:
        down = self._key_down
        if down is not None and down(_VK_CONTROL) and down(_VK_SHIFT) and down(_VK_Q):
            self.fire()

    def fire(self) -> None:
        if not self._fired:
            self._fired = True
            self.triggered.emit()

    def _register_hotkey(self) -> bool:
        import ctypes

        modifiers = _MOD_CONTROL | _MOD_SHIFT | _MOD_NOREPEAT
        if not ctypes.windll.user32.RegisterHotKey(None, _HOTKEY_ID, modifiers, _VK_Q):
            return False  # someone else owns Ctrl+Shift+Q
        self._filter = _HotkeyFilter(self.fire)
        QCoreApplication.instance().installNativeEventFilter(self._filter)
        return True
