"""Небольшие неизменяемые модели данных между компонентами приложения."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Detection:
    """Лучший подходящий объект, найденный YOLO в текущем кадре."""

    class_name: str
    confidence: float
    area: int
    box: tuple[int, int, int, int]
    class_id: int = -1  # Номер класса в модели YOLO; нужен для разметки датасета.


@dataclass(frozen=True)
class SortRequest:
    """Подтверждённое решение, которое нужно передать механизму сортировки."""

    class_name: str
    section: str
    waste_type: str
    confidence: float
