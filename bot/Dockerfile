FROM python:3.12-slim

WORKDIR /app

# Установка необходимых зависимостей для компиляции
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libpq-dev \
    tzdata \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Настройка временной зоны (современный способ)
ENV TZ=Europe/Moscow
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование проекта
COPY . .

# Запуск бота
CMD ["python", "main.py"] 