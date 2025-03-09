from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_payment_keyboard(payment_url: str = None) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с кнопками "Оплатить" и "Назад".
    """
    builder = InlineKeyboardBuilder()
    
    if payment_url:
        builder.button(text="💳 Оплатить", url=payment_url)
    else:
        builder.button(text="💳 Купить", callback_data="pay_tickets")
    
    builder.button(text="🔙 Назад", callback_data="buy_tickets")
    
    builder.adjust(1)
    
    return builder.as_markup()


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с кнопкой "Отмена".
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="start")
    return builder.as_markup()


def get_back_keyboard() -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с кнопкой "Назад".
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="start")
    return builder.as_markup()
