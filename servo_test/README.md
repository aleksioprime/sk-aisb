# Тест сервомотора на Raspberry Pi Zero

Скрипт [test_servo_rpi.py](test_servo_rpi.py) проверяет сервомотор, подключённый к Raspberry Pi по PWM-сигналу.

По умолчанию выбран `GPIO 12`, так как у вас сервопривод подключён к PWM-пину. При необходимости можно передать `--pin 13`.

Перед запуском:

- подайте питание сервомотора от подходящего источника;
- объедините `GND` источника питания сервомотора и `GND` Raspberry Pi;
- подключите сигнальный провод сервомотора к GPIO, который указан в `--pin`.

Запуск:

```bash
python servo_test/test_servo_rpi.py --pin 12
```

Проверка центра:

```bash
python servo_test/test_servo_rpi.py --pin 12 --mode center --center-angle 90
```

Проверка нескольких углов:

```bash
python servo_test/test_servo_rpi.py --pin 12 --mode angles --angles 0,45,90,135,180
```

Медленный прогон туда-обратно:

```bash
python servo_test/test_servo_rpi.py --pin 12 --mode sweep --step 10 --delay 1.0 --repeat 0
```

Если сервомотор упирается в край или дрожит, подберите диапазон импульсов:

```bash
python servo_test/test_servo_rpi.py --pin 12 --min-pulse-us 600 --max-pulse-us 2400
```

Примечания:

- стандартно используется `50 Hz`;
- текущая реализация построена на `RPi.GPIO`, то есть это программный PWM; если нужен именно hardware PWM на `GPIO 12/13`, лучше переписать утилиту на `pigpio` или `lgpio`;
- типичный диапазон для большинства servo: `500..2500 us`, но у конкретной модели он может отличаться;
- `--repeat 0` означает бесконечный цикл до `Ctrl+C`;
- по умолчанию PWM отключается при завершении, флаг `--keep-active` оставляет удержание позиции.
