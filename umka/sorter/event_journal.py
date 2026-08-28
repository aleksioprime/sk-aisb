"""История отдельных сортировок в ротируемом журнале JSON Lines."""

from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from .models import SortRequest


class EventJournal:
    """Записывать события построчно, ежедневно ротируя активный файл.

    В отличие от ``sort_stats.json``, журнал предназначен не для текущих итогов,
    а для последующего анализа каждого решения. Одна строка является независимым
    JSON-объектом, поэтому повреждение последней записи не затрагивает остальные.
    """

    def __init__(self, path: Path, retention_days: int = 30):
        if retention_days < 1:
            raise ValueError("retention_days должен быть положительным")
        self.path = path
        self.retention_days = retention_days
        self._lock = threading.Lock()
        self._active_date = self._detect_active_date()

    def record_sort(
        self,
        event_id: str,
        request: SortRequest,
        estimated_weight_kg: float,
    ) -> None:
        """Записать успешно завершённую сортировку."""
        self._append({
            "event": "sort",
            "event_id": event_id,
            "class": request.class_name,
            "waste_type": request.waste_type,
            "section": request.section,
            "confidence": round(request.confidence, 4),
            "estimated_weight_kg": estimated_weight_kg,
        })

    def record_feedback(self, event_id: str, answer: str) -> None:
        """Записать ответ пользователя для ранее созданного события."""
        self._append({
            "event": "feedback",
            "event_id": event_id,
            "answer": answer,
        })

    def _append(self, payload: dict, now: datetime | None = None) -> None:
        """Добавить одну JSON-строку под общей блокировкой записи и ротации."""
        timestamp = now or datetime.now().astimezone()
        current_date = timestamp.date()
        record = {"timestamp": timestamp.isoformat(timespec="seconds"), **payload}
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"

        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._rotate_if_needed(current_date)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())
            self._active_date = current_date

    def _detect_active_date(self) -> date | None:
        """Определить дату активного файла по времени последнего изменения."""
        try:
            return datetime.fromtimestamp(self.path.stat().st_mtime).astimezone().date()
        except OSError:
            return None

    def _rotate_if_needed(self, current_date: date) -> None:
        """Перенести вчерашний файл в архив и удалить архивы старше лимита."""
        if self.path.exists() and self._active_date and self._active_date != current_date:
            archive = self.path.with_name(
                f"{self.path.stem}.{self._active_date.isoformat()}{self.path.suffix}"
            )
            if archive.exists():
                # Такое возможно после нескольких запусков в день: объединяем
                # части одного дня, не перезаписывая уже собранную историю.
                with archive.open("ab") as destination, self.path.open("rb") as source:
                    destination.write(source.read())
                self.path.unlink()
            else:
                os.replace(self.path, archive)
        self._remove_expired(current_date)

    def _remove_expired(self, current_date: date) -> None:
        """Удалить датированные архивы за пределами периода хранения."""
        cutoff = current_date - timedelta(days=self.retention_days - 1)
        pattern = f"{self.path.stem}.*{self.path.suffix}"
        prefix = f"{self.path.stem}."
        for candidate in self.path.parent.glob(pattern):
            raw_date = candidate.name[len(prefix):-len(self.path.suffix)]
            try:
                archive_date = date.fromisoformat(raw_date)
            except ValueError:
                continue
            if archive_date < cutoff:
                candidate.unlink(missing_ok=True)
