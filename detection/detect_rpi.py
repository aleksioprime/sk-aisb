from time import sleep, time
import argparse

import cv2
from ultralytics import YOLO
from picamera2 import Picamera2

# ======================
# Глобальные настройки
# ======================

DEFAULT_MODEL_PATH = "example.pt"

DEFAULT_CONF_THRES = 0.50
DEFAULT_IMG_SIZE = None

DEFAULT_CAMERA_SIZE = (640, 480)
DEFAULT_WARMUP_SEC = 1.0

PRINT_EVERY_SEC = 1.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_PATH,
        help="Путь к файлу весов YOLO (.pt)."
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=DEFAULT_CONF_THRES,
        help="Порог confidence. Для уменьшения ложных классов обычно повышают до 0.5-0.7."
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=DEFAULT_IMG_SIZE,
        help="Размер входа YOLO. Если не указан, используется поведение модели по умолчанию."
    )
    parser.add_argument(
        "--camera-width",
        type=int,
        default=DEFAULT_CAMERA_SIZE[0],
        help="Ширина кадра Picamera2."
    )
    parser.add_argument(
        "--camera-height",
        type=int,
        default=DEFAULT_CAMERA_SIZE[1],
        help="Высота кадра Picamera2."
    )
    parser.add_argument(
        "--warmup-sec",
        type=float,
        default=DEFAULT_WARMUP_SEC,
        help="Сколько секунд подождать после запуска камеры для автоэкспозиции и AWB."
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Без окна (подходит для SSH/без GUI). Если указан — imshow/waitKey не вызываются."
    )
    args = parser.parse_args()

    print("Loading YOLO model...")
    model = YOLO(args.model)

    print("Starting Picamera2...")
    picam2 = Picamera2()
    camera_size = (args.camera_width, args.camera_height)
    config = picam2.create_video_configuration(
        main={"size": camera_size, "format": "RGB888"}
    )
    picam2.configure(config)
    picam2.start()
    sleep(args.warmup_sec)

    print("Camera started. Inference running...\n")

    last_print = 0.0

    try:
        while True:
            # RGB888 from Picamera2 already matches the channel order expected by OpenCV.
            frame = picam2.capture_array()

            # 4) Инференс
            t0 = time()
            predict_kwargs = {
                "conf": args.conf,
                "verbose": False,
            }
            if args.imgsz is not None:
                predict_kwargs["imgsz"] = args.imgsz

            results = model(frame, **predict_kwargs)
            infer_ms = (time() - t0) * 1000.0

            r0 = results[0]
            boxes = r0.boxes
            n = int(boxes.shape[0]) if boxes is not None else 0

            # 5) Печать раз в секунду
            now = time()
            if now - last_print >= PRINT_EVERY_SEC:
                h, w = frame.shape[:2]
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
