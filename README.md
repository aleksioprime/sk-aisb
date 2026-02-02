# Установка окружения на Raspbery Pi (64 bit)

- Raspberry Pi Zero 2W: Raspberry Pi OS (Legacy, 64-bit) Lite - A port of Debian Bookworm with security updates and no desktop environment
- Raspberry Pi 4: Raspberry Pi OS (64-bit) - A port of Debian Trixie with the Raspberry Pi Desktop

Обновите список доступных пакетов:
```sh
sudo apt update
```

Установите обновления для всех пакетов:
```sh
sudo apt upgrade -y
```

Проверьте камеру:
```sh
sudo rpicam-hello
```

Установите системную Python-библиотеку picamera2 для работы с камерой через libcamera:
```sh
sudo apt install -y python3-picamera2
```

## Создание виртуального окружения virtualenv:

Установите среду виртуального окружения (если необходимо):
```sh
sudo apt install python3-venv
```

Создайте виртуальное окружение (с доступом к пакетам, установленным в системе):
```sh
python -m venv --system-site-packages ~/venv
```

Запустите виртуальное окружение и обновите менеджер pip:
```sh
source ~/venv/bin/activate
pip install --upgrade pip
```

Для деактивации виртуального окружения:
```sh
deactivate
```

Для удаления виртуального окружения:
```sh
rm -rf ~/venv
```

Установите дополнительные зависимости:
```sh
pip install wheel
```

Для просмотра индексов пакета можно использовать `pip index versions <имя пакета>`

Установите библиотеку opencv:
```sh
pip install opencv-python==4.11.0.86
```

Установите пакет для YOLO:
```sh
pip install ultralytics==8.4.9
```

Проверьте установки:
```sh
python -c "import picamera2; print('PiCamera2 - OK')"
python -c "import numpy; print(numpy.__version__)"
python -c "import cv2; print(cv2.__version__)"
python -c "import torch; print(torch.__version__)"
python -c "import torchvision; print(torchvision.__version__)"
python -c "import ultralytics; print(ultralytics.__version__)"
```

Если для cameralib понадобится `numpy<2`, то переустановите на `numpy-1.26.4`:
```sh
pip install --force-reinstall numpy==1.26.4
```

Если torch выдаёт ошибку `Illegal instruction`, то установи другую версию torch:
```sh
pip install --force-reinstall torch==2.9.0
pip install --force-reinstall torchvision==0.24.0
```

Проверка работы камеры:
```sh
python
>> from picamera2 import Picamera2
>> picam2 = Picamera2()
>> picam2.configure(picam2.create_still_configuration())
>> picam2.start()
>> picam2.capture_file("photo.jpg")
>> picam2.stop()
>> exit()
```

Проверка работы YOLO:
```sh
curl -L -o bus.jpg https://ultralytics.com/images/bus.jpg
python
>> from ultralytics import YOLO
>> model = YOLO("yolov8n.pt")
>> results = model("bus.jpg", imgsz=320, verbose=True)
>> print("Inference OK. Detections:", results[0].boxes.shape[0])
>> exit()
```

Если будет выходит ошибка `ImportError: libGL.so.1: cannot open shared object file: No such file or directory`, то установите зависимости:
```sh
sudo apt install libgl1
```