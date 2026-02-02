from time import sleep, time
import cv2
from picamera2 import Picamera2
from ultralytics import YOLO

MODEL_PATH = "yolov8n.pt"
IMG_SIZE = 256
CAMERA_SIZE = (640, 480)

print("Loading YOLO model...")
model = YOLO(MODEL_PATH)

picam2 = Picamera2()
config = picam2.create_preview_configuration(
    main={"size": CAMERA_SIZE, "format": "RGB888"}
)
picam2.configure(config)
picam2.start()
sleep(1.0)

print("Camera started. Inference running...\n")

try:
    while True:
        t0 = time()

        frame_rgb = picam2.capture_array()

        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

        results = model(
            frame_bgr,
            imgsz=IMG_SIZE,
            verbose=False,
            save=False
        )

        boxes = results[0].boxes
        dt = time() - t0

        if boxes is not None and len(boxes) > 0:
            names = results[0].names
            classes = boxes.cls.cpu().numpy()
            confs = boxes.conf.cpu().numpy()

            detected = [
                f"{names[int(c)]} ({p:.2f})"
                for c, p in zip(classes, confs)
            ]

            print(f"Detected: {', '.join(detected)} | Time: {dt:.2f}s")
        else:
            print(f"Detected: none | Time: {dt:.2f}s")

        sleep(0.1)

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    picam2.stop()
