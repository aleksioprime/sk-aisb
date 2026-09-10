"""Драйверы реального механизма и безопасной консольной имитации."""

from __future__ import annotations

import logging
import time


LOG = logging.getLogger(__name__)

# Общая калибровка для GPIO, PCA9685 и calibrate.py.
# Здесь задаются абсолютные углы сервоприводов в градусах (0–180), а не смещения.
# После редактирования перезапустите UMKA или calibrate.py.
CENTER_TILT_ANGLE = 97  # Нейтральный наклон площадки перед следующим поворотом.
CENTER_ROTATE_ANGLE = 80  # Исходное положение поворота распределителя.

# Углы сброса по физическим отсекам; номер проверяется командой 1–4 в calibrate.py.
# rotate — сначала повернуть к отсеку; tilt — затем наклонить площадку для сброса.
# После сброса оба мотора возвращаются к CENTER_*_ANGLE.
# Какой класс попадает в отсек, задаёт AppConfig.class_to_section в config.py.
# Названия секций сами по себе не обозначают «слева» или «справа».
ACTIONS = {
    "section_1": {"rotate": 160, "tilt": 50},
    "section_2": {"rotate": 20, "tilt": 55},
    "section_3": {"rotate": 160, "tilt": 150},
    "section_4": {"rotate": 20, "tilt": 145},
}


class ConsoleHardware:
    """Имитировать механизм сообщениями в журнале, не обращаясь к GPIO."""

    def __init__(self, delay: float = 1.0):
        """delay — длительность имитации одного сброса в секундах."""
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

    GPIO 12 наклоняет площадку, GPIO 13 поворачивает распределитель. Это номера
    BCM, а не номера физических контактов разъёма и не каналы PCA9685. Углы в
    общей таблице ``ACTIONS`` должны проверяться на реальной механике.
    """

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

        # min_angle/max_angle — диапазон команд в градусах.
        # min/max_pulse_width — импульсы для краёв диапазона, в секундах:
        # 0.0005–0.0025 с = 500–2500 мкс. frame_width=0.02 с — период PWM (50 Гц).
        options = dict(min_angle=0, max_angle=180, min_pulse_width=0.0005,
                       max_pulse_width=0.0025, frame_width=0.02)
        self.tilt = AngularServo(12, **options)
        self.rotate = AngularServo(13, **options)
        self.center()

    @staticmethod
    def _move(servo, angle: float) -> None:
        """Задать servo угол angle в градусах и выдержать паузу на движение."""
        # Ограничение 0–180 не учитывает механические упоры конкретной конструкции.
        servo.angle = max(0, min(180, angle))
        time.sleep(0.7)  # Секунды на каждое движение; обратной связи о положении нет.

    def center(self) -> None:
        """Сначала восстановить наклон площадки, затем вернуть поворот в центр."""
        self._move(self.tilt, CENTER_TILT_ANGLE)
        self._move(self.rotate, CENTER_ROTATE_ANGLE)

    def sort_to(self, section: str) -> None:
        """Повернуть распределитель, сбросить предмет и вернуться в центр."""
        action = ACTIONS[section]
        self._move(self.rotate, action["rotate"])
        self._move(self.tilt, action["tilt"])
        time.sleep(0.5)  # Дополнительная выдержка для падения предмета, секунды.
        self.center()

    def close(self) -> None:
        """Освободить GPIO-ресурсы обоих сервоприводов."""
        self.tilt.close()
        self.rotate.close()


class Pca9685Hardware:
    """Управлять сервоприводами через I2C-драйвер PCA9685.

    Канал 1 наклоняет площадку, канал 0 поворачивает распределитель. Углы секций
    и нейтрального положения общие с GPIO-вариантом и заданы в начале файла.
    """

    def __init__(
        self,
        address: int = 0x40,
        tilt_channel: int = 1,
        rotate_channel: int = 0,
    ):
        """Открыть PCA9685 и настроить диапазон импульсов сервоприводов.

        address — I2C-адрес платы; tilt_channel/rotate_channel — разные выходы
        платы с номерами 0–15. При запуске UMKA сюда передаются настройки из
        AppConfig, при калибровке — параметры командной строки calibrate.py.
        Сам конструктор PCA9685 не центрирует моторы: вызывающий код делает это
        через center().
        """
        try:
            from adafruit_servokit import ServoKit
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Драйвер PCA9685 недоступен. Установите пакет "
                "adafruit-circuitpython-servokit и включите I2C."
            ) from exc

        self.kit = ServoKit(channels=16, address=address)  # У платы 16 PWM-каналов.
        self.tilt = self.kit.servo[tilt_channel]
        self.rotate = self.kit.servo[rotate_channel]
        for servo in (self.tilt, self.rotate):
            servo.set_pulse_width_range(500, 2500)  # Импульсы для 0° и 180°, микросекунды.

    @staticmethod
    def _move(servo, angle: float) -> None:
        """Задать servo угол angle в градусах и выдержать паузу на движение."""
        # Ограничение 0–180 не учитывает механические упоры конкретной конструкции.
        servo.angle = max(0, min(180, angle))
        time.sleep(0.7)  # Секунды на каждое движение; обратной связи о положении нет.

    def center(self) -> None:
        """Сначала восстановить наклон площадки, затем вернуть поворот в центр."""
        self._move(self.tilt, CENTER_TILT_ANGLE)
        self._move(self.rotate, CENTER_ROTATE_ANGLE)

    def sort_to(self, section: str) -> None:
        """Повернуть распределитель, сбросить предмет и вернуться в центр."""
        action = ACTIONS[section]
        self._move(self.rotate, action["rotate"])
        self._move(self.tilt, action["tilt"])
        time.sleep(0.5)  # Дополнительная выдержка для падения предмета, секунды.
        self.center()

    def close(self) -> None:
        """Отключить PWM на обоих каналах и освободить I2C-ресурсы."""
        # None отключает PWM: это освобождение мотора, а не команда на угол 0°.
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

    driver выбирает console, gpiozero или pca9685. simulate_delay — секунды
    имитации (только console). pca9685_address — адрес платы I2C, tilt_channel
    и rotate_channel — выходы наклона и поворота (только pca9685).

    Неизвестные значения заранее отклоняются в ``AppConfig.validate()``, поэтому
    здесь безопасным значением по умолчанию остаётся консольная имитация.
    """
    if driver == "gpiozero":
        return GpioZeroHardware()
    if driver == "pca9685":
        return Pca9685Hardware(pca9685_address, tilt_channel, rotate_channel)
    return ConsoleHardware(simulate_delay)
