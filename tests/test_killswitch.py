import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QElapsedTimer
from PySide6.QtWidgets import QApplication

from wellbeing.killswitch import _HOTKEY_ID, _WM_HOTKEY, KillSwitch

app = QApplication.instance() or QApplication([])
CTRL, SHIFT, Q = 0x11, 0x10, ord("Q")


def listen(switch):
    fired = []
    switch.triggered.connect(lambda: fired.append(True))
    return fired


class PollingTest(unittest.TestCase):
    def test_ctrl_shift_q_triggers_it_once(self):
        switch = KillSwitch(key_down=lambda vk: vk in {CTRL, SHIFT, Q})
        fired = listen(switch)
        self.assertEqual(switch.start(), "polling")

        switch.poll()
        switch.poll()

        self.assertEqual(fired, [True])
        switch.stop()

    def test_part_of_the_combination_does_nothing(self):
        for held in ({CTRL, SHIFT}, {CTRL, Q}, {SHIFT, Q}, {Q}, set()):
            switch = KillSwitch(key_down=lambda vk, held=held: vk in held)
            fired = listen(switch)
            switch.start()
            switch.poll()
            self.assertEqual(fired, [], f"fired with only {held}")
            switch.stop()


@unittest.skipUnless(sys.platform == "win32", "Windows system hotkey")
class SystemHotkeyTest(unittest.TestCase):
    def test_the_hotkey_message_from_windows_triggers_it(self):
        import ctypes

        switch = KillSwitch()
        fired = listen(switch)
        mode = switch.start()
        try:
            if mode != "hotkey":
                self.skipTest("another program owns Ctrl+Shift+Q")
            # Exactly what Windows posts when the registered keys are pressed.
            thread = ctypes.windll.kernel32.GetCurrentThreadId()
            ctypes.windll.user32.PostThreadMessageW(thread, _WM_HOTKEY, _HOTKEY_ID, 0)
            waited = QElapsedTimer()
            waited.start()
            while not fired and waited.elapsed() < 2000:
                QCoreApplication.processEvents()
            self.assertEqual(fired, [True])
        finally:
            switch.stop()

    def test_it_lets_go_of_the_hotkey_when_stopped(self):
        import ctypes

        switch = KillSwitch()
        if switch.start() != "hotkey":
            self.skipTest("another program owns Ctrl+Shift+Q")
        switch.stop()
        # Free again: registering it ourselves now works.
        self.assertTrue(ctypes.windll.user32.RegisterHotKey(None, 0x1234, 0x0006, Q))
        ctypes.windll.user32.UnregisterHotKey(None, 0x1234)


if __name__ == "__main__":
    unittest.main()
