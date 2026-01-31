#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import time

import cv2
from ultralytics import YOLO
from picamera2 import Picamera2

# =========================
# ГЛОБАЛЬНЫЕ НАСТРОЙКИ
# =========================

# Разрешение видеопотока (чем меньше — тем быстрее)
WIDTH = 640
HEIGHT = 480

# Формат кадра: стараемся получить BGR для OpenCV/YOLO без конверта,
# если не выйдет — берём RGB и конвертируем.
PREFERRED_FORMATS = ("BGR888", "RGB888")

# Частота (libcamera старается держать, но это не “жёстко” как в USB)
TARGET_FPS = 30

# YOLO параметры
IMGSZ = 320        # 256/320 быстрее на Zero 2 W
CONF = 0.35
IOU = 0.45
MAX_DET = 50

# Производительность
EVERY_N = 2        # инференс раз в N кадров (2..5 сильно ускоряет)
SHOW_FPS = True

# =========================


def parse_args():
    p = argparse.ArgumentParser("Minimal YOLOv8 + Picamera2 (CSI) detector")
    p.add_argument("--model", type=str, default="yolov8n.pt", help="Путь к модели .pt")
    p.add_argument("--view", action="store_true", help="Показывать окно с результатом")
    return p.parse_args()


def pick_format(pic: Picamera2):
    """
    Выбираем самый удобный формат из PREFERRED_FORMATS.
    """
    # Picamera2 обычно принимает строку формата напрямую в конфиге,
    # но поддержка зависит от камеры/драйвера.
    for fmt in PREFERRED_FORMATS:
        try:
            # пробуем создать конфигурацию с этим форматом
            config = pic.create_video_configuration(
                main={"size": (WIDTH, HEIGHT), "format": fmt},
                controls={"FrameRate": TARGET_FPS},
                buffer_count=4,
            )
            return config, fmt
        except Exception:
            continue

    # Фолбэк: пусть Picamera2 выберет формат сам (часто RGB888)
    config = pic.create_video_configuration(
        main={"size": (WIDTH, HEIGHT)},
        controls={"FrameRate": TARGET_FPS},
        buffer_count=4,
    )
    # формат узнаем позже по первому кадру
    return config, None


def main():
    args = parse_args()

    # Модель
    model = YOLO(args.model)

    # Камера через libcamera
    picam2 = Picamera2(0)

    config, fmt = pick_format(picam2)
    picam2.configure(config)
    picam2.start()

    frame_i = 0
    last_t = time.time()
    fps_smooth = 0.0
    last_infer_ms = None

    try:
        while True:
            frame_i += 1

            # Кадр (numpy array)
            frame = picam2.capture_array()

            # Определим формат, если не знали
            # Часто кадр приходит как RGB, а OpenCV/plot ждут BGR.
            # Если мы не уверены, безопасно привести к BGR:
            # - если кадр уже BGR, cvtColor “испортит”
            # Поэтому делаем так:
            #   - если явно выбрали BGR888 — не конвертируем
            #   - иначе считаем, что это RGB и конвертируем в BGR
            if fmt == "BGR888":
                frame_bgr = frame
            else:
                # большинство случаев: RGB888
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

            do_infer = (frame_i % EVERY_N == 0)

            if do_infer:
                t0 = time.time()
                results = model.predict(
                    source=frame_bgr,
                    imgsz=IMGSZ,
                    conf=CONF,
                    iou=IOU,
                    max_det=MAX_DET,
                    device="cpu",
                    verbose=False
                )
                last_infer_ms = (time.time() - t0) * 1000.0
                annotated = results[0].plot()  # рисует боксы/подписи
            else:
                annotated = frame_bgr

            # FPS (сглаженный)
            now = time.time()
            dt = now - last_t
            last_t = now
            inst_fps = (1.0 / dt) if dt > 0 else 0.0
            fps_smooth = fps_smooth * 0.9 + inst_fps * 0.1

            if SHOW_FPS:
                txt = f"FPS: {fps_smooth:.1f}"
                if last_infer_ms is not None and do_infer:
                    txt += f" | infer: {last_infer_ms:.1f} ms"
                cv2.putText(annotated, txt, (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(annotated, txt, (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)

            if args.view:
                cv2.imshow("YOLOv8 (Picamera2)", annotated)
                # ESC — выход
                if cv2.waitKey(1) & 0xFF == 27:
                    break

    finally:
        picam2.stop()
        if args.view:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
