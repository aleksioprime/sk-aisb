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

Локально страница мониторинга - <http://localhost:8301>, API - <http://localhost:8300>.

## Продакшн (Coolify)

Адрес: **https://umka.technocrew.ru**. Схема как у empolimer:

1. При пуше в `main` с изменениями в `web/` workflow
   [web.yml](../.github/workflows/web.yml) собирает образы `umka-backend`,
   `umka-worker`, `umka-frontend`, публикует их в GHCR, выставляет теги
   `*_IMAGE_TAG` в Coolify и запускает деплой.
2. Coolify разворачивает [docker-compose.prod.yaml](docker-compose.prod.yaml)
   (приложение из репозитория, сборка Docker Compose, базовый каталог `/web`).
   Домен и TLS - на стороне Coolify, наружу смотрит только `frontend` (порт 80).
3. Брокер MQTT - общий сервис в сети `iot`; worker подключается к нему по
   `MQTT_HOST`. Пароль PostgreSQL Coolify генерирует сам.
4. Устройства подключаются к брокеру снаружи: `mqtt.technocrew.ru:8883`, TLS
   (Traefik), пользователь `umka`.

Переменные в Coolify: `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`
(брокер), остальное по умолчанию. Секреты GitHub: `COOLIFY_API`
(`https://devops.skeducator.ru/api/v1`), `COOLIFY_TOKEN`, `COOLIFY_APP` (UUID приложения).

## Вход на сайт

Как в empolimer: пара JWT - access (30 минут, заголовок `Authorization: Bearer`)
и refresh (30 дней; при выходе отзывается). Данные устройств отдаются только
вошедшим, открыт лишь `/api/health`. Секрет подписи `JWT_SECRET_KEY` в Coolify
генерируется сам (`SERVICE_PASSWORD_64_JWT`).

Пользователя создаёт скрипт (пароль спрашивается дважды; повторный запуск
меняет пароль, `--disable` отключает пользователя):

```bash
# Coolify: приложение umka → Terminal → контейнер backend
python create_user.py admin --admin
# локально
docker compose exec backend python create_user.py admin --admin
```

| Путь | Что делает |
| --- | --- |
| `POST /api/auth/login` | логин и пароль → `access_token`, `refresh_token` |
| `POST /api/auth/refresh` | `refresh_token` → новый `access_token` |
| `POST /api/auth/logout` | отзывает `refresh_token` |
| `GET /api/auth/me` | текущий пользователь |

## Формат сообщений

| Топик | QoS | Когда | Содержимое |
| --- | --- | --- | --- |
| `umka/<device_id>/status` | 1, retain | раз в минуту и при изменениях | `/api/state` устройства без детекции: `name`, `camera`, `model`, `hardware`, `stats`, `display` |
| `umka/<device_id>/event` | 1 | каждое событие | строка `data/events/events.jsonl`: `event` (`sort`/`feedback`), `event_id`, `timestamp`, `class`, `waste_type`, `section`, `confidence`, `answer` |

`device_id` - латиница без пробелов (`opi-expo`, `school-1`). Устройство
переотправляет события, накопленные без сети; повтор с тем же
`(device_id, event_id, event)` сервер отбрасывает.

## API

Все пути ниже требуют входа (см. выше).

| Путь | Что отдаёт |
| --- | --- |
| `GET /api/devices` | устройства, `online` (статус не старше 3 минут), последний статус |
| `GET /api/devices/{id}` | одно устройство |
| `GET /api/devices/{id}/events?limit=100` | последние события |
| `GET /api/summary` | число устройств и сортировок по типам отходов |

## Дальше

- **Сервер:** миграции Alembic вместо `create_all`, авторизация устройств
  (пароли Mosquitto на каждое устройство), WebSocket для живого обновления.
- **Фронтенд** (`web/front`, Vue + Vite, как в empolimer): карта и список
  устройств с состоянием, графики сортировок по дням и типам, журнал событий.
