"""Создать пользователя сайта или сменить ему пароль (как create_superuser в empolimer).

В Coolify: приложение umka → Terminal → контейнер backend:
    python create_user.py admin --admin
Локально:
    docker compose exec backend python create_user.py admin --admin
Пароль спрашивается дважды и не попадает в историю команд.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass

from sqlalchemy import select
from werkzeug.security import generate_password_hash

from shared.db import Session, User, create_tables


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("username")
    parser.add_argument("--admin", action="store_true", help="Сделать администратором")
    parser.add_argument("--disable", action="store_true", help="Отключить пользователя без удаления")
    args = parser.parse_args()
    await create_tables()
    async with Session() as session:
        user = await session.scalar(select(User).where(User.username == args.username))
        if args.disable:
            if user is None:
                raise SystemExit("Пользователь не найден")
            user.is_active = False
            await session.commit()
            print(f"Пользователь {args.username} отключён")
            return
        password = getpass.getpass("Пароль: ")
        if len(password) < 8:
            raise SystemExit("Пароль должен быть не короче 8 символов")
        if password != getpass.getpass("Повторите пароль: "):
            raise SystemExit("Пароли не совпадают")
        if user is None:
            user = User(username=args.username)
            session.add(user)
        user.password_hash = generate_password_hash(password)
        user.is_active = True
        user.is_admin = user.is_admin or args.admin
        await session.commit()
        print(f"Пользователь {args.username} сохранён" + (" (администратор)" if user.is_admin else ""))


if __name__ == "__main__":
    asyncio.run(main())
