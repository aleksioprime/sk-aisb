# Checking

Общая папка для быстрых проверок оборудования.

## Разделы

- [camera](camera/) — проверка камер на ПК и Raspberry Pi, в том числе с YOLO;
- [servo](servo/) — отдельные проверки сервоприводов через GPIO и PCA9685.

## Примеры

```bash
python3 checking/camera/camera_rpi.py
python3 checking/camera/camera_rpi_yolo.py
python3 checking/servo/servo_rpi_gpio.py --pin 12
python3 checking/servo/servo_rpi_driver.py
```

Подробности подключения и команды теста сервоприводов описаны в
[servo/README.md](servo/README.md).
