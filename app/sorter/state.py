"""Общее потокобезопасное состояние для приложения и HTTP API."""

from __future__ import annotations

import threading
import time
import uuid


class StateStore:
    """Хранить опубликованное состояние камеры, модели, автомата и UI.

    Все изменения выполняются под одним lock, поскольку HTTP-запросы, главный
    цикл и worker механизма обращаются к состоянию из разных потоков.
    """

    def __init__(self, stats: dict, hardware_driver: str):
        self._lock = threading.Lock()
        self._state = {
            "state": "idle",
            "controllerState": "IDLE",
            "type": None,
            "name": None,
            "section": None,
            "eventId": None,
            "lastAnswer": None,
            "lastAction": None,
            "detection": None,
            "camera": {"ok": False, "message": "Камера ещё не запущена"},
            "model": {"ok": False, "message": "Модель ещё не загружена"},
            "hardware": {"ok": True, "driver": hardware_driver, "message": "Готово"},
            "error": None,
            "startedAt": time.time(),
            "stats": stats,
        }

    def update(self, **changes) -> None:
        """Атомарно заменить поля верхнего уровня состояния."""
        with self._lock:
            self._state.update(changes)

    def update_component(self, component: str, **changes) -> None:
        """Обновить часть диагностики, сохранив остальные поля компонента."""
        with self._lock:
            current = dict(self._state[component])
            current.update(changes)
            self._state[component] = current

    def show_detection(self, detection) -> None:
        """Опубликовать компактное описание текущей детекции для страницы."""
        value = None if detection is None else {
            "className": detection.class_name,
            "confidence": round(detection.confidence, 3),
            "area": detection.area,
        }
        self.update(detection=value)

    def begin_sort(self, request) -> str:
        """Создать уникальное событие сортировки и показать его в UI."""
        event_id = uuid.uuid4().hex
        names = {
            "paper": "Бумага",
            "plastic_aluminum": "Пластик/алюминий",
            "organic": "Органика",
            "non_recyclable": "Несортируемые отходы",
        }
        self.update(
            state="waste",
            controllerState="SORTING",
            type=request.waste_type,
            name=names[request.waste_type],
            section=request.section,
            eventId=event_id,
            lastAnswer=None,
            lastAction=f"Сортировка в {request.section}",
        )
        return event_id

    def accept_feedback(self, answer: str, event_id: str | None) -> bool:
        """Атомарно принять не более одного ответа для текущего события."""
        with self._lock:
            current_event = self._state["eventId"]
            if (
                not current_event
                or self._state["lastAnswer"] is not None
                or (event_id and event_id != current_event)
            ):
                return False
            self._state["lastAnswer"] = answer
            return True

    def snapshot(self) -> dict:
        """Вернуть снимок состояния в формате, готовом для JSON API."""
        with self._lock:
            result = dict(self._state)
            result["stats"] = dict(self._state["stats"])
            # Поля totalCount/totalWeight сохраняют совместимость существующей
            # страницы с первоначальным протоколом Node.js-сервера.
            result["totalCount"] = result["stats"]["total_items"]
            result["totalWeight"] = round(result["stats"]["estimated_weight_kg"], 2)
            return result
