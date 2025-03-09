from utils.logger import logger


async def check_user_subscription(bot, user_id, channel_id):
    """
    Проверяет, подписан ли пользователь на канал или группу.
    """
    try:
        
        # Проверяем статус пользователя в канале/группе
        chat_member = await bot.get_chat_member(chat_id=int(channel_id), user_id=user_id)
        
        # Список статусов, при которых пользователь считается подписанным
        allowed_statuses = ['member', 'administrator', 'creator']
        
        is_subscribed = chat_member.status in allowed_statuses

        return is_subscribed
    except Exception as e:
        logger.warning(f"Ошибка при проверке подписки: {e}")
        return False

