import sys
import os
from datetime import datetime
from loguru import logger


def setup_logger():
    """
    Настройка логирования.
    Логи сохраняются в файлы по дням и выводятся в консоль.
    """
    # Используем абсолютный путь к директории логов
    logs_dir = "/app/logs"
    os.makedirs(logs_dir, exist_ok=True)

    # Формат логов
    log_format = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"

    # Имя файла логов с текущей датой
    log_file = os.path.join(logs_dir, f"bot_{datetime.now().strftime('%Y-%m-%d')}.log")

    logger.remove()

    logger.add(sys.stdout, format=log_format, level="INFO")

    # Добавляем запись в файл с правами на запись
    logger.add(
        log_file,
        format=log_format,
        level="DEBUG",
        rotation="00:00",
        compression="zip",
        retention="30 days",
        backtrace=True,
        diagnose=True,
    )

    # Добавляем обработчик для критических ошибок
    logger.add(
        os.path.join(logs_dir, "critical.log"),
        format=log_format,
        level="ERROR",
        backtrace=True,
        diagnose=True,
    )

    return logger


logger = setup_logger()
