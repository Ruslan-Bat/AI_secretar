@echo off
chcp 65001 > NUL

echo Запуск базы данных...
docker compose up -d

echo Ожидание инициализации БД...
timeout /t 5 /nobreak > NUL

echo Применение миграций...
call python -m alembic -c alembic.ini upgrade head

echo Запуск бэкенда...
.\.venv\Scripts\python.exe -m app.main