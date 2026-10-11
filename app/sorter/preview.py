"""Последний кадр камеры с разметкой для просмотра по сети."""

from __future__ import annotations

import threading


class FramePreview:
    """Хранить последний JPEG-кадр с рамками зоны обрезки и найденного объекта.

    Цикл зрения публикует кадры, веб-сервер раздаёт их как MJPEG-поток.
    Кадр кодируется только при наличии зрителей, чтобы не тратить CPU зря.
    """

    def __init__(self, quality: int = 70):
        self.quality = quality
        self._condition = threading.Condition()
        self._jpeg: bytes | None = None
        self._sequence = 0
        self._viewers = 0

    def publish(self, frame, crop: tuple[int, int, int, int], detection, rejected=None) -> None:
        """Нарисовать разметку на копии кадра и сохранить её как JPEG.

        ``crop`` - область распознавания (left, top, right, bottom) в координатах
        кадра, right и bottom не включаются;
        рамки ``detection`` и отсеянной ``rejected`` заданы в координатах
        обрезанного кадра.
        """
        if not self._viewers:
            return
        import cv2

        image = frame.copy()
        left, top, right, bottom = crop
        cv2.rectangle(image, (left, top), (right - 1, bottom - 1), (255, 200, 0), 2)
        for item, color, suffix in ((detection, (0, 255, 0), ""), (rejected, (0, 0, 255), " empty")):
            if item is None:
                continue
            x1, y1, x2, y2 = item.box
            cv2.rectangle(image, (left + x1, top + y1), (left + x2, top + y2), color, 2)
            label = f"{item.class_name} {item.confidence:.2f}{suffix}"
            cv2.putText(image, label, (left + x1, max(15, top + y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
        if not ok:
            return
        with self._condition:
            self._jpeg = encoded.tobytes()
            self._sequence += 1
            self._condition.notify_all()

    def next_jpeg(self, previous_sequence: int, timeout: float = 2.0):
        """Дождаться кадра новее ``previous_sequence``; вернуть (номер, JPEG или None)."""
        with self._condition:
            self._condition.wait_for(lambda: self._sequence != previous_sequence, timeout=timeout)
            if self._jpeg is None or self._sequence == previous_sequence:
                return previous_sequence, None
            return self._sequence, self._jpeg

    def add_viewer(self) -> None:
        """Отметить подключение зрителя потока."""
        with self._condition:
            self._viewers += 1

    def remove_viewer(self) -> None:
        """Отметить отключение зрителя потока."""
        with self._condition:
            self._viewers = max(0, self._viewers - 1)
