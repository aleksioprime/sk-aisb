from time import sleep, time
from picamera2 import Picamera2

CAMERA_SIZE = (640, 480)

picam2 = Picamera2()
config = picam2.create_preview_configuration(
    main={"size": CAMERA_SIZE, "format": "RGB888"}
)
picam2.configure(config)
picam2.start()

print("Camera started. Capturing frames...\n")

last_time = 0.0

try:
    while True:
        frame = picam2.capture_array()

        now = time()
        if now - last_time >= 1.0:
            h, w, c = frame.shape
            print(f"Frame: {w}x{h} | Channels: {c}")
            last_time = now

        sleep(0.1)

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    picam2.stop()