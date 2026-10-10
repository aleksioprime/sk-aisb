"""Проверки консольной калибровки без подключения к моторам."""

import io
import unittest
from unittest.mock import call, patch

from tools import calibrate


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        # Не читать настоящие data/servo_calibration.json и umka.conf: на плате в
        # них могут быть выключены моторы, другие углы и каналы.
        for target, value in (("tools.calibrate.calibration.load", None),
                              ("tools.calibrate.launch_config.load", {})):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_session(self, commands, hardware_args=None, failure=None):
        with patch("tools.calibrate.create_hardware") as factory, \
                patch("builtins.input", side_effect=commands), \
                patch("sys.stdout", new_callable=io.StringIO):
            hardware = factory.return_value
            hardware.sort_to.side_effect = failure
            calibrate.main(hardware_args or [])
            return factory, hardware

    def test_sections_center_and_invalid_input(self):
        _, hardware = self.run_session(["bad", "1", "2", "3", "4", " c ", "q"])
        self.assertEqual(hardware.method_calls, [
            call.center(), call.sort_to("section_1"), call.sort_to("section_2"),
            call.sort_to("section_3"), call.sort_to("section_4"),
            call.center(), call.close(),
        ])

    def test_custom_connection_is_forwarded(self):
        factory, _ = self.run_session(["q"], [
            "--hardware", "pca9685", "--pca9685-address", "0x41",
            "--tilt-channel", "2", "--rotate-channel", "3", "--i2c-bus", "5",
        ])
        factory.assert_called_once_with("pca9685", 0, 0x41, 2, 3, 5)

    def test_bus_is_detected_when_not_given(self):
        factory, _ = self.run_session(["q"], ["--hardware", "pca9685"])
        factory.assert_called_once_with("pca9685", 0, 0x40, 1, 0, None)

    def test_eof_and_interrupt_release_hardware(self):
        for ending in (EOFError, KeyboardInterrupt):
            with self.subTest(ending=ending):
                _, hardware = self.run_session([ending])
                hardware.close.assert_called_once_with()
                hardware.sort_to.assert_not_called()

    def test_interrupt_during_motion_releases_hardware(self):
        _, hardware = self.run_session(["1"], failure=KeyboardInterrupt)
        hardware.close.assert_called_once_with()
        self.assertEqual(hardware.center.call_count, 1)

    def test_driver_error_releases_hardware(self):
        with patch("tools.calibrate.create_hardware") as factory, \
                patch("builtins.input", return_value="1"), \
                patch("sys.stdout", new_callable=io.StringIO):
            factory.return_value.sort_to.side_effect = RuntimeError("I2C error")
            with self.assertRaisesRegex(RuntimeError, "I2C error"):
                calibrate.main([])
            factory.return_value.close.assert_called_once_with()

    def test_invalid_connection_never_opens_hardware(self):
        for args in (["--tilt-channel", "0", "--rotate-channel", "0"],
                     ["--tilt-channel", "16"], ["--pca9685-address", "0x80"],
                     ["--i2c-bus", "-1"]):
            with self.subTest(args=args), \
                    patch("tools.calibrate.create_hardware") as factory, \
                    patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit):
                    calibrate.main(args)
                factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
