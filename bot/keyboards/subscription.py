from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import CHANNEL_URL


def get_subscription_keyboard() -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с кнопками для подписки на канал и проверки подписки.
    """
    builder = InlineKeyboardBuilder()

    builder.button(text="📢 Подписаться на канал", url=CHANNEL_URL)
    builder.button(text="✅ Проверить подписку", callback_data="check_subscription")

    builder.adjust(1)
    
    return builder.as_markup()
