from aiogram import types
from sqlalchemy import select

from database.models import TelegramUser
from database.base import async_session
from utils.logger import logger

async def check_admin(message: types.Message) -> bool:
    """
    Проверяет, является ли пользователь администратором.
    """
    try:
        user_id = message.from_user.id
        
        # Запрашиваем пользователя из базы данных
        async with async_session() as session:
            query = select(TelegramUser).where(TelegramUser.telegram_id == user_id)
            result = await session.execute(query)
            user = result.scalar_one_or_none()

            # Проверяем, является ли пользователь администратором
            if user and user.is_admin:
                return True

            return False
    except Exception as e:
        logger.error(f"Ошибка при проверке прав администратора: {e}")
        return False

async def admin_required(message: types.Message) -> bool:
    """
    Проверяет, является ли пользователь администратором и отправляет сообщение,
    если у пользователя нет прав администратора.
    """
    is_admin = await check_admin(message)
    
    if not is_admin:
        await message.reply("У вас нет прав для выполнения этой команды.")
        
    return is_admin 