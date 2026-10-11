"""Сбор датасета во время работы: кадры решений с разметкой модели и негативы.

Группы в data/dataset/:
  unverified/ - решение модели без ответа посетителя;
  confirmed/  - посетитель ответил «Да»: разметка верна, кадр готов к обучению;
  rejected/   - ответ «Нет»: модель ошиблась, кадр нужно переразметить;
  background/ - пустая площадка, на которой модель «увидела» предмет
                (отсеяно фильтром): фон без разметки против ложных срабатываний.
Каждый кадр - <id>.jpg, разметка YOLO <id>.txt и сведения <id>.json.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import threading
import time
import zipfile
from pathlib import Path


LOG = logging.getLogger(__name__)

GROUPS = ("unverified", "confirmed", "rejected", "background")
DEFAULTS = {"enabled": False, "limitMb": 2000}
LIMIT_RANGE_MB = (100, 20000)
BACKGROUND_INTERVAL = 30.0  # Не чаще одного негатива в 30 с: ложное срабатывание повторяется каждый кадр.


class DatasetCollector:
    """Сохранять кадры для дообучения модели и выгружать их архивом."""

    def __init__(self, directory: Path, settings_path: Path):
        self.directory = directory
        self.settings_path = settings_path
        self.class_names: list[str] = []  # Имена классов модели по номерам YOLO.
        self._lock = threading.Lock()
        self._last_background = 0.0
        self.settings = dict(DEFAULTS)
        if settings_path.is_file():
            try:
                self.settings = self._validate(json.loads(settings_path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                LOG.error("Настройки датасета %s не загружены: %s", settings_path, exc)

    @staticmethod
    def _validate(data: dict) -> dict:
        enabled = data.get("enabled", DEFAULTS["enabled"])
        limit = data.get("limitMb", DEFAULTS["limitMb"])
        if not isinstance(enabled, bool):
            raise ValueError("enabled должен быть true или false")
        if isinstance(limit, bool) or not isinstance(limit, (int, float)):
            raise ValueError("limitMb должен быть числом")
        low, high = LIMIT_RANGE_MB
        if not low <= limit <= high:
            raise ValueError(f"Лимит должен быть от {low} до {high} МБ")
        return {"enabled": enabled, "limitMb": int(limit)}

    def save_settings(self, changes: dict) -> dict:
        """Применить и записать настройки сбора."""
        settings = self._validate({**self.settings, **changes})
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(settings), encoding="utf-8")
        self.settings = settings
        LOG.info("Сбор датасета: %s, лимит %d МБ", "включён" if settings["enabled"] else "выключен",
                 settings["limitMb"])
        return self.snapshot()

    @property
    def enabled(self) -> bool:
        return self.settings["enabled"]

    # ---------- Запись ----------
    def _write(self, group: str, item_id: str, frame, label: str, meta: dict) -> None:
        import cv2

        folder = self.directory / group
        folder.mkdir(parents=True, exist_ok=True)
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            LOG.warning("Кадр %s не закодирован", item_id)
            return
        (folder / f"{item_id}.jpg").write_bytes(encoded.tobytes())
        (folder / f"{item_id}.txt").write_text(label, encoding="utf-8")
        (folder / f"{item_id}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        self._enforce_limit()

    def record_decision(self, event_id: str, frame, box, class_id: int, class_name: str,
                        confidence: float) -> None:
        """Сохранить кадр, по которому принято решение, с рамкой модели в формате YOLO.

        ``box`` - (x1, y1, x2, y2) в координатах полного кадра.
        """
        if not self.enabled:
            return
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = box
        label = ""
        if class_id >= 0:
            label = (f"{class_id} {(x1 + x2) / 2 / width:.6f} {(y1 + y2) / 2 / height:.6f} "
                     f"{(x2 - x1) / width:.6f} {(y2 - y1) / height:.6f}\n")
        self._write("unverified", event_id, frame, label, {
            "event_id": event_id, "time": time.time(), "class": class_name,
            "class_id": class_id, "confidence": round(confidence, 3), "box": list(box),
        })

    def record_feedback(self, event_id: str | None, answer: str) -> None:
        """Перенести кадр события в confirmed («Да») или rejected («Нет»)."""
        if not event_id:
            return
        group = "confirmed" if answer == "yes" else "rejected"
        source = self.directory / "unverified"
        target = self.directory / group
        with self._lock:
            files = list(source.glob(f"{event_id}.*"))
            if not files:
                return
            target.mkdir(parents=True, exist_ok=True)
            for path in files:
                path.replace(target / path.name)
        LOG.info("Кадр события %s → %s", event_id, group)

    def record_background(self, frame, class_name: str, confidence: float) -> None:
        """Сохранить пустую площадку, на которой модель ошибочно нашла предмет."""
        now = time.monotonic()
        if not self.enabled or now - self._last_background < BACKGROUND_INTERVAL:
            return
        self._last_background = now
        item_id = str(int(time.time() * 1000))
        self._write("background", item_id, frame, "", {
            "time": time.time(), "false_class": class_name, "confidence": round(confidence, 3),
        })

    def _enforce_limit(self) -> None:
        """Удалять самые старые кадры, пока набор не уложится в лимит."""
        limit = self.settings["limitMb"] * 1024 * 1024
        with self._lock:
            files = [path for group in GROUPS for path in (self.directory / group).glob("*.jpg")]
            total = sum(path.stat().st_size for path in self.directory.rglob("*") if path.is_file())
            for image in sorted(files, key=lambda path: path.stat().st_mtime):
                if total <= limit:
                    break
                for path in image.parent.glob(f"{image.stem}.*"):
                    total -= path.stat().st_size
                    path.unlink(missing_ok=True)

    # ---------- Просмотр, очистка, выгрузка ----------
    def snapshot(self) -> dict:
        """Настройки, число кадров по группам и занятое место."""
        counts = {group: len(list((self.directory / group).glob("*.jpg"))) for group in GROUPS}
        size = sum(path.stat().st_size for path in self.directory.rglob("*") if path.is_file()) \
            if self.directory.exists() else 0
        return {**self.settings, "counts": counts, "sizeMb": round(size / 1024 / 1024, 1)}

    def clear(self) -> dict:
        with self._lock:
            for group in GROUPS:
                shutil.rmtree(self.directory / group, ignore_errors=True)
        LOG.info("Датасет очищен")
        return self.snapshot()

    def export(self) -> Path:
        """Собрать ZIP: группы с images/ и labels/ в формате YOLO, data.yaml и README."""
        handle = tempfile.NamedTemporaryFile(prefix="umka-dataset-", suffix=".zip", delete=False)
        handle.close()
        path = Path(handle.name)
        names = "\n".join(f"  {index}: {name}" for index, name in enumerate(self.class_names))
        with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
            archive.writestr("data.yaml", f"# Классы модели UMKA на момент выгрузки\nnames:\n{names}\n")
            archive.writestr("README.txt", (
                "confirmed  - посетитель подтвердил распознавание: разметка верна.\n"
                "rejected   - посетитель ответил «Нет»: класс или рамку нужно исправить.\n"
                "unverified - без ответа посетителя: проверить перед обучением.\n"
                "background - пустая площадка, где модель ошиблась: фон без разметки.\n"
                "В каждой группе images/ и labels/ (YOLO), в meta/ - сведения о кадре.\n"))
            with self._lock:
                for group in GROUPS:
                    for image in sorted((self.directory / group).glob("*.jpg")):
                        archive.write(image, f"{group}/images/{image.name}")
                        for suffix, folder in ((".txt", "labels"), (".json", "meta")):
                            extra = image.with_suffix(suffix)
                            if extra.exists():
                                archive.write(extra, f"{group}/{folder}/{extra.name}")
        return path
