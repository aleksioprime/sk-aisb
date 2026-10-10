"""Проверки фильтра пустой площадки; нужны numpy и OpenCV (есть на плате)."""

import tempfile
import unittest
from pathlib import Path

try:
    import cv2  # noqa: F401
    import numpy as np
except ModuleNotFoundError:  # На ПК без OpenCV тесты пропускаются.
    np = None

from sorter.background import EmptyPlatformFilter


@unittest.skipIf(np is None, "нужны numpy и OpenCV")
class EmptyPlatformFilterTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp()) / "refs"
        self.box = (100, 100, 200, 200)

    @staticmethod
    def frame(brightness, spot=None):
        image = np.full((480, 640, 3), brightness, np.uint8)
        if spot is not None:
            image[120:180, 120:180] = spot
        return image

    def capture(self, platform, frame):
        platform.request_capture()
        self.assertTrue(platform.capture_if_requested(frame))

    def test_without_references_everything_passes(self):
        platform = EmptyPlatformFilter(self.directory, 18)
        self.assertIsNone(platform.difference(self.frame(100), self.box))
        self.assertFalse(platform.is_empty(self.frame(100), self.box))

    def test_any_matching_reference_rejects(self):
        platform = EmptyPlatformFilter(self.directory, 18)
        self.capture(platform, self.frame(100))
        glare = self.frame(100, spot=250)
        self.assertFalse(platform.is_empty(glare, self.box))
        self.capture(platform, glare)
        self.assertTrue(platform.is_empty(glare, self.box))
        self.assertTrue(platform.is_empty(self.frame(100), self.box))
        self.assertFalse(platform.is_empty(self.frame(100, spot=0), self.box))

    def test_references_survive_restart_and_can_be_deleted(self):
        platform = EmptyPlatformFilter(self.directory, 18)
        self.capture(platform, self.frame(100))
        self.capture(platform, self.frame(150))
        reloaded = EmptyPlatformFilter(self.directory, 18)
        self.assertEqual(reloaded.count, 2)
        self.assertTrue(reloaded.thumbnail(reloaded.items()[0]["id"]).startswith(b"\xff\xd8"))
        reloaded.delete(reloaded.items()[0]["id"])
        self.assertEqual(EmptyPlatformFilter(self.directory, 18).count, 1)
        reloaded.clear()
        self.assertEqual(EmptyPlatformFilter(self.directory, 18).count, 0)

    def test_oldest_reference_is_dropped_over_limit(self):
        platform = EmptyPlatformFilter(self.directory, 18)
        platform.MAX_REFERENCES = 2
        for brightness in (10, 20, 30):
            self.capture(platform, self.frame(brightness))
        self.assertEqual(platform.count, 2)
        self.assertEqual(len(list(self.directory.glob("*.png"))), 2)

    def test_legacy_single_reference_is_migrated(self):
        legacy = self.directory.parent / "empty_platform.png"
        cv2.imwrite(str(legacy), self.frame(100)[:, :, 0])
        platform = EmptyPlatformFilter(self.directory, 18, legacy_path=legacy)
        self.assertFalse(legacy.exists())
        self.assertEqual(platform.count, 1)
        self.assertTrue(platform.is_empty(self.frame(100), self.box))


if __name__ == "__main__":
    unittest.main()
