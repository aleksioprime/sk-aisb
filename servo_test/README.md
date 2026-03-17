# Тест сервомотора на Raspberry Pi Zero

Скрипт [test_servo_rpi.py](/Users/aleksioprime/edu/gymnasium/sk-aisb/servo_test/test_servo_rpi.py) проверяет сервомотор, подключённый к Raspberry Pi по PWM-сигналу.

Перед запуском:

- подайте питание сервомотора от подходящего источника;
- объедините `GND` источника питания сервомотора и `GND` Raspberry Pi;
- подключите сигнальный провод сервомотора к GPIO, который указан в `--pin`.

Запуск:

```bash
python3 servo_test/test_servo_rpi.py --pin 18
```

Проверка центра:

```bash
python3 servo_test/test_servo_rpi.py --pin 18 --mode center --center-angle 90
```

Проверка нескольких углов:

```bash
python3 servo_test/test_servo_rpi.py --pin 18 --mode angles --angles 0,45,90,135,180
```

Медленный прогон туда-обратно:

```bash
python3 servo_test/test_servo_rpi.py --pin 18 --mode sweep --step 10 --delay 1.0 --repeat 0
```

Если сервомотор упирается в край или дрожит, подберите диапазон импульсов:

```bash
python3 servo_test/test_servo_rpi.py --pin 18 --min-pulse-us 600 --max-pulse-us 2400
```

Примечания:

- стандартно используется `50 Hz`;
- типичный диапазон для большинства servo: `500..2500 us`, но у конкретной модели он может отличаться;
- `--repeat 0` означает бесконечный цикл до `Ctrl+C`;
- по умолчанию PWM отключается при завершении, флаг `--keep-active` оставляет удержание позиции.
