"""Сохранённая калибровка углов сервоприводов поверх значений из hardware.py."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import hardware


LOG = logging.getLogger(__name__)


def snapshot() -> dict:
    """Вернуть текущие углы центра и секций."""
    return {
        "center": {"tilt": hardware.CENTER_TILT_ANGLE, "rotate": hardware.CENTER_ROTATE_ANGLE},
        "sections": {name: dict(angles) for name, angles in hardware.ACTIONS.items()},
        "enabled": dict(hardware.MOTORS_ENABLED),
    }


def angle(value) -> int:
    """Проверить угол сервопривода: целое число 0–180."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Угол должен быть числом")
    if not 0 <= value <= 180:
        raise ValueError("Угол должен находиться в диапазоне 0–180")
    return int(round(value))


def validate(data: dict) -> dict:
    """Проверить калибровку и вернуть нормализованную копию.

    Секции должны совпадать с ``hardware.ACTIONS``: их список задаёт механика,
    а не файл калибровки.
    """
    center = data["center"]
    sections = data["sections"]
    # Файлы, сохранённые до появления переключателей, включают оба мотора.
    enabled = data.get("enabled", {})
    if set(sections) != set(hardware.ACTIONS):
        raise ValueError(f"Нужны секции: {', '.join(sorted(hardware.ACTIONS))}")
    return {
        "center": {"tilt": angle(center["tilt"]), "rotate": angle(center["rotate"])},
        "sections": {
            name: {"rotate": angle(angles["rotate"]), "tilt": angle(angles["tilt"])}
            for name, angles in sections.items()
        },
        "enabled": {motor: bool(enabled.get(motor, True)) for motor in ("tilt", "rotate")},
    }


def apply(data: dict) -> None:
    """Подставить проверенную калибровку в общие углы hardware.py."""
    data = validate(data)
    hardware.CENTER_TILT_ANGLE = data["center"]["tilt"]
    hardware.CENTER_ROTATE_ANGLE = data["center"]["rotate"]
    hardware.ACTIONS = data["sections"]
    hardware.MOTORS_ENABLED = data["enabled"]


def load(path: Path) -> None:
    """Загрузить калибровку из файла; без файла остаются углы из hardware.py."""
    if not path.is_file():
        return
    try:
        apply(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        LOG.error("Калибровка %s не загружена: %s. Используются углы из hardware.py", path, exc)
        return
    LOG.info("Калибровка моторов загружена: %s", path)


def save(path: Path, data: dict) -> dict:
    """Проверить, применить и записать калибровку; вернуть сохранённые значения."""
    data = validate(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    apply(data)
    LOG.info("Калибровка моторов сохранена: %s", path)
    return data
