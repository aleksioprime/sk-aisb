#!/usr/bin/env bash
# Установить или обновить UMKA на Raspberry Pi 4/5 или Orange Pi 5/5B по сети.
# Запускается на КОМПЬЮТЕРЕ из любого каталога репозитория:
#
#   deploy/install.sh orangepi@192.168.10.100
#   deploy/install.sh pi@192.168.1.101 --hardware pca9685 --autostart
#   deploy/install.sh orangepi@192.168.10.100 --tilt-channel 0 --rotate-channel 1
#
# Что делает:
#   1. копирует приложение app/ в ~/app на устройстве (data/, umka.conf и .venv
#      устройства не трогаются, удалённые из репозитория файлы удаляются);
#   2. запускает на устройстве deploy/setup_device.sh: системные пакеты, I2C,
#      группы, Python-окружение с PyTorch под эту плату, umka.conf, ярлыки,
#      по флагу - автозапуск.
#
# Параметры компьютера:
#   --dest DIR        каталог на устройстве относительно домашнего (по умолчанию app)
#   --ssh-key FILE    ключ SSH; без него используются ~/.ssh/config и пароль
#   --port N          порт SSH, если не 22
#   --ssh-opt OPTION  дополнительная опция ssh -o (можно повторять)
#   --code-only       только код: без системных пакетов и pip; umka.conf, ярлыки
#                     и перезапуск службы обновляются
#   --dry-run         показать команды, ничего не выполняя
# Параметры устройства (передаются в setup_device.sh):
#   --hardware NAME, --tilt-channel N, --rotate-channel N, --camera N, --i2c-bus N,
#   --autostart, --no-autostart, --skip-system

set -euo pipefail

usage() { sed -n '2,29p' "$0"; }

[ $# -ge 1 ] || { usage; exit 2; }
case "$1" in -h|--help) usage; exit 0 ;; esac
TARGET="$1"; shift

DEST="app"
SSH_KEY=""
SSH_PORT=""
EXTRA_OPTS=()
CODE_ONLY=0
DRY_RUN=0
DEVICE_ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --dest) DEST="${2#\~/}"; shift 2 ;;
        --ssh-key) SSH_KEY="$2"; shift 2 ;;
        --port) SSH_PORT="$2"; shift 2 ;;
        --ssh-opt) EXTRA_OPTS+=(-o "$2"); shift 2 ;;
        --code-only) CODE_ONLY=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --hardware|--tilt-channel|--rotate-channel|--camera|--i2c-bus)
            DEVICE_ARGS+=("$1" "$2"); shift 2 ;;
        --autostart|--no-autostart|--skip-system)
            DEVICE_ARGS+=("$1"); shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Неизвестный параметр: $1" >&2; usage; exit 2 ;;
    esac
done

REPO="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$REPO/app/app.py" ] || { echo "Не найден $REPO/app/app.py" >&2; exit 1; }

# Одно SSH-соединение на весь запуск: пароль, если ключа нет, спрашивается один раз.
CONTROL="${TMPDIR:-/tmp}/umka-ssh-$$"
SSH_OPTS=(-o ControlMaster=auto -o "ControlPath=$CONTROL" -o ControlPersist=120)
[ -n "$SSH_KEY" ] && SSH_OPTS+=(-i "$SSH_KEY")
[ -n "$SSH_PORT" ] && SSH_OPTS+=(-p "$SSH_PORT")
SSH_OPTS+=(${EXTRA_OPTS[@]+"${EXTRA_OPTS[@]}"})
cleanup() { ssh "${SSH_OPTS[@]}" -O exit "$TARGET" >/dev/null 2>&1 || true; }
trap cleanup EXIT

run() {
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '[dry-run]'; printf ' %q' "$@"; printf '\n'
    else
        "$@"
    fi
}
step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
remote() { ssh "${SSH_OPTS[@]}" "$TARGET" "$@"; }

step "Подключение к $TARGET"
if [ "$DRY_RUN" -eq 0 ]; then
    remote 'echo "$(uname -n): $(tr -d "\0" < /proc/device-tree/model 2>/dev/null || uname -m)"'
fi

# rsync есть почти везде; если нет на устройстве - копирование через tar.
sync_dir() {
    local source="$1" target="$2"; shift 2
    if [ "$DRY_RUN" -eq 1 ] || remote 'command -v rsync >/dev/null'; then
        run rsync -az --delete -e "ssh ${SSH_OPTS[*]}" "$@" "$source/" "$TARGET:$target/"
    else
        local excludes=()
        for option in "$@"; do excludes+=("${option/--exclude=/--exclude=./}"); done
        remote "mkdir -p '$target'"
        tar -C "$source" ${excludes[@]+"${excludes[@]}"} -czf - . | remote "tar -C '$target' -xzf -"
    fi
}

step "Копирование приложения в ~/$DEST"
sync_dir "$REPO/app" "$DEST" \
    --exclude=.venv/ --exclude=data/ --exclude=umka.conf --exclude=.deploy/ \
    --exclude=__pycache__/ --exclude='*.pyc' --exclude=.DS_Store
sync_dir "$REPO/deploy" "$DEST/.deploy" --exclude=.DS_Store --exclude=constraints.txt

# --code-only: без системных пакетов и pip - только umka.conf, ярлыки и перезапуск службы.
SETUP_ARGS=(--app-dir "$DEST")
[ "$CODE_ONLY" -eq 1 ] && SETUP_ARGS+=(--skip-system --skip-python)
SETUP_ARGS+=(${DEVICE_ARGS[@]+"${DEVICE_ARGS[@]}"})

step "Настройка устройства"
# -t: sudo на устройстве спросит пароль в этом же терминале.
run ssh "${SSH_OPTS[@]}" -t "$TARGET" "bash '$DEST/.deploy/setup_device.sh'$(printf ' %q' "${SETUP_ARGS[@]}")"

if [ "$DRY_RUN" -eq 0 ] && remote "pgrep -f '[.]venv/bin/python .*app[.]py' >/dev/null && ! systemctl is-active --quiet umka.service"; then
    printf '\n\033[1;33m!   UMKA запущена вручную и работает со старым кодом - перезапустите её.\033[0m\n'
fi
