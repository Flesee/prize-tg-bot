from typing import Optional, Dict, Any, Tuple
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from datetime import datetime

from utils.logger import logger
from .base import async_session
from .models import TelegramUser


async def get_or_create_user(telegram_id: int, full_name: str, username: Optional[str] = None) -> Tuple[Dict[str, Any], bool]:
    """
    Получает или создает пользователя в базе данных через SQLAlchemy.
    
    Args:
        telegram_id: ID пользователя в Telegram
        full_name: Полное имя пользователя
        username: Имя пользователя (опционально)
        
    Returns:
        Tuple[Dict[str, Any], bool]: Кортеж из данных пользователя и флага, был ли пользователь создан
    """
    # Форматируем username, добавляя @ если его нет
    if username and not username.startswith('@'):
        username = f"@{username}"
    
    try:
        async with async_session() as session:
            # Ищем пользователя по telegram_id
            query = select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
            result = await session.execute(query)
            user = result.scalars().first()
            
            if user:
                # Пользователь существует, обновляем данные если нужно
                if user.full_name != full_name or user.username != username:
                    user.full_name = full_name
                    user.username = username
                    user.updated_at = datetime.now()
                    await session.commit()
                    logger.info(f"Пользователь обновлен в базе данных: {telegram_id}")
                created = False
            else:
                # Пользователь не существует, создаем нового
                try:
                    now = datetime.now()
                    user = TelegramUser(
                        telegram_id=telegram_id,
                        full_name=full_name,
                        username=username,
                        created_at=now,
                        updated_at=now
                    )
                    session.add(user)
                    await session.commit()
                    logger.info(f"Пользователь создан в базе данных: {telegram_id}")
                    created = True
                except IntegrityError as e:
                    # Если произошла ошибка уникальности, значит пользователь уже был создан
                    # другим процессом, откатываем транзакцию и получаем пользователя заново
                    await session.rollback()
                    query = select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
                    result = await session.execute(query)
                    user = result.scalars().first()
                    if not user:
                        # Если пользователь все еще не найден, что-то пошло не так
                        logger.error(f"Не удалось найти пользователя после ошибки IntegrityError: {e}")
                        raise
                    created = False

            await session.refresh(user)

            user_dict = user.to_dict()
            
            return user_dict, created
    
    except Exception as e:
        logger.error(f"Ошибка при работе с базой данных: {e}")
        return {
            "telegram_id": telegram_id,
            "full_name": full_name,
            "username": username
        }, False