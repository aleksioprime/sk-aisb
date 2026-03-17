import argparse
import time

import RPi.GPIO as GPIO


DEFAULT_PIN = 18
DEFAULT_FREQUENCY = 50.0
DEFAULT_MIN_PULSE_US = 500.0
DEFAULT_MAX_PULSE_US = 2500.0
DEFAULT_MIN_ANGLE = 0.0
DEFAULT_MAX_ANGLE = 180.0
DEFAULT_DELAY = 0.7
DEFAULT_STEP = 15.0


def parse_angles(raw_value: str) -> list[float]:
    values = []
    for item in raw_value.split(","):
        item = item.strip()
        if not item:
            continue
        values.append(float(item))

    if not values:
        raise argparse.ArgumentTypeError("Список углов пуст.")

    return values


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def angle_to_pulse_us(
    angle: float,
    min_angle: float,
    max_angle: float,
    min_pulse_us: float,
    max_pulse_us: float,
) -> float:
    if max_angle <= min_angle:
        raise ValueError("max_angle должен быть больше min_angle.")

    clipped = clamp(angle, min_angle, max_angle)
    ratio = (clipped - min_angle) / (max_angle - min_angle)
    return min_pulse_us + ratio * (max_pulse_us - min_pulse_us)


def pulse_us_to_duty_cycle(pulse_us: float, frequency_hz: float) -> float:
    period_us = 1_000_000.0 / frequency_hz
    return pulse_us / period_us * 100.0


def move_servo(
    pwm: GPIO.PWM,
    angle: float,
    frequency_hz: float,
    min_angle: float,
    max_angle: float,
    min_pulse_us: float,
    max_pulse_us: float,
    delay_s: float,
) -> None:
    pulse_us = angle_to_pulse_us(
        angle=angle,
        min_angle=min_angle,
        max_angle=max_angle,
        min_pulse_us=min_pulse_us,
        max_pulse_us=max_pulse_us,
    )
    duty_cycle = pulse_us_to_duty_cycle(pulse_us, frequency_hz)

    print(
        f"Angle={angle:.1f} deg | pulse={pulse_us:.0f} us | duty={duty_cycle:.2f}%"
    )
    pwm.ChangeDutyCycle(duty_cycle)
    time.sleep(delay_s)


def build_sequence(args: argparse.Namespace) -> list[float]:
    if args.mode == "center":
        return [args.center_angle]

    if args.mode == "angles":
        return args.angles

    sweep_up = []
    current = args.min_angle
    while current < args.max_angle:
        sweep_up.append(current)
        current += args.step
    sweep_up.append(args.max_angle)

    sweep_down = list(reversed(sweep_up[:-1]))
    return sweep_up + sweep_down


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Тест сервомотора на Raspberry Pi через PWM."
    )
    parser.add_argument(
        "--pin",
        type=int,
        default=DEFAULT_PIN,
        help="BCM номер GPIO-пина для сигнала сервомотора.",
    )
    parser.add_argument(
        "--mode",
        choices=["center", "angles", "sweep"],
        default="sweep",
        help="Режим тестирования: центр, список углов или прогон туда-обратно.",
    )
    parser.add_argument(
        "--angles",
        type=parse_angles,
        default=[0.0, 90.0, 180.0],
        help="Список углов через запятую для режима angles.",
    )
    parser.add_argument(
        "--center-angle",
        type=float,
        default=90.0,
        help="Угол для режима center.",
    )
    parser.add_argument(
        "--frequency",
        type=float,
        default=DEFAULT_FREQUENCY,
        help="Частота PWM в Гц. Для большинства сервоприводов 50 Гц.",
    )
    parser.add_argument(
        "--min-pulse-us",
        type=float,
        default=DEFAULT_MIN_PULSE_US,
        help="Импульс для минимального угла в микросекундах.",
    )
    parser.add_argument(
        "--max-pulse-us",
        type=float,
        default=DEFAULT_MAX_PULSE_US,
        help="Импульс для максимального угла в микросекундах.",
    )
    parser.add_argument(
        "--min-angle",
        type=float,
        default=DEFAULT_MIN_ANGLE,
        help="Минимальный угол сервомотора.",
    )
    parser.add_argument(
        "--max-angle",
        type=float,
        default=DEFAULT_MAX_ANGLE,
        help="Максимальный угол сервомотора.",
    )
    parser.add_argument(
        "--step",
        type=float,
        default=DEFAULT_STEP,
        help="Шаг в градусах для режима sweep.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help="Пауза после каждой команды в секундах.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Сколько раз повторить последовательность. 0 означает бесконечно.",
    )
    parser.add_argument(
        "--settle",
        type=float,
        default=0.5,
        help="Пауза после запуска PWM перед первой командой.",
    )
    parser.add_argument(
        "--keep-active",
        action="store_true",
        help="Не отключать PWM в конце, оставить удержание позиции.",
    )
    args = parser.parse_args()

    if args.frequency <= 0:
        raise ValueError("frequency должен быть больше 0.")
    if args.max_angle <= args.min_angle:
        raise ValueError("max_angle должен быть больше min_angle.")
    if args.max_pulse_us <= args.min_pulse_us:
        raise ValueError("max_pulse_us должен быть больше min_pulse_us.")
    if args.step <= 0:
        raise ValueError("step должен быть больше 0.")
    if args.delay < 0:
        raise ValueError("delay не может быть отрицательным.")
    if args.repeat < 0:
        raise ValueError("repeat не может быть отрицательным.")

    sequence = build_sequence(args)

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(args.pin, GPIO.OUT)

    pwm = GPIO.PWM(args.pin, args.frequency)
    pwm.start(0.0)

    print(f"GPIO pin: {args.pin} (BCM)")
    print(f"Mode: {args.mode}")
    print(f"Sequence: {', '.join(f'{angle:.1f}' for angle in sequence)}")
    print("Press Ctrl+C to stop.\n")

    try:
        time.sleep(args.settle)

        cycles_done = 0
        while args.repeat == 0 or cycles_done < args.repeat:
            for angle in sequence:
                move_servo(
                    pwm=pwm,
                    angle=angle,
                    frequency_hz=args.frequency,
                    min_angle=args.min_angle,
                    max_angle=args.max_angle,
                    min_pulse_us=args.min_pulse_us,
                    max_pulse_us=args.max_pulse_us,
                    delay_s=args.delay,
                )
            cycles_done += 1

        if args.keep_active:
            print("\nPWM remains active. Press Ctrl+C to release the servo.")
            while True:
                time.sleep(1.0)

    except KeyboardInterrupt:
        print("\nStopping...")

    finally:
        pwm.ChangeDutyCycle(0.0)
        time.sleep(0.2)
        pwm.stop()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
