# minimal_detect_webcam.py
# Минимальная программа детекции из видеопотока (webcam) с YOLOv8 .pt
# Требования: pip install ultralytics opencv-python

from ultralytics import YOLO
import cv2

MODEL_PATH = "example.pt"

def main():
    model = YOLO(MODEL_PATH)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Не удалось открыть камеру (VideoCapture(0))")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        # Инференс
        results = model(frame, conf=0.50, verbose=False)

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
