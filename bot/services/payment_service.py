import uuid
import base64
from datetime import datetime, timedelta
import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import Table, Column, Integer, String, Boolean, DateTime, ForeignKey, Float, MetaData, and_, or_, insert

from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, YOOKASSA_API_URL
from database.models import Ticket, TelegramUser, Prize
from utils.logger import logger
from utils.formatting import format_price


async def get_user_reserved_tickets(session: AsyncSession, user_telegram_id: int):
    """
    Получение зарезервированных билетов пользователя
    
    Args:
        session: Сессия базы данных
        user_telegram_id: Telegram ID пользователя
    
    Returns:
        Tuple[List[Ticket], Prize, TelegramUser]: Список билетов, приз и пользователь
    """
    try:
        # Находим пользователя по Telegram ID
        user_query = select(TelegramUser).where(TelegramUser.telegram_id == user_telegram_id)
        user_result = await session.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"Пользователь с Telegram ID {user_telegram_id} не найден")
            return [], None, None
        
        # Находим активный приз
        prize_query = select(Prize).where(Prize.is_active == True)
        prize_result = await session.execute(prize_query)
        prize = prize_result.scalar_one_or_none()
        
        if not prize:
            logger.warning("Активный приз не найден")
            return [], None, user
        
        # Находим зарезервированные билеты пользователя
        tickets_query = select(Ticket).where(
            and_(
                Ticket.user_id == user.id,
                Ticket.prize_id == prize.id,
                Ticket.is_reserved == True,
                Ticket.is_paid == False
            )
        )
        tickets_result = await session.execute(tickets_query)
        tickets = tickets_result.scalars().all()
        
        return tickets, prize, user
    except Exception as e:
        logger.error(f"Ошибка при получении зарезервированных билетов: {e}")
        return [], None, None


async def init_payment(session: AsyncSession, user_telegram_id: int, bot_username: str):
    """
    Инициализация платежа в системе ЮKassa
    
    Args:
        session: Сессия базы данных
        user_telegram_id: Telegram ID пользователя
        bot_username: Имя бота для формирования return_url
    
    Returns:
        Dict: Информация о платеже или None в случае ошибки
    """
    try:
        # Проверяем, что настройки ЮKassa загружены
        if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
            logger.error(f"Ошибка: Не заданы настройки ЮKassa. SHOP_ID: {YOOKASSA_SHOP_ID}, SECRET_KEY: {YOOKASSA_SECRET_KEY}")
            return None
        
        # Получаем зарезервированные билеты пользователя
        tickets, prize, user = await get_user_reserved_tickets(session, user_telegram_id)
        
        if not tickets or not prize or not user:
            logger.warning(f"Не найдены зарезервированные билеты для пользователя {user_telegram_id}")
            return None
        
        # Рассчитываем общую сумму
        ticket_price = float(prize.ticket_price or 0)
        total_amount = len(tickets) * ticket_price
        
        # Формируем уникальный ключ для идемпотентности запросов
        idempotence_key = str(uuid.uuid4())
        
        # Формируем данные для запроса
        data = {
            "amount": {
                "value": f"{total_amount:.2f}",
                "currency": "RUB"
            },
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{bot_username}"
            },
            "description": f"Оплата билетов для розыгрыша '{prize.title}'",
            "metadata": {
                "user_id": str(user_telegram_id),
                "prize_id": str(prize.id),
                "ticket_numbers": ",".join(str(ticket.ticket_number) for ticket in tickets)
            }
        }
        
        # Формируем заголовки для авторизации
        auth_string = f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {encoded_auth}",
            "Idempotence-Key": idempotence_key,
            "Content-Type": "application/json"
        }
        
        # Логируем данные запроса
        logger.info(f"Отправка запроса к API ЮKassa: {YOOKASSA_API_URL}/payments")
        
        # Отправляем запрос к API ЮKassa
        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(
                f"{YOOKASSA_API_URL}/payments", 
                json=data, 
                headers=headers,
                ssl=True
            ) as response:
                if response.status != 200:
                    logger.error(f"Ошибка при инициализации платежа. Статус: {response.status}")
                    return None
                
                result = await response.json()
                
                if result.get("id"):
                    # Обновляем время резервации билетов на 10 минут
                    reserved_until = datetime.now() + timedelta(minutes=10)
                    for ticket in tickets:
                        ticket.reserved_until = reserved_until
                        ticket.updated_at = datetime.now()
                    
                    # Сохраняем ID платежа в первом билете (для упрощения)
                    tickets[0].payment_id = result.get("id")
                    
                    await session.commit()
                    
                    # Форматируем сумму
                    formatted_amount = format_price(total_amount)
                    
                    # Возвращаем информацию о платеже
                    return {
                        "payment_id": result.get("id"),
                        "payment_url": result.get("confirmation", {}).get("confirmation_url"),
                        "status": result.get("status"),
                        "amount": total_amount,
                        "formatted_amount": formatted_amount,
                        "ticket_count": len(tickets)
                    }
                else:
                    logger.error(f"Ошибка при инициализации платежа: {result}")
                    return None
    except Exception as e:
        logger.error(f"Ошибка при инициализации платежа: {e}")
        return None


async def check_payment_status(payment_id: str):
    """
    Проверка статуса платежа в системе ЮKassa
    """
    try:
        # Проверяем, что настройки ЮKassa загружены
        if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
            logger.error(f"Ошибка: Не заданы настройки ЮKassa")
            return None
        
        # Формируем заголовки для авторизации
        auth_string = f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}"
        auth_base64 = base64.b64encode(auth_string.encode()).decode()
        headers = {
            "Authorization": f"Basic {auth_base64}",
            "Content-Type": "application/json"
        }
        
        # Отправляем запрос к API ЮKassa
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{YOOKASSA_API_URL}/payments/{payment_id}", 
                headers=headers,
                ssl=True
            ) as response:
                if response.status != 200:
                    logger.error(f"Ошибка при проверке статуса платежа. Статус: {response.status}")
                    return None
                
                result = await response.json()
                
                if result.get("id"):
                    return {
                        "status": result.get("status"),
                        "payment_id": result.get("id"),
                        "paid": result.get("paid", False),
                        "amount": float(result.get("amount", {}).get("value", 0)),
                        "metadata": result.get("metadata", {})
                    }
                else:
                    logger.error(f"Ошибка при проверке статуса платежа: {result}")
                    return None
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса платежа: {e}")
        return None


async def update_tickets_payment_status(session: AsyncSession, payment_id: str, status: str):
    """
    Обновление статуса оплаты билетов
    
    Args:
        session: Сессия базы данных
        payment_id: ID платежа
        status: Статус платежа
    
    Returns:
        Tuple[bool, List[Ticket]]: Успешность операции и список оплаченных билетов
    """
    try:
        # Проверяем, является ли это бесплатным платежом
        is_free_payment = payment_id.startswith("free_")
        
        if is_free_payment:
            # Для бесплатных билетов извлекаем user_id и prize_id из payment_id
            # Формат: free_{user_id}_{prize_id}_{timestamp}
            parts = payment_id.split("_")
            if len(parts) >= 3:
                user_id = int(parts[1])
                prize_id = int(parts[2])
                
                # Находим все билеты пользователя для данного приза
                tickets_query = select(Ticket).where(
                    and_(
                        Ticket.user_id == user_id,
                        Ticket.prize_id == prize_id,
                        Ticket.is_reserved == True,
                        Ticket.is_paid == False
                    )
                )
                tickets_result = await session.execute(tickets_query)
                tickets = tickets_result.scalars().all()
                
                if not tickets:
                    logger.warning(f"Не найдены зарезервированные билеты для пользователя {user_id} и приза {prize_id}")
                    return False, []
            else:
                logger.error(f"Неверный формат ID бесплатного платежа: {payment_id}")
                return False, []
        else:
            # Для обычных платежей ищем билет с ID платежа
            ticket_query = select(Ticket).where(Ticket.payment_id == payment_id)
            ticket_result = await session.execute(ticket_query)
            ticket = ticket_result.scalar_one_or_none()
            
            if not ticket:
                logger.error(f"Билет с ID платежа {payment_id} не найден")
                return False, []
            
            # Находим все билеты пользователя для данного приза
            user_id = ticket.user_id
            prize_id = ticket.prize_id
            
            tickets_query = select(Ticket).where(
                and_(
                    Ticket.user_id == user_id,
                    Ticket.prize_id == prize_id,
                    Ticket.is_reserved == True,
                    Ticket.is_paid == False
                )
            )
            tickets_result = await session.execute(tickets_query)
            tickets = tickets_result.scalars().all()
            
            if not tickets:
                logger.warning(f"Не найдены зарезервированные билеты для пользователя {user_id} и приза {prize_id}")
                return False, []
        
        # Если платеж успешен, обновляем статус билетов
        if status == "succeeded":
            # Находим пользователя
            user_query = select(TelegramUser).where(TelegramUser.id == user_id)
            user_result = await session.execute(user_query)
            user = user_result.scalar_one_or_none()
            
            if not user:
                logger.error(f"Пользователь с ID {user_id} не найден")
                return False, []
            
            # Находим приз
            prize_query = select(Prize).where(Prize.id == prize_id)
            prize_result = await session.execute(prize_query)
            prize = prize_result.scalar_one_or_none()
            
            if not prize:
                logger.error(f"Приз с ID {prize_id} не найден")
                return False, []
            
            # Рассчитываем общую сумму
            ticket_price = float(prize.ticket_price or 0)
            total_amount = len(tickets) * ticket_price
            
            # Получаем метаданные
            metadata = MetaData()
            
            # Определяем таблицу Payment
            payment_table = Table(
                'prizes_payment',
                metadata,
                Column('id', Integer, primary_key=True),
                Column('user_id', Integer, ForeignKey('prizes_telegramuser.id')),
                Column('prize_id', Integer, ForeignKey('prizes_prize.id')),
                Column('amount', Float),
                Column('payment_id', String(255)),
                Column('is_successful', Boolean, default=True),
                Column('created_at', DateTime),
                Column('updated_at', DateTime)
            )
            
            # Определяем таблицу для связи Payment и Ticket (many-to-many)
            payment_ticket_table = Table(
                'prizes_payment_tickets',
                metadata,
                Column('id', Integer, primary_key=True),
                Column('payment_id', Integer, ForeignKey('prizes_payment.id')),
                Column('ticket_id', Integer, ForeignKey('prizes_ticket.id'))
            )
                
            now = datetime.now()
            
            payment_insert = insert(payment_table).values(
                user_id=user_id,
                prize_id=prize_id,
                amount=total_amount,
                payment_id=payment_id,
                is_successful=True,
                created_at=now,
                updated_at=now
            )
            
            payment_result = await session.execute(payment_insert)
            payment_id_db = payment_result.inserted_primary_key[0]
            
            # Создаем записи в таблице связи Payment и Ticket
            for ticket in tickets:
                payment_ticket_insert = insert(payment_ticket_table).values(
                    payment_id=payment_id_db,
                    ticket_id=ticket.id
                )
                await session.execute(payment_ticket_insert)
            
            # Обновляем статус билетов
            for ticket in tickets:
                ticket.is_paid = True
                ticket.is_reserved = False
                ticket.reserved_until = None
                ticket.updated_at = datetime.now()
            
            await session.commit()
            logger.info(f"Статус оплаты билетов обновлен на 'оплачено' для пользователя {user_id}")
            logger.info(f"Создана запись в модели Payment с ID {payment_id_db}")
            return True, tickets
        else:
            logger.info(f"Платеж {payment_id} имеет статус {status}, билеты остаются зарезервированными")
            return False, tickets
    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса оплаты билетов: {e}")
        await session.rollback()
        return False, []


async def get_payment_by_id(session: AsyncSession, payment_id: str):
    """
    Получение информации о платеже по ID
    
    Args:
        session: Сессия базы данных
        payment_id: ID платежа
    
    Returns:
        Dict: Информация о платеже или None в случае ошибки
    """
    try:
        # Находим билет с ID платежа
        ticket_query = select(Ticket).where(Ticket.payment_id == payment_id)
        ticket_result = await session.execute(ticket_query)
        ticket = ticket_result.scalar_one_or_none()
        
        if not ticket:
            logger.warning(f"Билет с ID платежа {payment_id} не найден")
            return None
        
        # Находим все билеты пользователя для данного приза
        user_id = ticket.user_id
        prize_id = ticket.prize_id
        
        tickets_query = select(Ticket).where(
            and_(
                Ticket.user_id == user_id,
                Ticket.prize_id == prize_id,
                or_(
                    Ticket.is_paid == True,
                    and_(
                        Ticket.is_reserved == True,
                        Ticket.payment_id == payment_id
                    )
                )
            )
        )
        tickets_result = await session.execute(tickets_query)
        tickets = tickets_result.scalars().all()
        
        # Находим приз
        prize_query = select(Prize).where(Prize.id == prize_id)
        prize_result = await session.execute(prize_query)
        prize = prize_result.scalar_one_or_none()
        
        if not prize:
            logger.warning(f"Приз с ID {prize_id} не найден")
            return None
        
        # Находим пользователя
        user_query = select(TelegramUser).where(TelegramUser.id == user_id)
        user_result = await session.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"Пользователь с ID {user_id} не найден")
            return None
        
        # Рассчитываем общую сумму
        total_amount = len(tickets) * float(prize.ticket_price or 0)
        
        # Возвращаем информацию о платеже
        return {
            "payment_id": payment_id,
            "user_id": user.telegram_id,
            "prize_id": prize_id,
            "prize_title": prize.title,
            "ticket_count": len(tickets),
            "amount": total_amount,
            "formatted_amount": format_price(total_amount),
            "tickets": [ticket.ticket_number for ticket in tickets]
        }
    except Exception as e:
        logger.error(f"Ошибка при получении информации о платеже: {e}")
        return None 