"""Проверки сбора датасета; нужны numpy и OpenCV (есть на плате)."""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

try:
    import cv2  # noqa: F401
    import numpy as np
except ModuleNotFoundError:  # На ПК без OpenCV тесты пропускаются.
    np = None

from sorter.dataset import DatasetCollector


@unittest.skipIf(np is None, "нужны numpy и OpenCV")
class DatasetCollectorTests(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.collector = DatasetCollector(root / "dataset", root / "dataset.json")
        self.collector.class_names = ["hand", "organic", "paper", "plastic"]
        self.frame = np.full((480, 640, 3), 120, np.uint8)

    def test_nothing_is_saved_while_disabled(self):
        self.collector.record_decision("e1", self.frame, (100, 100, 200, 300), 3, "plastic", 0.9)
        self.assertEqual(self.collector.snapshot()["counts"]["unverified"], 0)

    def test_decision_label_and_feedback_groups(self):
        self.collector.save_settings({"enabled": True})
        self.collector.record_decision("e1", self.frame, (100, 100, 200, 300), 3, "plastic", 0.9)
        self.collector.record_decision("e2", self.frame, (0, 0, 640, 480), 2, "paper", 0.8)
        label = (self.collector.directory / "unverified" / "e1.txt").read_text()
        self.assertEqual(label, "3 0.234375 0.416667 0.156250 0.416667\n")
        self.collector.record_feedback("e1", "yes")
        self.collector.record_feedback("e2", "no")
        self.collector.record_feedback("missing", "yes")
        counts = self.collector.snapshot()["counts"]
        self.assertEqual((counts["confirmed"], counts["rejected"], counts["unverified"]), (1, 1, 0))
        self.assertTrue((self.collector.directory / "confirmed" / "e1.json").is_file())

    def test_background_is_rate_limited_and_unlabelled(self):
        self.collector.save_settings({"enabled": True})
        self.collector.record_background(self.frame, "plastic", 0.8)
        self.collector.record_background(self.frame, "plastic", 0.8)
        files = list((self.collector.directory / "background").glob("*.txt"))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_text(), "")

    def test_limit_removes_oldest_frames(self):
        self.collector.save_settings({"enabled": True, "limitMb": 100})
        noisy = np.random.default_rng(1).integers(0, 255, (480, 640, 3), dtype=np.uint8)
        with patch.object(DatasetCollector, "_enforce_limit"):
            for index in range(3):
                self.collector.record_decision(f"e{index}", noisy, (0, 0, 10, 10), 0, "hand", 0.5)
        size = self.collector.snapshot()["sizeMb"]
        self.collector.settings["limitMb"] = size * 0.5  # Лимит меньше набора.
        self.collector._enforce_limit()
        left = sorted(path.stem for path in (self.collector.directory / "unverified").glob("*.jpg"))
        self.assertLess(len(left), 3)
        self.assertIn("e2", left, "новые кадры остаются")

    def test_export_contains_yolo_layout(self):
        self.collector.save_settings({"enabled": True})
        self.collector.record_decision("e1", self.frame, (100, 100, 200, 300), 3, "plastic", 0.9)
        self.collector.record_feedback("e1", "yes")
        path = self.collector.export()
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            self.assertIn("confirmed/images/e1.jpg", names)
            self.assertIn("confirmed/labels/e1.txt", names)
            self.assertIn("3: plastic", archive.read("data.yaml").decode())
        path.unlink()

    def test_invalid_settings_rejected(self):
        for bad in ({"enabled": "yes"}, {"limitMb": 10}, {"limitMb": True}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.collector.save_settings(bad)
        self.assertEqual(json.loads(json.dumps(self.collector.settings)), {"enabled": False, "limitMb": 2000})


if __name__ == "__main__":
    unittest.main()
