import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

from aiogram import Bot
from aiogram.types import InputMediaPhoto, FSInputFile
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select, update

from database.base import async_session
from database.models import Prize, Ticket
from utils.formatting import format_price
from utils.logger import logger


def make_naive(dt: datetime) -> datetime:
    """
    Преобразует дату с часовым поясом (aware) в дату без часового пояса (naive).
    """
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def convert_to_moscow_time(dt: datetime) -> datetime:
    """
    Преобразует время из UTC в московское время (UTC+3).
    """
    # Проверяем, имеет ли дата информацию о часовом поясе
    if dt.tzinfo is None:
        # Если нет, предполагаем, что это UTC
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Определяем смещение для московского времени (UTC+3)
    moscow_offset = timedelta(hours=3)
    
    # Преобразуем в московское время
    moscow_time = dt.astimezone(timezone(moscow_offset))
    
    return moscow_time


async def get_active_prize() -> Optional[Prize]:
    """
    Получает активный розыгрыш из базы данных.
    """
    async with async_session() as session:
        query = select(Prize).where(Prize.is_active == True)
        result = await session.execute(query)
        return result.scalar_one_or_none()


async def get_pending_prize() -> Optional[Prize]:
    """
    Получает розыгрыш, который должен начаться (время начала наступило, но он еще не активен).
    """
    async with async_session() as session:
        now = make_naive(datetime.now())
        
        query = select(Prize).where(
            (Prize.is_active == False) & 
            (Prize.winner_determined == False) & 
            (Prize.start_date <= now) & 
            (Prize.end_date > now)
        ).order_by(Prize.start_date)
        
        result = await session.execute(query)
        pending_prize = result.scalar_one_or_none()
        
        return pending_prize


async def get_available_ticket_numbers(prize_id: int) -> List[int]:
    """
    Получает список доступных номеров билетов для розыгрыша.
    """
    async with async_session() as session:
        # Получаем розыгрыш для определения количества билетов
        prize_query = select(Prize).where(Prize.id == prize_id)
        prize_result = await session.execute(prize_query)
        prize = prize_result.scalar_one_or_none()
        
        if not prize:
            logger.error(f"Розыгрыш с ID {prize_id} не найден")
            return []
        
        # Получаем все билеты для розыгрыша
        query = select(Ticket).where(Ticket.prize_id == prize_id)
        result = await session.execute(query)
        tickets = result.scalars().all()
        
        # Создаем множество всех номеров билетов
        all_numbers = set(range(1, prize.ticket_count + 1))
        
        # Создаем множество недоступных номеров (зарезервированные или оплаченные)
        unavailable = {ticket.ticket_number for ticket in tickets 
                      if ticket.is_paid or ticket.is_reserved}
        
        # Вычисляем доступные номера и возвращаем их отсортированными
        return sorted(all_numbers - unavailable)


def format_ticket_numbers_for_message(ticket_numbers: List[int]) -> str:
    """
    Форматирует список номеров билетов для отображения в сообщении.
    """
    if not ticket_numbers:
        return "Все билеты проданы или зарезервированы"
    
    # Выводим номера билетов через пробел
    return " ".join(map(str, sorted(ticket_numbers)))


async def format_prize_message(prize: Prize, bot_username: str) -> Tuple[str, Optional[str]]:
    """
    Форматирует сообщение о розыгрыше для отправки в чат.
    """
    # Получаем доступные номера билетов
    available_tickets = await get_available_ticket_numbers(prize.id)
    
    # Преобразуем даты в московское время и форматируем
    start_date_moscow = convert_to_moscow_time(prize.start_date)
    end_date_moscow = convert_to_moscow_time(prize.end_date)
    
    start_date = start_date_moscow.strftime("%d.%m.%Y %H:%M")
    end_date = end_date_moscow.strftime("%d.%m.%Y %H:%M")
    
    # Форматируем цену билета
    ticket_price = format_price(prize.ticket_price)
    
    # Форматируем номера билетов
    formatted_tickets = format_ticket_numbers_for_message(available_tickets)
    
    # Формируем текст сообщения
    message_text = (
        f"🎉 Начался новый розыгрыш!\n\n"
        f"🏆 Приз: {prize.title}\n"
        f"📅 Дата начала: {start_date}\n"
        f"🔚 Дата окончания: {end_date}\n"
        f"💰 Стоимость билета: {ticket_price}\n\n"
        f"🎫 Свободные номера: {formatted_tickets}\n\n"
        f"🔗 Купить билеты: https://t.me/{bot_username}?start=0"
    )
    
    # Путь к изображению (если есть)
    image_path = None
    if prize.image:
        # Проверяем, является ли путь к изображению абсолютным
        if os.path.isabs(prize.image):
            image_path = prize.image
        else:
            # Если путь относительный, добавляем префикс /app/media/
            image_path = os.path.join('/app/media', prize.image)
    
    return message_text, image_path


async def send_prize_announcement(bot: Bot, prize: Prize) -> Optional[int]:
    """
    Отправляет сообщение о розыгрыше в чат.
    """
    try:
        # Получаем ID чата из переменной окружения
        chat_id = os.getenv("CHANNEL_ID")
        if not chat_id:
            logger.error("Не указан CHANNEL_ID в .env")
            return None
        
        # Получаем имя пользователя бота
        bot_info = await bot.get_me()
        bot_username = bot_info.username
        
        # Форматируем сообщение
        message_text, image_path = await format_prize_message(prize, bot_username)
        
        # Отправляем сообщение
        if image_path and os.path.exists(image_path):
            # Если есть изображение, отправляем фото с подписью
            photo = FSInputFile(image_path)
            message = await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=message_text
            )
        else:
            # Если нет изображения или файл не существует, отправляем текстовое сообщение
            message = await bot.send_message(
                chat_id=chat_id,
                text=message_text
            )
        
        # Возвращаем ID сообщения
        return message.message_id
    
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения о розыгрыше: {e}")
        return None


async def update_prize_announcement(bot: Bot, prize: Prize) -> bool:
    """
    Обновляет сообщение о розыгрыше в чате.
    """
    try:
        # Проверяем, есть ли ID сообщения
        if not prize.chat_message_id:
            logger.error(f"Не указан chat_message_id для розыгрыша {prize.id}")
            return False
        
        # Получаем ID чата из переменной окружения
        chat_id = os.getenv("CHANNEL_ID")
        if not chat_id:
            logger.error("Не указан CHANNEL_ID в .env")
            return False
        
        # Получаем имя пользователя бота
        bot_info = await bot.get_me()
        bot_username = bot_info.username
        
        # Форматируем сообщение
        message_text, image_path = await format_prize_message(prize, bot_username)
        
        # Обновляем сообщение
        if image_path and os.path.exists(image_path):
            # Если есть изображение, обновляем фото с подписью
            photo = FSInputFile(image_path)
            await bot.edit_message_media(
                chat_id=chat_id,
                message_id=prize.chat_message_id,
                media=InputMediaPhoto(
                    media=photo,
                    caption=message_text
                )
            )
        else:
            # Если нет изображения или файл не существует, обновляем текстовое сообщение
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=prize.chat_message_id,
                text=message_text
            )
        
        return True
    
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return True
        logger.error(f"Ошибка Telegram при обновлении сообщения о розыгрыше: {e}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при обновлении сообщения о розыгрыше: {e}")
        return False


async def deactivate_all_active_prizes() -> None:
    """
    Деактивирует все активные розыгрыши.
    Используется перед активацией нового розыгрыша, чтобы избежать ситуации,
    когда активно несколько розыгрышей одновременно.
    """
    async with async_session() as session:
        # Находим все активные розыгрыши
        query = select(Prize).where(Prize.is_active == True)
        result = await session.execute(query)
        active_prizes = result.scalars().all()
        
        # Деактивируем каждый розыгрыш
        for prize in active_prizes:
            # Проверяем, не закончился ли розыгрыш
            now = make_naive(datetime.now())
            prize_end_date = make_naive(prize.end_date)
            
            if prize_end_date <= now:
                prize.is_active = False

                session.add(prize)
                logger.info(f"Розыгрыш {prize.id} автоматически завершен по истечении времени")
        
        # Сохраняем изменения
        if active_prizes:
            await session.commit()


async def check_and_announce_prizes(bot: Bot) -> None:
    """
    Проверяет, нужно ли отправить или обновить сообщение о розыгрыше.
    """
    try:
        # Сначала проверяем и деактивируем завершенные розыгрыши
        await deactivate_all_active_prizes()
        
        # Получаем активный розыгрыш
        active_prize = await get_active_prize()
        
        if active_prize:
            # Если есть активный розыгрыш, обновляем сообщение
            if active_prize.chat_message_id:
                await update_prize_announcement(bot, active_prize)
            else:
                # Если сообщение еще не отправлено, отправляем его
                async with async_session() as session:
                    message_id = await send_prize_announcement(bot, active_prize)
                    if message_id:
                        # Сохраняем ID сообщения
                        active_prize.chat_message_id = message_id
                        session.add(active_prize)
                        await session.commit()
        else:
            # Если нет активного розыгрыша, проверяем, есть ли розыгрыш, который должен начаться
            pending_prize = await get_pending_prize()
            
            if pending_prize:
                # Активируем розыгрыш и сохраняем ID сообщения
                async with async_session() as session:
                    pending_prize.is_active = True
                    session.add(pending_prize)
                    
                    # Отправляем сообщение
                    message_id = await send_prize_announcement(bot, pending_prize)
                    if message_id:
                        # Сохраняем ID сообщения
                        pending_prize.chat_message_id = message_id
                        session.add(pending_prize)
                    
                    await session.commit()
                    logger.info(f"Розыгрыш {pending_prize.id} активирован и анонсирован в чате")
    
    except Exception as e:
        logger.error(f"Ошибка при проверке и анонсировании розыгрышей: {e}")
        # Откат транзакции не нужен, так как мы используем контекстный менеджер async_session
