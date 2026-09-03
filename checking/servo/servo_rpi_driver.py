"""Interactive test for two servos connected to PCA9685 channels 0 and 1."""

from __future__ import annotations

import time

try:
    from adafruit_servokit import ServoKit
except ImportError as exc:
    raise SystemExit(
        "Не найдена библиотека adafruit-circuitpython-servokit. "
        "Установите её: python3 -m pip install adafruit-circuitpython-servokit"
    ) from exc


PCA9685_ADDRESS = 0x40
PCA9685_CHANNELS = 16
SERVO_CHANNELS = (0, 1)
MIN_ANGLE = 0.0
MAX_ANGLE = 180.0
CENTER_ANGLE = 90.0
MIN_PULSE_US = 500
MAX_PULSE_US = 2500
MOVE_DELAY_S = 0.5
SWEEP_STEP_DEG = 10
SWEEP_DELAY_S = 0.08


def clamp(angle: float) -> float:
    return max(MIN_ANGLE, min(angle, MAX_ANGLE))


def parse_target(value: str) -> tuple[int, ...]:
    if value.lower() in {"all", "both"}:
        return SERVO_CHANNELS
    try:
        channel = int(value)
    except ValueError as exc:
        raise ValueError("Канал должен быть 0, 1 или all.") from exc
    if channel not in SERVO_CHANNELS:
        raise ValueError(f"Доступны только каналы {SERVO_CHANNELS}.")
    return (channel,)


def set_angle(
    kit: ServoKit,
    current_angles: dict[int, float | None],
    channels: tuple[int, ...],
    angle: float,
) -> None:
    actual_angle = clamp(angle)
    for channel in channels:
        kit.servo[channel].angle = actual_angle
        current_angles[channel] = actual_angle
        print(f"Канал {channel}: {actual_angle:.1f}°")
    time.sleep(MOVE_DELAY_S)


def release(kit: ServoKit, current_angles: dict[int, float | None]) -> None:
    for channel in SERVO_CHANNELS:
        kit.servo[channel].angle = None
        current_angles[channel] = None


def sweep(
    kit: ServoKit,
    current_angles: dict[int, float | None],
    channels: tuple[int, ...],
) -> None:
    angles = list(range(int(MIN_ANGLE), int(MAX_ANGLE) + 1, SWEEP_STEP_DEG))
    angles += list(
        range(int(MAX_ANGLE) - SWEEP_STEP_DEG, int(MIN_ANGLE) - 1, -SWEEP_STEP_DEG)
    )
    angles.append(int(CENTER_ANGLE))
    for angle in angles:
        for channel in channels:
            kit.servo[channel].angle = angle
            current_angles[channel] = float(angle)
        time.sleep(SWEEP_DELAY_S)
    print("Sweep завершён, выбранные сервоприводы установлены в центр.")


def print_help() -> None:
    print(
        """Команды:
  set <0|1|all> <angle>  установить угол
  turn <0|1|all> <delta> повернуть относительно текущего угла
  center <0|1|all>       установить в центр
  sweep <0|1|all>        плавно проверить весь диапазон
  status                 показать последние заданные углы
  release                отключить PWM на обоих каналах
  help                    показать справку
  quit                    выход"""
    )


def main() -> None:
    kit = ServoKit(channels=PCA9685_CHANNELS, address=PCA9685_ADDRESS)
    current_angles: dict[int, float | None] = {
        channel: None for channel in SERVO_CHANNELS
    }
    for channel in SERVO_CHANNELS:
        kit.servo[channel].set_pulse_width_range(MIN_PULSE_US, MAX_PULSE_US)

    print(
        f"PCA9685: адрес 0x{PCA9685_ADDRESS:02X}; "
        f"тестовые каналы: {SERVO_CHANNELS}."
    )
    print("При запуске моторы не двигаются. Начните с: center all")
    print_help()

    try:
        while True:
            parts = input("\nservo> ").strip().split()
            if not parts:
                continue
            command = parts[0].lower()
            if command in {"quit", "exit", "q"}:
                break
            if command == "help":
                print_help()
                continue
            if command == "status":
                for channel, angle in current_angles.items():
                    value = "PWM отключён" if angle is None else f"{angle:.1f}°"
                    print(f"Канал {channel}: {value}")
                continue
            if command == "release":
                release(kit, current_angles)
                print("PWM отключён на каналах 0 и 1.")
                continue
            if command in {"center", "sweep"} and len(parts) == 2:
                channels = parse_target(parts[1])
                if command == "center":
                    set_angle(kit, current_angles, channels, CENTER_ANGLE)
                else:
                    sweep(kit, current_angles, channels)
                continue
            if command in {"set", "turn"} and len(parts) == 3:
                channels = parse_target(parts[1])
                value = float(parts[2])
                if command == "set":
                    set_angle(kit, current_angles, channels, value)
                else:
                    for channel in channels:
                        current = current_angles[channel]
                        if current is None:
                            raise ValueError(
                                f"Канал {channel}: сначала используйте set или center."
                            )
                        set_angle(kit, current_angles, (channel,), current + value)
                continue
            print("Неверная команда. Используйте help.")
    except (ValueError, OSError) as exc:
        print(f"Ошибка: {exc}")
        print("Перезапустите тест после исправления подключения или команды.")
    except KeyboardInterrupt:
        print("\nОстановка...")
    finally:
        release(kit, current_angles)
        print("PWM отключён.")


if __name__ == "__main__":
    main()
