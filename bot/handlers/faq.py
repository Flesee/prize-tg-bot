from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from utils.logger import logger
from database.base import async_session
from database.models import FAQ
from keyboards import get_back_keyboard


# Создаем роутер для обработки запросов, связанных с FAQ
faq_router = Router()


async def get_active_faqs():
    """
    Получает список активных FAQ из базы данных.
    """
    try:
        from sqlalchemy.future import select
        
        async with async_session() as session:
            query = select(FAQ).where(FAQ.is_active == True).order_by(FAQ.order, FAQ.created_at)
            result = await session.execute(query)
            faqs = result.scalars().all()
            
            return [
                {
                    "id": faq.id,
                    "question": faq.question,
                    "answer": faq.answer
                }
                for faq in faqs
            ]
    except Exception as e:
        logger.error(f"Ошибка при получении FAQ: {e}")
        return []


def get_faq_keyboard(faqs):
    """
    Создает клавиатуру с кнопками вопросов FAQ.
    """
    builder = InlineKeyboardBuilder()
    
    for faq in faqs:
        builder.button(text=faq["question"], callback_data=f"faq:{faq['id']}")
    
    builder.button(text="🔙 Назад", callback_data="start")
    
    # Размещаем кнопки по одной в ряд
    builder.adjust(1)
    
    return builder.as_markup()


@faq_router.callback_query(F.data == "faq")
async def show_faq_list(callback: CallbackQuery):
    """
    Обработчик нажатия на кнопку "FAQ".
    Показывает список вопросов.
    """
    user = callback.from_user
    logger.info(f"Пользователь {user.id} ({user.full_name}) открыл FAQ")
    
    # Получаем список активных FAQ
    faqs = await get_active_faqs()
    
    if not faqs:
        await callback.message.edit_text(
            "В данный момент нет доступных вопросов и ответов.",
            reply_markup=get_back_keyboard()
        )
        await callback.answer()
        return
    
    # Формируем сообщение со списком вопросов
    message_text = "❓ *Часто задаваемые вопросы*\n\nВыберите интересующий вас вопрос:"
    
    # Отправляем сообщение с клавиатурой вопросов
    await callback.message.edit_text(
        message_text,
        reply_markup=get_faq_keyboard(faqs),
        parse_mode="Markdown"
    )
    
    await callback.answer()


@faq_router.callback_query(F.data.startswith("faq:"))
async def show_faq_answer(callback: CallbackQuery):
    """
    Обработчик нажатия на кнопку с вопросом.
    Показывает ответ на выбранный вопрос.
    """
    user = callback.from_user
    
    # Получаем ID вопроса из callback_data
    faq_id = int(callback.data.split(":")[1])
    
    logger.info(f"Пользователь {user.id} ({user.full_name}) открыл вопрос с ID {faq_id}")
    
    # Получаем список активных FAQ
    faqs = await get_active_faqs()
    
    # Находим выбранный вопрос
    selected_faq = next((faq for faq in faqs if faq["id"] == faq_id), None)
    
    if not selected_faq:
        await callback.answer("Вопрос не найден", show_alert=True)
        return
    
    # Формируем сообщение с вопросом и ответом
    message_text = (
        f"❓ *{selected_faq['question']}*\n\n"
        f"{selected_faq['answer']}"
    )
    
    # Создаем клавиатуру с кнопкой "Назад к списку вопросов"
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад к списку вопросов", callback_data="faq")
    builder.button(text="🏠 На главную", callback_data="start")
    builder.adjust(1)
    
    # Отправляем сообщение с ответом и клавиатурой
    await callback.message.edit_text(
        message_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    
    await callback.answer() 