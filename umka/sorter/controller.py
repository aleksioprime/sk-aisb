"""Потокобезопасный автомат состояний процесса сортировки."""

from __future__ import annotations

import threading

from .models import Detection, SortRequest


class SortingController:
    """Подтверждать детекции и не сортировать один предмет повторно.

    Состояния автомата:

    * ``IDLE`` — площадка свободна;
    * ``CANDIDATE`` — один класс накапливает подтверждающие кадры;
    * ``SORTING`` — команда выполняется отдельным потоком механизма;
    * ``WAITING_FOR_REMOVAL`` — новый запуск запрещён до пустой площадки.
    """

    IDLE = "IDLE"
    CANDIDATE = "CANDIDATE"
    SORTING = "SORTING"
    WAITING_FOR_REMOVAL = "WAITING_FOR_REMOVAL"

    def __init__(self, stable_frames: int, clear_frames: int, class_to_section: dict, class_to_type: dict):
        self.stable_frames = stable_frames
        self.clear_frames = clear_frames
        self.class_to_section = class_to_section
        self.class_to_type = class_to_type
        self.state = self.IDLE
        self.candidate: str | None = None
        self.candidate_count = 0
        self.clear_count = 0
        self._lock = threading.Lock()

    def observe(self, detection: Detection | None) -> SortRequest | None:
        """Обработать очередной результат зрения и, если он устойчив, дать команду."""
        with self._lock:
            return self._observe(detection)

    def _observe(self, detection: Detection | None) -> SortRequest | None:
        """Выполнить переход автомата; вызывается только под ``_lock``."""
        if self.state == self.SORTING:
            return None
        if self.state == self.WAITING_FOR_REMOVAL:
            # Счётчик сбрасывается при любом новом объекте: площадка должна быть
            # свободна несколько кадров именно подряд.
            self.clear_count = self.clear_count + 1 if detection is None else 0
            if self.clear_count >= self.clear_frames:
                self._reset()
            return None
        if detection is None:
            self._reset()
            return None

        if detection.class_name == self.candidate:
            self.candidate_count += 1
        else:
            # Стабилизируется класс, а не секция: два разных класса не могут
            # случайно сложиться в одну подтверждённую последовательность.
            self.candidate = detection.class_name
            self.candidate_count = 1
        self.state = self.CANDIDATE

        if self.candidate_count < self.stable_frames:
            return None

        class_name = detection.class_name
        self.state = self.SORTING
        return SortRequest(
            class_name=class_name,
            section=self.class_to_section[class_name],
            waste_type=self.class_to_type[class_name],
            confidence=detection.confidence,
        )

    def sorting_finished(self) -> None:
        """Отметить успешное завершение механизма и ждать удаления предмета."""
        with self._lock:
            if self.state == self.SORTING:
                self.state = self.WAITING_FOR_REMOVAL
                self.clear_count = 0

    def sorting_failed(self) -> None:
        """После ошибки механизма вернуть автомат в исходное состояние."""
        with self._lock:
            self._reset()

    def _reset(self) -> None:
        """Сбросить кандидата и счётчики в состояние ожидания."""
        self.state = self.IDLE
        self.candidate = None
        self.candidate_count = 0
        self.clear_count = 0
