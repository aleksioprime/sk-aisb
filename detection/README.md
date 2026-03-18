# Detection

В этой папке лежат программы для запуска детекции объектов YOLO из видеопотока.

## Файлы

- [detect_pc.py](detect_pc.py)
  Минимальный запуск детекции с обычной веб-камеры через OpenCV на ПК.
- [detect_rpi.py](detect_rpi.py)
  Детекция на Raspberry Pi через `Picamera2` с настраиваемыми параметрами модели и камеры.
- [example.pt](example.pt)
  Файл весов YOLO, который используется по умолчанию.

## Зависимости

Для ПК:

```bash
pip install ultralytics opencv-python
```

Подробная настройка окружения для Raspberry Pi описана в [docs/setup-rpi.md](../docs/setup-rpi.md).

## Запуск на ПК

Запуск с моделью по умолчанию:

```bash
python detection/detect_pc.py
```

Запуск с явным указанием файла весов:

```bash
python detection/detect_pc.py --model detection/example.pt
```

Запуск с настройкой порога confidence:

```bash
python detection/detect_pc.py --model detection/example.pt --conf 0.50
```

Что делает программа:

- открывает камеру `VideoCapture(0)`;
- для сравнения с Raspberry Pi поток сначала пережимается в JPEG с качеством `80`;
- подаёт кадры в YOLO;
- показывает окно с боксами;
- завершение по `q` или `Esc`.

## Запуск на Raspberry Pi

Базовый запуск:

```bash
python detect_rpi.py --model example.pt
```

Запуск без окна:

```bash
python detect_rpi.py --model example.pt --headless
```

Рекомендуемый старт для Raspberry Pi Zero 2 W:

```bash
python detect_rpi.py \
  --model example.pt \
  --conf 0.55 \
  --imgsz 320 \
  --camera-width 640 \
  --camera-height 480 \
  --warmup-sec 2
```

Более осторожный вариант, если сеть путает классы:

```bash
python detect_rpi.py \
  --model example.pt \
  --conf 0.60 \
  --imgsz 320 \
  --camera-width 640 \
  --camera-height 480 \
  --warmup-sec 2
```

Более точный, но более тяжёлый вариант:

```bash
python detect_rpi.py \
  --model example.pt \
  --conf 0.55 \
  --imgsz 416 \
  --camera-width 640 \
  --camera-height 480 \
  --warmup-sec 2
```

## Параметры `detect_rpi.py`

- `--model`
  Путь к `.pt` файлу модели.
- `--conf`
  Порог confidence. Чем выше значение, тем меньше ложных срабатываний, но можно потерять слабые детекции.
- `--imgsz`
  Размер входа YOLO. Для `Raspberry Pi Zero 2 W` обычно имеет смысл `320`, иногда `416`.
- `--camera-width`, `--camera-height`
  Разрешение кадра с камеры.
- `--warmup-sec`
  Время ожидания после старта камеры, чтобы стабилизировались автоэкспозиция и баланс белого.
- `--headless`
  Запуск без `imshow`, удобно по SSH.

## Практические замечания

- Если на Raspberry Pi классы определяются неверно, первым делом повышайте `--conf` до `0.55` или `0.60`.
- Для `Raspberry Pi Zero 2 W` не стоит сразу ставить `--imgsz 640`: обычно это слишком тяжело.
- `--imgsz 256` работает быстрее, но классификация обычно хуже.
- `--imgsz 320` это основной компромисс между скоростью и качеством.
- Если объект стабильно определяется неправильным классом даже при `conf=0.6`, проблема, скорее всего, уже в самой модели или в отличии кадров с Pi-камеры от обучающего датасета.
