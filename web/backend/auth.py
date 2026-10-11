"""Авторизация как в empolimer: пара JWT (access + refresh), пароли в хешах.

Access-токен живёт 30 минут и передаётся в заголовке Authorization: Bearer.
Refresh-токен живёт 30 дней и нужен, чтобы получить новый access; при выходе
он отзывается (таблица revoked_tokens).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import delete, select
from werkzeug.security import check_password_hash

from shared.db import RevokedToken, Session, User

SECRET_KEY = os.environ["JWT_SECRET_KEY"]
ALGORITHM = "HS256"
ACCESS_LIFETIME = timedelta(minutes=int(os.environ.get("JWT_ACCESS_MINUTES", "30")))
REFRESH_LIFETIME = timedelta(days=int(os.environ.get("JWT_REFRESH_DAYS", "30")))

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


class LoginBody(BaseModel):
    username: str
    password: str


class RefreshBody(BaseModel):
    refresh_token: str


def create_token(user: User, kind: str, lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user.id), "username": user.username, "is_admin": user.is_admin,
                       "type": kind, "jti": uuid.uuid4().hex, "iat": now, "exp": now + lifetime},
                      SECRET_KEY, algorithm=ALGORITHM)


def decode(token: str, kind: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Срок действия токена истёк")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Недействительный токен")
    if payload.get("type") != kind:
        raise HTTPException(401, "Неверный тип токена")
    return payload


async def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    """Зависимость для защищённых маршрутов: проверить access-токен."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Нужна авторизация")
    return decode(credentials.credentials, "access")


async def _active_user(session, user_id: str) -> User:
    user = await session.get(User, int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(401, "Пользователь не найден или отключён")
    return user


@router.post("/login")
async def login(body: LoginBody) -> dict:
    async with Session() as session:
        user = await session.scalar(select(User).where(User.username == body.username))
        if user is None or not user.is_active or not check_password_hash(user.password_hash, body.password):
            raise HTTPException(401, "Неверный логин или пароль")
        return {"access_token": create_token(user, "access", ACCESS_LIFETIME),
                "refresh_token": create_token(user, "refresh", REFRESH_LIFETIME)}


@router.post("/refresh")
async def refresh(body: RefreshBody) -> dict:
    payload = decode(body.refresh_token, "refresh")
    async with Session() as session:
        if await session.get(RevokedToken, payload["jti"]):
            raise HTTPException(401, "Токен отозван")
        user = await _active_user(session, payload["sub"])
        return {"access_token": create_token(user, "access", ACCESS_LIFETIME)}


@router.post("/logout")
async def logout(body: RefreshBody) -> dict:
    payload = decode(body.refresh_token, "refresh")
    async with Session() as session:
        # Заодно удалить отозванные токены, срок которых уже истёк.
        await session.execute(delete(RevokedToken).where(RevokedToken.expires_at < datetime.now(timezone.utc)))
        if not await session.get(RevokedToken, payload["jti"]):
            session.add(RevokedToken(jti=payload["jti"],
                                     expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc)))
        await session.commit()
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(current_user)) -> dict:
    return {"id": int(user["sub"]), "username": user["username"], "is_admin": user.get("is_admin", False)}
