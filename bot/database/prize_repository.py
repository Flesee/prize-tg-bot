import re

from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.future import select
from sqlalchemy import func
from datetime import datetime, timezone, timedelta

from utils.logger import logger
from .base import async_session
from .models import Prize, Ticket, TelegramUser


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


def get_current_moscow_time() -> datetime:
    """
    Возвращает текущее время в московском часовом поясе.
    """
    now_utc = datetime.now(timezone.utc)
    return convert_to_moscow_time(now_utc)


async def get_active_prize() -> Optional[Dict[str, Any]]:
    """
    Получает активный розыгрыш.
    """
    try:
        async with async_session() as session:
            # Ищем активный розыгрыш
            query = select(Prize).where(Prize.is_active == True)
            result = await session.execute(query)
            prize = result.scalars().first()
            
            if prize:
                # Преобразуем приз в словарь
                prize_dict = prize.to_dict()
                return prize_dict
            
            return None
    
    except Exception as e:
        logger.error(f"Ошибка при получении активного розыгрыша: {e}")
        return None


async def get_available_tickets(prize_id: int) -> List[int]:
    """
    Получает список доступных билетов для розыгрыша одним запросом.
    """
    try:
        async with async_session() as session:
            # Получаем розыгрыш и сразу вычисляем доступные билеты
            query = select(
                Prize.ticket_count,
                select(func.array_agg(Ticket.ticket_number))
                .where(
                    Ticket.prize_id == prize_id,
                    (Ticket.is_reserved == True) | (Ticket.is_paid == True)
                )
                .scalar_subquery().label("reserved_tickets")
            ).where(Prize.id == prize_id)
            
            result = await session.execute(query)
            row = result.first()
            
            if not row:
                logger.error(f"Розыгрыш с ID {prize_id} не найден")
                return []
            
            ticket_count, reserved_tickets = row
            reserved_tickets = reserved_tickets or []
            
            all_tickets = set(range(1, ticket_count + 1))
            available_tickets = sorted(list(all_tickets - set(reserved_tickets)))
            
            return available_tickets
    
    except Exception as e:
        logger.error(f"Ошибка при получении доступных билетов: {e}")
        return []


async def reserve_tickets(prize_id: int, user_id: int, ticket_numbers: List[int], reserve_time: int = 1) -> Tuple[bool, List[int], str]:
    """
    Резервирует билеты для пользователя.
    
    Args:
        prize_id: ID розыгрыша
        user_id: ID пользователя в Telegram
        ticket_numbers: Список номеров билетов для резервации
        
    Returns:
        Tuple[bool, List[int], str]: Кортеж из флага успешности, списка зарезервированных билетов и сообщения
    """
    try:
        async with async_session() as session:
            # Получаем розыгрыш
            prize_query = select(Prize).where(Prize.id == prize_id)
            prize_result = await session.execute(prize_query)
            prize = prize_result.scalars().first()
            
            if not prize:
                return False, [], "Розыгрыш не найден"
            
            # Проверяем, активен ли розыгрыш
            if not prize.is_active:
                return False, [], "Розыгрыш не активен"
            
            # Получаем пользователя
            user_query = select(TelegramUser).where(TelegramUser.telegram_id == user_id)
            user_result = await session.execute(user_query)
            user = user_result.scalars().first()
            
            if not user:
                return False, [], "Пользователь не найден"
            
            # Получаем доступные билеты
            available_tickets = await get_available_tickets(prize_id)
            
            # Проверяем, доступны ли все запрошенные билеты
            unavailable_tickets = [num for num in ticket_numbers if num not in available_tickets]
            if unavailable_tickets:
                return False, unavailable_tickets, f"Билеты {' '.join(map(str, unavailable_tickets))} недоступны"

            reserved_tickets = []
            reservation_time = datetime.now() + timedelta(minutes=reserve_time)
            
            for ticket_number in ticket_numbers:
                # Проверяем, существует ли уже билет
                ticket_query = select(Ticket).where(
                    Ticket.prize_id == prize_id,
                    Ticket.ticket_number == ticket_number
                )
                ticket_result = await session.execute(ticket_query)
                ticket = ticket_result.scalars().first()
                
                if ticket:
                    # Если билет существует, проверяем, не зарезервирован ли он и не оплачен ли он
                    if ticket.is_reserved or ticket.is_paid:
                        continue
                    
                    # Обновляем билет
                    ticket.user_id = user.id
                    ticket.is_reserved = True
                    ticket.reserved_until = reservation_time
                    ticket.updated_at = datetime.now()
                else:
                    # Создаем новый билет
                    now = datetime.now()
                    ticket = Ticket(
                        prize_id=prize_id,
                        user_id=user.id,
                        ticket_number=ticket_number,
                        is_reserved=True,
                        is_paid=False,
                        reserved_until=reservation_time,
                        created_at=now,
                        updated_at=now
                    )
                    session.add(ticket)
                
                reserved_tickets.append(ticket_number)
            
            # Сохраняем изменения
            await session.commit()
            
            return True, reserved_tickets, "Билеты успешно зарезервированы"
    
    except Exception as e:
        logger.error(f"Ошибка при резервации билетов: {e}")
        return False, [], f"Ошибка при резервации билетов: {e}"


async def cancel_all_reservations(user_id: int):
    """
    Отменяет все резервации для данного пользователя.
    """
    try:
        async with async_session() as session:
            # Сначала находим пользователя по его Telegram ID
            user_query = select(TelegramUser).where(TelegramUser.telegram_id == user_id)
            user_result = await session.execute(user_query)
            user = user_result.scalar_one_or_none()
            
            if not user:
                logger.warning(f"Пользователь с Telegram ID {user_id} не найден при отмене резерваций")
                return True, "Нет активных резерваций"
            
            # Получаем все билеты для данного пользователя
            query = select(Ticket).where(
                (Ticket.user_id == user.id) & 
                (Ticket.is_reserved == True) & 
                (Ticket.is_paid == False)
            )
            result = await session.execute(query)
            tickets = result.scalars().all()

            if tickets:
                for ticket in tickets:
                    ticket.is_reserved = False
                    ticket.reserved_until = None
                    ticket.user_id = None
                    ticket.updated_at = datetime.now()
                
                await session.commit()
                return True, f"Отменены резервации для {len(tickets)} билетов"
    
    except Exception as e:
        logger.error(f"Ошибка при отмене резерваций: {e}")
        return False, f"Ошибка при отмене резерваций: {e}"


async def check_and_release_expired_reservations() -> int:
    """
    Проверяет и снимает просроченные резервации билетов.
    """
    try:
        async with async_session() as session:
            # Получаем все зарезервированные билеты с истекшим сроком резервации
            now = datetime.now()
            query = select(Ticket).where(
                Ticket.is_reserved == True,
                Ticket.is_paid == False,
                Ticket.reserved_until < now
            )
            result = await session.execute(query)
            expired_tickets = result.scalars().all()
            
            # Снимаем резервацию с просроченных билетов
            count = 0
            for ticket in expired_tickets:
                ticket.is_reserved = False
                ticket.reserved_until = None
                ticket.user_id = None
                ticket.updated_at = now
                count += 1
            
            # Сохраняем изменения
            if count > 0:
                await session.commit()
                logger.info(f"Снята резервация с {count} просроченных билетов")
            
            return count
    
    except Exception as e:
        logger.error(f"Ошибка при проверке просроченных резерваций: {e}")
        return 0


async def check_and_finish_expired_prizes():
    """
    Проверяет и завершает розыгрыши, у которых истекло время.
    Возвращает список завершенных розыгрышей.
    """
    try:
        async with async_session() as session:
            # Получаем текущее время в московском часовом поясе
            now = get_current_moscow_time()
            
            # Получаем все активные розыгрыши
            query = select(Prize).where(Prize.is_active == True)
            result = await session.execute(query)
            active_prizes = result.scalars().all()
            
            finished_prizes = []
            for prize in active_prizes:
                # Преобразуем дату окончания розыгрыша в московское время
                prize_end_date = convert_to_moscow_time(prize.end_date)
                
                # Проверяем, истекло ли время розыгрыша
                if prize_end_date < now:
                    # Деактивируем розыгрыш
                    prize.is_active = False
                    prize.updated_at = datetime.now()
                    finished_prizes.append(prize)
                    logger.info(f"Розыгрыш {prize.id} завершен по истечении времени.")
            
            if finished_prizes:
                await session.commit()
                logger.info(f"Завершено {len(finished_prizes)} розыгрышей с истекшим сроком")
            
            return finished_prizes
    except Exception as e:
        logger.error(f"Ошибка при проверке и завершении розыгрышей: {e}")
        return []


async def parse_ticket_numbers(text: str) -> List[int]:
    """
    Парсит номера билетов из текста.
    """
    # Находим все числа в тексте с помощью регулярного выражения
    numbers = re.findall(r'\d+', text)
    
    # Преобразуем строки в числа, удаляем дубликаты и сортируем
    ticket_numbers = sorted(set(int(num) for num in numbers))
    
    return ticket_numbers
