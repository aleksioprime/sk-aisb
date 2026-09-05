"""Оркестрация камеры, распознавания, автомата, механизма и веб-интерфейса."""

from __future__ import annotations

import logging
import queue
import threading
import time

from .camera import UsbCamera, crop_frame
from .controller import SortingController
from .detector import YoloDetector
from .event_journal import EventJournal
from .hardware import create_hardware
from .state import StateStore
from .statistics import StatisticsStore
from .web import WebServer


LOG = logging.getLogger(__name__)


class UmkaApplication:
    """Связать независимые компоненты UMKA в единый жизненный цикл.

    Главный поток выполняет распознавание. Камера, HTTP-сервер и механизм имеют
    отдельные потоки, поэтому медленное движение сервопривода не блокирует UI и
    не заставляет OpenCV обрабатывать накопившиеся старые кадры.
    """

    def __init__(self, config):
        """Создать компоненты без открытия камеры и GPIO."""
        self.config = config
        self.stats = StatisticsStore(config.stats_path)
        self.events = EventJournal(config.events_path, retention_days=30)
        self.state = StateStore(self.stats.snapshot(), config.hardware_driver)
        self.controller = SortingController(
            config.stable_frames,
            config.clear_frames,
            config.class_to_section,
            config.class_to_waste_type,
        )
        self.hardware = None
        self.camera = None
        self.detector = None
        self.web = WebServer(config.web_host, config.web_port, config.static_dir, self.state, self.feedback)
        # Автомат не создаёт новую команду в состоянии SORTING, поэтому одной
        # ячейки достаточно и очередь не может бесконтрольно расти.
        self.sort_queue: queue.Queue = queue.Queue(maxsize=1)
        self.stop_event = threading.Event()
        self.sort_thread = None

    def feedback(self, answer: str, event_id: str | None) -> bool:
        """Атомарно принять один ответ для текущего события сортировки."""
        current_event_id = self.state.snapshot()["eventId"]
        if not self.state.accept_feedback(answer, event_id):
            return False
        try:
            stats = self.stats.record_feedback(answer)
            self.state.update(stats=stats)
        except OSError as exc:
            LOG.exception("Не удалось сохранить статистику обратной связи")
            self.state.update(error=f"Ошибка сохранения статистики: {exc}")
        try:
            self.events.record_feedback(current_event_id, answer)
        except OSError as exc:
            LOG.exception("Не удалось записать событие обратной связи")
            self.state.update(error=f"Ошибка журнала событий: {exc}")
        LOG.info("Обратная связь: %s для события %s", answer, current_event_id)
        return True

    def run(self) -> None:
        """Проверить настройки, запустить компоненты и войти в цикл зрения."""
        self.config.validate()
        self.web.start()
        try:
            # Сервер запускается первым, чтобы на странице были видны ошибки
            # последующей инициализации модели, GPIO или камеры.
            self.detector = YoloDetector(self.config)
            self.state.update_component("model", ok=True, message="YOLO загружена")
            self.hardware = create_hardware(
                self.config.hardware_driver,
                self.config.simulate_delay,
                self.config.pca9685_address,
                self.config.tilt_servo_channel,
                self.config.rotate_servo_channel,
            )
            self.hardware.center()
            self.camera = UsbCamera(
                self.config.camera_index,
                self.config.camera_width,
                self.config.camera_height,
            )
            self.camera.start()
            self.state.update_component("camera", ok=True, message=f"/dev/video{self.config.camera_index}")
            self.sort_thread = threading.Thread(target=self._sort_worker, name="sort-worker", daemon=True)
            self.sort_thread.start()
            self._vision_loop()
        except Exception as exc:
            LOG.exception("Критическая ошибка UMKA")
            self.state.update(error=str(exc))
            if self.detector is None:
                self.state.update_component("model", ok=False, message=str(exc))
            raise
        finally:
            self.close()

    def _vision_loop(self) -> None:
        """Обрабатывать свежие кадры и передавать решения автомату состояний."""
        sequence = 0
        while not self.stop_event.is_set():
            sequence, frame = self.camera.next_frame(sequence)
            if frame is None:
                message = self.camera.error or "Таймаут ожидания кадра"
                self.state.update_component("camera", ok=False, message=message)
                continue
            self.state.update_component("camera", ok=True, message=f"/dev/video{self.config.camera_index}")
            detection = self.detector.detect(crop_frame(frame, self.config))
            self.state.show_detection(detection)
            previous_state = self.controller.state
            request = self.controller.observe(detection)
            self.state.update(controllerState=self.controller.state)
            if (
                previous_state == self.controller.WAITING_FOR_REMOVAL
                and self.controller.state == self.controller.IDLE
            ):
                # UI очищается только после подтверждённого освобождения
                # площадки, а не сразу после завершения движения.
                self.state.update(
                    state="idle",
                    type=None,
                    name=None,
                    section=None,
                    eventId=None,
                    lastAnswer=None,
                    lastAction="Площадка свободна, система готова",
                )
            if request:
                # Веб-состояние публикуется до помещения команды в очередь,
                # поэтому пользователь сразу видит выбранный тип и секцию.
                event_id = self.state.begin_sort(request)
                LOG.info(
                    "Решение: %s (%.2f) → %s",
                    request.class_name,
                    request.confidence,
                    request.section,
                )
                self.sort_queue.put((request, event_id))

    def _sort_worker(self) -> None:
        """Последовательно выполнять команды механизма в отдельном потоке."""
        while not self.stop_event.is_set():
            try:
                request, event_id = self.sort_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.hardware.sort_to(request.section)
            except Exception as exc:
                # Ошибка механики не должна навсегда оставить автомат в SORTING.
                LOG.exception("Ошибка механизма")
                self.controller.sorting_failed()
                self.state.update(
                    state="idle",
                    controllerState=self.controller.state,
                    type=None,
                    name=None,
                    section=None,
                    eventId=None,
                    error=f"Ошибка механизма: {exc}",
                )
            else:
                # Ошибка диска не отменяет уже выполненное физическое движение и
                # не должна ошибочно переводить систему в состояние сбоя механики.
                estimated_weight = self.config.estimated_weight_kg[request.class_name]
                state_changes = {
                    "lastAction": f"Завершено: {request.class_name} → {request.section}",
                }
                try:
                    state_changes["stats"] = self.stats.record_sort(
                        request.waste_type,
                        estimated_weight,
                    )
                except OSError as exc:
                    LOG.exception("Не удалось сохранить статистику сортировки")
                    state_changes["error"] = f"Ошибка сохранения статистики: {exc}"
                try:
                    self.events.record_sort(event_id, request, estimated_weight)
                except OSError as exc:
                    LOG.exception("Не удалось записать событие сортировки")
                    state_changes["error"] = f"Ошибка журнала событий: {exc}"
                self.controller.sorting_finished()
                state_changes["controllerState"] = self.controller.state
                self.state.update(**state_changes)
            finally:
                self.sort_queue.task_done()

    def close(self) -> None:
        """Остановить фоновые компоненты и освободить аппаратные ресурсы."""
        self.stop_event.set()
        if self.camera:
            self.camera.close()
        if self.hardware:
            self.hardware.close()
        self.web.close()
