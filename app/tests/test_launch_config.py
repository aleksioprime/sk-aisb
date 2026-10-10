"""Проверки чтения umka.conf."""

import tempfile
import unittest
from pathlib import Path

from sorter import launch_config


class LaunchConfigTests(unittest.TestCase):
    def write(self, text):
        path = Path(tempfile.mkdtemp()) / "umka.conf"
        path.write_text(text, encoding="utf-8")
        return path

    def test_missing_file_gives_no_overrides(self):
        self.assertEqual(launch_config.load(Path(tempfile.mkdtemp()) / "umka.conf"), {})

    def test_values_comments_and_types(self):
        path = self.write(
            "# устройство на выставке\n"
            "hardware = pca9685\n"
            "tilt_channel = 0   # моторы перепутаны при сборке\n"
            "rotate_channel=1\n"
            "pca9685_address = 0x41\n"
            "\n"
            "# i2c_bus = 5\n"
        )
        self.assertEqual(launch_config.load(path), {
            "hardware": "pca9685", "tilt_channel": 0, "rotate_channel": 1, "pca9685_address": 0x41,
        })

    def test_bad_lines_are_skipped(self):
        path = self.write("unknown = 1\ncamera = two\nnot a setting\ncamera = 2\n")
        with self.assertLogs("sorter.launch_config", "WARNING"):
            self.assertEqual(launch_config.load(path), {"camera": 2})


if __name__ == "__main__":
    unittest.main()
