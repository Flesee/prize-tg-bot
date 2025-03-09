from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from utils.logger import logger
from database import check_and_release_expired_reservations, check_and_finish_expired_prizes
from utils.prize_announcer import check_and_announce_prizes


# Создаем планировщик задач
scheduler = AsyncIOScheduler(
    job_defaults={
        'misfire_grace_time': 30,  # Допустимое время опоздания в секундах
        'coalesce': True
    }
)

# Глобальная переменная для хранения экземпляра бота
bot_instance = None


async def check_expired_reservations_job():
    """
    Задача для проверки и снятия просроченных резерваций.
    """
    try:
        await check_and_release_expired_reservations()
    except Exception as e:
        logger.error(f"Ошибка при выполнении задачи по проверке резерваций: {e}")


async def check_expired_prizes_job():
    """
    Задача для проверки и завершения розыгрышей с истекшим сроком.
    """
    try:
        await check_and_finish_expired_prizes()
    except Exception as e:
        logger.error(f"Ошибка при выполнении задачи по проверке розыгрышей: {e}")


async def announce_prizes_job():
    """
    Задача для проверки и анонсирования розыгрышей.
    """
    if bot_instance is None:
        logger.error("Бот не инициализирован для задачи анонсирования розыгрышей")
        return
    
    try:
        await check_and_announce_prizes(bot_instance)
    except Exception as e:
        logger.error(f"Ошибка при выполнении задачи по анонсированию розыгрышей: {e}")


def setup_scheduler(bot=None):
    """
    Настраивает планировщик задач.
    """
    global bot_instance
    bot_instance = bot
    
    # Добавляем задачу для проверки просроченных резерваций каждые 30 секунд
    scheduler.add_job(
        check_expired_reservations_job,
        trigger=IntervalTrigger(seconds=30),
        id="check_expired_reservations_job",
        replace_existing=True
    )
    
    # Добавляем задачу для проверки розыгрышей с истекшим сроком каждую минуту
    scheduler.add_job(
        check_expired_prizes_job,
        trigger=IntervalTrigger(minutes=1),
        id="check_expired_prizes",
        replace_existing=True
    )
    
    # Добавляем задачу для проверки и анонсирования розыгрышей каждую минуту
    scheduler.add_job(
        announce_prizes_job,
        trigger=IntervalTrigger(minutes=1),
        id="announce_prizes_job",
        replace_existing=True
    )
    
    # Запускаем планировщик
    scheduler.start()
    logger.info("Планировщик задач запущен")


def shutdown_scheduler():
    """
    Останавливает планировщик задач.
    """
    scheduler.shutdown()
    logger.info("Планировщик задач остановлен") 