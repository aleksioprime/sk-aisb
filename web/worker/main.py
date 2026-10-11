"""Принимать сообщения устройств UMKA из MQTT и сохранять в PostgreSQL.

Топики: umka/<device_id>/status - состояние устройства (раз в минуту, retain);
        umka/<device_id>/event  - событие сортировки или ответа (QoS 1).
Формат сообщений - web/README.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from aiomqtt import Client, MqttError
from sqlalchemy.dialects.postgresql import insert

from shared.db import Device, Event, Session, create_tables

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("worker")


def parse_time(value) -> datetime:
    """ISO-время устройства; без него - время приёма."""
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


async def handle(topic: str, payload: dict) -> None:
    """Обновить устройство и сохранить событие или статус."""
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "umka":
        LOG.warning("Неизвестный топик %s", topic)
        return
    device_id, kind = parts[1], parts[2]
    now = datetime.now(timezone.utc)
    async with Session() as session:
        device = await session.get(Device, device_id) or Device(id=device_id)
        device.last_seen = now
        if kind == "status":
            device.status = payload
            device.name = payload.get("name") or device.name
        session.add(device)
        await session.flush()
        if kind == "event":
            await session.execute(insert(Event).values(
                device_id=device_id,
                event_id=str(payload.get("event_id", "")),
                kind=str(payload.get("event", "unknown")),
                timestamp=parse_time(payload.get("timestamp")),
                payload=payload,
            ).on_conflict_do_nothing())
        await session.commit()
    LOG.info("%s %s", device_id, kind)


async def main() -> None:
    await create_tables()
    topic = os.environ.get("MQTT_TOPIC", "umka/+/+")
    while True:
        try:
            async with Client(
                hostname=os.environ.get("MQTT_HOST", "mosquitto"),
                port=int(os.environ.get("MQTT_PORT", "1883")),
                username=os.environ.get("MQTT_USERNAME") or None,
                password=os.environ.get("MQTT_PASSWORD") or None,
            ) as client:
                await client.subscribe(topic, qos=1)
                LOG.info("Подписка на %s", topic)
                async for message in client.messages:
                    try:
                        await handle(message.topic.value, json.loads(message.payload))
                    except Exception:
                        LOG.exception("Сообщение %s не сохранено", message.topic.value)
        except MqttError as exc:
            LOG.error("MQTT: %s, переподключение через 5 с", exc)
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
