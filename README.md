# Сравнение версий проекта

В этом README описаны изменения между старой версией проекта, находящейся в папке `BOT_SHARE`, и текущей версией проекта в корне репозитория.

## 1. Общие отличия

### Старая версия `BOT_SHARE`
- Telegram-бот работал с Google Calendar через сервисный аккаунт.
- Хранилище пользователей было памятью (`MemoryUserRepository`).
- Не было пользовательского OAuth для доступа к личному Google Calendar.
- В `app/api` был только `/health` и webhook для Telegram.
- В `app/bot` были команды `/start`, `/help`, `/ping`, `/calendar`, `/add_event`, `/delete_event`.

### Новая версия
- Добавлена поддержка PostgreSQL через асинхронный репозиторий `SqlUserRepository`.
- Добавлен пользовательский Google OAuth через команду `/login` и callback FastAPI маршрут `/auth/google/callback`.
- Calendar integration перенесена от сервисного аккаунта к OAuth-авторизации пользователя.
- Добавлен Alembic для управления миграциями базы данных.
- Добавлен `docker-compose.yml` для запуска PostgreSQL.
- Обновлены зависимости в `requirements.txt`.

## 2. Файлы, которые добавились и что они делают

### Новые файлы
- `app/alembic.ini` — конфигурация Alembic.
- `app/alembic/env.py` — скрипт запуска миграций, который конфигурирует асинхронный движок и использует SQLAlchemy metadata из `app/repositories/sql_user.py`.
- `app/alembic/versions/75d61ad13989_.py` — первая миграция для создания таблицы `users`.
- `app/alembic/versions/0380d0dbba44_add_googlecredentials.py` — миграция для создания таблицы `google_credentials`.
- `app/api/google_auth.py` — обработчик callback Google OAuth, сохраняет токены в БД и возвращает пользователя обратно в Telegram.
- `app/bot/handlers/login.py` — новая команда `/login`, которая генерирует ссылку на Google OAuth и отправляет её пользователю.
- `app/domain/credentials.py` — доменная модель для хранения Google OAuth credentials.
- `app/integrations/google_auth.py` — слой интеграции с Google OAuth 2.0: генерация ссылки, обмен кода на токены и обновление учётных данных.
- `app/repositories/sql_user.py` — SQLAlchemy-репозитории для пользователей и Google credentials.
- `app/services/google_auth.py` — бизнес-логика OAuth: state-токен, верификация, обмен кода на токены, сохранение, обновление access token.

### Файлы, затронутые изменениями
- `app/api/router.py` — теперь включает роутер Google OAuth.
- `app/bot/routers.py` — теперь включает роутер логина.
- `app/bot/dispatcher.py` — теперь регистрирует `auth_service` в контексте диспетчера aiogram.
- `app/bot/lifecycle.py` — теперь передаёт `auth_service` в `create_dispatcher`.
- `app/services/calendar.py` — теперь требует авторизации пользователя и использует Google OAuth токены.
- `app/dependencies.py` — теперь создаёт асинхронный движок, сессию и `GoogleAuthService`.
- `app/config.py` — добавлены настройки PostgreSQL и Google OAuth, построение `database_url_asyncpg()`.
- `app/integrations/google_calendar.py` — изменён интеграционный адаптер для работы через OAuth Credentials.
- `requirements.txt` — добавлены зависимости для Alembic, SQLAlchemy, asyncpg, psycopg, google_auth_oauthlib, PyJWT.

## 3. Изменения в `app/api`

### `app/api/router.py`
- В старой версии API собирал только `health_router` и `webhook_router`.
- В новой версии добавлен `google_auth_router`.

### `app/api/google_auth.py`
- Новый файл, где реализован endpoint `GET /auth/google/callback`.
- Логика:
  1. Принимает `code` и `state` из query-параметров.
  2. Верифицирует `state` как JWT, получая `telegram_id`.
  3. Передаёт код и `telegram_id` в `GoogleAuthService`.
  4. Сохраняет полученные access/refresh токены в базу данных.
  5. Редиректит пользователя обратно в Telegram через deep link с `start=auth_success`. (т.е. бот тебе пишет сообщение об успешной авторизации)
- Обрабатывает ошибки валидации токена и общий сбой OAuth.

### `app/api/webhook.py`
- Остался функционально тем же, что и в старой версии: принимает обновления от Telegram webhook.
- Проверяет `X-Telegram-Bot-Api-Secret-Token` и состояние `BOT_MODE == "webhook"`.
- Валидирует payload как `aiogram.types.Update` и передаёт его диспетчеру.

### `app/api/health.py`
- Оставлен прежним: возвращает `status`, `service` и `bot_mode`.

## 4. Изменения в `app/bot`

### Общая архитектура
- В старой версии бот был сконфигурирован на запуск /help /start /ping /calendar /add_event /delete_event.
- В новой версии добавлен новый логин-поток и сервис авторизации.

### `app/bot/routers.py`
- Включает новый роутер `create_login_router()`.
- Это позволяет обрабатывать `/login` вместе с остальными командами.

### `app/bot/dispatcher.py`
- В старой версии диспетчер хранил только `user_service` и `calendar_service`.
- В новой версии диспетчер также хранит `auth_service`, чтобы его можно было инжектировать в хендлеры aiogram.

### `app/bot/lifecycle.py`
- При создании диспетчера теперь передаётся `container.auth_service`.
- Это обеспечивает доступ к OAuth-сервису в Telegram-командах.

### `app/bot/handlers/login.py`
- Новая команда `/login`.
- Проверяет, что команда вызвана в приватном чате.
- Генерирует Google OAuth ссылку через `GoogleAuthService.build_authorization_url(telegram_id)`.
- Отправляет пользователю ссылку для авторизации.

### `app/bot/handlers/start.py`
- Дополнен логикой распознавания аргумента `auth_success`.
- После OAuth-редиректа пользователь получает подтверждение: токены сохранены и бот может работать с календарём.
- По-прежнему регистрирует/обновляет Telegram-пользователя в БД.

### `app/bot/handlers/calendar.py`
- Теперь передаёт `telegram_id` в `calendar_service`.
- При отсутствии авторизации отвечает `Нужно пройти /login`.
- Обрабатывает новые ошибки:
  - `CalendarAuthRequiredError`
  - `CalendarTokenRefreshError`
  - `EventNotFoundError`
- При наличии доступа использует OAuth-credentials конкретного пользователя.

## 5. Файлы, отвечающие за взаимодействие с базой данных

### `app/config.py`
- Добавляет переменные окружения для PostgreSQL: `USER_REPOSITORY`, `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME`.
- Добавляет Google OAuth настройки: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`.
- Создаёт URL `database_url_asyncpg()` в формате `postgresql+asyncpg://...`.

### `app/dependencies.py`
- Создаёт асинхронный движок SQLAlchemy `create_async_engine(..., echo=False)`.
- Создаёт `async_sessionmaker(..., expire_on_commit=False)`.
- Выбирает репозиторий:
  - `SqlUserRepository`, если `USER_REPOSITORY == "postgres"`.
  - `MemoryUserRepository`, если PostgreSQL не включён.
- Инициализирует `GoogleAuthService` только если есть `session_factory`.
- Экспортирует `get_google_auth_service(request)` для FastAPI dependency injection.

### `app/repositories/sql_user.py`
- Определяет метаданные и таблицы SQLAlchemy:
  - `users`
  - `google_credentials`
- Реализует `SqlUserRepository`:
  - `get_by_telegram_id(telegram_id)`
  - `upsert(user)` с `INSERT ... ON CONFLICT DO UPDATE`
  - `count()`
- Реализует `SqlCredentialsRepository`:
  - `get_by_telegram_id(telegram_id)`
  - `upsert(credentials)` с `INSERT ... ON CONFLICT DO UPDATE`
  - `delete_by_telegram_id(telegram_id)`
- Использует асинхронные сессии SQLAlchemy и `asyncpg`.
- Преобразует результаты SQLAlchemy в доменные объекты `User` и `GoogleCredentials`.

### `app/services/google_auth.py`
- Сохраняет и обновляет токены Google OAuth в базе данных.
- Генерирует защищённый `state` JWT с `telegram_id`.
- Верифицирует `state` токен и извлекает `telegram_id`.
- Обменивает `code` на access/refresh токены через `GoogleOAuthIntegration`.
- Приводит данные к доменной модели `GoogleCredentials`.
- Обновляет access token при необходимости через refresh token и сохраняет новые значения в БД.

### `app/services/calendar.py`
- Теперь передаёт user-specific OAuth credentials в `CalendarGateway`.
- Если пользователь не авторизован или токен просрочен, выбрасывает `CalendarAuthRequiredError` или `CalendarTokenRefreshError`.
- Это делает логику календаря зависимой от состояния в БД, а не только от сервисного аккаунта.

## 6. Зачем нужна папка `alembic`

Папка `app/alembic` содержит инфраструктуру миграций базы данных.
Она важна, потому что:
- фиксирует состояние схемы БД в виде версий;
- позволяет воспроизводимо создавать таблицы `users` и `google_credentials`;
- помогает безопасно изменять схему в будущем;
- позволяет запустить миграции автоматически или вручную при деплое.

В текущем проекте Alembic управляет схемой для PostgreSQL, опираясь на SQLAlchemy metadata из `app/repositories/sql_user.py`.

## 7. Что находится в `docker-compose.yml`

`docker-compose.yml` описывает один сервис:
- `db` — контейнер PostgreSQL `postgres:17-alpine`.

Он настраивается так:
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` берутся из переменных окружения `DB_USER`, `DB_PASS`, `DB_NAME`.
- порт контейнера `5432` проброшен наружу через `${DB_PORT}:5432`.
- настроен `healthcheck` с командой `pg_isready`.
- том `./db_data` монтируется в контейнер как `/var/lib/postgresql/data` для сохранения данных.

## 8. Дополнительно

### Обновления зависимостей
В `requirements.txt` добавлены библиотеки для работы с базой данных, Alembic и OAuth:
- `alembic`
- `asyncpg`
- `psycopg`
- `psycopg-binary`
- `sqlalchemy`
- `pydantic`
- `google_auth_oauthlib`
- `PyJWT`

### Замечание
В новой версии появилась команда `/login`, но в `app/bot/handlers/help.py` пока не обновлено текстовое описание команды. Это стоит учесть при дальнейшем улучшении UX.

## 9. PyJWT в проекте

PyJWT используется для безопасной передачи `telegram_id` между Telegram-ботом и Google OAuth callback. Это необходимо, чтобы:
- зашифровать `telegram_id` в параметр `state`, который Google возвращает обратно в callback;
- защититься от подделки параметра `state` (CSRF) и от повторного использования устаревших ссылок;
- убедиться, что callback связан именно с тем пользователем Telegram, который начал OAuth-поток.

PyJWT применяется в файле `app/services/google_auth.py` в методах:
- `generate_state_token(self, telegram_id: int) -> str` — генерирует JWT с полем `telegram_id` и сроком жизни;
- `verify_state_token(self, token: str) -> int` — проверяет подпись и срок годности JWT, возвращает `telegram_id`.

Этот токен затем передаётся через `state` в `app/api/google_auth.py` при обработке `/auth/google/callback`.



--------------------------------------------------------------------------------------------
--------------------------------------------------------------------------------------------

# Как подключить Google Calendar

Интеграция использует пользовательский Google OAuth и работает с календарём
пользователя через токены, сохранённые в базе данных.

## 1. Подготовить Google Cloud

1. Создать проект в Google Cloud Console.
2. Включить **Google Calendar API**.
3. Создать OAuth 2.0 Client ID в разделе Credentials.
4. Добавить redirect URI вида `http://localhost:8000/auth/google/callback`.

## 2. Заполнить `.env`

```dotenv
GOOGLE_CALENDAR_ENABLED=true
GOOGLE_CALENDAR_TIMEZONE=Europe/Moscow
GOOGLE_CALENDAR_MAX_RESULTS=10
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
```

## 4. Установить зависимости и запустить

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.main
```

## 5. Проверить в Telegram

```text
/calendar
/add_event 2026-07-20 14:30 60 Тестовая встреча
/delete_event EVENT_ID
```

`/calendar` выводит ID событий. Этот ID нужно передать в `/delete_event`.

Если бот сообщает, что календарь не настроен, проверить переменные `.env` и правильность Google OAuth настроек.







