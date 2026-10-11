"""Настройки главного экрана: подтверждение распознавания и время показа результата."""

from __future__ import annotations

import json
import logging
from pathlib import Path


LOG = logging.getLogger(__name__)

DEFAULTS = {
    # True - экран спрашивает «Да/Нет»; False - только показывает результат.
    "confirm": True,
    # Сколько секунд показывать результат без подтверждения.
    "resultSeconds": 5,
}
RESULT_SECONDS_RANGE = (2, 30)


def validate(data: dict) -> dict:
    """Проверить настройки экрана и дополнить отсутствующие значениями по умолчанию."""
    confirm = data.get("confirm", DEFAULTS["confirm"])
    seconds = data.get("resultSeconds", DEFAULTS["resultSeconds"])
    if not isinstance(confirm, bool):
        raise ValueError("confirm должен быть true или false")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise ValueError("resultSeconds должен быть числом")
    low, high = RESULT_SECONDS_RANGE
    if not low <= seconds <= high:
        raise ValueError(f"Время показа результата должно быть от {low} до {high} секунд")
    return {"confirm": confirm, "resultSeconds": int(round(seconds))}


class DisplaySettings:
    """Хранить настройки главного экрана в файле и отдавать текущие значения."""

    def __init__(self, path: Path):
        self.path = path
        self.values = dict(DEFAULTS)
        if path.is_file():
            try:
                self.values = validate(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                LOG.error("Настройки экрана %s не загружены: %s", path, exc)

    def save(self, changes: dict) -> dict:
        """Применить изменения поверх текущих значений и записать в файл."""
        values = validate({**self.values, **changes})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(values, indent=2), encoding="utf-8")
        temporary.replace(self.path)
        self.values = values
        LOG.info("Настройки экрана сохранены: %s", values)
        return dict(values)
