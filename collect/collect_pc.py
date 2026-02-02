# Программа для захвата стоп-кадров с веб-камеры ПК
# и сохранения их в папку "snapshots" в домашней директории пользователя

import cv2
from datetime import datetime
import os

def center_crop_to_aspect(frame, target_w, target_h):
    h, w = frame.shape[:2]
    target_aspect = target_w / target_h
    cur_aspect = w / h

    if cur_aspect > target_aspect:
        # слишком широко — режем по ширине
        new_w = int(h * target_aspect)
        x1 = (w - new_w) // 2
        return frame[:, x1:x1 + new_w]
    else:
        # слишком высоко — режем по высоте
        new_h = int(w / target_aspect)
        y1 = (h - new_h) // 2
        return frame[y1:y1 + new_h, :]


def main():
    # Папка для снимков
    base_dir = os.path.dirname(os.path.abspath(__file__))
    snapshots_dir = os.path.join(base_dir, "snapshots")
    os.makedirs(snapshots_dir, exist_ok=True)

    # Инициализация камеры
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Не удалось открыть камеру")

    # cap.set(cv2.CAP_PROP_FRAME_WIDTH, 800)
    # cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 600)

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Текущее разрешение: {w}x{h}")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Не удалось получить кадр")
                break

            frame = center_crop_to_aspect(frame, 800, 600)

            cv2.imshow("Preview", frame)

            key = cv2.waitKey(1) & 0xFF

            if key == 13:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                filepath = os.path.join(snapshots_dir, f"img_{timestamp}.jpg")
                cv2.imwrite(filepath, frame)
                print(f"Снимок сохранён: {filepath}")

            elif key == ord("q"):
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Программа завершена")


if __name__ == "__main__":
    main()
