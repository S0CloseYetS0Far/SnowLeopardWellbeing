import tempfile
import unittest
from pathlib import Path

from wellbeing import media


class FindMediaTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def touch(self, name):
        path = self.dir / name
        path.write_bytes(b"")
        return path

    def test_pictures_are_found_by_extension_in_any_case(self):
        for name in ("b.JPEG", "a.jpg", "c.png", "notes.txt", "clip.mp4"):
            self.touch(name)
        (self.dir / "folder.jpg").mkdir()

        names = [p.name for p in media.find_pictures(self.dir)]

        self.assertEqual(names, ["a.jpg", "b.JPEG", "c.png"])

    def test_missing_folder_has_no_pictures(self):
        self.assertEqual(media.find_pictures(self.dir / "nope"), [])

    def test_first_folder_with_a_video_wins(self):
        other = self.dir / "other"
        other.mkdir()
        (other / "later.mp4").write_bytes(b"")
        self.touch("picture.jpeg")

        self.assertEqual(media.find_video(self.dir, other), other / "later.mp4")
        self.assertIsNone(media.find_video(self.dir / "nope"))


class ProjectMediaTest(unittest.TestCase):
    """The media that ships in this repository."""

    def test_all_snow_leopard_pictures_and_the_video_are_found(self):
        found = media.discover()

        self.assertEqual(len(found.pictures), 53)
        self.assertIsNotNone(found.video)
        self.assertEqual(found.video.name, "Download (1).mp4")


if __name__ == "__main__":
    unittest.main()
