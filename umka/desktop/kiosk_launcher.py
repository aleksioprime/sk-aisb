#!/usr/bin/env python3
"""Запустить Chromium kiosk и разрешить странице закрыть только это окно."""

from __future__ import annotations

import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen


KIOSK_HELPER_HOST = "127.0.0.1"
KIOSK_HELPER_PORT = 3001
UMKA_STATE_URL = "http://127.0.0.1:3000/api/state"


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


def main() -> None:
    """Запустить локальный endpoint выхода и отдельный процесс Chromium."""
    token = secrets.token_urlsafe(24)
    chromium_process: subprocess.Popen | None = None

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
        profile = Path.home() / ".cache" / "umka-kiosk-chromium"
        profile.mkdir(parents=True, exist_ok=True)
        chromium_process = subprocess.Popen([
            "chromium",
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
            "--start-maximized",
            f"--user-data-dir={profile}",
        ])
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


if __name__ == "__main__":
    main()
