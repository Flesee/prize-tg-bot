from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import CONTACT_MANAGER_URL


def get_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text="🎁 Купить билеты", callback_data="buy_tickets")
    builder.button(text="❓ FAQ", callback_data="faq")
    builder.button(text="💬 Связаться с менеджером", url=CONTACT_MANAGER_URL)
    
    builder.adjust(1)

    return builder.as_markup()
