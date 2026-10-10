"""Параметры изображения USB-камеры (яркость, контраст и т. п.) через v4l2-ctl."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
from pathlib import Path


LOG = logging.getLogger(__name__)

# Строка v4l2-ctl --list-ctrls-menus, например:
#   brightness 0x00980900 (int)    : min=0 max=255 step=1 default=137 value=137
CONTROL_LINE = re.compile(r"^\s*(?P<name>\w+)\s+0x[0-9a-f]+\s+\((?P<type>\w+)\)\s*:\s*(?P<fields>.*)$")
MENU_LINE = re.compile(r"^\s*(?P<index>-?\d+):\s*(?P<label>.+)$")
SUPPORTED_TYPES = {"int", "bool", "menu"}


def parse_controls(text: str) -> list[dict]:
    """Разобрать вывод ``v4l2-ctl --list-ctrls-menus`` в список параметров."""
    controls = []
    current = None
    for line in text.splitlines():
        match = CONTROL_LINE.match(line)
        if match:
            current = None
            if match["type"] not in SUPPORTED_TYPES:
                continue
            fields = dict(re.findall(r"(\w+)=(-?\d+)", match["fields"]))
            if "value" not in fields:
                continue
            current = {
                "name": match["name"],
                "type": match["type"],
                "min": int(fields.get("min", 0)),
                "max": int(fields.get("max", 1)),
                "step": int(fields.get("step", 1)),
                "default": int(fields.get("default", fields["value"])),
                "value": int(fields["value"]),
                # flags=inactive: параметр сейчас не действует, например при автонастройке.
                "inactive": "inactive" in match["fields"],
                "menu": {},
            }
            controls.append(current)
            continue
        menu = MENU_LINE.match(line)
        if menu and current is not None and current["type"] == "menu":
            current["menu"][menu["index"]] = menu["label"].strip()
    return controls


class CameraControls:
    """Читать, менять и сохранять параметры изображения камеры.

    Сохранённые значения применяются при каждом открытии камеры, в том числе
    после её переподключения по USB, когда драйвер сбрасывает настройки.
    """

    def __init__(self, path: Path):
        self.path = path
        self.device: str | None = None
        self._lock = threading.Lock()
        self._saved: dict[str, int] = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._saved = {str(name): int(value) for name, value in data.items()}
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                LOG.error("Параметры камеры %s не загружены: %s", path, exc)

    @staticmethod
    def _run(*args: str) -> str:
        """Выполнить v4l2-ctl и вернуть вывод; ошибку превратить в понятный текст."""
        try:
            result = subprocess.run(["v4l2-ctl", *args], capture_output=True, text=True, timeout=5)
        except FileNotFoundError as exc:
            raise RuntimeError("Не найдена программа v4l2-ctl: sudo apt install v4l-utils") from exc
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"v4l2-ctl завершился с кодом {result.returncode}")
        return result.stdout

    def list(self) -> list[dict]:
        """Вернуть параметры текущей камеры с диапазонами и значениями."""
        if self.device is None:
            raise RuntimeError("Камера ещё не открыта")
        return parse_controls(self._run("-d", self.device, "--list-ctrls-menus"))

    def set(self, name: str, value: int) -> dict:
        """Задать параметр, сохранить его и вернуть обновлённое описание."""
        if not re.fullmatch(r"\w+", name):
            raise ValueError("Недопустимое имя параметра")
        control = next((item for item in self.list() if item["name"] == name), None)
        if control is None:
            raise ValueError(f"Камера не поддерживает параметр {name}")
        value = int(value)
        if not control["min"] <= value <= control["max"]:
            raise ValueError(f"{name}: значение должно быть от {control['min']} до {control['max']}")
        self._run("-d", self.device, "-c", f"{name}={value}")
        with self._lock:
            self._saved[name] = value
            self._write()
        return next(item for item in self.list() if item["name"] == name)

    def reset(self) -> list[dict]:
        """Вернуть все параметры к значениям по умолчанию и очистить сохранённые."""
        controls = self.list()
        values = [f"{item['name']}={item['default']}" for item in controls if not item["inactive"]]
        if values:
            self._run("-d", self.device, "-c", ",".join(values))
        with self._lock:
            self._saved = {}
            self._write()
        return self.list()

    def apply_saved(self, device: str) -> None:
        """Запомнить открытую камеру и применить к ней сохранённые параметры."""
        self.device = device
        with self._lock:
            saved = dict(self._saved)
        for name, value in saved.items():
            try:
                self._run("-d", device, "-c", f"{name}={value}")
            except RuntimeError as exc:
                LOG.warning("Параметр камеры %s=%s не применён: %s", name, value, exc)
        if saved:
            LOG.info("Параметры камеры применены: %s", saved)

    def _write(self) -> None:
        """Записать сохранённые параметры в файл атомарно."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._saved, indent=2), encoding="utf-8")
        temporary.replace(self.path)
