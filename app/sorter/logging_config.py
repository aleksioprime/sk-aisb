"""Единая настройка консольного и файлового журналирования UMKA."""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(
    log_file: Path,
    verbose: bool = False,
    backup_count: int = 14,
) -> bool:
    """Настроить корневой logger для терминала, journald и файла.

    Активный файл каждый день переименовывается с датой в имени. Хранятся
    ``backup_count`` последних архивов. Если файл создать нельзя, приложение
    продолжает работать с консольным журналом и возвращает ``False``.
    """
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    root = logging.getLogger()

    # Функция вызывается один раз при старте, но очистка делает повторный вызов
    # предсказуемым в тестах и не допускает дублирования каждой строки.
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()

    root.setLevel(level)
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            log_file,
            when="midnight",
            interval=1,
            backupCount=backup_count,
            encoding="utf-8",
            delay=False,
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler.suffix = "%Y-%m-%d"
        root.addHandler(file_handler)
    except OSError as exc:
        root.error("Не удалось открыть файл журнала %s: %s", log_file, exc)
        return False

    root.info("Файловый журнал: %s (хранится архивов: %d)", log_file, backup_count)
    return True
