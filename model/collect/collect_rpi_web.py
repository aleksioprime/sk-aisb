"""Веб-сервер для стриминга видео с Raspberry Pi камеры и создания снимков.

Модуль реализует MJPEG стриминг с камеры Picamera2 через HTTP-сервер.
Поддерживает просмотр видео в реальном времени через браузер и создание снимков.

Основные эндпоинты:
    / или /index.html - веб-интерфейс
    /stream.mjpg - MJPEG видеопоток
    /snapshot - создание и сохранение снимка
"""

import os
import io
import json
import logging
import argparse
import socket
import socketserver
from http import server
from threading import Condition
from datetime import datetime

from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
from libcamera import Transform


# Определение путей к директориям
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "template", "index.html")
SNAPSHOTS_DIR = os.path.join(BASE_DIR, "snapshots")


def load_html_template(path: str) -> str:
    """Загружает HTML-шаблон из файла"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logging.error("Template not found: %s", path)
        return "<html><body><h1>Error: template not found</h1></body></html>"


class StreamingOutput(io.BufferedIOBase):
    """Хранит последний JPEG-кадр и будит клиентов стрима"""

    def __init__(self):
        """Инициализирует буфер для потокового вывода."""
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        """Записывает новый кадр и уведомляет всех ожидающих клиентов"""
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


class StreamingHandler(server.BaseHTTPRequestHandler):
    """Обработчик HTTP-запросов для стриминга и снимков"""

    def do_GET(self):
        """Обрабатывает GET-запросы к серверу."""
        # Редирект с корня на главную страницу
        if self.path == "/":
            self.send_response(301)
            self.send_header("Location", "/index.html")
            self.end_headers()
            return

        # Отдаём главную HTML-страницу
        if self.path == "/index.html":
            html = load_html_template(TEMPLATE_PATH).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        # MJPEG стриминг - отправка непрерывного потока JPEG-кадров
        if self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()

            try:
                while True:
                    # Ожидаем новый кадр от камеры
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame

                    if not frame:
                        continue

                    # Отправляем кадр клиенту в формате multipart
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(frame)))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                logging.info("Client disconnected: %s", self.client_address)
            except Exception as e:
                logging.warning("Streaming error %s: %s", self.client_address, e)
            return

        # Создание и сохранение снимка
        if self.path == "/snapshot":
            try:
                # Берём последний кадр (JPEG) из стрима
                with output.condition:
                    frame = output.frame

                if not frame:
                    self.send_response(503)
                    self.end_headers()
                    self.wfile.write(b"No frame yet.")
                    return

                # Создаём директорию для снимков, если её нет
                os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

                # Генерируем имя файла с текущей датой и временем
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                filename = f"img_{ts}.jpg"
                filepath = os.path.join(SNAPSHOTS_DIR, filename)

                # Сохраняем кадр в файл
                with open(filepath, "wb") as f:
                    f.write(frame)

                logging.info("Snapshot saved: %s", filepath)

                # Отправляем клиенту JSON с именем сохранённого файла
                payload = json.dumps({"filename": filename}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            except Exception as e:
                logging.exception("Snapshot error: %s", e)
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Failed to save snapshot.")
            return

        self.send_error(404)


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    """
    Многопоточный HTTP-сервер для обслуживания видеопотока.

    ThreadingMixIn позволяет обрабатывать каждый запрос в отдельном потоке,
    что необходимо для одновременного обслуживания нескольких клиентов стрима.
    """
    allow_reuse_address = True
    daemon_threads = True


def get_local_ip():
    """
    Получает локальный IP-адрес устройства в сети.

    Использует трюк с подключением к внешнему адресу (без реальной отправки данных)
    для определения локального IP-адреса, который используется для выхода в интернет
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # Подключаемся к внешнему адресу (данные не отправляются)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(level=logging.INFO)

    # Парсинг аргументов командной строки
    parser = argparse.ArgumentParser(description="MJPEG Streaming + snapshot (Picamera2)")
    parser.add_argument("--flip", choices=["none", "h", "v", "hv"], default="none",
                        help="Отражение изображения: h=горизонтально, v=вертикально, hv=оба")
    parser.add_argument("--port", type=int, default=8000,
                        help="Порт для HTTP-сервера (по умолчанию: 8000)")
    args = parser.parse_args()

    # Настройка трансформации изображения (отражение)
    transform = Transform(hflip=("h" in args.flip), vflip=("v" in args.flip))

    # Инициализация и настройка камеры
    picam2 = Picamera2()
    config = picam2.create_video_configuration(main={"size": (640, 480)}, transform=transform)
    picam2.configure(config)

    # Создание буфера вывода и запуск записи видео
    output = StreamingOutput()
    picam2.start_recording(JpegEncoder(), FileOutput(output))

    try:
        # Запуск HTTP-сервера
        ip = get_local_ip()
        httpd = StreamingServer(("", args.port), StreamingHandler)
        logging.info("Server started: http://%s:%d", ip, args.port)
        httpd.serve_forever()
    finally:
        # Корректное завершение работы камеры
        picam2.stop_recording()
        picam2.close()
