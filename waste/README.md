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

## Как это работает

1. `waste_server_rpi.py` открывает камеру и слушает TCP-порт.
2. `waste_client_pc.py` подключается к Raspberry Pi.
3. Raspberry Pi отправляет JPEG-кадры на ПК.
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
- `JPEG_QUALITY`
- `ROTATE_SERVO_PIN`
- `TILT_SERVO_PIN`
- `COMMAND_ACTIONS`

## Запуск

Raspberry Pi:

```bash
python waste/waste_server_rpi.py
```

ПК:

```bash
python waste/waste_client_pc.py
```

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
    "section_1": {"rotate": 20, "tilt": 140},
    "section_2": {"rotate": 65, "tilt": 140},
    "section_3": {"rotate": 115, "tilt": 140},
    "section_4": {"rotate": 160, "tilt": 140},
}
```

Смысл сервомоторов:

- `GPIO 12` поворачивает распределитель по горизонтали к нужной секции;
- `GPIO 13` наклоняет площадку для сброса.

То есть сопоставление класса и конкретного движения можно менять без изменения самой схемы обмена.
