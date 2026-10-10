"""Проверки области распознавания без камеры."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from sorter.config import AppConfig
from sorter.crop import CropArea


class FakeFrame:
    """Минимальная замена кадра numpy: нужны только shape и срез."""

    def __init__(self, width, height):
        self.shape = (height, width, 3)

    def __getitem__(self, key):
        return key


class CropAreaTests(unittest.TestCase):
    def make(self, **margins):
        directory = Path(tempfile.mkdtemp())
        config = replace(AppConfig(), crop_path=directory / "crop.json",
                         **{f"crop_{side}": value for side, value in margins.items()})
        return CropArea(config)

    def test_defaults_come_from_config(self):
        crop = self.make(top=40, bottom=85, left=100, right=66)
        self.assertEqual(crop.rect(FakeFrame(640, 480)), (100, 40, 574, 395))
        self.assertEqual(crop.snapshot()["frameWidth"], 640)

    def test_saved_margins_apply_now_and_after_restart(self):
        crop = self.make(top=0, bottom=0, left=0, right=0)
        crop.save({"top": 10, "bottom": 20, "left": 30, "right": 40})
        self.assertEqual(crop.rect(FakeFrame(640, 480)), (30, 10, 600, 460))
        reloaded = CropArea(replace(AppConfig(), crop_path=crop.path))
        self.assertEqual(reloaded.rect(FakeFrame(640, 480)), (30, 10, 600, 460))

    def test_area_never_becomes_empty(self):
        crop = self.make(top=500, bottom=500, left=700, right=700)
        left, top, right, bottom = crop.rect(FakeFrame(640, 480))
        self.assertLess(left, right)
        self.assertLess(top, bottom)

    def test_invalid_margins_are_rejected(self):
        crop = self.make(top=0, bottom=0, left=0, right=0)
        for bad in ({"top": -1, "bottom": 0, "left": 0, "right": 0},
                    {"top": "1", "bottom": 0, "left": 0, "right": 0},
                    {"top": 1, "bottom": 0, "left": 0}):
            with self.subTest(bad=bad), self.assertRaises((ValueError, KeyError)):
                crop.save(bad)
        self.assertFalse(crop.path.exists())


if __name__ == "__main__":
    unittest.main()
