# Установка окружения на Raspberry Pi

## Рекомендуемые системы

- Raspberry Pi Zero 2 W: Raspberry Pi OS Lite 64-bit
- Raspberry Pi 4: Raspberry Pi OS 64-bit

## Системные пакеты

Обновите список пакетов:

```sh
sudo apt update
```

Установите обновления:

```sh
sudo apt upgrade -y
```

Проверьте камеру:

```sh
sudo rpicam-hello
```

Установите Picamera2:

```sh
sudo apt install -y python3-picamera2
```

Если нужно виртуальное окружение:

```sh
sudo apt install -y python3-venv
python -m venv --system-site-packages ~/venv
source ~/venv/bin/activate
pip install --upgrade pip
```

## Python-зависимости

Установите дополнительные зависимости:

```sh
pip install wheel
pip install opencv-python==4.11.0.86
pip install ultralytics==8.4.9
```

Проверка установок:

```sh
python -c "import picamera2; print('PiCamera2 - OK')"
python -c "import numpy; print(numpy.__version__)"
python -c "import cv2; print(cv2.__version__)"
python -c "import torch; print(torch.__version__)"
python -c "import torchvision; print(torchvision.__version__)"
python -c "import ultralytics; print(ultralytics.__version__)"
```

## Возможные проблемы

Если нужна совместимость с `numpy<2`:

```sh
pip install --force-reinstall numpy==1.26.4
```

Если `torch` падает с ошибкой `Illegal instruction`:

```sh
pip install --force-reinstall torch==2.9.0
pip install --force-reinstall torchvision==0.24.0
```

Если возникает ошибка `ImportError: libGL.so.1: cannot open shared object file`:

```sh
sudo apt install -y libgl1
```

## Быстрая проверка камеры

```sh
python
>>> from picamera2 import Picamera2
>>> picam2 = Picamera2()
>>> picam2.configure(picam2.create_still_configuration())
>>> picam2.start()
>>> picam2.capture_file("photo.jpg")
>>> picam2.stop()
```

## Быстрая проверка YOLO

```sh
curl -L -o bus.jpg https://ultralytics.com/images/bus.jpg
python
>>> from ultralytics import YOLO
>>> model = YOLO("yolov8n.pt")
>>> results = model("bus.jpg", imgsz=320, verbose=True)
>>> print("Inference OK. Detections:", results[0].boxes.shape[0])
```

## Связанные разделы

- [Главный README](../README.md)
- [Checking](../checking/README.md)
- [Detection](../detection/README.md)
