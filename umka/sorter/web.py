"""Встроенный многопоточный HTTP-сервер API и статического интерфейса."""

from __future__ import annotations

import json
import logging
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


LOG = logging.getLogger(__name__)


class WebServer:
    """Раздавать страницу UMKA и минимальный JSON API без Node.js."""

    def __init__(self, host: str, port: int, static_dir: Path, state, feedback_handler):
        self.host = host
        self.port = port
        self.static_dir = static_dir.resolve()
        self.state = state
        self.feedback_handler = feedback_handler
        self._server = None
        self._thread = None

    def start(self) -> None:
        """Создать HTTP-сервер и запустить его в фоновом daemon-потоке."""
        owner = self

        class Handler(BaseHTTPRequestHandler):
            """Обработчик одного HTTP-запроса с доступом к внешнему WebServer."""

            def do_GET(self):
                """Вернуть состояние, диагностику или статический файл."""
                path = urlsplit(self.path).path
                if path == "/api/state":
                    return self._json(200, owner.state.snapshot())
                if path == "/api/health":
                    snapshot = owner.state.snapshot()
                    ok = snapshot["camera"]["ok"] and snapshot["model"]["ok"]
                    return self._json(200 if ok else 503, {
                        "ok": ok,
                        "camera": snapshot["camera"],
                        "model": snapshot["model"],
                        "hardware": snapshot["hardware"],
                        "error": snapshot["error"],
                    })
                return self._static(path)

            def do_POST(self):
                """Принять подтверждение пользователя для события сортировки."""
                path = urlsplit(self.path).path
                if path != "/api/feedback" and path != "/api/answer":
                    return self._json(404, {"error": "Not found"})
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    # API принимает два коротких поля; лимит защищает память от
                    # случайно или намеренно огромного тела запроса.
                    if length > 4096:
                        return self._json(413, {"error": "Request too large"})
                    body = json.loads(self.rfile.read(length) or b"{}")
                    answer = body.get("answer")
                    if answer not in {"yes", "no"}:
                        return self._json(400, {"error": "answer must be yes or no"})
                    accepted = owner.feedback_handler(answer, body.get("eventId"))
                    return self._json(200 if accepted else 409, {"success": accepted})
                except (ValueError, TypeError, json.JSONDecodeError):
                    return self._json(400, {"error": "Invalid JSON"})

            def do_OPTIONS(self):
                """Сообщить допустимые методы для совместимости с браузерами."""
                self.send_response(204)
                self.send_header("Allow", "GET, POST, OPTIONS")
                self.end_headers()

            def _static(self, request_path: str):
                """Безопасно отдать файл только из настроенного static_dir."""
                relative = "index.html" if request_path == "/" else unquote(request_path).lstrip("/")
                candidate = (owner.static_dir / relative).resolve()
                # resolve() и проверка родителей блокируют ../ и кодированный
                # path traversal за пределы каталога интерфейса.
                if candidate != owner.static_dir and owner.static_dir not in candidate.parents:
                    return self._text(403, "Forbidden")
                if not candidate.is_file():
                    return self._text(404, "Not found")
                content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
                content = candidate.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(content)

            def _json(self, status: int, payload: dict):
                """Отправить JSON-ответ в UTF-8."""
                content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def _text(self, status: int, message: str):
                """Отправить короткий текстовый ответ об ошибке."""
                content = message.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def log_message(self, fmt, *args):
                """Перенаправить стандартный HTTP-журнал в logging."""
                LOG.debug("HTTP %s", fmt % args)

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="web-server", daemon=True)
        self._thread.start()
        LOG.info("Веб-интерфейс: http://%s:%s", self.host, self.port)

    def close(self) -> None:
        """Остановить HTTP-цикл, закрыть сокет и дождаться потока."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread:
            self._thread.join(timeout=2)
