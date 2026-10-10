#!/usr/bin/env python3
"""Запустить Chromium kiosk и разрешить странице закрыть только это окно."""

from __future__ import annotations

import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen


KIOSK_HELPER_HOST = "127.0.0.1"
KIOSK_HELPER_PORT = 3001
UMKA_STATE_URL = "http://127.0.0.1:3000/api/state"
# Сообщения Chromium о GPU, ANGLE, Vulkan и опросе камер не связаны с UMKA и
# засоряют терминал. Они уходят в этот файл и переписываются при каждом запуске.
CHROMIUM_LOG = Path(__file__).resolve().parent / "data" / "logs" / "kiosk.log"


def find_chromium() -> str:
    """Найти Chromium в Raspberry Pi OS или Ubuntu, включая Snap."""
    for name in ("chromium", "chromium-browser", "/snap/bin/chromium"):
        executable = shutil.which(name)
        if executable:
            return executable
    raise RuntimeError("Chromium не найден. Установите chromium или chromium-browser.")


def kiosk_profile() -> Path:
    """Выбрать отдельный профиль, доступный также Chromium из Snap."""
    if Path("/snap/chromium/current").exists():
        return Path.home() / "snap" / "chromium" / "common" / "umka-kiosk"
    return Path.home() / ".cache" / "umka-kiosk-chromium"


def open_chromium_log():
    """Открыть файл для вывода Chromium; при отказе вернуть None.

    None означает, что вывод браузера будет отброшен: файл недоступен,
    например когда киоск запущен другим пользователем, чем сама UMKA. Ошибки
    самого запуска киоска печатает Python, и они видны в любом случае.
    """
    try:
        CHROMIUM_LOG.parent.mkdir(parents=True, exist_ok=True)
        return open(CHROMIUM_LOG, "w", buffering=1, encoding="utf-8",
                    errors="replace")
    except OSError:
        return None


def wait_for_umka(timeout: float = 60.0) -> bool:
    """Дождаться готовности API, чтобы Chromium не показал страницу ошибки."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(UMKA_STATE_URL, timeout=1) as response:
                if response.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(1)
    return False


def exit_on_sigterm() -> None:
    """Обрабатывать сигнал TERM так же, как Ctrl+C.

    Без обработчика Python завершается сразу и не закрывает Chromium: тот
    остаётся на экране без управления. sys.exit возбуждает SystemExit, поэтому
    отрабатывает блок finally, который останавливает браузер. Так `pkill` по
    SSH закрывает киоск целиком.
    """
    signal.signal(signal.SIGTERM, lambda _signum, _frame: sys.exit(0))


def main() -> None:
    """Запустить локальный endpoint выхода и отдельный процесс Chromium."""
    exit_on_sigterm()
    chromium = find_chromium()
    token = secrets.token_urlsafe(24)
    chromium_process: subprocess.Popen | None = None
    chromium_log = open_chromium_log()

    class ExitHandler(BaseHTTPRequestHandler):
        """Принимать команду выхода только с loopback и с одноразовым токеном."""

        def do_POST(self):
            nonlocal chromium_process
            parsed = urlsplit(self.path)
            supplied = parse_qs(parsed.query).get("token", [""])[0]
            allowed = (
                parsed.path == "/exit"
                and self.client_address[0] in {"127.0.0.1", "::1"}
                and secrets.compare_digest(supplied, token)
            )
            self.send_response(204 if allowed else 403)
            self.send_header("Access-Control-Allow-Origin", "http://localhost:3000")
            self.end_headers()
            if allowed and chromium_process and chromium_process.poll() is None:
                threading.Timer(0.1, chromium_process.terminate).start()

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "http://localhost:3000")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.end_headers()

        def log_message(self, _format, *_args):
            pass

    server = ThreadingHTTPServer((KIOSK_HELPER_HOST, KIOSK_HELPER_PORT), ExitHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        wait_for_umka()
        query = urlencode({"kiosk_token": token})
        profile = kiosk_profile()
        profile.mkdir(parents=True, exist_ok=True)
        chromium_process = subprocess.Popen([
            chromium,
            f"http://localhost:3000/?{query}",
            "--kiosk",
            "--noerrdialogs",
            "--disable-infobars",
            "--no-first-run",
            # В киоске не нужны предложение перевода и связанная с ним панель.
            "--disable-translate",
            "--disable-features=Translate,TranslateUI",
            "--lang=ru",
            # Киоск-профиль не хранит пользовательские пароли. Этот параметр
            # не даёт Chromium запрашивать разблокировку системного keyring.
            "--password-store=basic",
            # Уровень 3 оставляет только фатальные сообщения Chromium.
            "--log-level=3",
            "--start-maximized",
            f"--user-data-dir={profile}",
        ], stdout=chromium_log or subprocess.DEVNULL,
           stderr=subprocess.STDOUT)
        chromium_process.wait()
    finally:
        if chromium_process and chromium_process.poll() is None:
            chromium_process.terminate()
            try:
                chromium_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                chromium_process.kill()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
        if chromium_log is not None:
            chromium_log.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Ctrl+C — штатный способ закрыть киоск из терминала. Chromium уже
        # остановлен в блоке finally, поэтому трассировка ничего не поясняет.
        print("Киоск закрыт.")
