# sk-aisb

Небольшой репозиторий для работы с компьютерным зрением на ПК и Raspberry Pi:

- сбор изображений с камер;
- проверка камеры и быстрые тесты;
- обучение и экспорт YOLO-моделей;
- локальная детекция;
- передача видеопотока с Raspberry Pi на ПК с распознаванием.

## Структура

- [docs/README.md](docs/README.md)
  Общая документация и установка окружения.
- [collect/README.md](collect/README.md)
  Сбор датасета с ПК и Raspberry Pi.
- [checking/README.md](checking/README.md)
  Быстрые проверки камер и тестовые скрипты.
- [training/README.md](training/README.md)
  Ноутбуки, зависимости и данные для обучения.
- [prepare/README.md](prepare/README.md)
  Экспорт моделей, включая NCNN.
- [detection/README.md](detection/README.md)
  Локальный запуск детекции на ПК и Raspberry Pi.
- [network/README.md](network/README.md)  
  Стрим с Raspberry Pi на ПК и распознавание на стороне ПК.
- [waste/README.md](waste/README.md)  
  Прототип умной мусорки: детекция на ПК и команды сервомоторам на Raspberry Pi.
- [servo_test/README.md](servo_test/README.md)  
  Тест сервопривода на Raspberry Pi.

## Быстрый маршрут по проекту

1. Подготовить окружение: [docs/setup-rpi.md](docs/setup-rpi.md)
2. Проверить камеру: [checking/README.md](checking/README.md)
3. Собрать снимки: [collect/README.md](collect/README.md)
4. Обучить или обновить модель: [training/README.md](training/README.md)
5. При необходимости экспортировать модель: [prepare/README.md](prepare/README.md)
6. Запустить детекцию локально или по сети:
   [detection/README.md](detection/README.md),
   [network/README.md](network/README.md)

## Основные сценарии

Локальная детекция на ПК:

```bash
python detection/detect_pc.py --model detection/example.pt
```

Локальная детекция на Raspberry Pi:

```bash
python detection/detect_rpi.py --model detection/example.pt
```

Стрим с Raspberry Pi на ПК:

```bash
# Raspberry Pi
python network/stream_server_rpi.py

# PC
python network/stream_client_pc.py --host <IP_RPI> --port 5000 --model detection/example.pt
```

## Замечания

- Для `Raspberry Pi Zero 2 W` лучше начинать с умеренных параметров качества и размера кадра.
- В папках проекта лежат как рабочие скрипты, так и тестовые/диагностические утилиты.
