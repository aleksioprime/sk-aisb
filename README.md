# Установка окружения на Raspbery Pi

```sh
sudo apt install -y python3-picamera2 python3-opencv
```

## Создание виртуального окружения virtualenv:

Установите среду виртуального окружения (если необходимо):
```
sudo apt install python3-venv
```

## Создание виртуального окружения virtualenv:

Установите среду виртуального окружения (если необходимо):
```sh
sudo apt install python3-venv
```

Создайте виртуальное окружение:
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
sudo apt install libcap-dev
pip install wheel
```

Установите необходимые библиотеки:
```sh
pip install opencv-python==4.13.0.90
pip install ultralytics
```

Переустановите NumPy (для cameralib нужна версия < 2):
```sh
pip install --force-reinstall numpy==1.26.4
```
