import argparse
import socket
import struct
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5001
DEFAULT_SAVE_KEY = "s"
DEFAULT_WINDOW_NAME = "Waste stream capture"


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


def normalize_key(raw_key: str) -> int:
    """Convert a CLI key value to an OpenCV key code."""
    normalized = raw_key.strip().lower()
    if not normalized:
        raise ValueError("Save key must not be empty.")

    special_keys = {
        "space": 32,
        "enter": 13,
        "tab": 9,
    }
    if normalized in special_keys:
        return special_keys[normalized]

    if len(normalized) != 1:
        raise ValueError(
            "Save key must be a single character or one of: space, enter, tab."
        )

    return ord(normalized)


def build_output_path(output_dir: Path) -> Path:
    """Build a unique file path for the next saved frame."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return output_dir / f"frame_{timestamp}.jpg"


def main() -> None:
    """Show the stream from Raspberry Pi and save frames on key press."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST, help="IP address of Raspberry Pi.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP server port.")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where captured frames will be saved.",
    )
    parser.add_argument(
        "--save-key",
        default=DEFAULT_SAVE_KEY,
        help="Key that saves the current frame. Examples: s, k, space.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    save_key = normalize_key(args.save_key)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((args.host, args.port))

    print(f"Connected to {args.host}:{args.port}")
    print(f"Save key: {args.save_key!r}")
    print(f"Output directory: {output_dir}")
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

            cv2.imshow(DEFAULT_WINDOW_NAME, frame)
            key = cv2.waitKey(1) & 0xFF

            if key == save_key:
                output_path = build_output_path(output_dir)
                if cv2.imwrite(str(output_path), frame):
                    print(f"Saved: {output_path}")
                else:
                    print(f"Failed to save frame: {output_path}")
            elif key in (27, ord("q")):
                break

    except KeyboardInterrupt:
        print("\nStopping...")

    finally:
        sock.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
