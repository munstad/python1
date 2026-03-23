# 🛂 Visa Slot Bot

Автоматический Telegram-бот для мониторинга и бронирования слотов в визовых центрах.

## Архитектура

```
┌─────────────────────┐      RabbitMQ       ┌──────────────────────┐
│   Python Bot        │ ──── visa.tasks ──► │   Go Core            │
│   (aiogram 3.x)     │ ◄─ visa.notif. ──── │   (monitor + book)   │
└─────────┬───────────┘                     └──────────┬───────────┘
          │                                             │
          ▼                                             ▼
    PostgreSQL                                       Redis
    (users, tasks)                              (sessions, cache)
```

### Компоненты

| Сервис | Технология | Роль |
|--------|-----------|------|
| `bot` | Python 3.12 + aiogram 3 | Telegram UI, FSM-диалоги, уведомления |
| `core` | Go 1.22 | HTTP/Browser мониторинг, бронирование |
| `postgres` | PostgreSQL 16 | Хранение пользователей и задач |
| `redis` | Redis 7 | FSM-состояния, кеш сессий |
| `rabbitmq` | RabbitMQ 3.13 | Очередь задач между bot и core |

---

## Быстрый старт

### 1. Клонируйте / распакуйте проект

```bash
cd visa-bot
```

### 2. Создайте `.env`

```bash
cp .env.example .env
```

Заполните обязательные поля:

```env
BOT_TOKEN=            # Telegram Bot Token от @BotFather
POSTGRES_PASSWORD=    # сильный пароль
REDIS_PASSWORD=       # сильный пароль
RABBITMQ_PASSWORD=    # сильный пароль
ENCRYPTION_KEY=       # base64 ключ 32 байта (см. ниже)
ANTICAPTCHA_KEY=      # ключ от anti-captcha.com (необязательно)
```

Генерация ключа шифрования:
```bash
python3 -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

### 3. Подключите целевой сайт

Откройте `core/cmd/core/main.go` и настройте адаптер:

```go
// Для сайтов с REST API:
adapter := monitor.NewHTTPAdapter(
    "VFS Global",
    "https://visa.vfsglobal.com/api/slots",  // реальный URL
    "https://visa.vfsglobal.com/api/book",
    proxyRotator,
    captchaSolver,
)

// Для JS-сайтов (SPA):
adapter := monitor.NewBrowserAdapter(
    "VFS Global",
    "https://visa.vfsglobal.com/appointments",
    "https://visa.vfsglobal.com/appointments/book",
    cfg.ChromiumPath, captchaSolver, log,
)
```

Затем адаптируйте CSS-селекторы в `core/internal/monitor/browser_adapter.go`
или структуру JSON в `core/internal/monitor/http_adapter.go`.

### 4. Запустите

```bash
docker compose up --build -d
```

Проверить логи:
```bash
docker compose logs -f bot
docker compose logs -f core
```

---

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Начало работы |
| `/register` | Заполнить/обновить персональные данные |
| `/start_search` | Запустить поиск слота |
| `/stop_search` | Остановить все активные задачи |
| `/status` | Статус задач |
| `/edit_data` | Редактировать данные |
| `/help` | Справка |

---

## Добавление нового визового центра

1. Изучите сетевые запросы сайта в DevTools (вкладка Network).
2. Если сайт — REST API → используйте `HTTPAdapter`, адаптируйте `CheckSlots` и `Book`.
3. Если сайт — SPA/JS → используйте `BrowserAdapter`, обновите CSS-селекторы.
4. При необходимости — создайте отдельную реализацию `SiteAdapter`.

---

## Безопасность

- Персональные данные шифруются **AES-256-GCM** перед записью в БД.
- Пароли и ключи хранятся **только** в `.env` (не в коде).
- Прокси поддерживают HTTP/S и SOCKS5.
- Ротация User-Agent на каждый запрос.
- SSH-доступ к серверу — только по ключам.

---

## Структура проекта

```
visa-bot/
├── bot/                    # Python Telegram бот
│   ├── handlers/           # Обработчики команд и FSM
│   ├── keyboards/          # Клавиатуры
│   ├── services/           # DB, broker, encryption
│   ├── states/             # FSM-состояния
│   ├── models.py           # SQLAlchemy модели
│   ├── config.py           # Настройки
│   └── main.py             # Точка входа
├── core/                   # Go мониторинг-ядро
│   ├── cmd/core/           # Точка входа
│   └── internal/
│       ├── broker/         # RabbitMQ клиент
│       ├── captcha/        # Anti-Captcha API
│       ├── config/         # Конфигурация
│       ├── monitor/        # Адаптеры + менеджер воркеров
│       └── proxy/          # Ротация прокси
├── infrastructure/
│   └── migrations/         # SQL-миграции
├── docker-compose.yml
└── .env.example
```

---

## Требования к серверу

- OS: Ubuntu 22.04 LTS
- CPU: 2+ vCPU
- RAM: 2+ GB
- Docker 24+, Docker Compose v2
