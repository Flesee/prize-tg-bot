import asyncio
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from handlers import main_router
from middlewares import SubscriptionMiddleware
from utils.logger import logger
from utils.scheduler import setup_scheduler, shutdown_scheduler


async def main():
    # Проверка наличия токена
    if not BOT_TOKEN:
        logger.error("Ошибка: BOT_TOKEN не найден в переменных окружения")
        sys.exit(1)
    
    # Инициализация бота и диспетчера
    bot = Bot(token=BOT_TOKEN)
    
    # Инициализация хранилища состояний
    storage = MemoryStorage()
    
    # Инициализация диспетчера с хранилищем состояний
    dp = Dispatcher(storage=storage)

    # Регистрация middleware
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())
    
    # Регистрация роутеров
    dp.include_router(main_router)
    
    # Запуск планировщика задач с передачей экземпляра бота
    setup_scheduler(bot)
    
    # Запуск бота
    logger.info("✅ Бот запущен")

    # Устанавливаем команды бота
    await set_bot_commands(bot)

    try:
        await dp.start_polling(bot)
    finally:
        shutdown_scheduler()
        await bot.session.close()


async def set_bot_commands(bot: Bot):
    """Установка команд бота"""
    from aiogram.types import BotCommand
    
    commands = [
        BotCommand(command="start", description="Запустить бота"),
    ]
    
    await bot.set_my_commands(commands)
    logger.info("✅ Команды бота установлены")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("⛔️ Бот остановлен")
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")
        sys.exit(1)