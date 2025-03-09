import os
from dotenv import load_dotenv
from pathlib import Path

# Определяем путь к корневой директории проекта
BASE_DIR = Path(__file__).resolve().parent.parent

# Загрузка переменных окружения из файла .env
load_dotenv(BASE_DIR / '.env')

# Настройки бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_URL = os.getenv("CHANNEL_URL")
CHANNEL_ID = os.getenv("CHANNEL_ID")
CONTACT_MANAGER_URL = os.getenv("CONTACT_MANAGER_URL")

# Настройки для доступа к медиа-файлам
MEDIA_ROOT = os.getenv('MEDIA_ROOT', '/app/media')
HOST = os.getenv('HOST', 'localhost')
PORT = os.getenv('PORT', '8000')
MEDIA_URL_EXTERNAL = f"http://{HOST}:{PORT}/media/"

# Настройки базы данных
DB_NAME = os.getenv('DB_NAME', 'prizebot_db')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')
DB_HOST = os.getenv('DB_HOST', 'db')
DB_PORT = os.getenv('DB_PORT', '5432')
DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Настройки платежного шлюза ЮKassa
YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID')
YOOKASSA_SECRET_KEY = os.getenv('YOOKASSA_SECRET_KEY')
YOOKASSA_API_URL = os.getenv('YOOKASSA_API_URL', 'https://api.yookassa.ru/v3')

# Настройки логирования
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', '/app/logs/bot.log')

