"""Отправка состояния и событий устройства на сервер мониторинга по MQTT.

Топики (формат — web/README.md):
  umka/<device_id>/status — состояние раз в минуту, retain;
  umka/<device_id>/event  — строки журнала data/events/events.jsonl, QoS 1.

События читаются из журнала, поэтому без связи ничего не теряется: после
восстановления отправляется всё, что накопилось. Позиция — последнее
подтверждённое брокером событие (а не смещение в файле: в полночь журнал
переносится в архив). Повтор события сервер отбрасывает.

Настройки — в umka.conf: mqtt_host, mqtt_port, mqtt_tls, mqtt_username,
mqtt_password, device_id, device_name. Без mqtt_host и mqtt_username
телеметрия выключена.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from pathlib import Path


LOG = logging.getLogger(__name__)

STATUS_INTERVAL = 60.0  # Секунды между отправками состояния.
EVENTS_INTERVAL = 10.0  # Секунды между проверками журнала.
PUBLISH_TIMEOUT = 10.0  # Сколько ждать подтверждения брокера.
STATUS_FIELDS = ("camera", "model", "hardware", "stats", "display", "controllerState", "error", "lastAction")


def event_key(record: dict) -> str:
    """Ключ события: то же сочетание, по которому сервер отбрасывает повторы."""
    return f"{record.get('event_id', '')}:{record.get('event', '')}"


def journal_files(path: Path) -> list[Path]:
    """Журнал по порядку: датированные архивы по возрастанию, затем активный файл."""
    archives = sorted(path.parent.glob(f"{path.stem}.*{path.suffix}"))
    return archives + ([path] if path.exists() else [])


def pending_events(path: Path, cursor: dict | None) -> list[dict]:
    """События журнала после курсора ``{"timestamp", "key"}``; без курсора — все."""
    records = []
    for file in journal_files(path):
        try:
            lines = file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
    if not cursor:
        return records
    for index, record in enumerate(records):
        if event_key(record) == cursor["key"]:
            return records[index + 1:]
    # Событие курсора уже удалено вместе со старым архивом: продолжаем по времени.
    return [record for record in records if record.get("timestamp", "") > cursor["timestamp"]]


class Telemetry:
    """Фоновая отправка данных устройства в брокер MQTT."""

    def __init__(self, settings: dict, state, events_path: Path, cursor_path: Path):
        self.settings = settings
        self.state = state
        self.events_path = events_path
        self.cursor_path = cursor_path
        self.device_id = settings.get("device_id") or socket.gethostname()
        self.device_name = settings.get("device_name") or self.device_id
        self.client = None
        self._stop = threading.Event()
        self._thread = None
        self._connected = threading.Event()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.get("mqtt_host") and self.settings.get("mqtt_username"))

    def topic(self, kind: str) -> str:
        return f"umka/{self.device_id}/{kind}"

    # ---------- Подключение ----------
    def _make_client(self):
        try:
            import paho.mqtt.client as mqtt
        except ModuleNotFoundError:
            LOG.warning("Телеметрия выключена: нет пакета paho-mqtt (pip install paho-mqtt)")
            return None
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                             client_id=f"umka-{self.device_id}")
        client.username_pw_set(self.settings.get("mqtt_username"), self.settings.get("mqtt_password") or None)
        if self.settings.get("mqtt_tls", True):
            client.tls_set()
        client.reconnect_delay_set(min_delay=2, max_delay=120)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        return client

    def _on_connect(self, _client, _userdata, _flags, reason_code, _properties=None):
        if reason_code.is_failure:
            LOG.warning("MQTT: подключение отклонено: %s", reason_code)
            return
        LOG.info("MQTT: подключено к %s как %s", self.settings["mqtt_host"], self.device_id)
        self._connected.set()

    def _on_disconnect(self, _client, _userdata, _flags, reason_code, _properties=None):
        if self._connected.is_set() and not self._stop.is_set():
            LOG.warning("MQTT: связь потеряна (%s), переподключение", reason_code)
        self._connected.clear()

    def _publish(self, kind: str, payload: dict, retain: bool = False) -> bool:
        """Отправить и дождаться подтверждения брокера (QoS 1)."""
        if not self._connected.is_set():
            return False
        info = self.client.publish(self.topic(kind), json.dumps(payload, ensure_ascii=False),
                                   qos=1, retain=retain)
        try:
            info.wait_for_publish(timeout=PUBLISH_TIMEOUT)
        except (RuntimeError, ValueError):
            return False
        return info.is_published()

    # ---------- Данные ----------
    def status_payload(self) -> dict:
        snapshot = self.state.snapshot()
        return {"name": self.device_name, **{key: snapshot.get(key) for key in STATUS_FIELDS}}

    def _load_cursor(self) -> dict | None:
        try:
            return json.loads(self.cursor_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _save_cursor(self, record: dict) -> None:
        self.cursor_path.parent.mkdir(parents=True, exist_ok=True)
        self.cursor_path.write_text(json.dumps(
            {"timestamp": record.get("timestamp", ""), "key": event_key(record)}), encoding="utf-8")

    def send_events(self) -> int:
        """Отправить накопившиеся события по порядку; вернуть число отправленных."""
        sent = 0
        for record in pending_events(self.events_path, self._load_cursor()):
            if not self._publish("event", record):
                break  # Связи нет: остальное — в следующий раз, с этого же места.
            self._save_cursor(record)
            sent += 1
        if sent:
            LOG.info("MQTT: отправлено событий: %d", sent)
        return sent

    # ---------- Жизненный цикл ----------
    def start(self) -> None:
        if not self.enabled:
            LOG.info("Телеметрия выключена: в umka.conf нет mqtt_host и mqtt_username")
            return
        self.client = self._make_client()
        if self.client is None:
            return
        self.client.connect_async(self.settings["mqtt_host"], int(self.settings.get("mqtt_port", 8883)),
                                  keepalive=60)
        self.client.loop_start()
        self._thread = threading.Thread(target=self._loop, name="telemetry", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        last_status = None
        while not self._stop.wait(EVENTS_INTERVAL if last_status is not None else 2):
            if not self._connected.is_set():
                continue
            try:
                now = time.monotonic()
                if last_status is None or now - last_status >= STATUS_INTERVAL:
                    if self._publish("status", self.status_payload(), retain=True):
                        last_status = now
                self.send_events()
            except Exception:
                LOG.exception("Ошибка телеметрии")

    def close(self) -> None:
        self._stop.set()
        if self.client is not None:
            self.client.loop_stop()
            self.client.disconnect()
