#!/usr/bin/env bash
# Подготовить устройство к работе UMKA. Выполняется НА ПЛАТЕ пользователем,
# от имени которого будет работать UMKA (не root). Обычно его запускает
# deploy/install.sh с компьютера; вручную:
#
#   bash ~/app/.deploy/setup_device.sh --app-dir ~/app [параметры]
#
# Параметры:
#   --app-dir DIR            каталог приложения (по умолчанию ~/app)
#   --hardware NAME          pca9685 | console | gpiozero (запишется в umka.conf)
#   --tilt-channel N         канал PCA9685 наклона
#   --rotate-channel N       канал PCA9685 поворота
#   --camera N               номер /dev/videoN
#   --i2c-bus N              номер шины /dev/i2c-N
#   --autostart              служба systemd + автозапуск киоска при входе
#   --no-autostart           убрать службу и автозапуск киоска
#   --skip-system            не ставить системные пакеты и не менять I2C/группы
#   --skip-python            не трогать .venv и Python-зависимости (обновление только кода)
#
# Скрипт можно запускать повторно: он обновляет зависимости, а umka.conf,
# статистику и настройки в data/ сохраняет.

set -euo pipefail

APP_DIR="$HOME/app"
SKIP_SYSTEM=0
SKIP_PYTHON=0
AUTOSTART=""
CONF_UPDATES=()

while [ $# -gt 0 ]; do
    case "$1" in
        --app-dir) APP_DIR="$2"; shift 2 ;;
        --hardware) CONF_UPDATES+=("hardware=$2"); shift 2 ;;
        --tilt-channel) CONF_UPDATES+=("tilt_channel=$2"); shift 2 ;;
        --rotate-channel) CONF_UPDATES+=("rotate_channel=$2"); shift 2 ;;
        --camera) CONF_UPDATES+=("camera=$2"); shift 2 ;;
        --i2c-bus) CONF_UPDATES+=("i2c_bus=$2"); shift 2 ;;
        --autostart) AUTOSTART=on; shift ;;
        --no-autostart) AUTOSTART=off; shift ;;
        --skip-system) SKIP_SYSTEM=1; shift ;;
        --skip-python) SKIP_PYTHON=1; shift ;;
        -h|--help) sed -n '2,23p' "$0"; exit 0 ;;
        *) echo "Неизвестный параметр: $1" >&2; exit 2 ;;
    esac
done

APP_DIR="$(cd "$APP_DIR" && pwd)"
DEPLOY_DIR="$APP_DIR/.deploy"
VENV="$APP_DIR/.venv"
USER_NAME="$(id -un)"
NEED_REBOOT=0
NEED_RELOGIN=0
WARNINGS=()

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!   %s\033[0m\n' "$*"; WARNINGS+=("$*"); }

if [ "$(id -u)" -eq 0 ]; then
    echo "Запускайте от пользователя UMKA, а не от root: sudo скрипт вызовет сам." >&2
    exit 1
fi
if [ "$(uname -m)" != "aarch64" ]; then
    warn "Архитектура $(uname -m): UMKA проверялась только на aarch64 (64-битная ОС)."
fi

# ---------- Плата ----------
# UMKA_BOARD_MODEL подменяет модель платы — для проверки скрипта в контейнере.
MODEL="${UMKA_BOARD_MODEL:-$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || true)}"
MODEL_KEY="$(printf '%s' "$MODEL" | tr '[:upper:]' '[:lower:]' | tr -d ' _-')"
case "$MODEL_KEY" in
    *raspberrypi5*) BOARD=rpi5 ;;
    *raspberrypi4*) BOARD=rpi4 ;;
    *orangepi5plus*|*orangepi5max*|*orangepi5pro*|*orangepi5ultra*) BOARD=other ;;
    *orangepi5*) BOARD=opi5 ;;
    *) BOARD=other ;;
esac
step "Плата: ${MODEL:-неизвестно} ($BOARD), пользователь $USER_NAME, каталог $APP_DIR"
[ "$BOARD" = other ] && warn "Плата не из списка (Raspberry Pi 4/5, Orange Pi 5/5B): шину I2C задайте через --i2c-bus."

case "$BOARD" in
    opi5) DEFAULT_BUS=5 ;;
    rpi4|rpi5) DEFAULT_BUS=1 ;;
    *) DEFAULT_BUS="" ;;
esac

# ---------- Системные пакеты, I2C, права ----------
if [ "$SKIP_SYSTEM" -eq 0 ]; then
    step "Системные пакеты (потребуется пароль sudo)"
    PACKAGES=(python3-venv python3-dev build-essential libopenblas-dev
              libgl1 libglib2.0-0 v4l-utils i2c-tools)
    case "$BOARD" in
        rpi4|rpi5) PACKAGES+=(python3-gpiozero python3-lgpio) ;;
        opi5) PACKAGES+=(libgpiod2) ;;
    esac
    # apt трогаем, только если чего-то не хватает: повторная установка не зависит
    # от доступности зеркал (на выставке сторонний репозиторий висел минутами).
    MISSING=()
    for package in "${PACKAGES[@]}"; do
        # «install ok installed» или «hold ok installed» — пакет на месте.
        [[ "$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)" == *" ok installed" ]] \
            || MISSING+=("$package")
    done
    if [ ${#MISSING[@]} -eq 0 ]; then
        echo "Все системные пакеты уже установлены."
    else
        echo "Не хватает: ${MISSING[*]}"
        # Недоступный сторонний источник не должен срывать установку.
        sudo apt-get update -o Acquire::Retries=1 -o Acquire::http::Timeout=20 \
            -o Acquire::https::Timeout=20 || warn "apt-get update завершился с ошибкой — пробую установить из имеющихся списков."
        sudo apt-get install -y "${MISSING[@]}"
    fi

    # Киоску нужен Chromium, но только там, где есть графический рабочий стол.
    if ls /usr/share/xsessions/*.desktop >/dev/null 2>&1; then
        if ! command -v chromium >/dev/null && ! command -v chromium-browser >/dev/null \
                && [ ! -x /snap/bin/chromium ]; then
            sudo apt-get install -y chromium || sudo apt-get install -y chromium-browser \
                || warn "Chromium не установился: киоск не запустится, страница доступна по сети."
        fi
    fi

    step "Шина I2C"
    case "$BOARD" in
        rpi4|rpi5)
            if [ ! -e /dev/i2c-1 ]; then
                sudo raspi-config nonint do_i2c 0
                NEED_REBOOT=1
            fi
            ;;
        opi5)
            # Контакты 3 (SDA) и 5 (SCL) — шина I2C5, оверлей i2c5-m3.
            ENV_FILE=/boot/orangepiEnv.txt
            if [ -e /dev/i2c-5 ]; then
                echo "/dev/i2c-5 уже есть."
            elif [ -f "$ENV_FILE" ]; then
                if grep -q '^overlays=.*\bi2c5-m3\b' "$ENV_FILE"; then
                    echo "Оверлей i2c5-m3 уже включён, шина появится после перезагрузки."
                elif grep -q '^overlays=' "$ENV_FILE"; then
                    sudo sed -i 's/^overlays=\(.*\)$/overlays=\1 i2c5-m3/' "$ENV_FILE"
                    echo "Оверлей i2c5-m3 добавлен в $ENV_FILE."
                else
                    echo "overlays=i2c5-m3" | sudo tee -a "$ENV_FILE" >/dev/null
                    echo "Оверлей i2c5-m3 добавлен в $ENV_FILE."
                fi
                NEED_REBOOT=1
                if grep -q '^overlays=.*\buart1' "$ENV_FILE"; then
                    warn "В $ENV_FILE включён UART1 — он занимает те же контакты 3 и 5. Отключите его в sudo orangepi-config."
                fi
            else
                warn "Не найден $ENV_FILE: включите i2c5-m3 через sudo orangepi-config."
            fi
            ;;
    esac

    step "Группы и права на устройства"
    sudo groupadd -f i2c
    sudo groupadd -f gpio
    USER_GROUPS=" $(id -nG "$USER_NAME") "
    for group in video i2c gpio; do
        if [[ "$USER_GROUPS" != *" $group "* ]]; then
            sudo usermod -aG "$group" "$USER_NAME"
            NEED_RELOGIN=1
        fi
    done
    if [ "$BOARD" = opi5 ]; then
        # В образах Orange Pi у /dev/i2c-* и /dev/gpiochip* нет группы: без
        # правил udev доступ к ним есть только у root.
        echo 'KERNEL=="i2c-[0-9]*", GROUP="i2c", MODE="0660"' \
            | sudo tee /etc/udev/rules.d/99-umka-i2c.rules >/dev/null
        echo 'KERNEL=="gpiochip[0-9]*", GROUP="gpio", MODE="0660"' \
            | sudo tee /etc/udev/rules.d/99-umka-gpio.rules >/dev/null
        if sudo udevadm control --reload-rules 2>/dev/null; then
            sudo udevadm trigger --subsystem-match=i2c-dev --subsystem-match=gpio || true
        else
            warn "udev не перечитал правила: права на /dev/i2c-* применятся после перезагрузки."
            NEED_REBOOT=1
        fi
    fi
fi

# ---------- Python ----------
if [ "$SKIP_PYTHON" -eq 1 ]; then
    [ -x "$VENV/bin/python" ] || { echo "Нет $VENV: запустите установку без --skip-python." >&2; exit 1; }
else
    step "Виртуальное окружение Python"
    # --system-site-packages: gpiozero и lgpio на Raspberry Pi ставятся через apt.
    [ -x "$VENV/bin/python" ] || python3 -m venv --system-site-packages "$VENV"
    "$VENV/bin/python" -m pip install --upgrade pip wheel

    step "PyTorch для $BOARD"
    case "$BOARD" in
        rpi4)
            # Свежие сборки требуют ARMv8.2 и падают на Cortex-A72 с Illegal instruction.
            "$VENV/bin/python" -m pip install torch==2.9.0 torchvision==0.24.0
            ;;
        *)
            "$VENV/bin/python" -m pip install "torch==2.10.0+cpu" "torchvision==0.25.0+cpu" \
                --index-url https://download.pytorch.org/whl/cpu
            ;;
    esac
    # Зафиксировать установленный PyTorch, чтобы ultralytics не заменил его другой версией.
    "$VENV/bin/python" -m pip freeze | grep -E '^(torch|torchvision)==' > "$DEPLOY_DIR/constraints.txt"

    step "Зависимости UMKA"
    REQUIREMENTS="$APP_DIR/requirements.txt"
    [ "$BOARD" = opi5 ] && REQUIREMENTS="$APP_DIR/requirements-opi.txt"
    "$VENV/bin/python" -m pip install -r "$REQUIREMENTS" -c "$DEPLOY_DIR/constraints.txt"

    step "Проверка вычислений PyTorch"
    if "$VENV/bin/python" -X faulthandler -c \
            "import torch; torch.nn.Conv2d(3, 8, 3)(torch.rand(1, 3, 64, 64)); print('PyTorch', torch.__version__, 'работает')"; then
        :
    else
        warn "PyTorch не выполняет свёртку на этом процессоре — см. docs/troubleshooting.md, «Illegal instruction»."
    fi
fi

# ---------- umka.conf ----------
CONF="$APP_DIR/umka.conf"
set_conf() {
    local key="$1" value="$2"
    if grep -qE "^[[:space:]]*#?[[:space:]]*$key[[:space:]]*=" "$CONF"; then
        sed -i -E "s|^[[:space:]]*#?[[:space:]]*$key[[:space:]]*=.*|$key = $value|" "$CONF"
    else
        echo "$key = $value" >> "$CONF"
    fi
}

step "Параметры запуска $CONF"
if [ ! -f "$CONF" ]; then
    # PCA9685 отвечает по адресу 0x40. Если шину только что включили, проверить
    # её до перезагрузки нельзя — тогда считаем, что моторы подключены.
    HARDWARE=console
    if [ "$NEED_REBOOT" -eq 1 ]; then
        HARDWARE=pca9685
    elif [ -n "$DEFAULT_BUS" ] && [ -e "/dev/i2c-$DEFAULT_BUS" ]; then
        # Вывод сохраняется заранее: с pipefail ранний выход grep -q обрывает
        # i2cdetect сигналом SIGPIPE, и цепочка ложно считается неудачной.
        SCAN="$(i2cdetect -y "$DEFAULT_BUS" 2>/dev/null || true)"
        grep -qE '^40:[[:space:]]+(40|UU)' <<< "$SCAN" && HARDWARE=pca9685
    fi
    cat > "$CONF" <<EOF
# Параметры запуска UMKA на этом устройстве. Читаются app.py и tools/*.py;
# аргументы командной строки важнее. Обновляется установщиком, правится вручную.
hardware = $HARDWARE
tilt_channel = 1
rotate_channel = 0
camera = 0
# i2c_bus = 5
EOF
    echo "Создан $CONF (найден драйвер: $HARDWARE)."
    if [ "$HARDWARE" = console ] && [[ " ${CONF_UPDATES[*]-} " != *" hardware="* ]]; then
        warn "PCA9685 не найдена на шине ${DEFAULT_BUS:-?}: UMKA работает без моторов (hardware = console)."
    fi
fi
for update in ${CONF_UPDATES[@]+"${CONF_UPDATES[@]}"}; do
    set_conf "${update%%=*}" "${update#*=}"
done
grep -vE '^[[:space:]]*(#|$)' "$CONF" | sed 's/^/    /'

# ---------- Ярлыки и автозапуск ----------
render() {
    sed -e "s|@APP_DIR@|$APP_DIR|g" -e "s|@USER@|$USER_NAME|g" "$DEPLOY_DIR/templates/$1"
}

DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
if ls /usr/share/xsessions/*.desktop >/dev/null 2>&1; then
    step "Ярлыки на рабочем столе $DESKTOP_DIR"
    mkdir -p "$DESKTOP_DIR"
    SHORTCUTS=(umka-screen.desktop)
    # Со службой UMKA уже работает: второй экземпляр упал бы с «Address already in use».
    if [ "$AUTOSTART" = on ] || { [ "$AUTOSTART" != off ] && systemctl is-enabled --quiet umka.service 2>/dev/null; }; then
        rm -f "$DESKTOP_DIR/umka-start.desktop"
    else
        SHORTCUTS+=(umka-start.desktop)
    fi
    for name in "${SHORTCUTS[@]}"; do
        render "$name" > "$DESKTOP_DIR/$name"
        chmod +x "$DESKTOP_DIR/$name"
        # Рабочие столы на GLib иначе спрашивают, доверять ли ярлыку.
        gio set "$DESKTOP_DIR/$name" metadata::trusted true 2>/dev/null || true
    done
fi

SERVICE=/etc/systemd/system/umka.service
KIOSK_AUTOSTART="$HOME/.config/autostart/umka-kiosk.desktop"
if [ "$AUTOSTART" = on ]; then
    step "Автозапуск: служба umka и киоск при входе"
    render umka.service | sudo tee "$SERVICE" >/dev/null
    sudo systemctl daemon-reload
    sudo systemctl enable umka.service
    mkdir -p "$(dirname "$KIOSK_AUTOSTART")"
    render umka-kiosk-autostart.desktop > "$KIOSK_AUTOSTART"
elif [ "$AUTOSTART" = off ]; then
    step "Автозапуск выключается"
    if [ -f "$SERVICE" ]; then
        sudo systemctl disable --now umka.service || true
        sudo rm -f "$SERVICE"
        sudo systemctl daemon-reload
    fi
    rm -f "$KIOSK_AUTOSTART"
fi
if systemctl is-enabled --quiet umka.service 2>/dev/null && [ "$NEED_REBOOT" -eq 0 ] && [ "$NEED_RELOGIN" -eq 0 ]; then
    # Служба подхватывает новый код и umka.conf только после перезапуска.
    sudo systemctl restart umka.service
    echo "Служба umka перезапущена."
fi

# ---------- Итог ----------
step "Готово"
ADDRESS="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Веб-интерфейс: http://${ADDRESS:-<IP>}:3000"
echo "Проверки по этапам (UMKA должна быть остановлена):"
echo "    cd $APP_DIR && .venv/bin/python tools/check_camera.py"
echo "    cd $APP_DIR && .venv/bin/python tools/check_servo.py --channel 0"
echo "    cd $APP_DIR && .venv/bin/python tools/calibrate.py"
if [ "$NEED_REBOOT" -eq 1 ]; then
    WARNINGS+=("Перезагрузите плату (sudo reboot): включена шина I2C или изменены права. После перезагрузки i2cdetect -y ${DEFAULT_BUS:-<шина>} должен показать адрес 40.")
elif [ "$NEED_RELOGIN" -eq 1 ]; then
    WARNINGS+=("Пользователь добавлен в группы video/i2c/gpio: перезагрузите плату или войдите заново.")
fi
if [ ${#WARNINGS[@]} -gt 0 ]; then
    printf '\nОбратите внимание:\n'
    printf '  - %s\n' "${WARNINGS[@]}"
fi
