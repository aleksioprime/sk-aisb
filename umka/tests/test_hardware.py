"""Тесты выбора аппаратного драйвера без Raspberry Pi."""

import unittest
from unittest.mock import patch

from sorter.hardware import ConsoleHardware, create_hardware


class HardwareFactoryTests(unittest.TestCase):
    def test_console_driver(self):
        self.assertIsInstance(create_hardware("console", 0), ConsoleHardware)

    @patch("sorter.hardware.Pca9685Hardware")
    def test_pca9685_settings_are_forwarded(self, driver):
        create_hardware("pca9685", 0, 0x41, 2, 3)
        driver.assert_called_once_with(0x41, 2, 3)

    @patch("sorter.hardware.GpioZeroHardware")
    def test_gpiozero_option_remains_available(self, driver):
        create_hardware("gpiozero", 0)
        driver.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
