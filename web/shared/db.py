"""Модели и подключение к PostgreSQL, общие для worker и backend."""

from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

engine = create_async_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Device(Base):
    """Устройство UMKA; создаётся при первом сообщении от него."""

    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(128))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Последний статус целиком: камера, модель, моторы, статистика.
    status: Mapped[dict | None] = mapped_column(JSON)


class Event(Base):
    """Событие устройства: сортировка или ответ «Да/Нет» (как в events.jsonl)."""

    __tablename__ = "events"
    # Устройство переотправляет события после пропадания сети: дубли отсекаются.
    __table_args__ = (UniqueConstraint("device_id", "event_id", "kind"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))  # sort | feedback
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload: Mapped[dict] = mapped_column(JSON)


class User(Base):
    """Пользователь сайта мониторинга. Создаётся скриптом backend/create_user.py."""

    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RevokedToken(Base):
    """Отозванный при выходе refresh-токен (по jti) до истечения его срока."""

    __tablename__ = "revoked_tokens"
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


async def create_tables() -> None:
    """Создать таблицы, если их нет. Позже заменить миграциями Alembic."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
