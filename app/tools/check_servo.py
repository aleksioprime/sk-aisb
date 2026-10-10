#!/usr/bin/env python3
"""Проверить ОДИН сервопривод на канале PCA9685 отдельно от механизма и приложения.

Для поэтапной сборки: сначала каждый мотор без нагрузки, затем в механизме,
с поиском крайних углов, в которых площадка ещё не упирается в корпус.
Перед запуском остановите UMKA: два процесса не должны управлять PCA9685.

    python tools/check_servo.py --channel 1
    python tools/check_servo.py --channel 0 --min 20 --max 160

Команды: число — встать в угол; s — медленно пройти диапазон туда и обратно;
off — снять сигнал (мотор перестаёт держать положение и греться); q — выход.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sorter import launch_config  # noqa: E402
from sorter.hardware import SERVO_PULSE_RANGE_US, open_pca9685  # noqa: E402


def parse_args(argv=None) -> argparse.Namespace:
    """Разобрать номер канала, подключение и допустимый диапазон углов."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--channel", type=int, choices=range(16), required=True, help="Канал PCA9685 0–15")
    parser.add_argument("--pca9685-address", type=lambda value: int(value, 0), default=0x40)
    parser.add_argument("--i2c-bus", type=int, default=None, help="Номер /dev/i2c-N; по умолчанию автоопределение")
    parser.add_argument("--min", dest="low", type=int, default=0, help="Наименьший разрешённый угол")
    parser.add_argument("--max", dest="high", type=int, default=180, help="Наибольший разрешённый угол")
    parser.add_argument("--step-delay", type=float, default=0.05, help="Пауза на градус при проходе, с")
    config = launch_config.load()
    parser.set_defaults(**{key: config[key] for key in ("pca9685_address", "i2c_bus") if key in config})
    args = parser.parse_args(argv)
    if not 0 <= args.low < args.high <= 180:
        parser.error("Нужно 0 ≤ --min < --max ≤ 180")
    return args


def main(argv=None) -> None:
    """Выполнять команды для одного канала и обязательно снять сигнал при выходе."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    kit, i2c = open_pca9685(args.pca9685_address, args.i2c_bus)
    servo = kit.servo[args.channel]
    servo.set_pulse_width_range(*SERVO_PULSE_RANGE_US)
    current = None

    def move(angle: int) -> int:
        angle = max(args.low, min(args.high, angle))
        servo.angle = angle
        print(f"Канал {args.channel}: {angle}°")
        return angle

    print(f"Канал {args.channel}, разрешённые углы {args.low}–{args.high}°. Сигнал пока не подан.")
    print("Команды: угол (например 90), s — проход по диапазону, off — снять сигнал, q — выход.")
    print("Если мотор гудит, трясётся или греется — сразу off: он упирается или неисправен.")
    try:
        while True:
            command = input("Угол> ").strip().lower()
            if command == "q":
                break
            if command == "off":
                servo.angle = None
                current = None
                print("Сигнал снят.")
            elif command == "s":
                start = current if current is not None else move((args.low + args.high) // 2)
                for angle in [*range(start, args.high + 1), *range(args.high, args.low - 1, -1),
                              *range(args.low, start + 1)]:
                    servo.angle = angle
                    time.sleep(args.step_delay)
                current = start
                print(f"Проход {args.low}–{args.high}° завершён, мотор в {start}°.")
            elif command.lstrip("-").isdigit():
                current = move(int(command))
            else:
                print("Введите угол, s, off или q.")
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        servo.angle = None
        if i2c is not None:
            i2c.deinit()
        print("Сигнал снят, проверка завершена.")


if __name__ == "__main__":
    main()
