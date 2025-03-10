from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from utils.logger import logger
from database.base import async_session
from database.models import FAQ
from keyboards import get_back_keyboard


# Создаем роутер для обработки запросов, связанных с FAQ
faq_router = Router()


async def get_active_faq():
    """
    Получает активный текст FAQ из базы данных.
    """
    try:
        from sqlalchemy.future import select
        
        async with async_session() as session:
            query = select(FAQ).where(FAQ.is_active == True)
            result = await session.execute(query)
            faq = result.scalar_one_or_none()
            
            if faq:
                return faq.to_dict()
            return None
    except Exception as e:
        logger.error(f"Ошибка при получении FAQ: {e}")
        return None


@faq_router.callback_query(F.data == "faq")
async def show_faq(callback: CallbackQuery):
    """
    Обработчик нажатия на кнопку "FAQ".
    Показывает текст FAQ.
    """
    user = callback.from_user
    logger.info(f"Пользователь {user.id} ({user.full_name}) открыл FAQ")
    
    # Получаем активный FAQ
    faq = await get_active_faq()
    
    if not faq:
        await callback.message.edit_text(
            "В данный момент информация FAQ недоступна.",
            reply_markup=get_back_keyboard()
        )
        await callback.answer()
        return
    
    # Создаем клавиатуру с кнопкой "Назад"
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="start")
    builder.adjust(1)
    
    # Отправляем сообщение с текстом FAQ и клавиатурой
    await callback.message.edit_text(
        faq["text"],
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    
    await callback.answer() 