"""Драйверы реального механизма и безопасной консольной имитации."""

from __future__ import annotations

import contextlib
import logging
import time
import warnings
from pathlib import Path


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


# Шина /dev/i2c-5 — контакты 3 (SDA) и 5 (SCL) 26-контактного разъёма Orange Pi 5B.
ORANGE_PI_5_I2C_BUS = 5
# Платы с другим разъёмом: у них контакты 3 и 5 относятся к другой шине,
# поэтому номер 5 им не подставляется и задаётся параметром --i2c-bus.
OTHER_ORANGE_PI_5_BOARDS = ("orangepi5plus", "orangepi5max", "orangepi5pro",
                            "orangepi5ultra")


@contextlib.contextmanager
def _quiet_i2c_frequency_warning():
    """Скрыть предупреждение Blinka о том, что частоту I2C нельзя задать.

    Blinka принимает параметр frequency только ради совместимости с
    микроконтроллерами: в Linux частоту шины задаёт драйвер ядра, а не
    программа. Предупреждение появляется при каждом открытии шины, ни на что
    не влияет и только мешает читать журнал. Остальные предупреждения
    RuntimeWarning продолжают выводиться.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning,
                                message="I2C frequency is not settable")
        yield


def _board_model() -> str:
    """Собрать описание платы из Device Tree и файла образа Armbian.

    Device Tree есть не в каждом образе, а имя платы у Orange Pi надёжнее всего
    хранится в /etc/armbian-release (строка BOARD). Возвращается склейка обоих
    источников без пробелов, дефисов и подчёркиваний, в нижнем регистре: так
    совпадают написания Orange Pi, OrangePi и orangepi5b.
    """
    parts = []
    for path in (Path("/proc/device-tree/model"), Path("/etc/armbian-release")):
        try:
            parts.append(path.read_text(errors="ignore"))
        except OSError:
            # Файла нет или он недоступен: этот источник просто пропускается.
            continue
    text = " ".join(parts).lower()
    for symbol in (" ", "-", "_"):
        text = text.replace(symbol, "")
    return text


def _is_orange_pi_5() -> bool:
    """Определить Orange Pi 5 или 5B — платы с одинаковым 26-контактным разъёмом.

    Образы Orange Pi 5B нередко сообщают о себе просто «Orange Pi 5», поэтому
    различать эти две платы здесь не нужно и не всегда возможно. Orange Pi 5
    Plus, Max, Pro и Ultra исключаются: у них другой разъём.
    """
    model = _board_model()
    if any(board in model for board in OTHER_ORANGE_PI_5_BOARDS):
        return False
    return "orangepi5" in model


def _resolve_i2c_bus(i2c_bus: int | None) -> int | None:
    """Выбрать номер шины I2C: сначала явная настройка, затем автоопределение.

    i2c_bus — значение --i2c-bus (None означает «определить самостоятельно»).
    None в ответе оставляет выбор шины библиотеке Blinka: так работает
    Raspberry Pi, где board.I2C() сам находит /dev/i2c-1.
    """
    if i2c_bus is not None:
        return i2c_bus
    if _is_orange_pi_5():
        return ORANGE_PI_5_I2C_BUS
    return None


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
        i2c_bus: int | None = None,
    ):
        """Открыть PCA9685 и настроить диапазон импульсов сервоприводов.

        address — I2C-адрес платы; tilt_channel/rotate_channel — разные выходы
        платы с номерами 0–15. i2c_bus — номер шины /dev/i2c-N; None означает
        автоопределение: Orange Pi 5B получает шину 5, на остальных платах шину
        выбирает сама библиотека Blinka. При запуске UMKA сюда передаются
        настройки из AppConfig, при калибровке — параметры командной строки
        calibrate.py. Сам конструктор PCA9685 не центрирует моторы: вызывающий
        код делает это через center().
        """
        try:
            from adafruit_servokit import ServoKit
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Драйвер PCA9685 недоступен. Установите пакет "
                "adafruit-circuitpython-servokit и включите I2C."
            ) from exc

        self._i2c = None
        options = dict(channels=16, address=address)
        bus = _resolve_i2c_bus(i2c_bus)
        if bus is not None:
            try:
                from adafruit_extended_bus import ExtendedI2C
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "Для выбора шины I2C по номеру установите пакет "
                    "adafruit-extended-bus (он есть в requirements-opi.txt). "
                    "Без него номер шины задавать нельзя: уберите --i2c-bus, "
                    "чтобы шину выбрала библиотека Blinka."
                ) from exc
            device = Path(f"/dev/i2c-{bus}")
            if not device.exists():
                raise RuntimeError(
                    f"Шина {device} не найдена. Включите I2C: на Raspberry Pi "
                    "через sudo raspi-config, на Orange Pi 5B — оверлеем "
                    "i2c5-m3 в sudo orangepi-config (раздел 2 ORANGE_PI.md). "
                    "Другой номер шины задаётся параметром --i2c-bus."
                )
            # ExtendedI2C открывает /dev/i2c-N напрямую, минуя список шин Blinka:
            # на одноплатниках кроме Raspberry Pi нужные контакты в него не входят.
            with _quiet_i2c_frequency_warning():
                self._i2c = ExtendedI2C(bus)
            options["i2c"] = self._i2c
            LOG.info("PCA9685: шина /dev/i2c-%d", bus)
        else:
            LOG.info("PCA9685: шину выбирает Blinka (board.I2C)")
        try:
            with _quiet_i2c_frequency_warning():
                self.kit = ServoKit(**options)
            self.tilt = self.kit.servo[tilt_channel]
            self.rotate = self.kit.servo[rotate_channel]
            for servo in (self.tilt, self.rotate):
                servo.set_pulse_width_range(500, 2500)
        except BaseException as exc:
            if self._i2c is not None:
                self._i2c.deinit()
                self._i2c = None
            if bus is None and isinstance(exc, ValueError):
                # Blinka не нашла контакты I2C платы: плата не Raspberry Pi и не
                # опознана автоматически. Номер шины задаётся явно.
                raise RuntimeError(
                    "Не удалось открыть I2C автоматически на плате "
                    f"'{_board_model() or 'неизвестно'}'. Включите I2C (на "
                    "Raspberry Pi — sudo raspi-config) или укажите номер шины "
                    "параметром --i2c-bus (на Orange Pi 5B это 5), проверив "
                    "её командой i2cdetect -y <номер>."
                ) from exc
            raise

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
        try:
            self.tilt.angle = None
            self.rotate.angle = None
            pca = getattr(self.kit, "_pca", None)
            if pca is not None and hasattr(pca, "deinit"):
                pca.deinit()
        finally:
            if self._i2c is not None:
                self._i2c.deinit()
                self._i2c = None


def create_hardware(
    driver: str,
    simulate_delay: float,
    pca9685_address: int = 0x40,
    tilt_channel: int = 1,
    rotate_channel: int = 0,
    i2c_bus: int | None = None,
):
    """Создать выбранный драйвер механизма.

    driver выбирает console, gpiozero или pca9685. simulate_delay — секунды
    имитации (только console). pca9685_address — адрес платы I2C, tilt_channel
    и rotate_channel — выходы наклона и поворота, i2c_bus — номер шины
    /dev/i2c-N или None для автоопределения (только pca9685).

    Неизвестные значения заранее отклоняются в ``AppConfig.validate()``, поэтому
    здесь безопасным значением по умолчанию остаётся консольная имитация.
    """
    if driver == "gpiozero":
        return GpioZeroHardware()
    if driver == "pca9685":
        return Pca9685Hardware(pca9685_address, tilt_channel, rotate_channel,
                               i2c_bus)
    return ConsoleHardware(simulate_delay)
