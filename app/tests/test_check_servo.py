"""Проверки утилиты tools/check_servo.py без PCA9685."""

import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools import check_servo


class RecordingServo:
    """Запоминать все команды угла, включая снятие сигнала (None)."""

    def __init__(self):
        self.history = []
        self.set_pulse_width_range = Mock()

    @property
    def angle(self):
        return self.history[-1] if self.history else None

    @angle.setter
    def angle(self, value):
        self.history.append(value)


class CheckServoTests(unittest.TestCase):
    def run_session(self, commands, args):
        servo = RecordingServo()
        kit = SimpleNamespace(servo={channel: RecordingServo() for channel in range(16)})
        kit.servo[3] = servo
        i2c = Mock()
        with patch("tools.check_servo.launch_config.load", return_value={}), \
                patch("tools.check_servo.open_pca9685", return_value=(kit, i2c)) as opened, \
                patch("tools.check_servo.time.sleep"), \
                patch("builtins.input", side_effect=commands), \
                patch("sys.stdout", new_callable=io.StringIO):
            check_servo.main(["--channel", "3", *args])
        return servo, i2c, opened

    def test_angles_are_limited_and_signal_released(self):
        servo, i2c, opened = self.run_session(["90", "170", "5", "off", "bad", "q"], ["--min", "20", "--max", "150"])
        self.assertEqual(servo.history, [90, 150, 20, None, None])
        servo.set_pulse_width_range.assert_called_once_with(500, 2500)
        opened.assert_called_once_with(0x40, None)
        i2c.deinit.assert_called_once_with()

    def test_sweep_stays_inside_range_and_returns(self):
        servo, _, _ = self.run_session(["s", "q"], ["--min", "80", "--max", "100"])
        moves = [angle for angle in servo.history if angle is not None]
        self.assertEqual((min(moves), max(moves)), (80, 100))
        self.assertEqual(servo.history[-2:], [90, None])

    def test_interrupt_still_releases_signal(self):
        servo, i2c, _ = self.run_session(["120", KeyboardInterrupt()], [])
        self.assertEqual(servo.history, [120, None])
        i2c.deinit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
