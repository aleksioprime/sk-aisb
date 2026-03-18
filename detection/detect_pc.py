# minimal_detect_webcam.py
# Минимальная программа детекции из видеопотока (webcam) с YOLOv8 .pt
# Требования: pip install ultralytics opencv-python

from ultralytics import YOLO
import argparse
from pathlib import Path
import cv2

DEFAULT_MODEL_PATH = str(Path(__file__).resolve().parent / "example.pt")
DEFAULT_CONF = 0.50
DEFAULT_JPEG_QUALITY = 80

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
        default=DEFAULT_CONF,
        help="Порог confidence."
    )
    args = parser.parse_args()

    model = YOLO(args.model)
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), DEFAULT_JPEG_QUALITY]

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Не удалось открыть камеру (VideoCapture(0))")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        # Simulate the JPEG quality used in the Raspberry Pi stream for comparison.
        ok, encoded = cv2.imencode(".jpg", frame, encode_params)
        if not ok:
            continue

        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
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

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
