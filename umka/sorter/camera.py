"""Получение свежих кадров с USB-камеры и обрезка рабочей области."""

from __future__ import annotations

import threading
import time


class UsbCamera:
    """Непрерывно читать USB-камеру и хранить только последний кадр.

    Отдельный поток не даёт буферу камеры накапливать старые кадры, пока YOLO
    занят вычислениями. Потребитель получает копию кадра с новым номером.
    """

    def __init__(self, index: int, width: int, height: int):
        self.index = index
        self.width = width
        self.height = height
        self._condition = threading.Condition()
        self._frame = None
        self._sequence = 0
        self._stopped = threading.Event()
        self._thread = None
        self._capture = None
        self.error: str | None = None

    def start(self) -> None:
        """Открыть V4L2-камеру и запустить фоновое чтение кадров."""
        import cv2

        self._capture = cv2.VideoCapture(self.index, cv2.CAP_V4L2)
        if not self._capture.isOpened():
            self._capture.release()
            raise RuntimeError(f"Не удалось открыть USB-камеру /dev/video{self.index}")
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        # Не все V4L2-драйверы учитывают эту настройку, но там, где учитывают,
        # она дополнительно уменьшает задержку видеопотока.
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._thread = threading.Thread(target=self._reader, name="camera-reader", daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        """Фоновый цикл чтения; после десяти ошибок публикует диагностику."""
        failures = 0
        while not self._stopped.is_set():
            ok, frame = self._capture.read()
            if not ok or frame is None:
                failures += 1
                if failures >= 10:
                    self.error = "Камера не возвращает кадры"
                time.sleep(0.05)
                continue
            failures = 0
            self.error = None
            with self._condition:
                # Старый кадр намеренно перезаписывается: обработка каждого
                # кадра менее важна, чем реакция системы на текущее изображение.
                self._frame = frame
                self._sequence += 1
                self._condition.notify_all()

    def next_frame(self, previous_sequence: int, timeout: float = 2.0):
        """Дождаться кадра новее ``previous_sequence`` или вернуть ``None``."""
        with self._condition:
            self._condition.wait_for(
                lambda: self._sequence != previous_sequence or self._stopped.is_set(),
                timeout=timeout,
            )
            if self._frame is None or self._sequence == previous_sequence:
                return previous_sequence, None
            return self._sequence, self._frame.copy()

    def close(self) -> None:
        """Остановить поток чтения и освободить устройство камеры."""
        self._stopped.set()
        with self._condition:
            self._condition.notify_all()
        if self._thread:
            self._thread.join(timeout=2)
        if self._capture:
            self._capture.release()


def crop_frame(frame, config):
    """Обрезать кадр до площадки, не допуская пустого массива."""
    height, width = frame.shape[:2]
    top = max(0, min(config.crop_top, height))
    bottom = max(0, min(config.crop_bottom, height - top))
    left = max(0, min(config.crop_left, width))
    right = max(0, min(config.crop_right, width - left))
    cropped = frame[top:height - bottom, left:width - right]
    return cropped if cropped.size else frame
