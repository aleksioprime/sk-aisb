"""Получение свежих кадров с USB-камеры."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

LOG = logging.getLogger(__name__)


class UsbCamera:
    """Непрерывно читать USB-камеру и хранить только последний кадр.

    Отдельный поток не даёт буферу камеры накапливать старые кадры, пока YOLO
    занят вычислениями. Потребитель получает копию кадра с новым номером.
    """

    def __init__(self, index: int, width: int, height: int, on_open=None):
        """on_open(device) вызывается после каждого открытия камеры, в том числе повторного."""
        self.index = index
        self.on_open = on_open
        self.width = width
        self.height = height
        self._condition = threading.Condition()
        self._frame = None
        self._sequence = 0
        self._stopped = threading.Event()
        self._thread = None
        self._capture = None
        self.device = f"/dev/video{index}"
        self.error: str | None = None

    def start(self) -> None:
        """Открыть V4L2-камеру и запустить фоновое чтение кадров."""
        if not self._open():
            raise RuntimeError(f"Не удалось открыть USB-камеру /dev/video{self.index}")
        self._thread = threading.Thread(target=self._reader, name="camera-reader", daemon=True)
        self._thread.start()

    def _candidates(self) -> list[str]:
        """Устройства для открытия: сначала заданный индекс, затем любые USB-камеры.

        После сброса USB камера часто получает другой номер /dev/videoN, поэтому
        дополнительно перебираются первые узлы камер из /dev/v4l/by-id.
        """
        devices = [f"/dev/video{self.index}"]
        for link in sorted(Path("/dev/v4l/by-id").glob("*-video-index0")):
            device = str(link.resolve())
            if device not in devices:
                devices.append(device)
        return devices

    def _open(self) -> bool:
        """Открыть первое работающее устройство камеры и настроить его."""
        import cv2

        for device in self._candidates():
            capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
            if not capture.isOpened():
                capture.release()
                continue
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            # Не все V4L2-драйверы учитывают эту настройку, но там, где учитывают,
            # она дополнительно уменьшает задержку видеопотока.
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._capture = capture
            self.device = device
            if self.on_open is not None:
                try:
                    self.on_open(device)
                except Exception:
                    # Настройки изображения не должны мешать получать кадры.
                    LOG.exception("Ошибка обработчика открытия камеры")
            return True
        return False

    def _reopen(self) -> None:
        """Закрыть потерянную камеру и пытаться открыть её заново до успеха."""
        LOG.warning("Камера %s не отвечает, переподключение", self.device)
        self._capture.release()
        while not self._stopped.is_set():
            if self._open():
                LOG.info("Камера снова подключена: %s", self.device)
                return
            self._stopped.wait(2)

    def _reader(self) -> None:
        """Фоновый цикл чтения; после десяти ошибок переподключает камеру."""
        failures = 0
        while not self._stopped.is_set():
            ok, frame = self._capture.read()
            if not ok or frame is None:
                failures += 1
                if failures >= 10:
                    self.error = "Камера не возвращает кадры"
                    self._reopen()
                    failures = 0
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

