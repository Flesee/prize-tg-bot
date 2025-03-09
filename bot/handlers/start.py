from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from config import CHANNEL_ID
from utils.logger import logger
from utils import check_user_subscription
from keyboards import get_main_keyboard
from database import get_or_create_user

start_router = Router()


@start_router.message(Command("start"))
async def cmd_start(message: Message):
    """
    Обработчик команды /start
    """
    user = message.from_user
    await get_or_create_user(
        telegram_id=user.id,
        full_name=user.full_name,
        username=user.username
    )
    logger.info(f"Пользователь {user.id} ({user.full_name}) запустил бота")
    
    await message.answer(
        f"👋 Привет, {user.full_name}!\n\n"
        f"Я бот для проведения розыгрышей призов.",
        reply_markup=get_main_keyboard()
    )


@start_router.callback_query(F.data == "start")
async def start_callback(callback: CallbackQuery):
    """
    Обработчик нажатия на кнопку с callback_data == "start"
    """
    user = callback.from_user
    await get_or_create_user(
        telegram_id=user.id,
        full_name=user.full_name,
        username=user.username
    )

    await callback.message.edit_text(
        f"👋 Привет, {user.full_name}!\n\n"
        f"Я бот для проведения розыгрышей призов.",
        reply_markup=get_main_keyboard()
    )

    logger.info(f"Пользователь {user.id} ({user.full_name}) запустил бота")
    await callback.answer()



@start_router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery):
    """
    Обработчик нажатия на кнопку "Проверить подписку"
    """
    user = callback.from_user
    bot = callback.bot
    
    # Проверяем подписку пользователя
    is_subscribed = await check_user_subscription(bot, user.id, CHANNEL_ID)
    
    if is_subscribed:
        await callback.answer(
            "✅ Спасибо за подписку! Теперь вы можете участвовать в розыгрышах.",
            show_alert=True
        )
        await callback.message.edit_text(
        f"👋 Привет, {user.full_name}!\n\n"
        "Я бот для проведения розыгрышей призов.",
        reply_markup=get_main_keyboard()
    )
        await get_or_create_user(
        telegram_id=user.id,
        full_name=user.full_name,
        username=user.username
    )
        logger.info(f"Пользователь {user.id} ({user.full_name}) подписался на канал")
    else:
        await callback.answer(
            "❌ Вы не подписаны на канал. Пожалуйста, подпишитесь и нажмите кнопку проверки снова.",
            show_alert=True
        )
        logger.info(f"Пользователь {user.id} ({user.full_name}) не подписался на канал")

    await callback.answer()
