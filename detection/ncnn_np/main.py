#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Минимальный и практичный детектор YOLOv8 (NCNN) на Raspberry Pi с CSI-камерой через Picamera2.

Почему так:
- PyTorch на Raspberry часто нестабилен/тяжёлый.
- NCNN — легковесный и быстрый runtime под ARM.
- Picamera2 — самый надёжный способ получать кадры с CSI (libcamera).

CLI:
  --view   показывать окно с боксами (для отладки)

Все остальные параметры — глобальные переменные ниже.
"""

import argparse
import time
from typing import List, Tuple

import cv2
import numpy as np
import ncnn
from picamera2 import Picamera2

# =========================
# ГЛОБАЛЬНЫЕ НАСТРОЙКИ
# =========================

# Пути к NCNN-модели (экспорт из Ultralytics: format=ncnn)
MODEL_DIR   = "/home/pi/yolov8n_ncnn_model"
PARAM_PATH  = MODEL_DIR + "/model.ncnn.param"
BIN_PATH    = MODEL_DIR + "/model.ncnn.bin"

# Имена входного/выходного blob (часто in0/out0, но бывает иначе!)
IN_BLOB  = "in0"
OUT_BLOB = "out0"

# Камера (Picamera2)
CAMERA_INDEX = 0
WIDTH, HEIGHT = 640, 480
FORMAT = "RGB888"     # Picamera2 отдаёт RGB — удобно: меньше преобразований

# Параметры YOLOv8
INPUT_SIZE = 320      # ДОЛЖЕН совпадать с imgsz при export!
NUM_CLASSES = 80      # COCO=80; для кастомной модели поменяй
CONF_THRES = 0.35
NMS_THRES  = 0.45

# Производительность
NUM_THREADS = 2       # Zero 2 W: 2 (часто оптимально); RPi4: 4

# =========================


# Тип детекции: (box_xyxy, class_id, score)
Det = Tuple[np.ndarray, int, float]


def parse_args() -> argparse.Namespace:
    """
    Оставляем только режим просмотра через CLI.
    """
    p = argparse.ArgumentParser("Picamera2 + NCNN YOLOv8 detector")
    p.add_argument("--view", action="store_true", help="Показывать окно и рисовать боксы")
    return p.parse_args()


# ---------- Вспомогательные функции постобработки ----------

def sigmoid(x: np.ndarray) -> np.ndarray:
    """
    Сигмоида для class logits (YOLOv8 head часто выдаёт логиты).
    """
    return 1.0 / (1.0 + np.exp(-x))


def nms(boxes: np.ndarray, scores: np.ndarray, iou_thr: float) -> List[int]:
    """
    Non-Max Suppression на CPU.
    boxes: [N,4] в формате xyxy
    scores: [N]
    Возвращает индексы оставшихся боксов.
    """
    if boxes.size == 0:
        return []

    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]

    keep = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)

        inds = np.where(iou <= iou_thr)[0]
        order = order[inds + 1]

    return keep


def letterbox_rgb(im_rgb: np.ndarray, new_size: int) -> Tuple[np.ndarray, float, int, int]:
    """
    Letterbox (resize + padding) как в YOLO:
    - сохраняем пропорции
    - дополняем серым цветом до квадрата new_size x new_size

    Возвращает:
      padded_rgb, scale, pad_left, pad_top
    """
    h, w = im_rgb.shape[:2]
    r = min(new_size / w, new_size / h)
    nw, nh = int(round(w * r)), int(round(h * r))

    # resize - один из заметных CPU-расходов, но необходим для стабильной детекции
    resized = cv2.resize(im_rgb, (nw, nh), interpolation=cv2.INTER_LINEAR)

    pad_w = new_size - nw
    pad_h = new_size - nh
    left = pad_w // 2
    top = pad_h // 2

    out = cv2.copyMakeBorder(
        resized,
        top, pad_h - top,
        left, pad_w - left,
        cv2.BORDER_CONSTANT,
        value=(114, 114, 114)
    )
    return out, r, left, top


def decode_yolov8(out_mat: "ncnn.Mat") -> List[Det]:
    """
    Декодирование типичного вывода YOLOv8 detect-head в NCNN.

    Ожидаем shape:
    - либо (C, N) где C = 4 + NUM_CLASSES
    - либо (N, C)

    Где 4 = cx, cy, w, h
    И далее идут logits классов (применяем sigmoid).
    """
    out = np.array(out_mat)  # ncnn.Mat -> numpy (важный шаг, но это нормально)

    if out.ndim != 2:
        return []

    # Приводим к (N, C)
    C_expected = 4 + NUM_CLASSES
    if out.shape[0] == C_expected:
        out = out.T
    elif out.shape[1] != C_expected:
        # если здесь пусто — чаще всего:
        # - неверный OUT_BLOB
        # - другая модель (seg/obb)
        # - другой layout выхода
        return []

    boxes_cxcywh = out[:, :4]
    cls_logits = out[:, 4:]

    cls_scores = sigmoid(cls_logits)           # [N, num_classes]
    scores = cls_scores.max(axis=1)            # [N]
    labels = cls_scores.argmax(axis=1)         # [N]

    # confidence filter
    m = scores >= CONF_THRES
    boxes_cxcywh = boxes_cxcywh[m]
    scores = scores[m]
    labels = labels[m]

    if boxes_cxcywh.shape[0] == 0:
        return []

    # cxcywh -> xyxy
    cx, cy, w, h = boxes_cxcywh.T
    x1 = cx - w / 2
    y1 = cy - h / 2
    x2 = cx + w / 2
    y2 = cy + h / 2
    boxes_xyxy = np.stack([x1, y1, x2, y2], axis=1)

    keep = nms(boxes_xyxy, scores, NMS_THRES)
    return [(boxes_xyxy[i], int(labels[i]), float(scores[i])) for i in keep]


# ---------- Инференс NCNN вынесен в отдельную функцию ----------

def infer_yolov8_ncnn(
    net: "ncnn.Net",
    frame_rgb: np.ndarray
) -> Tuple[List[Det], float, int, int]:
    """
    Полный цикл инференса:
    1) letterbox RGB -> INPUT_SIZE
    2) преобразование в ncnn.Mat
    3) нормализация [0..1]
    4) net forward -> out
    5) decode + NMS

    Возвращает:
      detections, scale, pad_left, pad_top

    Важно:
    - координаты боксов det'ов находятся в системе координат letterbox-изображения (INPUT_SIZE x INPUT_SIZE),
      поэтому для рисования/использования на исходном кадре нужно выполнить обратное преобразование.
    """
    # 1) preprocess: letterbox
    lb_rgb, r, pad_left, pad_top = letterbox_rgb(frame_rgb, INPUT_SIZE)

    # 2) RGB pixels -> NCNN Mat
    # Здесь нет конвертации цветов: Picamera2 уже отдаёт RGB.
    mat_in = ncnn.Mat.from_pixels(
        lb_rgb,
        ncnn.Mat.PixelType.PIXEL_RGB,
        INPUT_SIZE,
        INPUT_SIZE
    )

    # 3) normalize to [0..1]
    # mean=None, norm=(1/255,1/255,1/255)
    mat_in.substract_mean_normalize(None, (1/255.0, 1/255.0, 1/255.0))

    # 4) forward
    ex = net.create_extractor()
    # light_mode уменьшает пиковую память (актуально для Raspberry)
    ex.set_light_mode(True)

    # Вход/выход — по именам blob'ов из .param
    ex.input(IN_BLOB, mat_in)
    ret, out = ex.extract(OUT_BLOB)
    if ret != 0:
        raise RuntimeError(
            "NCNN extract failed. Проверь OUT_BLOB/IN_BLOB в .param файле."
        )

    # 5) decode
    dets = decode_yolov8(out)
    return dets, r, pad_left, pad_top


def draw_detections_bgr(
    frame_bgr: np.ndarray,
    dets: List[Det],
    r: float,
    pad_left: int,
    pad_top: int
) -> None:
    """
    Рисование боксов на кадре.
    Вызывается ТОЛЬКО если view=True.
    """
    h, w = frame_bgr.shape[:2]

    for (box, cls, score) in dets:
        x1, y1, x2, y2 = box

        # обратное преобразование letterbox -> оригинальный кадр
        x1 = (x1 - pad_left) / r
        y1 = (y1 - pad_top) / r
        x2 = (x2 - pad_left) / r
        y2 = (y2 - pad_top) / r

        # clamp
        x1 = int(max(0, min(w - 1, x1)))
        y1 = int(max(0, min(h - 1, y1)))
        x2 = int(max(0, min(w - 1, x2)))
        y2 = int(max(0, min(h - 1, y2)))

        cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            frame_bgr,
            f"{cls}:{score:.2f}",
            (x1, max(0, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA
        )


def load_ncnn_net() -> "ncnn.Net":
    """
    Загружаем сеть один раз.
    """
    net = ncnn.Net()
    net.opt.num_threads = NUM_THREADS
    # Vulkan можно включать только если ты ставил ncnn-vulkan и у тебя есть поддержка:
    # net.opt.use_vulkan_compute = True

    if net.load_param(PARAM_PATH) != 0:
        raise RuntimeError("load_param failed: проверь PARAM_PATH")
    if net.load_model(BIN_PATH) != 0:
        raise RuntimeError("load_model failed: проверь BIN_PATH")

    return net


def init_camera() -> Picamera2:
    """
    Инициализация CSI-камеры.
    Используем конфигурацию preview — это обычно самый стабильный поток.
    """
    cam = Picamera2(CAMERA_INDEX)
    cam.preview_configuration.main.size = (WIDTH, HEIGHT)
    cam.preview_configuration.main.format = FORMAT
    cam.preview_configuration.align()
    cam.configure("preview")
    cam.start()
    # маленькая пауза, чтобы камера “прогрелась”
    time.sleep(0.2)
    return cam


def main():
    args = parse_args()
    view = args.view

    net = load_ncnn_net()
    cam = init_camera()

    try:
        while True:
            # Picamera2 отдаёт RGB numpy array
            frame_rgb = cam.capture_array()

            # Инференс (вся логика внутри функции)
            dets, r, pad_left, pad_top = infer_yolov8_ncnn(net, frame_rgb)

            if view:
                # Только если view: конвертим в BGR и рисуем.
                # Если view=False — не делаем НИЧЕГО лишнего.
                frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                draw_detections_bgr(frame_bgr, dets, r, pad_left, pad_top)
                cv2.imshow("YOLOv8 NCNN (Picamera2)", frame_bgr)

                # ESC — выход
                if cv2.waitKey(1) & 0xFF == 27:
                    break

    finally:
        cam.stop()
        if view:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
