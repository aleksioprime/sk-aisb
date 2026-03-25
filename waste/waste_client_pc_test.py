import argparse
import queue
import socket
import struct
import threading
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


# Raspberry Pi server address and port.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5001

# YOLO model settings.
DEFAULT_MODEL_PATH = str(Path.cwd() / "example.pt")
DEFAULT_CONF = 0.60

# Manual commands accepted from the console.
VALID_COMMANDS = {
    "section_1",
    "section_2",
    "section_3",
    "section_4",
}
COMMAND_ALIASES = {
    "1": "section_1",
    "2": "section_2",
    "3": "section_3",
    "4": "section_4",
}


def recv_exact(sock: socket.socket, size: int) -> bytes:
    """Read exactly size bytes from the socket."""
    chunks = []
    remaining = size

    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("Connection closed.")
        chunks.append(chunk)
        remaining -= len(chunk)

    return b"".join(chunks)


def console_reader(command_queue: queue.Queue[str], stop_event: threading.Event) -> None:
    """Read commands from stdin in a background thread."""
    print("Manual mode: type section_1..section_4 or 1..4. Type quit to stop.")
    print("You can also press keys 1..4 in the OpenCV window to send commands.")

    while not stop_event.is_set():
        try:
            raw_value = input("> ").strip()
        except EOFError:
            stop_event.set()
            return

        if not raw_value:
            continue

        normalized = raw_value.lower()
        if normalized in {"q", "quit", "exit"}:
            stop_event.set()
            return

        command = COMMAND_ALIASES.get(normalized, normalized)
        if command not in VALID_COMMANDS:
            print(f"Unknown manual command: {raw_value}")
            continue

        command_queue.put(command)


def main() -> None:
    """Run video receiving, YOLO detection, and manual command sending."""
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
    args = parser.parse_args()

    model = YOLO(args.model)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((args.host, args.port))

    command_queue: queue.Queue[str] = queue.Queue()
    stop_event = threading.Event()
    input_thread = threading.Thread(
        target=console_reader,
        args=(command_queue, stop_event),
        daemon=True,
    )
    input_thread.start()

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

            results = model(frame, conf=args.conf, verbose=False)
            result = results[0]
            annotated = result.plot()

            while True:
                try:
                    command = command_queue.get_nowait()
                except queue.Empty:
                    break

                sock.sendall((command + "\n").encode("utf-8"))
                print(f"Sent manual command: {command}")

            cv2.imshow("Smart bin detect test", annotated)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("1"), ord("2"), ord("3"), ord("4")):
                command = COMMAND_ALIASES[chr(key)]
                sock.sendall((command + "\n").encode("utf-8"))
                print(f"Sent manual command: {command}")
            if key in (27, ord("q")):
                stop_event.set()
                break

    except KeyboardInterrupt:
        print("\nStopping...")

    finally:
        stop_event.set()
        sock.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
