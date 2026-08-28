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


def create_hardware(driver: str, simulate_delay: float):
    """Создать выбранный драйвер механизма.

    Неизвестные значения заранее отклоняются в ``AppConfig.validate()``, поэтому
    здесь безопасным значением по умолчанию остаётся консольная имитация.
    """
    if driver == "gpiozero":
        return GpioZeroHardware()
    return ConsoleHardware(simulate_delay)
