# Network Streaming

В этой папке лежат две минимальные программы:

- [stream_server_rpi.py](/Users/aleksioprime/edu/gymnasium/sk-aisb/network/stream_server_rpi.py)
  Запускается на Raspberry Pi, поднимает TCP-сервер, читает кадры с `Picamera2` и отдаёт их как JPEG-поток.
- [stream_client_pc.py](/Users/aleksioprime/edu/gymnasium/sk-aisb/network/stream_client_pc.py)
  Запускается на ПК, подключается к Raspberry Pi, принимает JPEG-кадры и распознаёт их через YOLO.

## Зависимости

Raspberry Pi:

```bash
sudo apt install -y python3-picamera2
pip install opencv-python
```

ПК:

```bash
pip install ultralytics opencv-python numpy
```

## Порядок запуска

Сначала на Raspberry Pi запустите сервер:

```bash
python stream_server_rpi.py
```

Потом на ПК запустите клиент и укажите IP-адрес Raspberry Pi:

```bash
python network/stream_client_pc.py --host 192.168.1.102 --port 5000 --model network/yolov8n.pt
```

Здесь `192.168.1.50` нужно заменить на реальный IP-адрес Raspberry Pi в локальной сети.

## Параметры

`stream_server_rpi.py`:

- настройки задаются константами в начале файла: `HOST`, `PORT`, `CAMERA_SIZE`, `JPEG_QUALITY`, `WARMUP_SEC`
- после отключения клиента сервер не завершается, а снова ждёт новое подключение

`stream_client_pc.py`:

- `--host` IP-адрес Raspberry Pi
- `--port` TCP-порт сервера
- `--model` путь к `.pt` модели
- `--conf` порог confidence, по умолчанию `0.50`

По параметрам распознавания клиент сделан таким же, как `detection/detect_pc.py`: одинаковые `--model`, `--conf` и одинаковый вызов `YOLO`.

## Пример для Raspberry Pi Zero 2 W

Если нужен более лёгкий поток:

```bash
python network/stream_server_rpi.py
```

Если сеть слабая, сначала уменьшайте `JPEG_QUALITY`, а не разрешение.
