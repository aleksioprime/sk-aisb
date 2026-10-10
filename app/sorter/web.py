"""Встроенный многопоточный HTTP-сервер API и статического интерфейса."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit


LOG = logging.getLogger(__name__)


class WebServer:
    """Раздавать страницу UMKA и минимальный JSON API без Node.js."""

    def __init__(self, host: str, port: int, static_dir: Path, state, feedback_handler, preview=None,
                 routes=None):
        self.host = host
        self.port = port
        self.static_dir = static_dir.resolve()
        self.state = state
        self.feedback_handler = feedback_handler
        self.preview = preview
        # (метод, путь) → функция(тело POST или параметры GET) → (HTTP-статус, ответ).
        # Ответ — словарь для JSON или bytes для JPEG-изображения.
        self.routes = routes or {}
        self._server = None
        self._thread = None

    def start(self) -> None:
        """Создать HTTP-сервер и запустить его в фоновом daemon-потоке."""
        owner = self

        class Handler(BaseHTTPRequestHandler):
            """Обработчик одного HTTP-запроса с доступом к внешнему WebServer."""

            def do_GET(self):
                """Вернуть состояние, диагностику или статический файл."""
                url = urlsplit(self.path)
                path = url.path
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
                if path == "/api/camera.mjpg" and owner.preview is not None:
                    return self._mjpeg()
                if ("GET", path) in owner.routes:
                    # GET-обработчик получает параметры строки запроса как словарь.
                    return self._route("GET", path, dict(parse_qsl(url.query)))
                return self._static(path)

            def do_POST(self):
                """Принять подтверждение пользователя или команду маршрута из routes."""
                path = urlsplit(self.path).path
                if path != "/api/feedback" and path != "/api/answer" and ("POST", path) not in owner.routes:
                    return self._json(404, {"error": "Not found"})
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    # API принимает короткие JSON-объекты; лимит защищает память от
                    # случайно или намеренно огромного тела запроса.
                    if length > 4096:
                        return self._json(413, {"error": "Request too large"})
                    body = json.loads(self.rfile.read(length) or b"{}")
                    if not isinstance(body, dict):
                        return self._json(400, {"error": "Invalid JSON"})
                    if ("POST", path) in owner.routes:
                        return self._route("POST", path, body)
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

            def _route(self, method: str, path: str, body: dict):
                """Вызвать обработчик маршрута; ошибки данных вернуть как 400."""
                try:
                    status, payload = owner.routes[(method, path)](body)
                except (ValueError, KeyError, TypeError) as exc:
                    return self._json(400, {"error": str(exc)})
                except RuntimeError as exc:
                    # Устройство недоступно или отказало: ошибка не в запросе.
                    return self._json(503, {"error": str(exc)})
                except Exception as exc:
                    LOG.exception("Ошибка обработчика %s %s", method, path)
                    return self._json(500, {"error": str(exc)})
                if isinstance(payload, Path):
                    # Файл-выгрузка (архив датасета): отдаётся потоком и затем удаляется.
                    try:
                        self.send_response(status)
                        self.send_header("Content-Type", "application/zip")
                        self.send_header("Content-Length", str(payload.stat().st_size))
                        self.send_header("Content-Disposition", f'attachment; filename="{payload.name}"')
                        self.end_headers()
                        with payload.open("rb") as source:
                            shutil.copyfileobj(source, self.wfile, 1024 * 1024)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    finally:
                        os.unlink(payload)
                    return
                if isinstance(payload, bytes):
                    # Двоичный ответ обработчиков — JPEG-миниатюра.
                    self.send_response(status)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Cache-Control", "max-age=3600")
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                return self._json(status, payload)

            def _mjpeg(self):
                """Отдавать кадры камеры потоком multipart, пока клиент подключён."""
                boundary = "umkaframe"
                self.send_response(200)
                self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={boundary}")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                owner.preview.add_viewer()
                sequence = 0
                try:
                    while True:
                        sequence, jpeg = owner.preview.next_jpeg(sequence)
                        if jpeg is None:
                            continue
                        self.wfile.write(
                            f"--{boundary}\r\nContent-Type: image/jpeg\r\n"
                            f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
                        )
                        self.wfile.write(jpeg)
                        self.wfile.write(b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    owner.preview.remove_viewer()

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
