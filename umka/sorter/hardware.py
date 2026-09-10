"""Драйверы реального механизма и безопасной консольной имитации."""

from __future__ import annotations

import logging
import time


LOG = logging.getLogger(__name__)


class ConsoleHardware:
    """Имитировать механизм сообщениями в журнале, не обращаясь к GPIO."""

    def __init__(self, delay: float = 1.0):
        self.delay = delay

    def center(self) -> None:
        """Вывести сообщение об имитации возврата механизма в центр."""
        LOG.info("[ИМИТАЦИЯ] Центрирование механизма")

    def sort_to(self, section: str) -> None:
        """Имитировать сортировку в секцию с небольшой задержкой."""
        LOG.info("[ИМИТАЦИЯ] Сортировка → %s", section)
        time.sleep(self.delay)
        LOG.info("[ИМИТАЦИЯ] Сортировка завершена → %s", section)

    def close(self) -> None:
        """Завершить драйвер; консольный режим не содержит ресурсов."""
        pass


class GpioZeroHardware:
    """Управлять двумя сервоприводами через gpiozero и backend lgpio.

    GPIO 12 наклоняет площадку, GPIO 13 поворачивает распределитель. Углы в
    ``ACTIONS`` являются калибровочными и должны проверяться на реальной механике.
    """

    ACTIONS = {
        "section_1": {"rotate": 160, "tilt": 70},
        "section_2": {"rotate": 20, "tilt": 70},
        "section_3": {"rotate": 160, "tilt": 140},
        "section_4": {"rotate": 20, "tilt": 140},
    }

    def __init__(self):
        """Создать сервоприводы и сразу привести механизм в нейтральное положение."""
        import os
        os.environ.setdefault("GPIOZERO_PIN_FACTORY", "lgpio")
        try:
            from gpiozero import AngularServo
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Драйвер gpiozero недоступен внутри .venv. Установите системные "
                "пакеты python3-gpiozero и python3-lgpio, затем выполните: "
                "python3 -m venv --upgrade --system-site-packages .venv"
            ) from exc

        options = dict(min_angle=0, max_angle=180, min_pulse_width=0.0005,
                       max_pulse_width=0.0025, frame_width=0.02)
        self.tilt = AngularServo(12, **options)
        self.rotate = AngularServo(13, **options)
        self.center()

    @staticmethod
    def _move(servo, angle: float) -> None:
        """Ограничить угол безопасным диапазоном и дождаться движения."""
        servo.angle = max(0, min(180, angle))
        time.sleep(0.7)

    def center(self) -> None:
        """Вернуть наклон и поворот в нейтральные положения."""
        self._move(self.tilt, 95)
        self._move(self.rotate, 90)

    def sort_to(self, section: str) -> None:
        """Повернуть распределитель, сбросить предмет и вернуться в центр."""
        action = self.ACTIONS[section]
        self._move(self.rotate, action["rotate"])
        self._move(self.tilt, action["tilt"])
        time.sleep(0.5)
        self.center()

    def close(self) -> None:
        """Освободить GPIO-ресурсы обоих сервоприводов."""
        self.tilt.close()
        self.rotate.close()


class Pca9685Hardware:
    """Управлять сервоприводами через I2C-драйвер PCA9685.

    Канал 1 наклоняет площадку, канал 0 поворачивает распределитель. Таблица
    действий совпадает с GPIO-вариантом, поэтому калибровку механики достаточно
    менять в одном месте.
    """

    ACTIONS = GpioZeroHardware.ACTIONS

    def __init__(
        self,
        address: int = 0x40,
        tilt_channel: int = 1,
        rotate_channel: int = 0,
    ):
        """Открыть PCA9685 и настроить диапазон импульсов сервоприводов."""
        try:
            from adafruit_servokit import ServoKit
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Драйвер PCA9685 недоступен. Установите пакет "
                "adafruit-circuitpython-servokit и включите I2C."
            ) from exc

        self.kit = ServoKit(channels=16, address=address)
        self.tilt = self.kit.servo[tilt_channel]
        self.rotate = self.kit.servo[rotate_channel]
        for servo in (self.tilt, self.rotate):
            servo.set_pulse_width_range(500, 2500)

    @staticmethod
    def _move(servo, angle: float) -> None:
        """Ограничить угол безопасным диапазоном и дождаться движения."""
        servo.angle = max(0, min(180, angle))
        time.sleep(0.7)

    def center(self) -> None:
        """Вернуть наклон и поворот в нейтральные положения."""
        self._move(self.tilt, 95)
        self._move(self.rotate, 90)

    def sort_to(self, section: str) -> None:
        """Повернуть распределитель, сбросить предмет и вернуться в центр."""
        action = self.ACTIONS[section]
        self._move(self.rotate, action["rotate"])
        self._move(self.tilt, action["tilt"])
        time.sleep(0.5)
        self.center()

    def close(self) -> None:
        """Отключить PWM на обоих каналах и освободить I2C-ресурсы."""
        self.tilt.angle = None
        self.rotate.angle = None
        pca = getattr(self.kit, "_pca", None)
        if pca is not None and hasattr(pca, "deinit"):
            pca.deinit()


def create_hardware(
    driver: str,
    simulate_delay: float,
    pca9685_address: int = 0x40,
    tilt_channel: int = 1,
    rotate_channel: int = 0,
):
    """Создать выбранный драйвер механизма.

    Неизвестные значения заранее отклоняются в ``AppConfig.validate()``, поэтому
    здесь безопасным значением по умолчанию остаётся консольная имитация.
    """
    if driver == "gpiozero":
        return GpioZeroHardware()
    if driver == "pca9685":
        return Pca9685Hardware(pca9685_address, tilt_channel, rotate_channel)
    return ConsoleHardware(simulate_delay)
