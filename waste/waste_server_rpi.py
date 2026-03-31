import select
import socket
import struct
import time
from time import sleep

import cv2
from picamera2 import Picamera2
import RPi.GPIO as GPIO


# Сетевые настройки TCP-сервера на Raspberry Pi.
HOST = "0.0.0.0"
PORT = 5001

# Настройки камеры и JPEG-потока.
CAMERA_SIZE = (640, 480)
JPEG_QUALITY = 80
WARMUP_SEC = 1.0
CROP_TOP = 40
CROP_BOTTOM = 85
CROP_LEFT = 100
CROP_RIGHT = 66

# Параметры управления сервоприводами.
SERVO_FREQUENCY = 50.0
MIN_PULSE_US = 500.0
MAX_PULSE_US = 2500.0
MIN_ANGLE = 0.0
MAX_ANGLE = 180.0
MOVE_SETTLE_SEC = 0.7
TILT_RETURN_ANGLE = 95.0
ROTATE_RETURN_ANGLE = 90.0
DUMP_PAUSE_SEC = 0.5

# GPIO 12: наклон площадки для сброса мусора
# GPIO 13: поворот распределителя по горизонтали
SERVO_PINS = [12, 13]
TILT_SERVO_PIN = 12
ROTATE_SERVO_PIN = 13


# Здесь задаются команды для 4 секций мусорки.
# Формат:
#   "section_X": {
#       "rotate": угол поворота горизонтального сервопривода,
#       "tilt": угол наклона площадки для сброса
#   }
#
# Эти углы сейчас тестовые. Их можно подправить на испытаниях под механику.
COMMAND_ACTIONS = {
    "section_1": {"rotate": 160, "tilt": 70},
    "section_2": {"rotate": 20, "tilt": 70},
    "section_3": {"rotate": 160, "tilt": 140},
    "section_4": {"rotate": 20, "tilt": 140},
}


def clamp(value: float, low: float, high: float) -> float:
    """Ограничивает значение диапазоном [low, high]."""
    return max(low, min(value, high))


def angle_to_duty_cycle(angle: float) -> float:
    """Преобразует угол сервомотора в duty cycle для PWM."""
    clipped = clamp(angle, MIN_ANGLE, MAX_ANGLE)
    ratio = (clipped - MIN_ANGLE) / (MAX_ANGLE - MIN_ANGLE)
    pulse_us = MIN_PULSE_US + ratio * (MAX_PULSE_US - MIN_PULSE_US)
    period_us = 1_000_000.0 / SERVO_FREQUENCY
    return pulse_us / period_us * 100.0


def crop_frame(frame):
    """Обрезает кадр перед отправкой по сети."""
    height, width = frame.shape[:2]
    top = clamp(CROP_TOP, 0, height)
    bottom = clamp(CROP_BOTTOM, 0, height - top)
    left = clamp(CROP_LEFT, 0, width)
    right = clamp(CROP_RIGHT, 0, width - left)

    y_start = int(top)
    y_end = int(height - bottom)
    x_start = int(left)
    x_end = int(width - right)

    if y_start >= y_end or x_start >= x_end:
        return frame

    return frame[y_start:y_end, x_start:x_end]


def create_pwm_map() -> dict[int, GPIO.PWM]:
    """Создаёт PWM-объекты для всех используемых GPIO-пинов."""
    GPIO.setmode(GPIO.BCM)
    pwm_map = {}
    for pin in SERVO_PINS:
        GPIO.setup(pin, GPIO.OUT)
        pwm = GPIO.PWM(pin, SERVO_FREQUENCY)
        pwm.start(0.0)
        pwm_map[pin] = pwm
    return pwm_map


def move_servo(pwm_map: dict[int, GPIO.PWM], pin: int, angle: float) -> None:
    """Перемещает указанный сервомотор в заданный угол."""
    pwm = pwm_map[pin]
    duty_cycle = angle_to_duty_cycle(angle)
    pwm.ChangeDutyCycle(duty_cycle)
    time.sleep(MOVE_SETTLE_SEC)
    pwm.ChangeDutyCycle(0.0)


def center_servos(pwm_map: dict[int, GPIO.PWM]) -> None:
    """Приводит все сервоприводы в центральное (нейтральное) положение."""
    print("Execute command: center")
    move_servo(pwm_map, TILT_SERVO_PIN, TILT_RETURN_ANGLE)
    move_servo(pwm_map, ROTATE_SERVO_PIN, ROTATE_RETURN_ANGLE)


def execute_command(command: str, pwm_map: dict[int, GPIO.PWM]) -> None:
    """Выполняет команду, переводя мусор в одну из 4 секций."""
    if command == "center":
        center_servos(pwm_map)
        return

    action = COMMAND_ACTIONS.get(command)
    if not action:
        print(f"Unknown command: {command}")
        return

    print(f"Execute command: {command}")

    # 1. Повернуть распределитель к нужной секции.
    move_servo(pwm_map, ROTATE_SERVO_PIN, action["rotate"])

    # 2. Наклонить площадку, чтобы мусор упал в выбранный отсек.
    move_servo(pwm_map, TILT_SERVO_PIN, action["tilt"])

    # Даём мусору время сойти после наклона.
    time.sleep(DUMP_PAUSE_SEC)

    # 3. Вернуть площадку в нейтральное положение, чтобы принять следующий объект.
    move_servo(pwm_map, TILT_SERVO_PIN, TILT_RETURN_ANGLE)

    # 4. Вернуть распределитель в нейтральное положение.
    move_servo(pwm_map, ROTATE_SERVO_PIN, ROTATE_RETURN_ANGLE)


def handle_pending_commands(
    conn: socket.socket,
    command_buffer: bytes,
    pwm_map: dict[int, GPIO.PWM],
) -> bytes:
    """Читает все доступные команды из сокета и выполняет их."""
    ready, _, _ = select.select([conn], [], [], 0.0)
    if not ready:
        return command_buffer

    chunk = conn.recv(1024)
    if not chunk:
        raise ConnectionError("Client disconnected.")

    command_buffer += chunk

    while b"\n" in command_buffer:
        raw_command, command_buffer = command_buffer.split(b"\n", 1)
        command = raw_command.decode("utf-8", errors="ignore").strip()
        if command:
            execute_command(command, pwm_map)

    return command_buffer


def main() -> None:
    """Запускает сервер потока камеры и обработчик команд сервоприводов."""
    pwm_map = create_pwm_map()

    picam2 = Picamera2()
    config = picam2.create_video_configuration(
        main={"size": CAMERA_SIZE, "format": "RGB888"}
    )
    picam2.configure(config)
    picam2.start()
    sleep(WARMUP_SEC)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)

    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    print(f"Listening on {HOST}:{PORT}...")

    try:
        while True:
            conn, addr = server.accept()
            print(f"Connected: {addr[0]}:{addr[1]}")
            command_buffer = b""

            try:
                while True:
                    command_buffer = handle_pending_commands(conn, command_buffer, pwm_map)

                    frame = picam2.capture_array()
                    frame = crop_frame(frame)
                    ok, encoded = cv2.imencode(".jpg", frame, encode_params)
                    if not ok:
                        continue

                    payload = encoded.tobytes()
                    conn.sendall(struct.pack("!I", len(payload)))
                    conn.sendall(payload)

            except (BrokenPipeError, ConnectionError):
                print("Client disconnected.")
            finally:
                conn.close()

    except KeyboardInterrupt:
        print("\nStopping...")

    finally:
        server.close()
        picam2.stop()
        for pwm in pwm_map.values():
            pwm.ChangeDutyCycle(0.0)
            pwm.stop()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
