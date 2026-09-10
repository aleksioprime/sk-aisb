# UMKA

Автономная система распознавания и сортировки мусора для Raspberry Pi 4/5 с USB-камерой.

## Быстрый старт

Рекомендуется актуальная Raspberry Pi OS 64-bit. Все команды ниже выполняются на Raspberry Pi по SSH пользователем `pi`.

Узнайте IP-адрес Raspberry Pi непосредственно на устройстве:

```bash
hostname -I
```

Перейдите на своём компьютере в корень этого репозитория, создайте каталог `app` на Pi и скопируйте в него содержимое папки `umka`:

```bash
ssh pi@192.168.1.101 'mkdir -p /home/pi/app'
scp -r umka/. pi@192.168.1.101:/home/pi/app/
```

После копирования снова подключитесь и проверьте файлы. Эти команды выполняются уже **на Raspberry Pi по SSH**:

```bash
cd ~/app
ls
```

Установите необходимое окружения и библиотеки:

```bash
# Если необходимо обновить через прокси
# sudo -E apt update
# sudo -E apt upgrade

sudo apt update
sudo apt install -y python3-full python3-venv libopenblas-dev v4l-utils \
    python3-gpiozero python3-lgpio i2c-tools

cd ~/app
# --system-site-packages нужен для gpiozero/lgpio, установленных через apt.
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install -r requirements.txt
```

## Создание отдельного пользователя на Raspberry Pi

Сначала войдите под пользователем, который уже имеет права `sudo`, и создайте отдельного пользователя `umka`:

```bash
sudo adduser umka
sudo usermod -aG sudo,video umka
```

Для сервоприводов добавьте пользователя в группы прямого GPIO и шины I2C:

```bash
sudo usermod -aG gpio,i2c umka
```

Переключитесь в полноценную login-сессию нового пользователя:

```bash
sudo -iu umka
```

Проверьте домашний каталог, группы и доступ к `sudo`:

```bash
whoami
pwd
groups
sudo -v
```

Ожидаемые значения `whoami` и `pwd`:

```text
umka
/home/umka
```

Все дальнейшие команды на Raspberry Pi выполняйте пользователем `umka`, а проект размещайте в `/home/umka/app`. Не создавайте виртуальное окружение и не запускайте приложение от `root`.


## Автоматический переход в программу при входе по SSH

После создания `.venv` можно настроить интерактивную оболочку пользователя `umka`. Откройте файл `~/.bashrc` на Raspberry Pi:

```bash
nano ~/.bashrc
```

Добавьте в самый конец файла:

```bash
# UMKA: переход в каталог программы и активация виртуального окружения.
if [[ $- == *i* ]] && [ -d "$HOME/app" ]; then
    cd "$HOME/app"
    if [ -f ".venv/bin/activate" ]; then
        source ".venv/bin/activate"
    fi
fi
```

Сохраните файл сочетанием `Ctrl+O`, нажмите `Enter`, затем выйдите из редактора сочетанием `Ctrl+X`. Применить настройку без переподключения можно командой:

```bash
source ~/.bashrc
```

После следующего входа:

```bash
ssh umka@<IP_RASPBERRY_PI>
```

оболочка сразу окажется в `/home/umka/app`, а в начале приглашения появится `(.venv)`. Проверка:

```bash
pwd
which python
```

Ожидаемый результат:

```text
/home/umka/app
/home/umka/app/.venv/bin/python
```

Эта настройка применяется только к интерактивному входу пользователя. Служба `systemd` не читает `~/.bashrc` и запускает Python из `.venv` по абсолютному пути, указанному в `umka.service`.

Проверьте USB-камеру:

```bash
v4l2-ctl --list-devices
ls -l /dev/video*
```

Пользователь `umka` уже должен входить в группу `video`. При необходимости это можно проверить и исправить:

```bash
sudo usermod -aG video "$USER"
```

После добавления группы нужно выйти из системы и войти снова.

## Запуск без моторов

На Raspberry Pi по SSH:

```bash
python app.py --camera 0 --hardware console
```

В консоли появятся сообщения вида:

```text
[ИМИТАЦИЯ] Сортировка → section_1
[ИМИТАЦИЯ] Сортировка завершена → section_1
```

Страница доступна на самом Pi по адресу `http://localhost:3000`, а с другого устройства — `http://<IP_RASPBERRY_PI>:3000`.

Диагностика:

```bash
curl http://localhost:3000/api/health
curl http://localhost:3000/api/state
```

Если USB-камера имеет другой индекс:

```bash
python app.py --camera 2 --hardware console
```

Для RPi4 размер входа YOLO по умолчанию уменьшен до `416`. Порог и число кадров можно настроить:

```bash
python app.py --confidence 0.55 --stable-frames 4 --clear-frames 8
```

## Имена классов и секции

| Класс модели | Нормализованный класс | Секция |
| --- | --- | --- |
| `papper` или `paper` | `paper` | `section_1` |
| `plastic` | `plastic` | `section_2` |
| `organic` | `organic` | `section_3` |
| `non_recyclable` и прочие классы | `non_recyclable` | `section_4` |
| `empty`, `hand` | игнорируется | — |

Проверьте, что эти секции соответствуют физическому расположению баков.

## Настоящие моторы через PCA9685 (I2C)

Тестовый режим `console` безопасен и используется по умолчанию. Для штатного
подключения используется PCA9685: сервопривод наклона подключён к каналу `1`,
поворота — к каналу `0`; стандартный адрес платы — `0x40`.

Включите I2C через `sudo raspi-config` (`Interface Options` → `I2C`), перезагрузите
Raspberry Pi и проверьте, что плата видна:

```bash
sudo reboot
i2cdetect -y 1
python -c "from adafruit_servokit import ServoKit; print('ServoKit доступен')"
python app.py --hardware pca9685
```

Если адрес или каналы отличаются, укажите их явно:

```bash
python app.py --hardware pca9685 --pca9685-address 0x41 \
    --tilt-channel 2 --rotate-channel 3
```

Не подавайте питание сервоприводов от линии `5V` Raspberry Pi: используйте
отдельный источник подходящей мощности и соедините его землю с GND Raspberry Pi.
Перед работой необходимо откалибровать углы в `sorter/hardware.py`.

## Прямое управление через GPIO

Предыдущий вариант сохранён: GPIO 12 управляет наклоном, GPIO 13 — поворотом.
Пакеты `gpiozero` и `lgpio` устанавливаются в основном шаге до создания `.venv`.

```bash
python -c "import gpiozero, lgpio; print('GPIO-библиотеки доступны')"
python app.py --hardware gpiozero
```

## Ярлыки на рабочем столе Raspberry Pi

В каталоге `desktop` подготовлены два ярлыка:

- `umka-start.desktop` запускает программу с I2C-драйвером `pca9685` и показывает журнал в терминале;
- `umka-screen.desktop` запускает локальный helper, ждёт сервер и открывает страницу `http://localhost:3000` в Chromium во весь экран.

Ярлыки предназначены для Raspberry Pi OS с графическим рабочим столом. На Raspberry Pi OS Lite Chromium и рабочий стол отсутствуют. Сначала откройте обычный терминал непосредственно на рабочем столе Raspberry Pi и выполните:

```bash
whoami
```

### Рабочий стол открыт под пользователем `admin`

В этом случае сама UMKA должна работать как служба от технического пользователя `umka`, а Chromium — от пользователя `admin`. Не запускайте `umka-start.desktop` от `admin`: процесс получит неправильного владельца, настройки групп и права на файлы статистики.

Сначала установите и запустите службу. Команды выполняются по SSH пользователем `umka`:

```bash
cd ~/app
sudo cp umka.service /etc/systemd/system/umka.service
sudo systemctl daemon-reload
sudo systemctl enable --now umka.service
sudo systemctl status umka.service
```

Затем скопируйте на рабочий стол `admin` только ярлык полноэкранной страницы:

```bash
gui_user="admin"
gui_group="$(id -gn "$gui_user")"
desktop_dir="$(sudo -H -u "$gui_user" xdg-user-dir DESKTOP)"
echo "$desktop_dir"
sudo install -d -o "$gui_user" -g "$gui_group" "$desktop_dir"
sudo install -o "$gui_user" -g "$gui_group" -m 0755 \
    ~/app/desktop/umka-screen.desktop "$desktop_dir/umka-screen.desktop"
```

Ожидаемый путь обычно `/home/admin/Desktop/umka-screen.desktop`, но `xdg-user-dir` корректно учитывает язык и настройки рабочего стола. В графической сессии `admin` нажмите на ярлык правой кнопкой мыши и выберите **Allow Launching** («Разрешить запуск»). Ярлык дождётся ответа `/api/state` и откроет Chromium во весь экран.

Для сенсорного выхода из kiosk пять раз быстро коснитесь логотипа UMKA. Касания должны уложиться в четыре секунды. Появится диалог подтверждения; нажмите **Закрыть экран**. Закроется только Chromium, а `umka.service`, камера и сортировка продолжат работать. Этот жест действует только при запуске через подготовленный `umka-screen.desktop`.

Аварийное закрытие с другого компьютера по SSH:

```bash
ssh umka@<IP_RASPBERRY_PI>
sudo pkill -TERM -u admin chromium
```

Если подключена клавиатура, для выхода также можно нажать `Alt+F4`.

### Рабочий стол открыт под пользователем `umka`

Если команда `whoami` на рабочем столе выводит `umka`, можно установить оба ярлыка без `sudo`:

```bash
desktop_dir="$(xdg-user-dir DESKTOP)"
mkdir -p "$desktop_dir"
cp ~/app/desktop/*.desktop "$desktop_dir/"
chmod +x "$desktop_dir"/umka-*.desktop
```

Для текущей конфигурации, в которой графический рабочий стол открыт под пользователем `umka`, используйте именно этот вариант. Ярлык **Открыть экран UMKA** запускает Chromium без `sudo` и с отдельным киоск-профилем. Для этого профиля отключены системное хранилище паролей и предложение перевода страницы.

Сначала запустите **Запустить UMKA**, затем **Открыть экран UMKA**. Не запускайте программу одновременно ярлыком и через `umka.service`: оба процесса попытаются занять камеру и порт `3000`. Для ручного запуска ярлыком предварительно остановите службу командой `sudo systemctl stop umka`; эта команда запрашивает пароль намеренно, потому что управляет системной службой.

### Остановка программы по SSH после запуска ярлыком

Чтобы остановить программу, запущенную ярлыком **Запустить UMKA**, подключитесь по SSH под пользователем `umka`:

```bash
ssh umka@<IP_RASPBERRY_PI>
```

Найдите процесс программы:

```bash
pgrep -a -u umka -f '/home/umka/app/[a]pp.py'
```

Первое число в строке — PID процесса. Подставьте его вместо `PID` в следующую команду:

```bash
kill -INT PID
```

Сигнал `INT` соответствует нажатию **Ctrl+C** в терминале; программа обрабатывает его для остановки. Через несколько секунд повторите команду `pgrep` выше: если вывода нет, процесс завершён.

Если процесс завис и не завершается, ещё раз проверьте его PID и выполните принудительную остановку:

```bash
kill -KILL PID
```

При принудительном завершении программа не сможет выполнить завершающие действия и очистку ресурсов. Закрытие окна **Открыть экран UMKA** завершает только Chromium и не останавливает программу сортировки. Если UMKA запущена как служба, останавливайте её командой `sudo systemctl stop umka`.

## Статистика и журналы

Текущая агрегированная статистика хранится в JSON-файле `/home/umka/app/data/sort_stats.json`. В нём записываются общее количество предметов, примерный суммарный вес, количество по типам и ответы пользователя. Файл обновляется атомарно через временный файл, чтобы снизить риск повреждения при отключении питания.

Пример просмотра статистики:

```bash
python -m json.tool ~/app/data/sort_stats.json
```

История отдельных операций записывается в `/home/umka/app/data/events/events.jsonl` в формате JSON Lines: одна строка соответствует одной завершённой сортировке или одному ответу пользователя. Запись сортировки содержит время, идентификатор события, класс, тип отхода, секцию, уверенность YOLO и примерный вес.

Пример строк:

```json
{"timestamp":"2026-08-28T15:10:13+03:00","event":"sort","event_id":"789492ad","class":"paper","waste_type":"paper","section":"section_1","confidence":0.94,"estimated_weight_kg":0.05}
{"timestamp":"2026-08-28T15:10:18+03:00","event":"feedback","event_id":"789492ad","answer":"yes"}
```

В полночь активный журнал переносится в датированный архив, а события нового дня продолжают записываться в `events.jsonl`:

```text
events.jsonl
events.2026-08-27.jsonl
events.2026-08-26.jsonl
```

Хранятся события за последние 30 дней. Более старые датированные архивы удаляются автоматически при следующей записи. Смотреть события в реальном времени:

```bash
tail -F ~/app/data/events/events.jsonl
```

Для построчного форматированного просмотра требуется `jq`:

```bash
sudo apt install -y jq
jq . ~/app/data/events/events.jsonl
```

Приложение одновременно выводит сообщения в консоль и записывает их в `/home/umka/app/data/logs/umka.log`. Файл ротируется каждый день, а последние 14 архивов сохраняются с датой в имени:

```text
umka.log
umka.log.2026-08-27
umka.log.2026-08-26
```

Следить за файловым журналом в реальном времени:

```bash
tail -F ~/app/data/logs/umka.log
```

Показать последние 200 строк:

```bash
tail -n 200 ~/app/data/logs/umka.log
```

При запуске через `systemd` те же консольные сообщения дополнительно попадают в системный журнал:

```bash
sudo journalctl -u umka.service -n 200
sudo journalctl -u umka.service -f
```

При необходимости путь к активному файлу можно изменить:

```bash
python app.py --hardware pca9685 --log-file /home/umka/app/data/logs/test.log
```

## Автозапуск

Готовый файл службы уже настроен для `/home/umka/app`:

```bash
cd ~/app
sudo cp umka.service /etc/systemd/system/umka.service
sudo systemctl daemon-reload
sudo systemctl enable --now umka.service
sudo journalctl -u umka.service -f
```

## Тесты

Тесты автомата и статистики не требуют камеры, YOLO или GPIO:

```bash
cd ~/app
source .venv/bin/activate
python -m unittest discover -s tests -v
```

Вес на странице является приблизительной оценкой по классу, а не показанием датчика. Для настоящего веса потребуется тензодатчик.
