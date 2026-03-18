import socket
import struct
from time import sleep

import cv2
from picamera2 import Picamera2


HOST = "0.0.0.0"
PORT = 5000
CAMERA_SIZE = (640, 480)
JPEG_QUALITY = 80
WARMUP_SEC = 1.0


def main() -> None:
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

    print(f"Listening on {HOST}:{PORT}...")
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]

    try:
        while True:
            conn, addr = server.accept()
            print(f"Connected: {addr[0]}:{addr[1]}")

            try:
                while True:
                    # For Picamera2/OpenCV, RGB888 already arrives in the channel
                    # order expected by OpenCV functions.
                    frame = picam2.capture_array()

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


if __name__ == "__main__":
    main()
