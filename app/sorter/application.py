"""Оркестрация камеры, распознавания, автомата, механизма и веб-интерфейса."""

from __future__ import annotations

import logging
import queue
import threading
import time

from . import calibration, launch_config
from .background import EmptyPlatformFilter
from .camera import UsbCamera
from .camera_controls import CameraControls
from .crop import CropArea
from .dataset import DatasetCollector
from .controller import SortingController
from .detector import YoloDetector
from .display_settings import DisplaySettings
from .event_journal import EventJournal
from .hardware import create_hardware
from .preview import FramePreview
from .screen import ScreenManager
from .state import StateStore
from .statistics import StatisticsStore
from .telemetry import Telemetry
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
        self.preview = FramePreview()
        self.crop = CropArea(config)
        self.camera_controls = CameraControls(config.camera_controls_path)
        self.display = DisplaySettings(config.display_path)
        self.dataset = DatasetCollector(config.dataset_dir, config.dataset_settings_path)
        self.screen = ScreenManager(config.screen_path)
        self.telemetry = Telemetry(launch_config.load(), self.state, config.events_path,
                                   config.telemetry_cursor_path)
        # Главный экран получает настройки вместе с остальным состоянием.
        self.state.update(display=dict(self.display.values))
        self.platform = EmptyPlatformFilter(
            config.background_dir, config.background_threshold, legacy_path=config.background_path,
        )
        # Один поток механизма за раз: сортировка или команда со страницы настроек.
        self.hardware_lock = threading.Lock()
        # Пока открыта страница настроек, распознавание не запускает сортировку.
        # Страница продлевает режим запросами; закрытая вкладка снимает его сама.
        self.maintenance_until = 0.0
        self.web = WebServer(
            config.web_host, config.web_port, config.static_dir, self.state, self.feedback, self.preview,
            {
                ("GET", "/api/background"): self._list_background,
                ("POST", "/api/background"): self._capture_background,
                ("POST", "/api/background/delete"): self._delete_background,
                ("POST", "/api/background/clear"): self._clear_background,
                ("GET", "/api/background/thumbnail"): lambda query: (
                    200, self.platform.thumbnail(str(query["id"]))),
                ("GET", "/api/calibration"): self._get_calibration,
                ("POST", "/api/calibration/mode"): self._set_maintenance,
                ("POST", "/api/calibration/move"): self._move_servos,
                ("POST", "/api/calibration/test"): self._test_section,
                ("POST", "/api/calibration/save"): self._save_calibration,
                ("POST", "/api/calibration/motor"): self._switch_motor,
                ("GET", "/api/camera/controls"): self._get_camera_controls,
                ("POST", "/api/camera/controls"): lambda body: (
                    200, self.camera_controls.set(str(body["name"]), body["value"])),
                ("POST", "/api/camera/controls/reset"): lambda _body: (
                    200, {"controls": self.camera_controls.reset()}),
                ("GET", "/api/display"): lambda _body: (200, dict(self.display.values)),
                ("POST", "/api/display"): self._save_display,
                ("GET", "/api/screen"): lambda _body: (200, self.screen.snapshot()),
                ("POST", "/api/screen"): lambda body: (200, self.screen.set_mode(body.get("mode"))),
                ("GET", "/api/dataset"): lambda _body: (200, self.dataset.snapshot()),
                ("POST", "/api/dataset"): lambda body: (200, self.dataset.save_settings(body)),
                ("POST", "/api/dataset/clear"): lambda _body: (200, self.dataset.clear()),
                ("GET", "/api/dataset/export"): lambda _body: (200, self.dataset.export()),
                ("GET", "/api/crop"): lambda _body: (200, self.crop.snapshot()),
                ("POST", "/api/crop"): lambda body: (200, self.crop.save(body)),
            },
        )
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
        try:
            self.dataset.record_feedback(current_event_id, answer)
        except OSError:
            LOG.exception("Кадр датасета не перенесён")
        LOG.info("Обратная связь: %s для события %s", answer, current_event_id)
        return True

    MAINTENANCE_SECONDS = 90  # Через столько секунд без запросов настройка завершается.

    @property
    def maintenance(self) -> bool:
        """Открыта ли страница настроек механизма."""
        return time.monotonic() < self.maintenance_until

    def _list_background(self, _body: dict):
        """Вернуть набор снимков пустой площадки."""
        return 200, {
            "items": self.platform.items(),
            "max": self.platform.MAX_REFERENCES,
            "threshold": self.platform.threshold,
        }

    def _capture_background(self, body: dict):
        """Добавить следующий кадр в набор; replace=true сначала очищает набор."""
        if body.get("replace"):
            self.platform.clear()
        self.platform.request_capture()
        return 200, {"success": True}

    def _delete_background(self, body: dict):
        """Удалить один снимок пустой площадки."""
        self.platform.delete(str(body["id"]))
        return self._list_background(body)

    def _clear_background(self, body: dict):
        """Удалить все снимки пустой площадки."""
        self.platform.clear()
        return self._list_background(body)

    def _get_calibration(self, _body: dict):
        """Вернуть углы, назначение секций и режим настройки."""
        section_classes = {}
        for class_name, section in self.config.class_to_section.items():
            section_classes.setdefault(section, []).append(class_name)
        return 200, {
            **calibration.snapshot(),
            "sectionClasses": section_classes,
            "maintenance": self.maintenance,
            "driver": self.config.hardware_driver,
        }

    def _set_maintenance(self, body: dict):
        """Включить или выключить режим настройки механизма."""
        if body.get("active"):
            self.maintenance_until = time.monotonic() + self.MAINTENANCE_SECONDS
            self.state.update(lastAction="Настройка механизма: сортировка приостановлена")
        else:
            self.maintenance_until = 0.0
            if self.hardware is not None:
                with self.hardware_lock:
                    self.hardware.center()
            self.state.update(lastAction="Настройка механизма завершена")
        return 200, {"maintenance": self.maintenance}

    def _hardware_command(self, action):
        """Выполнить команду механизма только в режиме настройки и без сортировки."""
        if self.hardware is None:
            return 503, {"error": "Механизм ещё не готов"}
        if not self.maintenance:
            return 409, {"error": "Откройте режим настройки"}
        if not self.hardware_lock.acquire(timeout=10):
            return 409, {"error": "Механизм занят"}
        try:
            self.maintenance_until = time.monotonic() + self.MAINTENANCE_SECONDS
            action()
            # Мотор с «отпускать в центре» не держит положение и во время
            # калибровки: иначе под нагрузкой он дрожит.
            self.hardware.rest()
        finally:
            self.hardware_lock.release()
        return 200, {"success": True}

    def _move_servos(self, body: dict):
        """Поставить моторы в заданные углы без сохранения."""
        rotate = body.get("rotate")
        tilt = body.get("tilt")
        rotate = None if rotate is None else calibration.angle(rotate)
        tilt = None if tilt is None else calibration.angle(tilt)
        return self._hardware_command(lambda: self.hardware.set_angles(rotate=rotate, tilt=tilt))

    def _test_section(self, body: dict):
        """Выполнить сброс по переданным, ещё не сохранённым углам."""
        center = body["center"]
        action = body["action"]
        center_tilt = calibration.angle(center["tilt"])
        center_rotate = calibration.angle(center["rotate"])
        rotate = calibration.angle(action["rotate"])
        tilt = calibration.angle(action["tilt"])

        def drop():
            self.hardware.set_angles(rotate=rotate)
            self.hardware.set_angles(tilt=tilt)
            time.sleep(0.5)  # Та же выдержка для падения предмета, что и при сортировке.
            self.hardware.set_angles(tilt=center_tilt)
            self.hardware.set_angles(rotate=center_rotate)

        return self._hardware_command(drop)

    def _save_calibration(self, body: dict):
        """Сохранить углы в файл и сразу применить их к сортировке."""
        saved = calibration.save(self.config.calibration_path, body)
        return 200, saved

    def _save_display(self, body: dict):
        """Сохранить настройки главного экрана и сразу передать их странице."""
        values = self.display.save(body)
        self.state.update(display=dict(values))
        return 200, values

    def _get_camera_controls(self, _body: dict):
        """Вернуть параметры изображения открытой камеры."""
        try:
            controls = self.camera_controls.list()
        except RuntimeError as exc:
            return 503, {"error": str(exc)}
        return 200, {"device": self.camera_controls.device, "controls": controls}

    def _switch_motor(self, body: dict):
        """Включить или выключить мотор, задать отпускание в центре; сохранить в файл.

        Работает и вне режима настройки: выключить перегретый мотор нужно
        немедленно. Сохранённые углы при этом не меняются.
        """
        motor = body["motor"]
        if motor not in ("tilt", "rotate"):
            raise ValueError("motor должен быть tilt или rotate")
        data = calibration.snapshot()
        if "enabled" in body:
            data["enabled"][motor] = bool(body["enabled"])
        if "release" in body:
            data["release"][motor] = bool(body["release"])
        calibration.save(self.config.calibration_path, data)
        if self.hardware is not None:
            with self.hardware_lock:
                if data["enabled"][motor]:
                    # Центрирование применяет выбор сразу: мотор встаёт в центр
                    # и, если так задано, отпускается.
                    self.hardware.center()
                else:
                    self.hardware.release(motor)
        LOG.info("Мотор %s: %s, %s в центре", motor,
                 "включён" if data["enabled"][motor] else "выключен",
                 "отпускается" if data["release"][motor] else "удерживается")
        snapshot = calibration.snapshot()
        return 200, {"enabled": snapshot["enabled"], "release": snapshot["release"]}

    def run(self) -> None:
        """Проверить настройки, запустить компоненты и войти в цикл зрения."""
        self.config.validate()
        calibration.load(self.config.calibration_path)
        self.web.start()
        self.screen.start()
        self.telemetry.start()
        try:
            # Сервер запускается первым, чтобы на странице были видны ошибки
            # последующей инициализации модели, GPIO или камеры.
            self.detector = YoloDetector(self.config)
            names = self.detector.model.names
            self.dataset.class_names = [str(names[index]) for index in sorted(names)] \
                if isinstance(names, dict) else [str(name) for name in names]
            self.state.update_component("model", ok=True, message="YOLO загружена")
            self.hardware = create_hardware(
                self.config.hardware_driver,
                self.config.simulate_delay,
                self.config.pca9685_address,
                self.config.tilt_servo_channel,
                self.config.rotate_servo_channel,
                self.config.i2c_bus,
            )
            self.hardware.center()
            for motor, enabled in calibration.snapshot()["enabled"].items():
                if not enabled:
                    # Сигнал мог остаться от прошлого запуска: снимаем его явно.
                    self.hardware.release(motor)
            self.camera = UsbCamera(
                self.config.camera_index,
                self.config.camera_width,
                self.config.camera_height,
                on_open=self.camera_controls.apply_saved,
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
            self.state.update_component("camera", ok=True, message=self.camera.device)
            cropped, area = self.crop.apply(frame)
            self.platform.capture_if_requested(frame)
            detection = self.detector.detect(cropped)
            rejected = None
            difference = None
            if detection is not None:
                # Рамка YOLO задана в обрезанном кадре, эталон — в полном.
                x1, y1, x2, y2 = detection.box
                left, top = area[:2]
                box = (left + x1, top + y1, left + x2, top + y2)
                difference = self.platform.difference(frame, box)
                if difference is not None and difference < self.platform.threshold:
                    # Рамка совпадает с пустой площадкой: блик или дно, не предмет.
                    rejected, detection = detection, None
                    self._save_dataset(self.dataset.record_background, frame,
                                       rejected.class_name, rejected.confidence)
            self.state.update(platform={
                "reference": self.platform.has_reference,
                "references": self.platform.count,
                "difference": None if difference is None else round(difference, 1),
                "threshold": self.config.background_threshold,
                "rejected": rejected is not None,
            })
            self.preview.publish(frame, area, detection, rejected)
            self.state.show_detection(detection)
            if self.maintenance:
                # Моторами управляет страница настроек: решения не принимаются.
                continue
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
                if detection is not None:
                    self._save_dataset(self.dataset.record_decision, event_id, frame, box,
                                       detection.class_id, detection.class_name, detection.confidence)
                self.sort_queue.put((request, event_id))

    def _save_dataset(self, method, *args) -> None:
        """Сохранить кадр датасета; ошибка диска не должна останавливать сортировку."""
        try:
            method(*args)
        except Exception:
            LOG.exception("Кадр датасета не сохранён")

    def _sort_worker(self) -> None:
        """Последовательно выполнять команды механизма в отдельном потоке."""
        while not self.stop_event.is_set():
            try:
                request, event_id = self.sort_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                with self.hardware_lock:
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
        self.screen.close()
        self.telemetry.close()
        if self.camera:
            self.camera.close()
        if self.hardware:
            self.hardware.close()
        self.web.close()
