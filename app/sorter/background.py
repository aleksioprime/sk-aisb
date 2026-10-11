"""Отсев ложных детекций по набору снимков пустой площадки."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path


LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Reference:
    """Один снимок пустой площадки: исходный кадр на диске и подготовленная копия."""

    id: str
    created: float
    prepared: object  # Сглаженный серый кадр numpy для сравнения.


class EmptyPlatformFilter:
    """Сравнивать рамку детекции с набором снимков пустой площадки.

    Модель может принимать блики и дно площадки за предмет. Настоящий предмет
    заметно меняет изображение внутри рамки, а ложное срабатывание - нет.
    Блики зависят от людей вокруг, поэтому снимков может быть несколько:
    рамка считается пустой, если совпадает хотя бы с одним из них.
    Снимки хранятся для всего кадра, поэтому изменение области распознавания
    их не портит. Без снимков фильтр пропускает все детекции.
    """

    MAX_REFERENCES = 30  # Старые снимки сверх этого числа удаляются.

    def __init__(self, directory: Path, threshold: float, legacy_path: Path | None = None):
        self.directory = directory
        self.threshold = threshold
        self._lock = threading.Lock()
        self._references: list[Reference] = []
        self._pending = 0
        self._load(legacy_path)

    @staticmethod
    def _prepare(frame):
        """Привести кадр к сглаженному серому изображению для сравнения."""
        import cv2

        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gray, (21, 21), 0)

    def _load(self, legacy_path: Path | None) -> None:
        """Загрузить снимки из каталога; одиночный эталон прошлых версий перенести в него."""
        import cv2

        self.directory.mkdir(parents=True, exist_ok=True)
        if legacy_path is not None and legacy_path.is_file():
            legacy_path.replace(self.directory / f"{int(legacy_path.stat().st_mtime * 1000)}.png")
            LOG.info("Эталон %s перенесён в набор %s", legacy_path, self.directory)
        references = []
        for path in sorted(self.directory.glob("*.png")):
            image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if image is None:
                LOG.warning("Снимок пустой площадки не прочитан: %s", path)
                continue
            references.append(Reference(path.stem, path.stat().st_mtime, self._prepare(image)))
        self._references = references
        if references:
            LOG.info("Снимков пустой площадки: %d", len(references))

    @property
    def count(self) -> int:
        """Сколько снимков пустой площадки в наборе."""
        return len(self._references)

    @property
    def has_reference(self) -> bool:
        """Есть ли хотя бы один снимок для сравнения."""
        return bool(self._references)

    def request_capture(self, count: int = 1) -> None:
        """Добавить в набор ``count`` следующих кадров цикла зрения."""
        with self._lock:
            self._pending += max(1, count)

    def capture_if_requested(self, frame) -> bool:
        """Сохранить кадр в набор, если об этом просили; вернуть True при съёмке."""
        with self._lock:
            if not self._pending:
                return False
            self._pending -= 1
        import cv2

        created = time.time()
        reference_id = str(int(created * 1000))
        path = self.directory / f"{reference_id}.png"
        cv2.imwrite(str(path), frame)
        with self._lock:
            references = self._references + [Reference(reference_id, created, self._prepare(frame))]
            while len(references) > self.MAX_REFERENCES:
                (self.directory / f"{references.pop(0).id}.png").unlink(missing_ok=True)
            self._references = references
        LOG.info("Добавлен снимок пустой площадки %s (всего %d)", reference_id, len(references))
        return True

    def items(self) -> list[dict]:
        """Вернуть список снимков: id и время съёмки."""
        return [{"id": item.id, "created": item.created} for item in self._references]

    def delete(self, reference_id: str) -> None:
        """Удалить один снимок из набора и с диска."""
        with self._lock:
            references = [item for item in self._references if item.id != reference_id]
            if len(references) == len(self._references):
                raise ValueError("Снимок не найден")
            self._references = references
        (self.directory / f"{reference_id}.png").unlink(missing_ok=True)
        LOG.info("Удалён снимок пустой площадки %s", reference_id)

    def clear(self) -> None:
        """Удалить все снимки пустой площадки."""
        with self._lock:
            references, self._references = self._references, []
            self._pending = 0
        for item in references:
            (self.directory / f"{item.id}.png").unlink(missing_ok=True)
        LOG.info("Набор снимков пустой площадки очищен")

    def thumbnail(self, reference_id: str, width: int = 160) -> bytes:
        """Вернуть уменьшенную копию снимка в JPEG для страницы настроек."""
        if not any(item.id == reference_id for item in self._references):
            raise ValueError("Снимок не найден")
        import cv2

        image = cv2.imread(str(self.directory / f"{reference_id}.png"))
        if image is None:
            raise ValueError("Снимок не прочитан")
        height = round(image.shape[0] * width / image.shape[1])
        ok, encoded = cv2.imencode(".jpg", cv2.resize(image, (width, height)), [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ok:
            raise ValueError("Снимок не закодирован")
        return encoded.tobytes()

    def difference(self, frame, box) -> float | None:
        """Наименьшая средняя разница яркости в рамке среди всех снимков, 0–255.

        ``frame`` - полный кадр камеры, ``box`` - рамка в его координатах.
        None означает, что сравнивать не с чем.
        """
        references = [item for item in self._references if item.prepared.shape[:2] == frame.shape[:2]]
        if not references:
            return None
        x1, y1, x2, y2 = box
        current = self._prepare(frame)[y1:y2, x1:x2]
        if not current.size:
            return None
        import cv2

        return min(float(cv2.absdiff(current, item.prepared[y1:y2, x1:x2]).mean()) for item in references)

    def is_empty(self, frame, box) -> bool:
        """True, если рамка почти не отличается хотя бы от одного снимка пустой площадки."""
        value = self.difference(frame, box)
        return value is not None and value < self.threshold
