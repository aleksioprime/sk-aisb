"""API мониторинга сети UMKA: устройства, их состояние и события."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException
from sqlalchemy import func, select, text

from shared.db import Device, Event, Session

app = FastAPI(title="UMKA monitoring")
ONLINE_WINDOW = timedelta(minutes=3)  # Статус приходит раз в минуту.


def device_view(device: Device) -> dict:
    online = bool(device.last_seen and datetime.now(timezone.utc) - device.last_seen < ONLINE_WINDOW)
    return {"id": device.id, "name": device.name, "online": online,
            "lastSeen": device.last_seen, "status": device.status}


@app.get("/api/health")
async def health() -> dict:
    """Проверка для Docker и Coolify: API отвечает и база доступна."""
    async with Session() as session:
        await session.execute(select(1))
    return {"ok": True}


@app.get("/api/devices")
async def devices() -> list[dict]:
    async with Session() as session:
        result = await session.scalars(select(Device).order_by(Device.id))
        return [device_view(device) for device in result]


@app.get("/api/devices/{device_id}")
async def device(device_id: str) -> dict:
    async with Session() as session:
        item = await session.get(Device, device_id)
        if item is None:
            raise HTTPException(404, "Устройство не найдено")
        return device_view(item)


@app.get("/api/devices/{device_id}/events")
async def events(device_id: str, limit: int = 100) -> list[dict]:
    async with Session() as session:
        result = await session.scalars(
            select(Event).where(Event.device_id == device_id)
            .order_by(Event.timestamp.desc()).limit(min(limit, 1000)))
        return [{"eventId": e.event_id, "kind": e.kind, "timestamp": e.timestamp, **e.payload} for e in result]


@app.get("/api/summary")
async def summary() -> dict:
    """Сводка по сети: устройства и сортировки по типам отходов."""
    async with Session() as session:
        rows = await session.execute(
            # Группировка по номеру столбца: ключ JSON в SELECT и GROUP BY иначе
            # передаётся разными параметрами, и PostgreSQL не считает их одним выражением.
            select(Event.payload["waste_type"].as_string(), func.count())
            .where(Event.kind == "sort").group_by(text("1")))
        devices_total = await session.scalar(select(func.count()).select_from(Device))
        return {"devices": devices_total, "sortedByType": {kind or "unknown": count for kind, count in rows}}
