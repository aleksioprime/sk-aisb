"""Тесты выбора аппаратного драйвера без Raspberry Pi."""

import unittest
import warnings
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from sorter.hardware import (
    ConsoleHardware, GpioZeroHardware, Pca9685Hardware, create_hardware,
    _is_orange_pi_5, _resolve_i2c_bus,
)


class BoardDetectionTests(unittest.TestCase):
    def test_orange_pi_5_and_5b_select_bus_five(self):
        for model, expected in (
            # Образы Orange Pi 5B встречаются с обоими именами платы.
            ("Orange Pi 5B\x00", True),
            ("Orange Pi 5\x00", True),
            ("Xunlong OrangePi 5B\x00", True),
            ("BOARD=orangepi5b\nBOARD_NAME=\"Orange Pi 5B\"\n", True),
            ("BOARD=orangepi5\n", True),
            ("Raspberry Pi 5 Model B Rev 1.0\x00", False),
            ("Orange Pi 5 Plus\x00", False),
            ("BOARD=orangepi5-plus\n", False),
            ("Orange Pi 5 Max\x00", False),
            ("Orange Pi 5 Pro\x00", False),
            ("Orange Pi 3B\x00", False),
        ):
            with self.subTest(model=model), \
                    patch("sorter.hardware.Path.read_text", return_value=model):
                self.assertEqual(_is_orange_pi_5(), expected)

    @patch("sorter.hardware.Path.read_text", side_effect=FileNotFoundError)
    def test_missing_device_tree_keeps_default_bus(self, _read):
        self.assertFalse(_is_orange_pi_5())

    @patch("sorter.hardware.Path.read_text", side_effect=PermissionError)
    def test_unreadable_device_tree_keeps_default_bus(self, _read):
        self.assertFalse(_is_orange_pi_5())

    @patch("sorter.hardware.Path.read_text", return_value="Raspberry Pi 5\x00")
    def test_explicit_bus_wins_over_detection(self, _read):
        self.assertEqual(_resolve_i2c_bus(5), 5)
        self.assertIsNone(_resolve_i2c_bus(None))

    @patch("sorter.hardware.Path.read_text", return_value="Orange Pi 5\x00")
    def test_explicit_bus_overrides_orange_pi_default(self, _read):
        self.assertEqual(_resolve_i2c_bus(3), 3)
        self.assertEqual(_resolve_i2c_bus(None), 5)


class Pca9685ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.kit = Mock()
        self.kit.servo = {channel: Mock() for channel in range(16)}
        self.servo_kit = Mock(return_value=self.kit)
        self.i2c = Mock()
        self.extended_i2c = Mock(return_value=self.i2c)
        modules = patch.dict("sys.modules", {
            "adafruit_servokit": SimpleNamespace(ServoKit=self.servo_kit),
            "adafruit_extended_bus": SimpleNamespace(ExtendedI2C=self.extended_i2c),
        })
        modules.start()
        self.addCleanup(modules.stop)
        # На компьютере разработчика /dev/i2c-N нет: проверка наличия шины
        # отключается, отдельный тест ниже проверяет её сам.
        device = patch("sorter.hardware.Path.exists", return_value=True)
        device.start()
        self.addCleanup(device.stop)

    @patch("sorter.hardware.Path.read_text", return_value="Orange Pi 5B\x00")
    def test_orange_pi_uses_i2c5_and_preserves_address_and_channels(self, _read):
        hardware = create_hardware("pca9685", 0, 0x41, 2, 3)
        self.extended_i2c.assert_called_once_with(5)
        self.servo_kit.assert_called_once_with(channels=16, address=0x41, i2c=self.i2c)
        self.assertIs(hardware.tilt, self.kit.servo[2])
        self.assertIs(hardware.rotate, self.kit.servo[3])
        for channel in (2, 3):
            self.kit.servo[channel].set_pulse_width_range.assert_called_once_with(500, 2500)
        hardware.close()
        self.assertIsNone(self.kit.servo[2].angle)
        self.assertIsNone(self.kit.servo[3].angle)
        self.kit._pca.deinit.assert_called_once_with()
        self.i2c.deinit.assert_called_once_with()

    @patch("sorter.hardware.Path.read_text", return_value="Raspberry Pi 5 Model B\x00")
    def test_raspberry_pi_keeps_servokit_default_bus(self, _read):
        hardware = Pca9685Hardware()
        self.servo_kit.assert_called_once_with(channels=16, address=0x40)
        self.extended_i2c.assert_not_called()
        hardware.close()
        self.i2c.deinit.assert_not_called()

    @patch("sorter.hardware.Path.read_text", return_value="Unknown board\x00")
    def test_explicit_bus_opens_requested_device(self, _read):
        Pca9685Hardware(i2c_bus=3)
        self.extended_i2c.assert_called_once_with(3)
        self.servo_kit.assert_called_once_with(channels=16, address=0x40, i2c=self.i2c)

    @patch("sorter.hardware.Path.read_text", return_value="Orange Pi 5\x00")
    def test_frequency_warning_is_hidden_but_others_are_kept(self, _read):
        def open_bus(bus):
            warnings.warn("I2C frequency is not settable in python, ignoring!",
                          RuntimeWarning)
            warnings.warn("шина перегружена", RuntimeWarning)
            return self.i2c

        self.extended_i2c.side_effect = open_bus
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            Pca9685Hardware()
        self.assertEqual([str(item.message) for item in caught],
                         ["шина перегружена"])

    @patch("sorter.hardware.Path.exists", return_value=False)
    @patch("sorter.hardware.Path.read_text", return_value="Orange Pi 5\x00")
    def test_disabled_overlay_names_the_missing_bus(self, _read, _exists):
        with self.assertRaisesRegex(RuntimeError, "/dev/i2c-5"):
            Pca9685Hardware()
        self.extended_i2c.assert_not_called()
        self.servo_kit.assert_not_called()

    @patch("sorter.hardware.Path.read_text", return_value="Unknown board\x00")
    def test_unknown_board_explains_how_to_set_bus(self, _read):
        self.servo_kit.side_effect = ValueError("No Hardware I2C on (scl,sda)")
        with self.assertRaisesRegex(RuntimeError, "--i2c-bus"):
            Pca9685Hardware()
        self.extended_i2c.assert_not_called()

    @patch("sorter.hardware.Path.read_text", return_value="Orange Pi 5B\x00")
    def test_missing_pca9685_releases_opened_bus(self, _read):
        self.servo_kit.side_effect = OSError("PCA9685 not responding")
        with self.assertRaisesRegex(OSError, "not responding"):
            Pca9685Hardware()
        self.i2c.deinit.assert_called_once_with()

    @patch("sorter.hardware.Path.read_text", return_value="Orange Pi 5B\x00")
    def test_bus_is_released_even_when_pwm_shutdown_fails(self, _read):
        hardware = Pca9685Hardware()
        self.kit._pca.deinit.side_effect = OSError("I2C disconnected")
        with self.assertRaisesRegex(OSError, "disconnected"):
            hardware.close()
        self.i2c.deinit.assert_called_once_with()


class HardwareFactoryTests(unittest.TestCase):
    def test_console_driver(self):
        self.assertIsInstance(create_hardware("console", 0), ConsoleHardware)

    @patch("sorter.hardware.Pca9685Hardware")
    def test_pca9685_settings_are_forwarded(self, driver):
        create_hardware("pca9685", 0, 0x41, 2, 3, 5)
        driver.assert_called_once_with(0x41, 2, 3, 5)

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
