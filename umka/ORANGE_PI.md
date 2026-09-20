# Запуск UMKA на Orange Pi 5B

Ubuntu 22.04 Jammy. Содержимое папки `umka` скопировано в `~/app`.
Команды выполняются на Orange Pi пользователем `orangepi`.
Если подготовка уже выполнена, начинайте с шага 3.

## 1. Установить зависимости — один раз

```bash
sudo apt update
sudo apt install -y python3-full python3-venv python3-dev build-essential \
    libopenblas-dev libgl1 libglib2.0-0 libgpiod2 i2c-tools xdg-user-dirs

cd ~/app
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install "torch==2.10.0+cpu" "torchvision==0.25.0+cpu" \
    --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements-opi.txt
```

## 2. Подключить PCA9685 и включить I2C5 — один раз

Подключайте при выключенном питании. Номера — физические контакты
26-контактного разъёма Orange Pi 5B.

| Orange Pi | PCA9685 |
| --- | --- |
| 1 — 3,3 В | VCC |
| 3 — SDA | SDA |
| 5 — SCL | SCL |
| 6 — GND | GND |

Отдельный источник питания моторов: плюс → **V+**, минус → **GND** PCA9685.
Земля общая с Orange Pi. Напряжение и ток — по характеристикам сервоприводов.
**V+ не соединяйте с VCC или питанием Orange Pi.** Контакт OE соедините с GND.

Поворот подключите к **каналу 0**, наклон — к **каналу 1**.
На каждом канале: сигнал → S/PWM, питание → V+, земля → GND.
Адресные перемычки A0–A5 оставьте разомкнутыми.

Включите питание и выполните:

```bash
sudo orangepi-config
```

Выберите **System → Hardware → i2c5-m3**, отметьте пробелом,
нажмите **Save** и выйдите. UART1 на тех же контактах должен быть отключён.

```bash
sudo groupadd -f i2c
sudo groupadd -f gpio
sudo usermod -aG video,i2c,gpio orangepi
echo 'KERNEL=="i2c-5", GROUP="i2c", MODE="0660"' \
    | sudo tee /etc/udev/rules.d/99-umka-i2c.rules
echo 'KERNEL=="gpiochip[0-9]*", GROUP="gpio", MODE="0660"' \
    | sudo tee /etc/udev/rules.d/99-umka-gpio.rules
sudo reboot
```

После повторного входа проверьте **без sudo**:

```bash
id
ls -l /dev/gpiochip* /dev/i2c-5
i2cdetect -y 5
```

В `id` должны быть группы `gpio` и `i2c`; у `/dev/gpiochip*` — группа
`gpio` с правами чтения и записи, у `/dev/i2c-5` — группа `i2c` с теми же правами.

Должен появиться адрес **40**. Дополнительный адрес **70** — нормальный
групповой адрес PCA9685.

UMKA автоматически выбирает I2C5 — в приложении, калибровке и при запуске
ярлыком. Плата определяется по `/proc/device-tree/model` и
`/etc/armbian-release`; образы Orange Pi 5B часто называют себя просто
«Orange Pi 5», поэтому подходят оба имени.

Если образ сообщает какое-то третье имя, автоопределение не сработает и
`calibrate.py` или `app.py` завершатся ошибкой
`No Hardware I2C on (scl,sda)`: библиотека Blinka знает только шины
Raspberry Pi. Тогда укажите номер шины явно — `--i2c-bus 5` — и добавьте
этот параметр в команды разделов 4 и 5 и в ярлык `umka-start.desktop`.
Посмотреть, как плата называет себя и какие шины доступны, можно так:

```bash
tr -d '\0' < /proc/device-tree/model; echo
ls /dev/i2c-*
```

## 3. Проверить камеру отдельно

Подключите USB-камеру. Остановите запущенную UMKA через `Ctrl+C`;
если она работает службой — `sudo systemctl stop umka`.

```bash
cd ~/app
source .venv/bin/activate
v4l2-ctl --list-devices

python - <<'PY'
import cv2

camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
try:
    ok, frame = camera.read()
    if not ok:
        raise SystemExit("Камера не вернула кадр")
    if not cv2.imwrite("camera-test.jpg", frame):
        raise SystemExit("Не удалось сохранить кадр")
    print("Камера работает. Кадр сохранён в ~/app/camera-test.jpg")
finally:
    camera.release()
PY
```

Откройте `~/app/camera-test.jpg` на рабочем столе и проверьте изображение.
Для камеры `/dev/video2` замените `VideoCapture(0,` на `VideoCapture(2,`.

## 4. Проверить моторы отдельно

Проверьте углы `CENTER_TILT_ANGLE`, `CENTER_ROTATE_ANGLE` и `ACTIONS`
в `sorter/hardware.py`: они должны соответствовать механике.
При запуске моторы сразу переходят в центр.

```bash
cd ~/app
source .venv/bin/activate
python -c "from adafruit_servokit import ServoKit; print('ServoKit доступен')"
python calibrate.py --hardware pca9685
```

Введите `c` для центра, `1`–`4` для проверки секций, `q` для выхода.

В журнале должна появиться строка `PCA9685: шина /dev/i2c-5`. Если вместо
неё выводится ошибка про `No Hardware I2C`, запустите с явной шиной:

```bash
python calibrate.py --hardware pca9685 --i2c-bus 5
```

## 5. Запустить основную программу

```bash
cd ~/app
source .venv/bin/activate
python app.py --hardware pca9685
```

Для камеры `/dev/video2` добавьте `--camera 2`. Если при калибровке
понадобился `--i2c-bus 5`, добавьте его и сюда.
Откройте **http://localhost:3000** на Orange Pi или
`http://<IP_ORANGE_PI>:3000` на другом компьютере.
Остановка программы — **Ctrl+C**.

## 6. Запуск с рабочего стола

Один раз скопируйте готовые ярлыки в терминале XFCE пользователя `orangepi`:

```bash
umka_desktop_dir="$(xdg-user-dir DESKTOP)"
mkdir -p "$umka_desktop_dir"
cp ~/app/desktop/opi/*.desktop "$umka_desktop_dir/"
chmod +x "$umka_desktop_dir"/umka-*.desktop
```

Для киоска нужен Chromium; если он отсутствует:
`sudo apt install -y chromium-browser`.

Остановите ручной запуск. Нажмите **Запустить UMKA**, затем
**Открыть экран UMKA**. При первом запуске разрешите выполнение ярлыков.
Если меняли индекс камеры, добавьте `--camera N` в `Exec` ярлыка запуска.

Выход из киоска — `Alt+F4` или пять касаний логотипа за четыре секунды →
**Закрыть экран**. Закрытие киоска не останавливает UMKA.

Собственные сообщения Chromium о GPU, ANGLE, Vulkan и опросе камер
(`Passthrough is not supported`, `Failed to query video capabilities`) к работе
UMKA отношения не имеют. В терминал они не выводятся: их принимает файл
`~/app/data/logs/kiosk.log`, который переписывается при каждом запуске киоска.

## 7. Запуск и остановка по SSH

Подключитесь к плате с другого компьютера:

```bash
ssh orangepi@<IP_ORANGE_PI>
```

### Запуск программы

```bash
cd ~/app && source .venv/bin/activate && python app.py --hardware pca9685
```

Журнал идёт прямо в SSH-терминал, остановка — **Ctrl+C**. Это подключение
остаётся занятым программой, поэтому для киоска откройте второе.

### Запуск киоска

Во втором SSH-подключении:

```bash
DISPLAY=:0 python3 ~/app/desktop/opi/kiosk_launcher.py
```

`DISPLAY=:0` — экран, подключённый к плате: без этой переменной Chromium не
знает, куда выводить изображение, и завершается с ошибкой. На плате уже должен
быть выполнен вход в графическую сессию XFCE. Виртуальная среда `.venv` киоску
не нужна — он работает на системном `python3`.

Киоск ждёт до 60 секунд, пока UMKA ответит на `http://127.0.0.1:3000/api/state`,
поэтому порядок запуска не важен.

Закрыть киоск из этого же терминала — **Ctrl+C**: Chromium закрывается вместе с
лаунчером, а распознавание и сортировка продолжают работать.

### Запуск без удержания SSH-сессии

С `nohup` процессы переживут отключение SSH:

```bash
cd ~/app && source .venv/bin/activate && nohup python app.py --hardware pca9685 > ~/app/data/logs/umka-ssh.log 2>&1 < /dev/null &
```

```bash
nohup env DISPLAY=:0 python3 ~/app/desktop/opi/kiosk_launcher.py > /dev/null 2>&1 < /dev/null &
```

### Остановка программы

Найдите процесс — первое число в строке будет его PID:

```bash
pgrep -a -u orangepi -f '[a]pp\.py'
```

Шаблон намеренно не содержит путь: в списке процессов программа выглядит
по-разному — `python app.py --hardware pca9685` при запуске из `~/app` и
`/home/orangepi/app/.venv/bin/python /home/orangepi/app/app.py ...` при запуске
ярлыком. Скобки вокруг первой буквы нужны, чтобы команда не нашла саму себя.

Подставьте PID и отправьте сигнал, равносильный **Ctrl+C**:

```bash
kill -INT PID
```

Через несколько секунд повторите `pgrep`: пустой вывод означает, что программа
остановлена. Если процесс завис, завершите принудительно — тогда программа не
успеет освободить камеру и моторы:

```bash
kill -KILL PID
```

### Остановка киоска

```bash
pkill -f '[k]iosk_launcher.py'
```

Chromium закрывается вместе с лаунчером. Если окно всё же осталось:

```bash
pkill -u orangepi chromium
```

Киоск и сортировка независимы: закрытие киоска не останавливает распознавание,
а остановка программы не закрывает окно Chromium.

### Ошибка «Address already in use»

```text
OSError: [Errno 98] Address already in use
```

Порт `3000` уже занят: UMKA запущена — в другом SSH-подключении, ярлыком
**Запустить UMKA** или в фоне через `nohup`. Двух копий быть не должно, они
поделят камеру и порт. Посмотрите, какой процесс держит порт:

```bash
ss -ltnp | grep :3000
```

В конце строки будет `users:(("python",pid=1234,...))` — это и есть PID.
Остановите его тем же способом:

```bash
kill -INT PID
```

Если страница уже открыта и работает, останавливать ничего не нужно: значит,
программа запущена и второй экземпляр просто не требуется.
