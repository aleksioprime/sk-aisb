import socket
import struct
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


# Адрес Raspberry Pi и порт сервера.
RPI_HOST = "127.0.0.1"
PORT = 5001

# Параметры модели и принятия решения.
MODEL_PATH = str(Path(__file__).resolve().parent.parent / "detection" / "example.pt")
CONF = 0.60
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


def main() -> None:
    """Запускает приём потока, YOLO-детекцию и отправку команд на Raspberry Pi."""
    model = YOLO(MODEL_PATH)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((RPI_HOST, PORT))

    last_command = None
    last_command_time = 0.0
    decision_history: deque[str | None] = deque(maxlen=DECISION_WINDOW)

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

            results = model(frame, conf=CONF, verbose=False)
            result = results[0]
            annotated = result.plot()

            # На каждом кадре сохраняем текущее решение в короткую историю.
            command = choose_command(result, result.names)
            decision_history.append(command)

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
