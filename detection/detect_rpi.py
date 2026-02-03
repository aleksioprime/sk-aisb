from time import time
import argparse

import cv2
from ultralytics import YOLO
from picamera2 import Picamera2

# ======================
# Глобальные настройки
# ======================

MODEL_PATH = "example.pt"

CONF_THRES = 0.35
IMG_SIZE = 320

CAMERA_SIZE = (640, 480)

PRINT_EVERY_SEC = 1.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Без окна (подходит для SSH/без GUI). Если указан — imshow/waitKey не вызываются."
    )
    args = parser.parse_args()

    print("Loading YOLO model...")
    model = YOLO(MODEL_PATH)

    print("Starting Picamera2...")
    picam2 = Picamera2()
    config = picam2.create_preview_configuration(
        main={"size": CAMERA_SIZE, "format": "RGB888"}
    )
    picam2.configure(config)
    picam2.start()

    print("Camera started. Inference running...\n")

    last_print = 0.0

    try:
        while True:
            # 1) Захват (RGB)
            frame_rgb = picam2.capture_array()

            # 3) Для инференса делаем BGR
            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

            # 4) Инференс
            t0 = time()
            results = model(
                frame_rgb,
                conf=CONF_THRES,
                imgsz=IMG_SIZE,
                verbose=False
            )
            infer_ms = (time() - t0) * 1000.0

            r0 = results[0]
            boxes = r0.boxes
            n = int(boxes.shape[0]) if boxes is not None else 0

            # 5) Печать раз в секунду
            now = time()
            if now - last_print >= PRINT_EVERY_SEC:
                h, w = frame_bgr.shape[:2]
                print(f"Frame: {w}x{h} | det={n} | infer={infer_ms:.1f} ms")

                if n > 0:
                    cls_ids = boxes.cls.tolist()
                    confs = boxes.conf.tolist()
                    for i, (cid, cf) in enumerate(zip(cls_ids, confs), 1):
                        name = model.names.get(int(cid), str(int(cid)))
                        print(f"  {i:02d}. {name}  conf={cf:.2f}")

                last_print = now

            # 6) Показ (если НЕ headless)
            if not args.headless:
                # plot() возвращает BGR-кадр — его можно сразу показывать через imshow()
                annotated_bgr = r0.plot()
                cv2.imshow("YOLO detect", annotated_bgr)

                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break

    except KeyboardInterrupt:
        print("\nStopping...")

    finally:
        picam2.stop()
        if not args.headless:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
