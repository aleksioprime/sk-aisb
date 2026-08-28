"""Тесты нормализации классов и безопасных значений конфигурации."""

import unittest

from sorter.config import AppConfig


class ConfigTests(unittest.TestCase):
    """Проверки правил обработки имён классов YOLO."""

    def test_normalizes_legacy_papper_class(self):
        self.assertEqual(AppConfig().normalize_class("PAPPER"), "paper")

    def test_empty_and_hand_are_ignored(self):
        config = AppConfig()
        self.assertIn("empty", config.ignored_classes)
        self.assertIn("hand", config.ignored_classes)


if __name__ == "__main__":
    unittest.main()
