"""Проверки сохранённой калибровки моторов."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sorter import calibration, hardware

SECTIONS = {f"section_{n}": {"rotate": 90, "tilt": 90} for n in range(1, 5)}


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        for name in ("CENTER_TILT_ANGLE", "CENTER_ROTATE_ANGLE", "ACTIONS",
                     "MOTORS_ENABLED", "MOTORS_RELEASE_AT_REST"):
            patcher = patch.object(hardware, name, getattr(hardware, name))
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_old_file_without_release_keeps_motors_holding(self):
        data = calibration.validate({"center": {"tilt": 97, "rotate": 80}, "sections": SECTIONS,
                                     "enabled": {"tilt": False}})
        self.assertEqual(data["enabled"], {"tilt": False, "rotate": True})
        self.assertEqual(data["release"], {"tilt": False, "rotate": False})

    def test_release_is_saved_and_applied(self):
        path = Path(tempfile.mkdtemp()) / "servo_calibration.json"
        calibration.save(path, {"center": {"tilt": 89, "rotate": 90}, "sections": SECTIONS,
                                "release": {"rotate": True}})
        self.assertEqual(hardware.MOTORS_RELEASE_AT_REST, {"tilt": False, "rotate": True})
        self.assertEqual(json.loads(path.read_text())["release"], {"tilt": False, "rotate": True})
        self.assertEqual(calibration.snapshot()["release"], {"tilt": False, "rotate": True})


if __name__ == "__main__":
    unittest.main()
