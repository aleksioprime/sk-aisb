"""Потокобезопасное хранение статистики в JSON-файле."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path


DEFAULT_STATS = {
    "total_items": 0,
    "estimated_weight_kg": 0.0,
    "by_type": {},
    "feedback": {"correct": 0, "incorrect": 0},
}


class StatisticsStore:
    """Хранить счётчики в памяти и атомарно сохранять их на диск."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        """Прочитать актуальный формат или мигрировать статистику старой UMKA."""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if "items" in raw:  # миграция dm3.py
                return {
                    "total_items": int(raw.get("items", 0)),
                    "estimated_weight_kg": float(raw.get("weight_kg", 0.0)),
                    "by_type": {},
                    "feedback": {
                        "correct": int(raw.get("correct", 0)),
                        "incorrect": int(raw.get("incorrect", 0)),
                    },
                }
            # Глубокая копия не позволяет вложенным словарям DEFAULT_STATS
            # измениться вместе с рабочим состоянием.
            result = json.loads(json.dumps(DEFAULT_STATS))
            result.update(raw)
            result["feedback"] = {**DEFAULT_STATS["feedback"], **raw.get("feedback", {})}
            return result
        except (OSError, ValueError, TypeError):
            return json.loads(json.dumps(DEFAULT_STATS))

    def snapshot(self) -> dict:
        """Вернуть независимую копию текущей статистики."""
        with self._lock:
            return json.loads(json.dumps(self._data))

    def record_sort(self, waste_type: str, estimated_weight: float) -> dict:
        """Учесть один предмет и вернуть обновлённый снимок статистики."""
        with self._lock:
            self._data["total_items"] += 1
            self._data["estimated_weight_kg"] += estimated_weight
            counts = self._data["by_type"]
            counts[waste_type] = counts.get(waste_type, 0) + 1
            snapshot = json.loads(json.dumps(self._data))
        # Файловый ввод-вывод выполняется без lock: другие потоки могут читать
        # или обновлять данные, пока готовый снимок записывается на диск.
        self._save(snapshot)
        return snapshot

    def record_feedback(self, answer: str) -> dict:
        """Учесть ответ пользователя ``yes`` или ``no``."""
        key = "correct" if answer == "yes" else "incorrect"
        with self._lock:
            self._data["feedback"][key] += 1
            snapshot = json.loads(json.dumps(self._data))
        self._save(snapshot)
        return snapshot

    def _save(self, snapshot: dict) -> None:
        """Атомарно заменить JSON через временный файл в том же каталоге."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        # os.replace атомарен в пределах одной файловой системы: при отключении
        # питания останется либо старый, либо полностью записанный новый JSON.
        os.replace(temporary, self.path)
