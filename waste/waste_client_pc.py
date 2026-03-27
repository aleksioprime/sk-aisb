import argparse
import socket
import struct
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


# Адрес Raspberry Pi и порт сервера.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5001

# Параметры модели и принятия решения.
DEFAULT_MODEL_PATH = str(Path.cwd() / "example.pt")
DEFAULT_CONF = 0.60
COMMAND_COOLDOWN_SEC = 3.0
DECISION_WINDOW = 5
REQUIRED_STREAK = 3

# Здесь задаётся, какой класс какую команду отправляет на Raspberry Pi.
# Подразумевается 4 класса и 4 секции мусорки.
CLASS_TO_COMMAND = {
    "class_1": "section_1",
    "class_2": "section_2",
    "class_3": "section_3",
    "class_4": "section_4",
}


def recv_exact(sock: socket.socket, size: int) -> bytes:
    """Читает из сокета ровно size байт или выбрасывает ошибку."""
    chunks = []
    remaining = size

    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("Connection closed.")
        chunks.append(chunk)
        remaining -= len(chunk)

    return b"".join(chunks)


def choose_command(result, names: dict[int, str]) -> str | None:
    """Выбирает команду по самому уверенному объекту в текущем кадре."""
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return None

    # Берём самый уверенный объект в текущем кадре.
    best_index = int(boxes.conf.argmax().item())
    class_id = int(boxes.cls[best_index].item())
    class_name = names.get(class_id, str(class_id))
    return CLASS_TO_COMMAND.get(class_name)


def should_send_command(history: deque[str | None], command: str | None) -> bool:
    """Проверяет, достаточно ли кадров подряд подтверждают одну команду."""
    if not command:
        return False

    # Команда отправляется только если один и тот же класс повторился
    # несколько кадров подряд. Это уменьшает ложные срабатывания.
    streak = 0
    for item in reversed(history):
        if item == command:
            streak += 1
        else:
            break

    return streak >= REQUIRED_STREAK


def describe_detections(result, names: dict[int, str]) -> str:
    """Возвращает краткое текстовое описание детекций для консоли."""
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return "no objects"

    detections = []
    for class_tensor, conf_tensor in zip(boxes.cls, boxes.conf):
        class_id = int(class_tensor.item())
        class_name = names.get(class_id, str(class_id))
        confidence = float(conf_tensor.item())
        detections.append(f"{class_name}:{confidence:.2f}")

    return ", ".join(detections)


def main() -> None:
    """Запускает приём потока, YOLO-детекцию и отправку команд на Raspberry Pi."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST, help="IP address of Raspberry Pi.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP server port.")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_PATH,
        help="Path to YOLO weights file (.pt).",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=DEFAULT_CONF,
        help="Confidence threshold.",
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Disable the OpenCV window and print recognition results to the console.",
    )
    args = parser.parse_args()

    model = YOLO(args.model)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((args.host, args.port))

    last_command = None
    last_command_time = 0.0
    decision_history: deque[str | None] = deque(maxlen=DECISION_WINDOW)
    last_logged_summary = ""

    print(f"Connected to {args.host}:{args.port}")
    if args.no_display:
        print("Display disabled. Recognition results will be printed to the console.")
    else:
        print("Press q or Esc to exit.")

    try:
        while True:
            header = recv_exact(sock, 4)
            frame_size = struct.unpack("!I", header)[0]
            payload = recv_exact(sock, frame_size)

            frame = cv2.imdecode(
                np.frombuffer(payload, dtype=np.uint8),
                cv2.IMREAD_COLOR,
            )
            if frame is None:
                continue

            results = model(frame, conf=args.conf, verbose=False)
            result = results[0]

            # На каждом кадре сохраняем текущее решение в короткую историю.
            command = choose_command(result, result.names)
            decision_history.append(command)
            detection_summary = describe_detections(result, result.names)

            if args.no_display:
                summary_line = f"Detections: {detection_summary}; command: {command or '-'}"
                if summary_line != last_logged_summary:
                    print(summary_line)
                    last_logged_summary = summary_line

            now = time.time()
            if command is None:
                # Если объект исчез или класс перестал определяться,
                # разрешаем повторную отправку при следующем стабильном появлении.
                last_command = None

            if (
                command is not None
                and should_send_command(decision_history, command)
                and command != last_command
                and now - last_command_time >= COMMAND_COOLDOWN_SEC
            ):
                sock.sendall((command + "\n").encode("utf-8"))
                print(f"Sent command: {command}")
                last_command = command
                last_command_time = now

            if not args.no_display:
                annotated = result.plot()
                cv2.imshow("Smart bin detect", annotated)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break

    except KeyboardInterrupt:
        print("\nStopping...")

    finally:
        sock.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
