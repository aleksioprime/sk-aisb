"""Загрузка YOLO и преобразование её результатов во внутреннюю детекцию."""

from __future__ import annotations

import logging

from .models import Detection


LOG = logging.getLogger(__name__)


class YoloDetector:
    """Фильтровать результаты YOLO и выбирать лучший мусорный объект."""

    def __init__(self, config):
        """Загрузить веса и убедиться, что модель содержит полезные классы."""
        # Тяжёлая зависимость импортируется только при реальном создании
        # детектора. Благодаря этому тесты автомата не требуют ultralytics.
        from ultralytics import YOLO

        self.config = config
        self.model = YOLO(str(config.model_path))
        model_names = self.model.names.values() if isinstance(self.model.names, dict) else self.model.names
        normalized = {config.normalize_class(str(name)) for name in model_names}
        useful = normalized - set(config.ignored_classes)
        LOG.info("Классы модели: %s", sorted(normalized))
        if not useful:
            raise ValueError("В модели нет классов мусора после исключения ignored_classes")

    def detect(self, frame) -> Detection | None:
        """Вернуть лучший подходящий объект кадра или ``None``.

        ``empty`` и ``hand`` отбрасываются, маленькие рамки считаются шумом,
        неизвестный модели приложения класс направляется в несортируемые.
        Приоритет имеет уверенность YOLO, площадь служит вторичным критерием.
        """
        result = self.model.predict(
            source=frame,
            imgsz=self.config.image_size,
            conf=self.config.confidence,
            verbose=False,
        )[0]
        candidates = []
        if result.boxes is None:
            return None
        for box in result.boxes:
            class_id = int(box.cls[0])
            raw_name = str(result.names[class_id])
            class_name = self.config.normalize_class(raw_name)
            if class_name in self.config.ignored_classes:
                continue
            x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().tolist())
            area = max(0, x2 - x1) * max(0, y2 - y1)
            if area < self.config.min_box_area:
                continue
            if class_name not in self.config.class_to_section:
                # Модель действительно увидела объект, но приложение не знает
                # отдельного маршрута для его класса.
                class_name = "non_recyclable"
            candidates.append(Detection(
                class_name=class_name,
                confidence=float(box.conf[0]),
                area=area,
                box=(x1, y1, x2, y2),
            ))
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item.confidence, item.area))
