"""Разрешение подключённого дисплея через xrandr и его удержание после переподключения.

Orange Pi 5B не выдаёт «родной» режим некоторых дисплеев 1024×600 (HDMI-передатчик
не запускается), а при каждом переподключении система выбирает именно его.
Выбранный режим сохраняется, и фоновый поток возвращает его, если он сбился.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
from pathlib import Path


LOG = logging.getLogger(__name__)

OUTPUT_LINE = re.compile(r"^(?P<name>\S+) (?P<state>connected|disconnected)")
MODE_LINE = re.compile(r"^\s+(?P<mode>\d+x\d+i?)\s+(?P<rates>.*)$")
CHECK_INTERVAL = 5.0  # Секунды между проверками режима.


def parse_xrandr(text: str) -> list[dict]:
    """Разобрать вывод ``xrandr --query``: выходы, их режимы, текущий и предпочтительный."""
    outputs = []
    current = None
    for line in text.splitlines():
        match = OUTPUT_LINE.match(line)
        if match:
            current = {"name": match["name"], "connected": match["state"] == "connected",
                       "modes": [], "current": None, "preferred": None}
            outputs.append(current)
            continue
        mode = MODE_LINE.match(line)
        if mode and current is not None:
            name = mode["mode"]
            if name not in current["modes"]:
                current["modes"].append(name)
            if "*" in mode["rates"]:
                current["current"] = name
            if "+" in mode["rates"]:
                current["preferred"] = name
    return outputs


class ScreenManager:
    """Читать и задавать режим дисплея; держать выбранный режим в фоне."""

    def __init__(self, path: Path, display: str = ":0"):
        self.path = path
        self.env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", display)}
        # Служба и SSH-сеанс не знают XAUTHORITY графической сессии того же пользователя.
        self.env.setdefault("XAUTHORITY", str(Path.home() / ".Xauthority"))
        self.mode: str | None = None
        self._stop = threading.Event()
        self._thread = None
        if path.is_file():
            try:
                self.mode = json.loads(path.read_text(encoding="utf-8")).get("mode")
            except (OSError, ValueError, AttributeError) as exc:
                LOG.error("Настройка дисплея %s не загружена: %s", path, exc)

    def _xrandr(self, *args: str) -> str:
        try:
            result = subprocess.run(["xrandr", *args], capture_output=True, text=True, env=self.env, timeout=10)
        except FileNotFoundError as exc:
            raise RuntimeError("xrandr не найден: на устройстве нет графического рабочего стола") from exc
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "xrandr завершился с ошибкой")
        return result.stdout

    def _output(self) -> dict | None:
        """Первый подключённый выход (HDMI, DP)."""
        return next((item for item in parse_xrandr(self._xrandr("--query")) if item["connected"]), None)

    def snapshot(self) -> dict:
        output = self._output()
        return {"saved": self.mode, "output": output}

    def set_mode(self, mode: str | None) -> dict:
        """Применить режим (или None - только перестать его удерживать) и сохранить."""
        if mode is not None:
            output = self._output()
            if output is None:
                raise RuntimeError("Дисплей не подключён")
            if mode not in output["modes"]:
                raise ValueError(f"Дисплей не поддерживает режим {mode}")
            self._xrandr("--output", output["name"], "--mode", mode)
            LOG.info("Дисплей %s: режим %s", output["name"], mode)
        self.mode = mode
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"mode": mode}), encoding="utf-8")
        return self.snapshot()

    def keep(self) -> None:
        """Вернуть сохранённый режим, если дисплей переключился на другой."""
        if not self.mode:
            return
        output = self._output()
        if output and output["current"] != self.mode and self.mode in output["modes"]:
            LOG.info("Дисплей %s переключился на %s, возвращаю %s", output["name"], output["current"], self.mode)
            self._xrandr("--output", output["name"], "--mode", self.mode)

    def start(self) -> None:
        """Запустить фоновую проверку режима."""
        def loop():
            while not self._stop.wait(CHECK_INTERVAL):
                try:
                    self.keep()
                except RuntimeError as exc:
                    LOG.debug("Проверка дисплея: %s", exc)
        self._thread = threading.Thread(target=loop, name="screen-keeper", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
