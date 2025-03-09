import re
from aiogram import Router, F
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.admin import admin_required

from utils.logger import logger


# Создаем роутер для обработки запросов, связанных с чатом
chat_router = Router()


@chat_router.message(lambda message: re.match(r'^/chat\d+', message.text))
async def process_chat_command(message: Message):
    """
    Обработчик команды /chat<user_id>.
    Отправляет ссылку на пользователя.
    """
    user = message.from_user
    logger.info(f"Пользователь {user.id} ({user.full_name}) использовал команду {message.text}")

    if not await admin_required(message):
        return
    
    # Извлекаем ID пользователя из команды
    match = re.match(r'^/chat(\d+)', message.text)
    if not match:
        await message.reply("Неверный формат команды. Используйте /chat<user_id>")
        return
    
    target_user_id = match.group(1)
    
    # Создаем клавиатуру с кнопкой-ссылкой на пользователя
    builder = InlineKeyboardBuilder()
    builder.button(text=f"Открыть чат с пользователем {target_user_id}", url=f"tg://user?id={target_user_id}")
    
    # Отправляем сообщение с клавиатурой
    await message.reply(
        f"Нажмите на кнопку ниже, чтобы открыть чат с пользователем {target_user_id}:",
        reply_markup=builder.as_markup()
    ) 