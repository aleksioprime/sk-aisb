"""Проверки разбора и сохранения параметров камеры без устройства."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sorter.camera_controls import CameraControls, parse_controls


# Вывод v4l2-ctl --list-ctrls-menus для камеры GEMBIRD (AppoTech AX2311).
SAMPLE = """
User Controls

                     brightness 0x00980900 (int)    : min=0 max=255 step=1 default=137 value=120
                            hue 0x00980903 (int)    : min=-127 max=127 step=1 default=0 value=0
           power_line_frequency 0x00980918 (menu)   : min=0 max=2 default=1 value=1 (50 Hz)
\t\t\t\t0: Disabled
\t\t\t\t1: 50 Hz
\t\t\t\t2: 60 Hz
                   white_balance_automatic 0x0098090c (bool)   : default=1 value=1
                      exposure_time_absolute 0x009a0902 (int)    : min=1 max=5000 step=1 default=157 value=157 flags=inactive
"""


class ParseControlsTests(unittest.TestCase):
    def test_int_menu_bool_and_inactive(self):
        controls = {item["name"]: item for item in parse_controls(SAMPLE)}
        self.assertEqual(controls["brightness"]["value"], 120)
        self.assertEqual(controls["brightness"]["default"], 137)
        self.assertEqual(controls["hue"]["min"], -127)
        self.assertEqual(controls["power_line_frequency"]["menu"],
                         {"0": "Disabled", "1": "50 Hz", "2": "60 Hz"})
        self.assertEqual(controls["white_balance_automatic"]["type"], "bool")
        self.assertTrue(controls["exposure_time_absolute"]["inactive"])
        self.assertFalse(controls["brightness"]["inactive"])


class CameraControlsTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "camera.json"

    def test_set_validates_saves_and_reapplies(self):
        controls = CameraControls(self.path)
        controls.device = "/dev/video0"
        with patch.object(CameraControls, "_run", return_value=SAMPLE) as run:
            controls.set("brightness", 100)
            self.assertIn(("-d", "/dev/video0", "-c", "brightness=100"), [c.args for c in run.call_args_list])
            with self.assertRaises(ValueError):
                controls.set("brightness", 300)
            with self.assertRaises(ValueError):
                controls.set("zoom", 1)
        self.assertEqual(json.loads(self.path.read_text()), {"brightness": 100})

        reloaded = CameraControls(self.path)
        with patch.object(CameraControls, "_run", return_value="") as run:
            reloaded.apply_saved("/dev/video2")
        run.assert_called_once_with("-d", "/dev/video2", "-c", "brightness=100")


if __name__ == "__main__":
    unittest.main()
