from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, CallbackQuery

from config import CHANNEL_ID
from utils import check_user_subscription
from keyboards import get_subscription_keyboard


class SubscriptionMiddleware(BaseMiddleware):
    """
    Middleware для проверки подписки пользователя на канал.
    Если пользователь не подписан, то запрос не будет обработан.
    """
    
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        
        # Если это callback_query с проверкой подписки, пропускаем проверку
        if isinstance(event, CallbackQuery) and event.data == "check_subscription":
            return await handler(event, data)
        
        # Получаем бота из данных
        bot: Bot = data["bot"]
        user = event.from_user
        
        is_subscribed = await check_user_subscription(bot, user.id, CHANNEL_ID)
        
        if is_subscribed:
            return await handler(event, data)
        else:
            # Если пользователь не подписан, отправляем сообщение с предложением подписаться
            if isinstance(event, Message):
                await event.answer(
                    "⚠️ Для участия в розыгрышах необходимо подписаться на наш канал.",
                    reply_markup=get_subscription_keyboard()
                )
            elif isinstance(event, CallbackQuery):
                await event.message.answer(
                    "⚠️ Для участия в розыгрышах необходимо подписаться на наш канал.",
                    reply_markup=get_subscription_keyboard()
                )
                await event.answer()
            
            # Прерываем обработку
            return None
