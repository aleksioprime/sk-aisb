#!/usr/bin/env python3
"""Командная точка входа в систему сортировки UMKA."""

from __future__ import annotations

import argparse
import logging
from dataclasses import replace
from pathlib import Path

from sorter.application import UmkaApplication
from sorter.config import AppConfig
from sorter.logging_config import configure_logging


def parse_args() -> argparse.Namespace:
    """Разобрать параметры запуска из командной строки."""
    parser = argparse.ArgumentParser(description="UMKA — автоматическая сортировка мусора")
    parser.add_argument("--camera", type=int, default=0, help="Индекс USB-камеры")
    parser.add_argument("--model", type=Path, help="Путь к YOLO .pt")
    parser.add_argument("--host", default="0.0.0.0", help="Адрес веб-сервера")
    parser.add_argument("--port", type=int, default=3000, help="Порт веб-сервера")
    parser.add_argument(
        "--hardware",
        choices=("console", "pca9685", "gpiozero"),
        default="console",
        help="Драйвер механизма: имитация, PCA9685 по I2C или прямой GPIO",
    )
    parser.add_argument(
        "--pca9685-address",
        type=lambda value: int(value, 0),
        default=0x40,
        help="I2C-адрес PCA9685 (по умолчанию 0x40)",
    )
    parser.add_argument("--tilt-channel", type=int, default=1, help="Канал PCA9685 для наклона")
    parser.add_argument("--rotate-channel", type=int, default=0, help="Канал PCA9685 для поворота")
    parser.add_argument("--confidence", type=float, default=0.60)
    parser.add_argument("--stable-frames", type=int, default=5)
    parser.add_argument("--clear-frames", type=int, default=10)
    parser.add_argument("--log-file", type=Path, help="Путь к ротируемому файлу журнала")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Настроить журналирование, собрать конфигурацию и запустить приложение."""
    args = parse_args()
    # Базовая конфигурация хранит безопасные значения по умолчанию. replace()
    # создаёт новый frozen-объект только с параметрами, заданными пользователем.
    config = AppConfig()
    config = replace(
        config,
        camera_index=args.camera,
        model_path=args.model.resolve() if args.model else config.model_path,
        web_host=args.host,
        web_port=args.port,
        hardware_driver=args.hardware,
        pca9685_address=args.pca9685_address,
        tilt_servo_channel=args.tilt_channel,
        rotate_servo_channel=args.rotate_channel,
        confidence=args.confidence,
        stable_frames=args.stable_frames,
        clear_frames=args.clear_frames,
        log_path=args.log_file.resolve() if args.log_file else config.log_path,
    )
    configure_logging(config.log_path, verbose=args.verbose)
    try:
        UmkaApplication(config).run()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Остановка по Ctrl+C")


if __name__ == "__main__":
    main()
