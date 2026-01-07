FROM python:3.11-slim

# Установка FFmpeg и зависимостей
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код бота
COPY DiscordBotStart.py .

# Переменные окружения
ENV PYTHONUNBUFFERED=1

# Запуск
CMD ["python", "DiscordBotStart.py"]
