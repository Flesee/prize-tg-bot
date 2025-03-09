#!/bin/bash

# Создаем директории для логов и медиа-файлов
mkdir -p /app/logs
mkdir -p /app/media/prizes

# Проверяем, существует ли файл settings.py
if [ ! -f /app/prizebot_admin/wsgi.py ]; then
    echo "Инициализация Django проекта..."
    django-admin startproject prizebot_admin .
    echo "Django проект успешно инициализирован!"
fi

# Функция для проверки доступности базы данных
wait_for_db() {
    echo "Ожидание готовности базы данных..."
    while ! python << END
import sys
import os
import psycopg2
try:
    psycopg2.connect(
        dbname=os.environ.get('DB_NAME', 'prizebot_db'),
        user=os.environ.get('DB_USER', 'postgres'),
        password=os.environ.get('DB_PASSWORD', 'postgres'),
        host=os.environ.get('DB_HOST', 'db'),
        port=os.environ.get('DB_PORT', '5432')
    )
except psycopg2.OperationalError:
    sys.exit(1)
sys.exit(0)
END
    do
        echo "База данных недоступна, ожидание..."
        sleep 1
    done
    echo "База данных готова!"
}

# Ждем готовности базы данных перед применением миграций
wait_for_db

# Создаем директорию для миграций, если её нет
mkdir -p /app/prizes/migrations

# Применяем миграции
python manage.py makemigrations --noinput
python manage.py migrate --noinput

# Создаем суперпользователя, если его нет
if [ "$DJANGO_SUPERUSER_USERNAME" ] && [ "$DJANGO_SUPERUSER_PASSWORD" ] && [ "$DJANGO_SUPERUSER_EMAIL" ]; then
    python manage.py createsuperuser --noinput || true
fi

# Создаем директории для статических файлов, если их нет
mkdir -p /app/static
mkdir -p /app/media

# Собираем статические файлы
python manage.py collectstatic --noinput --clear

# Запускаем Gunicorn для продакшена
echo "Запуск Gunicorn..."
exec gunicorn prizebot_admin.wsgi:application --bind 0.0.0.0:8000 --workers 3 --log-file=/app/logs/gunicorn.log --access-logfile=/app/logs/access.log 