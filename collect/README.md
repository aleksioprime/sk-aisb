# Collect

Папка для сбора снимков с камеры на ПК и Raspberry Pi.

## Файлы

- [collect_pc.py](collect_pc.py)  
  Сбор снимков с веб-камеры ПК через OpenCV.
- [collect_rpi.py](collect_rpi.py)  
  Сбор снимков с камеры Raspberry Pi через `capture_file`.
- [collect_rpi_cv.py](collect_rpi_cv.py)  
  Сбор снимков с Raspberry Pi через `capture_array()` и OpenCV-предпросмотр.
- [collect_rpi_web.py](collect_rpi_web.py)  
  Веб-интерфейс для MJPEG-стрима и создания снимков через браузер.
- [template/index.html](template/index.html)  
  HTML-шаблон для веб-интерфейса.
- [snapshots/](snapshots/)  
  Папка для сохранённых изображений.

## Типичные сценарии

ПК:

```bash
python collect/collect_pc.py
```

Raspberry Pi, консольный сбор:

```bash
python collect/collect_rpi.py
python collect/collect_rpi_cv.py
```

Raspberry Pi, веб-сервер:

```bash
python collect/collect_rpi_web.py --port 8000
```

После запуска веб-варианта откройте в браузере `http://<IP_RPI>:8000`.

## См. также

- [Главный README](../README.md)
- [Checking](../checking/README.md)
- [Training](../training/README.md)
