# sk-aisb - UMKA, умная сортировка мусора

UMKA распознаёт мусор USB-камерой и моделью YOLO, сбрасывает предмет в одну из
четырёх секций двумя сервоприводами и показывает результат на экране и в
браузере. Работает на Raspberry Pi 4/5 и Orange Pi 5/5B.

## Структура

| Каталог | Назначение |
| --- | --- |
| [app/](app/README.md) | **приложение** - то, что ставится на устройство; в `app/tools/` - калибровка и проверки оборудования |
| [deploy/](deploy/README.md) | **установка по сети** с компьютера на Raspberry Pi или Orange Pi |
| [docs/](docs/) | [подключение оборудования и поэтапная сборка](docs/hardware.md), [решение проблем](docs/troubleshooting.md) |
| [model/](model/README.md) | сбор снимков, обучение и экспорт модели |
| [web/](web/README.md) | сервер мониторинга сети устройств: MQTT → PostgreSQL → API (основа) |

## Быстрый старт

1. Подключите оборудование по [docs/hardware.md](docs/hardware.md).
2. Установите с компьютера по сети:

   ```bash
   ssh-copy-id orangepi@192.168.10.100
   deploy/install.sh orangepi@192.168.10.100 --autostart
   ```

3. Перезагрузите плату, если установщик попросит, и проверьте узлы по
   очереди: `tools/check_servo.py`, `tools/check_camera.py`.
4. Откройте `http://<IP>:3000/settings.html`, откалибруйте центр и секции,
   снимите пустую площадку.
5. Демонстрация распознавания - `http://<IP>:3000/camera.html`.

Обновить код на уже настроенном устройстве:

```bash
deploy/install.sh orangepi@192.168.10.100 --code-only
```

## Разработка

```bash
cd app
python3 -m unittest discover -s tests   # Python-тесты, без оборудования
node --test tests/test_feedback_ui.cjs  # логика главного экрана
```

Локально без камеры и моторов страницы можно проверить, запустив приложение с
`--hardware console` на компьютере с USB-камерой.
