# Waste

Минимальный прототип для "умной мусорки":

- Raspberry Pi стримит изображение с камеры и принимает простые текстовые команды;
- ПК принимает поток, распознаёт класс через YOLO и отправляет команду назад;
- Raspberry Pi выполняет заранее заданные действия сервомоторов для этой команды.

## Файлы

- [waste_server_rpi.py](waste_server_rpi.py)
  Камера + TCP-сервер + выполнение команд сервомоторов на Raspberry Pi.
- [waste_client_pc.py](waste_client_pc.py)
  Приём потока, YOLO-детекция и отправка команд с ПК.
- [waste_client_pc_test.py](waste_client_pc_test.py)
  Приём потока, YOLO-детекция и ручная отправка команд из консоли.
- [waste_capture_pc.py](waste_capture_pc.py)
  Приём потока и сохранение текущего кадра в папку по нажатию клавиши.

## Как это работает

1. `waste_server_rpi.py` открывает камеру и слушает TCP-порт.
2. `waste_client_pc.py` подключается к Raspberry Pi.
3. Raspberry Pi отправляет JPEG-кадры на ПК.
   Перед отправкой кадр можно обрезать параметрами `CROP_TOP`, `CROP_BOTTOM`, `CROP_LEFT`, `CROP_RIGHT`.
4. ПК находит класс объекта.
5. ПК не реагирует на один кадр, а ждёт несколько одинаковых решений подряд.
6. Если класс стабилен, на Pi уходит текстовая команда.
7. Raspberry Pi берёт действие из `COMMAND_ACTIONS` и двигает сервомоторы.

## Что править

На ПК в [waste_client_pc.py](waste_client_pc.py):

- `RPI_HOST`
- `MODEL_PATH`
- `CONF`
- `DECISION_WINDOW`
- `REQUIRED_STREAK`
- `CLASS_TO_COMMAND`

На Raspberry Pi в [waste_server_rpi.py](waste_server_rpi.py):

- `HOST`
- `PORT`
- `CAMERA_SIZE`
- `CROP_TOP`
- `CROP_BOTTOM`
- `CROP_LEFT`
- `CROP_RIGHT`
- `JPEG_QUALITY`
- `DUMP_PAUSE_SEC`
- `ROTATE_RETURN_ANGLE`
- `TILT_RETURN_ANGLE`
- `ROTATE_SERVO_PIN`
- `TILT_SERVO_PIN`
- `COMMAND_ACTIONS`

## Запуск

Raspberry Pi:

```bash
python waste_server_rpi.py
```

ПК:

```bash
python waste/waste_client_pc.py
```

ПК, ручной тестовый клиент:

```bash
python waste/waste_client_pc_test.py --model example.pt
```

ПК, ручной тестовый клиент с параметрами:

```bash
python waste/waste_client_pc_test.py --host 192.168.0.103 --port 5001 --model waste/AISB_trash_3.0v.pt --conf 0.60
```

ПК, утилита сохранения кадров:

```bash
python waste/waste_capture_pc.py --host 192.168.1.10 --port 5001 --output-dir waste/captures
```

Сменить клавишу сохранения:

```bash
python waste/waste_capture_pc.py --host 192.168.1.10 --output-dir waste/captures --save-key space
```

В `waste_client_pc_test.py` команды можно отправлять двумя способами:

- в консоли: `section_1` ... `section_4` или `1` ... `4`;
- в окне `OpenCV`: клавишами `1`, `2`, `3`, `4`.

В `waste_capture_pc.py`:

- `--output-dir` обязателен;
- `--save-key` по умолчанию равен `s`;
- выход из программы: `q` или `Esc`.

## Логика принятия решения

Сейчас команда отправляется не по одному кадру.

По умолчанию:

- хранится история из `5` последних решений;
- команда отправляется, если один и тот же класс встретился `3` кадра подряд;
- после отправки действует `cooldown`, чтобы механизм не дёргался повторно.

## Пример логики

На ПК:

```python
CLASS_TO_COMMAND = {
    "class_1": "section_1",
    "class_2": "section_2",
    "class_3": "section_3",
    "class_4": "section_4",
}
```

На Raspberry Pi:

```python
COMMAND_ACTIONS = {
    "section_1": {"rotate": 160, "tilt": 70},
    "section_2": {"rotate": 20, "tilt": 70},
    "section_3": {"rotate": 160, "tilt": 120},
    "section_4": {"rotate": 20, "tilt": 120},
}
```

Смысл сервомоторов:

- `GPIO 12` наклоняет площадку для сброса;
- `GPIO 13` поворачивает распределитель по горизонтали к нужной секции.

После выполнения команды оба сервомотора возвращаются в нейтральное положение `90` градусов.

То есть сопоставление класса и конкретного движения можно менять без изменения самой схемы обмена.
