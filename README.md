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



