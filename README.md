# Как подключить Google Calendar

Интеграция использует один общий Google Calendar и service account. LLM и
пользовательский OAuth не требуются.

## 1. Подготовить Google Cloud

1. Создать проект в Google Cloud Console.
2. Включить **Google Calendar API**.
3. Создать service account и скачать его JSON-ключ.
4. Сохранить ключ в корне проекта, например:

```text
google-service-account.json
```

Файл уже покрывается `.gitignore`; коммитить его нельзя.

## 2. Открыть календарь сервисному аккаунту

В JSON-ключе найти `client_email`. В настройках нужного Google Calendar
добавить этот email в список пользователей и дать право изменять события.

Там же скопировать **Calendar ID**. Для календаря пользователя указывается его
ID/email, а не `primary` сервисного аккаунта.

## 3. Заполнить `.env`

```dotenv
GOOGLE_CALENDAR_ENABLED=true
GOOGLE_SERVICE_ACCOUNT_FILE=google-service-account.json
GOOGLE_CALENDAR_ID=your_calendar_id
GOOGLE_CALENDAR_TIMEZONE=Europe/Moscow
GOOGLE_CALENDAR_MAX_RESULTS=10
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

Если бот сообщает, что календарь не настроен, проверить переменные `.env`,
путь к JSON и доступ service account к календарю.



