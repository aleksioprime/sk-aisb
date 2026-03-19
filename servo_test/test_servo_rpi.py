import argparse
import time

import RPi.GPIO as GPIO


# Все рабочие параметры редактируются здесь, а в аргументах остаётся только GPIO pin.
DEFAULT_FREQUENCY = 50.0
DEFAULT_MIN_PULSE_US = 500.0
DEFAULT_MAX_PULSE_US = 2500.0
DEFAULT_MIN_ANGLE = 0.0
DEFAULT_MAX_ANGLE = 180.0
DEFAULT_CENTER_ANGLE = 90.0
DEFAULT_DELAY = 0.7


def clamp(value: float, low: float, high: float) -> float:
    """Ограничивает значение диапазоном [low, high]."""
    return max(low, min(value, high))


def angle_to_pulse_us(
    angle: float,
    min_angle: float,
    max_angle: float,
    min_pulse_us: float,
    max_pulse_us: float,
) -> float:
    """Переводит угол сервомотора в длину импульса."""
    clipped = clamp(angle, min_angle, max_angle)
    ratio = (clipped - min_angle) / (max_angle - min_angle)
    return min_pulse_us + ratio * (max_pulse_us - min_pulse_us)


def pulse_us_to_duty_cycle(pulse_us: float, frequency_hz: float) -> float:
    """Переводит длину импульса в duty cycle PWM."""
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
) -> float:
    """Перемещает сервомотор в указанный угол и возвращает фактический угол."""
    actual_angle = clamp(angle, min_angle, max_angle)
    pulse_us = angle_to_pulse_us(
        angle=actual_angle,
        min_angle=min_angle,
        max_angle=max_angle,
        min_pulse_us=min_pulse_us,
        max_pulse_us=max_pulse_us,
    )
    duty_cycle = pulse_us_to_duty_cycle(pulse_us, frequency_hz)

    print(
        f"Angle={actual_angle:.1f} deg | pulse={pulse_us:.0f} us | duty={duty_cycle:.2f}%"
    )
    pwm.ChangeDutyCycle(duty_cycle)
    time.sleep(delay_s)
    pwm.ChangeDutyCycle(0.0)
    return actual_angle


def print_help() -> None:
    """Печатает список доступных команд."""
    print("Commands:")
    print("  set <angle>     - поставить сервомотор на указанный угол")
    print("  turn <delta>    - повернуть относительно текущего угла")
    print("  center          - поставить на центральный угол")
    print("  status          - показать текущий угол")
    print("  help            - показать эту справку")
    print("  quit            - выход")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Интерактивный тест сервомотора на Raspberry Pi."
    )
    parser.add_argument(
        "--pin",
        type=int,
        required=True,
        help="BCM номер GPIO-пина для сигнала сервомотора.",
    )
    args = parser.parse_args()

    if DEFAULT_FREQUENCY <= 0:
        raise ValueError("DEFAULT_FREQUENCY должен быть больше 0.")
    if DEFAULT_MAX_ANGLE <= DEFAULT_MIN_ANGLE:
        raise ValueError("max_angle должен быть больше min_angle.")
    if DEFAULT_MAX_PULSE_US <= DEFAULT_MIN_PULSE_US:
        raise ValueError("max_pulse_us должен быть больше min_pulse_us.")
    if DEFAULT_DELAY < 0:
        raise ValueError("DEFAULT_DELAY не может быть отрицательным.")

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(args.pin, GPIO.OUT)

    pwm = GPIO.PWM(args.pin, DEFAULT_FREQUENCY)
    pwm.start(0.0)

    current_angle = clamp(DEFAULT_CENTER_ANGLE, DEFAULT_MIN_ANGLE, DEFAULT_MAX_ANGLE)

    print(f"GPIO pin: {args.pin} (BCM)")
    print(f"Angle range: {DEFAULT_MIN_ANGLE:.1f}..{DEFAULT_MAX_ANGLE:.1f}")
    print(f"Center angle: {current_angle:.1f}")
    print_help()

    try:
        while True:
            raw = input("\nservo> ").strip()
            if not raw:
                continue

            parts = raw.split()
            command = parts[0].lower()

            if command in ("quit", "exit", "q"):
                break

            if command == "help":
                print_help()
                continue

            if command == "status":
                print(f"Current angle: {current_angle:.1f}")
                continue

            if command == "center":
                current_angle = move_servo(
                    pwm=pwm,
                    angle=DEFAULT_CENTER_ANGLE,
                    frequency_hz=DEFAULT_FREQUENCY,
                    min_angle=DEFAULT_MIN_ANGLE,
                    max_angle=DEFAULT_MAX_ANGLE,
                    min_pulse_us=DEFAULT_MIN_PULSE_US,
                    max_pulse_us=DEFAULT_MAX_PULSE_US,
                    delay_s=DEFAULT_DELAY,
                )
                continue

            if command in ("set", "turn"):
                if len(parts) != 2:
                    print("Нужно указать одно числовое значение.")
                    continue

                try:
                    value = float(parts[1])
                except ValueError:
                    print("Значение должно быть числом.")
                    continue

                target_angle = value if command == "set" else current_angle + value
                current_angle = move_servo(
                    pwm=pwm,
                    angle=target_angle,
                    frequency_hz=DEFAULT_FREQUENCY,
                    min_angle=DEFAULT_MIN_ANGLE,
                    max_angle=DEFAULT_MAX_ANGLE,
                    min_pulse_us=DEFAULT_MIN_PULSE_US,
                    max_pulse_us=DEFAULT_MAX_PULSE_US,
                    delay_s=DEFAULT_DELAY,
                )
                continue

            print("Неизвестная команда. Используйте help.")

    except KeyboardInterrupt:
        print("\nStopping...")

    finally:
        pwm.ChangeDutyCycle(0.0)
        time.sleep(0.2)
        pwm.stop()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
