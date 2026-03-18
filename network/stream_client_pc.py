import argparse
import socket
import struct
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000
DEFAULT_MODEL_PATH = str(
    Path(__file__).resolve().parent.parent / "detection" / "example.pt"
)
DEFAULT_CONF = 0.50


def recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = []
    remaining = size

    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("Соединение закрыто.")
        chunks.append(chunk)
        remaining -= len(chunk)

    return b"".join(chunks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST, help="IP-адрес Raspberry Pi.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP-порт сервера.")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_PATH,
        help="Путь к файлу весов YOLO (.pt).",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=DEFAULT_CONF,
        help="Порог confidence.",
    )
    args = parser.parse_args()

    model = YOLO(args.model)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((args.host, args.port))

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

            # Инференс
            results = model(frame, conf=args.conf, verbose=False)

            # Отрисовка боксов и вывод
            annotated = results[0].plot()

            cv2.imshow("YOLO detect", annotated)

            # ESC или q для выхода
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
