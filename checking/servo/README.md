# Проверка сервоприводов

В папке находятся два отдельных теста:

- `servo_rpi_gpio.py` — прежний тест одного сервопривода, подключённого
  напрямую к GPIO Raspberry Pi;
- `servo_rpi_driver.py` — тест двух сервоприводов, подключённых к каналам
  `0` и `1` драйвера PCA9685.

## Подключение

- `VCC` PCA9685 → `3.3V` Raspberry Pi;
- `GND` PCA9685 → `GND` Raspberry Pi;
- `SDA` → `GPIO 2` (`SDA`);
- `SCL` → `GPIO 3` (`SCL`);
- отдельное питание сервоприводов → клемма `V+` PCA9685;
- земля блока питания сервоприводов должна быть общей с землёй Raspberry Pi;
- сигнальные разъёмы сервоприводов → каналы `0` и `1`.

Не питайте сервоприводы от линии `3.3V` Raspberry Pi. Перед первым полным
`sweep` убедитесь, что механика может безопасно пройти весь диапазон.

## Копирование на Raspberry Pi

Сначала на своём компьютере перейдите в корень репозитория и скопируйте всю
папку `checking` в домашний каталог пользователя Raspberry Pi:

```bash
cd /путь/к/sk-aisb
scp -r checking <USER>@<IP_RASPBERRY_PI>:~/
```

Например, для пользователя `pi` и адреса `192.168.1.50`:

```bash
scp -r checking pi@192.168.1.50:~/
```

Затем подключитесь к Raspberry Pi. Все последующие команды выполняются уже
**на Raspberry Pi по SSH**:

```bash
ssh <USER>@<IP_RASPBERRY_PI>
```

## Подготовка Raspberry Pi

Включите I²C через `sudo raspi-config`. В Raspberry Pi OS Bookworm и новее
системный Python защищён механизмом PEP 668, поэтому библиотеку нужно
устанавливать в виртуальное окружение, а не системной командой `pip`.

Сначала установите поддержку виртуальных окружений, создайте окружение
`~/.venv` в домашнем каталоге и сразу активируйте его:

```bash
sudo apt update
sudo apt install -y python3-venv
python3 -m venv --system-site-packages ~/.venv
source ~/.venv/bin/activate
```

Параметр `--system-site-packages` сохраняет доступ к библиотекам оборудования,
которые Raspberry Pi OS устанавливает через `apt`, включая `RPi.GPIO`.
Использовать `--break-system-packages` для этой проверки не требуется.

После активации окружения перейдите в скопированную папку и установите
библиотеку:

```bash
cd ~/checking
python -m pip install --upgrade pip
python -m pip install adafruit-circuitpython-servokit
```

При каждом новом подключении по SSH сначала активируйте окружение, а затем
переходите к работе:

```bash
source ~/.venv/bin/activate
cd ~/checking
```

При стандартном адресе PCA9685 (`0x40`) устройство можно проверить командой:

```bash
sudo i2cdetect -y 1
```

## Запуск через PCA9685

```bash
python servo/servo_rpi_driver.py
```

Безопасный первый тест:

```text
servo> center 0
servo> center 1
servo> set 0 60
servo> turn 1 15
servo> status
servo> release
servo> quit
```

Для обоих моторов используйте `all`: `center all`, `set all 90` или
`sweep all`. Настройки адреса PCA9685, углов, задержек и длительности импульса
находятся в начале файла.

## Запуск напрямую через GPIO

Укажите BCM-номер GPIO, к которому подключён сигнальный провод сервопривода:

```bash
python servo/servo_rpi_gpio.py --pin 12
```

Этот вариант использует `RPi.GPIO` и предназначен для одного сервопривода.
