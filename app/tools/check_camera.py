#!/usr/bin/env python3
"""Проверить USB-камеру отдельно от приложения: кадр, частоту и засветку.

Перед запуском остановите UMKA: камеру может открыть только один процесс.

    python tools/check_camera.py
    python tools/check_camera.py --camera 2 --frames 60

Снимок сохраняется в data/camera-check.jpg. Доля пересвеченных пикселей
помогает подобрать яркость и контраст против бликов (вкладка «Камера»
в настройках).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from sorter import launch_config  # noqa: E402
from sorter.camera_controls import CameraControls  # noqa: E402


def parse_args(argv=None) -> argparse.Namespace:
    """Разобрать номер камеры и число кадров для замера."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--camera", type=int, default=0, help="Номер /dev/videoN")
    parser.add_argument("--frames", type=int, default=30, help="Сколько кадров читать для замера частоты")
    parser.add_argument("--output", type=Path, default=APP_DIR / "data" / "camera-check.jpg")
    config = launch_config.load()
    if "camera" in config:
        parser.set_defaults(camera=config["camera"])
    return parser.parse_args(argv)


def main(argv=None) -> int:
    """Открыть камеру, прочитать кадры, сохранить снимок и вывести сводку."""
    args = parse_args(argv)
    import cv2

    device = f"/dev/video{args.camera}"
    print("USB-камеры:", ", ".join(str(path.resolve()) for path in Path("/dev/v4l/by-id").glob("*"))
          if Path("/dev/v4l/by-id").exists() else "каталог /dev/v4l/by-id не найден")
    capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not capture.isOpened():
        print(f"Не удалось открыть {device}. Камера занята UMKA или номер другой.")
        return 1
    try:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        frame = None
        started = time.monotonic()
        received = 0
        for _ in range(args.frames):
            ok, image = capture.read()
            if ok and image is not None:
                frame = image
                received += 1
        elapsed = time.monotonic() - started
    finally:
        capture.release()
    if frame is None:
        print(f"{device} открылась, но не вернула ни одного кадра. Проверьте кабель и питание USB.")
        return 1

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    overexposed = float((gray >= 250).mean() * 100)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.output), frame)
    height, width = frame.shape[:2]
    print(f"Камера {device}: {width}×{height}, кадров {received}/{args.frames}, "
          f"≈{received / elapsed:.1f} кадр/с")
    print(f"Средняя яркость {gray.mean():.0f} из 255, пересвечено {overexposed:.1f}% пикселей"
          + (" - много бликов: уменьшите яркость, контраст или гамму" if overexposed > 5 else ""))
    print(f"Снимок: {args.output}")

    controls = CameraControls(APP_DIR / "data" / "camera_controls.json")
    controls.device = device
    try:
        listed = controls.list()
    except RuntimeError as exc:
        print(f"Параметры камеры недоступны: {exc}")
    else:
        print("Параметры камеры:", ", ".join(f"{item['name']}={item['value']}" for item in listed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
