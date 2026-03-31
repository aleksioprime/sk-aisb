import argparse
import queue
import socket
import struct
import threading
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
DETECTION_PAUSE_SEC = 5.0
DECISION_WINDOW = 10
REQUIRED_STREAK = 5
REQUIRED_STREAK_UNKNOWN = 8

# Здесь задаётся, какой класс какую команду отправляет на Raspberry Pi.
# Подразумевается 4 класса и 4 секции мусорки.
CLASS_TO_COMMAND = {
    "plastic": "section_1",
    "papper": "section_3",
    "organic": "section_4",
}

# Класс пустой площадки (не вызывает команду).
EMPTY_CLASS = "empty"

# Команда для неизвестного объекта (определяется по контуру через OpenCV).
UNKNOWN_COMMAND = "section_2"

# Команда для приведения моторов в центральное положение.
CENTER_COMMAND = "center"

# Диапазон площади контура для детекции неизвестного объекта на площадке.
CONTOUR_MIN_AREA = 500
CONTOUR_MAX_AREA = 40000

# Область интереса (ROI) для контурной детекции — доля от размера кадра.
# (x, y, width, height) в диапазоне 0.0–1.0.
CONTOUR_ROI = (0.25, 0.15, 0.50, 0.70)


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


def frame_reader(
    sock: socket.socket,
    frame_queue: queue.Queue[np.ndarray],
    stop_event: threading.Event,
) -> None:
    """Читает поток кадров и сохраняет для обработки только самый свежий кадр."""
    try:
        while not stop_event.is_set():
            header = recv_exact(sock, 4)
            frame_size = struct.unpack("!I", header)[0]
            payload = recv_exact(sock, frame_size)

            frame = cv2.imdecode(
                np.frombuffer(payload, dtype=np.uint8),
                cv2.IMREAD_COLOR,
            )
            if frame is None:
                continue

            while True:
                try:
                    frame_queue.put_nowait(frame)
                    break
                except queue.Full:
                    try:
                        frame_queue.get_nowait()
                    except queue.Empty:
                        break

    except (ConnectionError, OSError):
        stop_event.set()


def get_contour_roi(frame: np.ndarray) -> tuple[int, int, int, int]:
    """Возвращает абсолютные координаты ROI (x, y, w, h) для контурной детекции."""
    h, w = frame.shape[:2]
    rx, ry, rw, rh = CONTOUR_ROI
    x1 = int(w * rx)
    y1 = int(h * ry)
    roi_w = int(w * rw)
    roi_h = int(h * rh)
    return x1, y1, roi_w, roi_h


def detect_unknown_object(frame: np.ndarray) -> list:
    """Определяет наличие неизвестного объекта на площадке по контурам OpenCV.

    Поиск ведётся только внутри области CONTOUR_ROI.
    Возвращает список контуров в координатах полного кадра (пустой — если ничего не найдено).
    """
    rx, ry, rw, rh = get_contour_roi(frame)
    roi = frame[ry:ry + rh, rx:rx + rw]

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (21, 21), 0)
    edges = cv2.Canny(blurred, 30, 100)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    dilated = cv2.dilate(edges, kernel, iterations=2)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    matched = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if CONTOUR_MIN_AREA <= area <= CONTOUR_MAX_AREA:
            # Смещаем контур в координаты полного кадра.
            matched.append(contour + np.array([rx, ry]))
    return matched


def choose_command(result, names: dict[int, str], frame: np.ndarray) -> str | None:
    """Выбирает команду по самому уверенному объекту в текущем кадре.

    Если YOLO не обнаружил известных объектов (или обнаружил только empty),
    но OpenCV находит контур подходящего размера — возвращает команду для
    неизвестного объекта (section_2).
    """
    boxes = result.boxes
    if boxes is not None and len(boxes) > 0:
        # Отбираем детекции, не являющиеся пустой площадкой.
        meaningful = []
        for i, (cls_tensor, conf_tensor) in enumerate(zip(boxes.cls, boxes.conf)):
            class_id = int(cls_tensor.item())
            class_name = names.get(class_id, str(class_id))
            if class_name != EMPTY_CLASS:
                meaningful.append((class_name, float(conf_tensor.item())))

        if meaningful:
            best = max(meaningful, key=lambda x: x[1])
            return CLASS_TO_COMMAND.get(best[0]), []

    # Нет YOLO-детекций (или только empty) — проверяем контуры.
    matched_contours = detect_unknown_object(frame)
    if matched_contours:
        return UNKNOWN_COMMAND, matched_contours

    return None, []


def should_send_command(history: deque[str | None], command: str | None) -> bool:
    """Проверяет, достаточно ли кадров подряд подтверждают одну команду."""
    if not command:
        return False

    # Для неизвестного объекта (контурная детекция) требуется больше
    # подтверждающих кадров, чтобы снизить ложные срабатывания.
    required = REQUIRED_STREAK_UNKNOWN if command == UNKNOWN_COMMAND else REQUIRED_STREAK

    streak = 0
    for item in reversed(history):
        if item == command:
            streak += 1
        else:
            break

    return streak >= required


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

    frame_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=1)
    stop_event = threading.Event()
    reader_thread = threading.Thread(
        target=frame_reader,
        args=(sock, frame_queue, stop_event),
        daemon=True,
    )
    reader_thread.start()

    last_command = None
    last_command_time = 0.0
    detection_paused_until = 0.0
    decision_history: deque[str | None] = deque(maxlen=DECISION_WINDOW)
    last_logged_summary = ""

    print(f"Connected to {args.host}:{args.port}")
    if args.no_display:
        print("Display disabled. Recognition results will be printed to the console.")
    else:
        print("Press q or Esc to exit, c to center servos.")

    try:
        while not stop_event.is_set():
            try:
                frame = frame_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            now = time.time()

            # Пауза детекции после отправки команды (механизм работает).
            if now < detection_paused_until:
                if not args.no_display:
                    cv2.imshow("Smart bin detect", frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), 27):
                        break
                continue

            # После окончания паузы разрешаем повторную отправку той же команды,
            # если объект всё ещё в кадре (механизм не справился).
            if last_command is not None and detection_paused_until > 0 and now >= detection_paused_until:
                last_command = None
                detection_paused_until = 0.0

            results = model(frame, conf=args.conf, verbose=False)
            result = results[0]

            # На каждом кадре сохраняем текущее решение в короткую историю.
            command, unknown_contours = choose_command(result, result.names, frame)
            decision_history.append(command)
            detection_summary = describe_detections(result, result.names)

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
                reason = detection_summary
                if unknown_contours:
                    areas = [int(cv2.contourArea(c)) for c in unknown_contours]
                    reason = f"unknown object contours({len(areas)}): {areas}"
                print(f"Sent: {command} | Reason: {reason}")
                last_command = command
                last_command_time = now
                detection_paused_until = now + DETECTION_PAUSE_SEC
                decision_history.clear()

            if not args.no_display:
                annotated = result.plot()
                # Рисуем область ROI для контурной детекции.
                rx, ry, rw, rh = get_contour_roi(frame)
                cv2.rectangle(annotated, (rx, ry), (rx + rw, ry + rh), (255, 255, 0), 2)
                cv2.putText(
                    annotated, "ROI", (rx + 4, ry + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1,
                )
                # Рисуем контуры, найденные для else-детекции.
                if unknown_contours:
                    cv2.drawContours(annotated, unknown_contours, -1, (0, 0, 255), 2)
                    for contour in unknown_contours:
                        x, y, w, h = cv2.boundingRect(contour)
                        area = int(cv2.contourArea(contour))
                        cv2.putText(
                            annotated,
                            f"UNKNOWN area={area}",
                            (x, y - 8),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (0, 0, 255),
                            2,
                        )
                cv2.imshow("Smart bin detect", annotated)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break
                if key == ord("c"):
                    sock.sendall((CENTER_COMMAND + "\n").encode("utf-8"))
                    print(f"Sent: {CENTER_COMMAND} | Reason: manual (key 'c')")

    except KeyboardInterrupt:
        print("\nStopping...")

    finally:
        stop_event.set()
        sock.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
