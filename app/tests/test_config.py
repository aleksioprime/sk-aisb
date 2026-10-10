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

    def test_pca9685_is_supported(self):
        config = AppConfig(hardware_driver="pca9685")
        config.validate()

    def test_pca9685_channels_must_be_different(self):
        config = AppConfig(tilt_servo_channel=1, rotate_servo_channel=1)
        with self.assertRaisesRegex(ValueError, "разные каналы"):
            config.validate()


if __name__ == "__main__":
    unittest.main()
