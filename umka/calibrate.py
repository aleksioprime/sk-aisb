#!/usr/bin/env python3
"""Проверять сброс по секциям из консоли без камеры и распознавания."""

from __future__ import annotations

import argparse
import logging

from sorter.config import AppConfig
from sorter.hardware import ACTIONS, CENTER_ROTATE_ANGLE, CENTER_TILT_ANGLE, create_hardware


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
    args = parser.parse_args(argv)
    if not 0x03 <= args.pca9685_address <= 0x77:
        parser.error("Адрес PCA9685 должен находиться в диапазоне 0x03–0x77")
    if args.tilt_channel == args.rotate_channel:
        parser.error("Для наклона и поворота нужны разные каналы PCA9685")
    return args


def main(argv=None) -> None:
    """Выполнять команды по одной и освобождать драйвер при выходе."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(f"Драйвер: {args.hardware}")
    print(f"Центр: rotate={CENTER_ROTATE_ANGLE}°, tilt={CENTER_TILT_ANGLE}°")
    for section, angles in ACTIONS.items():
        print(f"{section}: rotate={angles['rotate']}°, tilt={angles['tilt']}°")
    print("При запуске механизм возвращается в центр.")
    hardware = create_hardware(args.hardware, 0, args.pca9685_address,
                               args.tilt_channel, args.rotate_channel)
    try:
        hardware.center()
        print("Команды: 1–4 — сброс в секцию; c — центр; q — выход.")
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
