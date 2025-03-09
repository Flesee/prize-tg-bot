from aiogram import Router
from .start import start_router
from .tickets import tickets_router
from .faq import faq_router
from .chat import chat_router


main_router = Router()

# Подключаем все роутеры к главному
main_router.include_router(start_router)
main_router.include_router(tickets_router)
main_router.include_router(faq_router)
main_router.include_router(chat_router)


__all__ = ["main_router"]
