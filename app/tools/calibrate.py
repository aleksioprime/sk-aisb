#!/usr/bin/env python3
"""Проверять сброс по секциям из консоли без камеры и распознавания."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Запуск как `python tools/calibrate.py` из каталога приложения: пакет sorter
# лежит уровнем выше.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sorter import calibration, hardware as angles, launch_config  # noqa: E402
from sorter.config import AppConfig  # noqa: E402
from sorter.hardware import create_hardware  # noqa: E402


def parse_args(argv=None) -> argparse.Namespace:
    """Проверить настройки подключения до обращения к моторам."""
    defaults = AppConfig()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hardware", choices=("console", "pca9685", "gpiozero"),
                        default="console", help="Драйвер; по умолчанию имитация")
    parser.add_argument("--pca9685-address", type=lambda value: int(value, 0),
                        default=defaults.pca9685_address)
    parser.add_argument("--tilt-channel", type=int, choices=range(16),
                        default=defaults.tilt_servo_channel)
    parser.add_argument("--rotate-channel", type=int, choices=range(16),
                        default=defaults.rotate_servo_channel)
    parser.add_argument("--i2c-bus", type=int, default=defaults.i2c_bus,
                        help="Номер шины /dev/i2c-N; по умолчанию автоопределение")
    # Те же параметры устройства, что и у app.py; аргументы командной строки важнее.
    parser.set_defaults(**launch_config.load())
    args = parser.parse_args(argv)
    if not 0x03 <= args.pca9685_address <= 0x77:
        parser.error("Адрес PCA9685 должен находиться в диапазоне 0x03–0x77")
    if args.tilt_channel == args.rotate_channel:
        parser.error("Для наклона и поворота нужны разные каналы PCA9685")
    if args.i2c_bus is not None and args.i2c_bus < 0:
        parser.error("Номер шины I2C не может быть отрицательным")
    return args


def main(argv=None) -> None:
    """Выполнять команды по одной и освобождать драйвер при выходе."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    calibration.load(AppConfig().calibration_path)
    print(f"Драйвер: {args.hardware}")
    print(f"Центр: rotate={angles.CENTER_ROTATE_ANGLE}°, tilt={angles.CENTER_TILT_ANGLE}°")
    for section, action in angles.ACTIONS.items():
        print(f"{section}: rotate={action['rotate']}°, tilt={action['tilt']}°")
    print("При запуске механизм возвращается в центр.")
    hardware = create_hardware(args.hardware, 0, args.pca9685_address,
                               args.tilt_channel, args.rotate_channel,
                               args.i2c_bus)
    try:
        hardware.center()
        print("Команды: 1–4 - сброс в секцию; c - центр; q - выход.")
        while True:
            command = input("Секция> ").strip().lower()
            if command == "q":
                break
            if command == "c":
                hardware.center()
            elif command in {"1", "2", "3", "4"}:
                section = f"section_{command}"
                print(f"Сброс в {section}...")
                hardware.sort_to(section)
                print("Сброс завершён, механизм вернулся в центр.")
            else:
                print("Введите 1, 2, 3, 4, c или q.")
    except (KeyboardInterrupt, EOFError):
        print("\nОстановка проверки.")
    finally:
        hardware.close()


if __name__ == "__main__":
    main()
