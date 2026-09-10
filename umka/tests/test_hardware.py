"""Тесты выбора аппаратного драйвера без Raspberry Pi."""

import unittest
from unittest.mock import Mock, call, patch

from sorter.hardware import ConsoleHardware, GpioZeroHardware, Pca9685Hardware, create_hardware


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


class SharedCalibrationTests(unittest.TestCase):
    @patch("sorter.hardware.time.sleep")
    def test_both_drivers_use_shared_angles_for_drop_and_return(self, _sleep):
        # Подменяем калибровку, чтобы обнаружить углы, зашитые в одном из драйверов.
        with patch("sorter.hardware.CENTER_TILT_ANGLE", 82), \
                patch("sorter.hardware.CENTER_ROTATE_ANGLE", 47), \
                patch("sorter.hardware.ACTIONS", {
                    "section_1": {"rotate": 155, "tilt": 65},
                }):
            for driver_type in (GpioZeroHardware, Pca9685Hardware):
                with self.subTest(driver=driver_type.__name__):
                    driver = object.__new__(driver_type)
                    driver.tilt = object()
                    driver.rotate = object()
                    driver._move = Mock()
                    driver.sort_to("section_1")
                    self.assertEqual(driver._move.call_args_list, [
                        call(driver.rotate, 155), call(driver.tilt, 65),
                        call(driver.tilt, 82), call(driver.rotate, 47),
                    ])


if __name__ == "__main__":
    unittest.main()
