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


def frame_reader(
    sock: socket.socket,
    frame_queue: queue.Queue[np.ndarray],
    stop_event: threading.Event,
) -> None:
    """Read frames continuously and keep only the newest one for processing."""
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


def console_reader(
    command_queue: queue.Queue[str],
    stop_event: threading.Event,
    display_enabled: bool,
) -> None:
    """Read commands from stdin in a background thread."""
    print("Manual mode: type section_1..section_4 or 1..4. Type quit to stop.")
    if display_enabled:
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


def describe_detections(result, names: dict[int, str]) -> str:
    """Return a short text description of detections for console mode."""
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
    command_queue: queue.Queue[str] = queue.Queue()
    stop_event = threading.Event()
    reader_thread = threading.Thread(
        target=frame_reader,
        args=(sock, frame_queue, stop_event),
        daemon=True,
    )
    input_thread = threading.Thread(
        target=console_reader,
        args=(command_queue, stop_event, not args.no_display),
        daemon=True,
    )
    reader_thread.start()
    input_thread.start()
    last_logged_summary = ""

    print(f"Connected to {args.host}:{args.port}")
    if args.no_display:
        print("Display disabled. Recognition results will be printed to the console.")
    else:
        print("Press q or Esc in the OpenCV window to exit.")

    try:
        while not stop_event.is_set():
            try:
                frame = frame_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            results = model(frame, conf=args.conf, verbose=False)
            result = results[0]
            detection_summary = describe_detections(result, result.names)

            if args.no_display:
                summary_line = f"Detections: {detection_summary}"
                if summary_line != last_logged_summary:
                    print(summary_line)
                    last_logged_summary = summary_line

            while True:
                try:
                    command = command_queue.get_nowait()
                except queue.Empty:
                    break

                sock.sendall((command + "\n").encode("utf-8"))
                print(f"Sent manual command: {command}")

            if not args.no_display:
                annotated = result.plot()
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
