"""Closing, respawning and the video lock, with Qt running offscreen."""

import os
import random
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia*=false")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from wellbeing import media
from wellbeing.swarm import Swarm

app = QApplication.instance() or QApplication([])
SOURCES = media.discover().pictures


def running_swarm(count=6, seed=5):
    """A swarm with every picture open, driven by hand instead of by timers."""
    swarm = Swarm(SOURCES[:count], rng=random.Random(seed))
    swarm.start()
    swarm._frame_timer.stop()
    swarm._spawn_timer.stop()
    while swarm._queue:
        swarm._spawn_next()
    return swarm


def centre(rect):
    return QPoint(round(rect.center().x()), round(rect.center().y()))


class RespawnTest(unittest.TestCase):
    def setUp(self):
        self.swarm = running_swarm()

    def tearDown(self):
        self.swarm.shutdown()

    def test_all_pictures_open(self):
        self.assertEqual(self.swarm.open_count, 6)
        self.assertEqual(len({p.source for p in self.swarm.pictures}), 6)

    def test_closing_a_picture_opens_a_different_one(self):
        victim = self.swarm.pictures[0]

        self.swarm.close_picture(victim)

        self.assertTrue(victim.closing)
        self.assertEqual(self.swarm.open_count, 6)
        newcomer = self.swarm.pictures[-1]
        self.assertFalse(newcomer.closing)
        self.assertNotEqual(newcomer.source, victim.source)

    def test_it_goes_on_and_on(self):
        rng = random.Random(1)
        for _ in range(200):
            victim = rng.choice([p for p in self.swarm.pictures if not p.closing])
            self.swarm.close_picture(victim)
            self.swarm.now += 1.0  # let closing animations finish
            self.swarm._tick()
        self.assertEqual(self.swarm.open_count, 6)
        self.assertEqual(len(self.swarm.pictures), 6, "finished pictures are cleaned up")

    def test_closing_the_same_picture_twice_opens_only_one(self):
        victim = self.swarm.pictures[0]
        self.swarm.close_picture(victim)
        self.swarm.close_picture(victim)
        self.assertEqual(len(self.swarm.pictures), 7)  # 6 open + 1 on its way out


class MouseTest(unittest.TestCase):
    def setUp(self):
        self.swarm = running_swarm()
        self.overlay = self.swarm.overlay

    def tearDown(self):
        self.swarm.shutdown()

    def top_picture(self):
        # Make sure nothing overlaps the one we click.
        picture = self.swarm.pictures[-1]
        for other in self.swarm.pictures[:-1]:
            other.body.move_to(-10_000, -10_000)
        picture.body.move_to(300, 400)
        return picture

    def test_clicking_the_close_button_closes_it_and_another_opens(self):
        picture = self.top_picture()

        QTest.mouseClick(self.overlay, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre(picture.close_rect()))

        self.assertTrue(picture.closing)
        self.assertEqual(self.swarm.open_count, 6)

    def test_alt_f4_closes_the_picture_last_clicked_not_the_layer(self):
        picture = self.top_picture()
        QTest.mouseClick(self.overlay, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre(picture.rect()))

        closed = self.overlay.close()

        self.assertFalse(closed)
        self.assertTrue(picture.closing)
        self.assertEqual(self.swarm.open_count, 6)

    def test_pressing_a_picture_grabs_it_and_brings_it_to_the_front(self):
        picture = self.swarm.pictures[0]
        for other in self.swarm.pictures[1:]:
            other.body.move_to(-10_000, -10_000)
        picture.body.move_to(300, 400)

        QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre(picture.rect()))
        self.assertTrue(picture.body.held)
        self.assertIs(self.swarm.pictures[-1], picture)

        QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre(picture.rect()))
        self.assertFalse(picture.body.held)

    def test_clicking_empty_space_does_nothing(self):
        for picture in self.swarm.pictures:
            picture.body.move_to(-10_000, -10_000)
        QTest.mouseClick(self.overlay, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(5, 5))
        self.assertEqual(self.swarm.open_count, 6)
        self.assertFalse(any(p.closing for p in self.swarm.pictures))


class VideoLockTest(unittest.TestCase):
    def test_not_closable_before_the_pictures_have_even_appeared(self):
        swarm = Swarm(SOURCES[:3], rng=random.Random(2))
        self.assertFalse(swarm.all_closed())
        swarm.start()
        self.assertFalse(swarm.all_closed(), "pictures are still queued")
        swarm.shutdown()

    def test_not_closable_while_pictures_are_open_and_closable_after(self):
        swarm = running_swarm(3)
        self.assertFalse(swarm.all_closed())
        swarm.shutdown()
        self.assertTrue(swarm.all_closed())

    def test_no_pictures_means_nothing_to_wait_for(self):
        self.assertTrue(Swarm([]).all_closed())

    def test_the_video_window_refuses_to_close_while_pictures_are_open(self):
        try:
            from wellbeing.video_window import VideoWindow
        except ImportError as error:  # pragma: no cover
            self.skipTest(f"QtMultimedia unavailable: {error}")
        swarm = running_swarm(3)
        video = VideoWindow(media.discover().video, muted=True, may_close=swarm.all_closed)

        self.assertFalse(video.close())
        self.assertIn("Nope", video.windowTitle())

        swarm.shutdown()
        self.assertTrue(video.close())


if __name__ == "__main__":
    unittest.main()
