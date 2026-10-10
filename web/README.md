# Мониторинг сети UMKA

Сервер, куда устройства UMKA отправляют состояние и события. Схема как в
проекте empolimer: **устройство → MQTT (Mosquitto) → worker → PostgreSQL → backend (FastAPI)**.
Очередь MQTT развязывает устройства и сервер: устройство с плохой связью
отправляет данные, когда может, а worker сохраняет их независимо от API.

```bash
cd web
cp .env.example .env        # задайте пароли
docker compose up -d --build
curl localhost:8300/api/devices
```

## Формат сообщений

| Топик | QoS | Когда | Содержимое |
| --- | --- | --- | --- |
| `umka/<device_id>/status` | 1, retain | раз в минуту и при изменениях | `/api/state` устройства без детекции: `name`, `camera`, `model`, `hardware`, `stats`, `display` |
| `umka/<device_id>/event` | 1 | каждое событие | строка `data/events/events.jsonl`: `event` (`sort`/`feedback`), `event_id`, `timestamp`, `class`, `waste_type`, `section`, `confidence`, `answer` |

`device_id` — латиница без пробелов (`opi-expo`, `school-1`). Устройство
переотправляет события, накопленные без сети; повтор с тем же
`(device_id, event_id, event)` сервер отбрасывает.

## API

| Путь | Что отдаёт |
| --- | --- |
| `GET /api/devices` | устройства, `online` (статус не старше 3 минут), последний статус |
| `GET /api/devices/{id}` | одно устройство |
| `GET /api/devices/{id}/events?limit=100` | последние события |
| `GET /api/summary` | число устройств и сортировок по типам отходов |

## Дальше

- **Устройство:** модуль `app/sorter/telemetry.py` — клиент MQTT (`paho-mqtt`)
  с адресом сервера и `device_id` в `umka.conf`; события читать из
  `events.jsonl` с сохранённой позицией, чтобы после пропадания сети
  догружать пропущенное.
- **Сервер:** миграции Alembic вместо `create_all`, авторизация устройств
  (пароли Mosquitto на каждое устройство), WebSocket для живого обновления.
- **Фронтенд** (`web/front`, Vue + Vite, как в empolimer): карта и список
  устройств с состоянием, графики сортировок по дням и типам, журнал событий.
