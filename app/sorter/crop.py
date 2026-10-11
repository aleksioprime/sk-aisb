"""Область распознавания: отступы площадки от краёв кадра камеры."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path


LOG = logging.getLogger(__name__)

SIDES = ("top", "bottom", "left", "right")


class CropArea:
    """Хранить отступы обрезки и менять их на ходу со страницы настроек.

    Значения по умолчанию берутся из AppConfig.crop_*, а сохранённые на странице
    настроек - из файла, который при запуске заменяет значения по умолчанию.
    """

    def __init__(self, config):
        self.path: Path = config.crop_path
        self.defaults = {side: getattr(config, f"crop_{side}") for side in SIDES}
        self._lock = threading.Lock()
        self._margins = dict(self.defaults)
        self.frame_size: tuple[int, int] | None = None  # (ширина, высота) последнего кадра.
        self._load()

    def _load(self) -> None:
        """Загрузить сохранённые отступы, если файл есть и корректен."""
        if not self.path.is_file():
            return
        try:
            self._margins = self._validate(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            LOG.error("Область распознавания %s не загружена: %s", self.path, exc)
            return
        LOG.info("Область распознавания загружена: %s", self.path)

    @staticmethod
    def _validate(data: dict) -> dict:
        """Проверить, что все четыре отступа - неотрицательные целые пиксели."""
        margins = {}
        for side in SIDES:
            value = data[side]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"Отступ {side} должен быть неотрицательным числом")
            margins[side] = int(round(value))
        return margins

    def snapshot(self) -> dict:
        """Вернуть текущие отступы, значения по умолчанию и размер кадра."""
        with self._lock:
            margins = dict(self._margins)
        width, height = self.frame_size or (None, None)
        return {**margins, "defaults": dict(self.defaults), "frameWidth": width, "frameHeight": height}

    def save(self, data: dict) -> dict:
        """Применить новые отступы сразу и записать их в файл."""
        margins = self._validate(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(margins, indent=2), encoding="utf-8")
        temporary.replace(self.path)
        with self._lock:
            self._margins = margins
        LOG.info("Область распознавания сохранена: %s", margins)
        return self.snapshot()

    def rect(self, frame) -> tuple[int, int, int, int]:
        """Вернуть область (left, top, right, bottom) в координатах кадра; right/bottom не включаются.

        Слишком большие отступы ограничиваются так, чтобы область не стала пустой.
        """
        height, width = frame.shape[:2]
        self.frame_size = (width, height)
        with self._lock:
            margins = dict(self._margins)
        top = min(margins["top"], height - 1)
        bottom = min(margins["bottom"], height - top - 1)
        left = min(margins["left"], width - 1)
        right = min(margins["right"], width - left - 1)
        return left, top, width - right, height - bottom

    def apply(self, frame):
        """Вернуть кадр, обрезанный до области распознавания, и саму область."""
        left, top, right, bottom = area = self.rect(frame)
        return frame[top:bottom, left:right], area
