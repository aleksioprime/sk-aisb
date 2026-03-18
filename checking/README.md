# Checking

Папка для быстрых проверок камер и простых диагностических скриптов.

## Файлы

- [camera_rpi.py](camera_rpi.py)  
  Проверка захвата кадров с `Picamera2`, выводит размер изображения и число каналов.
- [camera_rpi_yolo.py](camera_rpi_yolo.py)  
  Быстрый тест YOLO прямо на Raspberry Pi.
- [camera_pc.py](camera_pc.py)  
  Сейчас пустой файл-заготовка для проверки камеры ПК.

## Когда использовать

- если нужно убедиться, что камера вообще выдаёт кадры;
- если нужно быстро проверить цветовые каналы и размер изображения;
- если нужно отделить проблему камеры от проблемы модели.

## Примеры

```bash
python checking/camera_rpi.py
python checking/camera_rpi_yolo.py
```

## См. также

- [Главный README](../README.md)
- [Collect](../collect/README.md)
- [Detection](../detection/README.md)
