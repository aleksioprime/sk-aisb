"""Параметры запуска конкретного устройства из файла umka.conf.

Файл лежит в каталоге приложения, создаётся установщиком и не попадает в git.
Его значения становятся значениями по умолчанию для app.py и tools/calibrate.py;
аргументы командной строки их переопределяют. Пример:

    # Параметры запуска UMKA на этом устройстве
    hardware = pca9685
    tilt_channel = 1
    rotate_channel = 0
    camera = 0
    # i2c_bus = 5
"""

from __future__ import annotations

import logging
from pathlib import Path


LOG = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PATH = APP_DIR / "umka.conf"

# Ключ файла → преобразование значения.
FIELDS = {
    "hardware": str,
    "camera": int,
    "tilt_channel": int,
    "rotate_channel": int,
    "i2c_bus": int,
    "pca9685_address": lambda value: int(value, 0),
}


def load(path: Path = DEFAULT_PATH) -> dict:
    """Прочитать umka.conf; без файла вернуть пустой словарь.

    Строки вида ``ключ = значение``, комментарии начинаются с ``#``.
    Неизвестные ключи и ошибочные значения пропускаются с предупреждением,
    чтобы опечатка в файле не мешала запуску.
    """
    if not path.is_file():
        return {}
    values = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, separator, value = (part.strip() for part in line.partition("="))
        if not separator or key not in FIELDS:
            LOG.warning("%s:%d: строка пропущена: %s", path.name, number, raw.strip())
            continue
        try:
            values[key] = FIELDS[key](value)
        except ValueError:
            LOG.warning("%s:%d: недопустимое значение %s", path.name, number, value)
    return values
