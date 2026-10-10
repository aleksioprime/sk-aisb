"""Проверки разбора xrandr и удержания режима дисплея."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sorter.screen import ScreenManager, parse_xrandr

# Вывод xrandr на Orange Pi 5B с дисплеем 1024×600 сразу после подключения.
XRANDR = """Screen 0: minimum 320 x 200, current 1024 x 600, maximum 16384 x 16384
HDMI-1 connected 1024x600+0+0 (normal left inverted right x axis y axis) 0mm x 0mm
   1024x600      59.82*+
   1920x1080     60.00    50.00    50.00    59.94
   1280x720      60.00    50.00    50.00    59.94
DP-1 disconnected (normal left inverted right x axis y axis)
"""


class ScreenTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "screen.json"

    def test_parse_outputs_modes_current_preferred(self):
        hdmi, dp = parse_xrandr(XRANDR)
        self.assertEqual((hdmi["name"], hdmi["connected"], dp["connected"]), ("HDMI-1", True, False))
        self.assertEqual(hdmi["modes"], ["1024x600", "1920x1080", "1280x720"])
        self.assertEqual((hdmi["current"], hdmi["preferred"]), ("1024x600", "1024x600"))

    def test_saved_mode_is_restored_after_replug(self):
        calls = []

        def fake(self, *args):
            calls.append(args)
            return XRANDR

        with patch.object(ScreenManager, "_xrandr", fake):
            screen = ScreenManager(self.path)
            screen.set_mode("1280x720")
            self.assertIn(("--output", "HDMI-1", "--mode", "1280x720"), calls)
            calls.clear()
            ScreenManager(self.path).keep()  # После перезапуска режим берётся из файла.
            self.assertIn(("--output", "HDMI-1", "--mode", "1280x720"), calls)
            with self.assertRaises(ValueError):
                screen.set_mode("800x480")
            calls.clear()
            screen.set_mode(None)
            screen.keep()
            self.assertNotIn(("--output", "HDMI-1", "--mode", "1280x720"), calls)


if __name__ == "__main__":
    unittest.main()
