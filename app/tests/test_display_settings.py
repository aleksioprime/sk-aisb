"""Проверки настроек главного экрана."""

import json
import tempfile
import unittest
from pathlib import Path

from sorter.display_settings import DEFAULTS, DisplaySettings


class DisplaySettingsTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "display.json"

    def test_defaults_without_file(self):
        self.assertEqual(DisplaySettings(self.path).values, DEFAULTS)

    def test_partial_change_is_saved_and_reloaded(self):
        DisplaySettings(self.path).save({"confirm": False})
        reloaded = DisplaySettings(self.path)
        self.assertEqual(reloaded.values, {"confirm": False, "resultSeconds": 5})
        reloaded.save({"resultSeconds": 8})
        self.assertEqual(json.loads(self.path.read_text()), {"confirm": False, "resultSeconds": 8})

    def test_invalid_values_are_rejected(self):
        settings = DisplaySettings(self.path)
        for bad in ({"confirm": "no"}, {"resultSeconds": 1}, {"resultSeconds": 31}, {"resultSeconds": True}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                settings.save(bad)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
