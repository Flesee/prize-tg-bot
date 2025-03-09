from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio

from utils.logger import logger
from utils.formatting import format_price, format_ticket_numbers
from database import get_active_prize, get_available_tickets, reserve_tickets, parse_ticket_numbers, cancel_all_reservations
from database.base import async_session
from services.payment_service import init_payment, check_payment_status, update_tickets_payment_status, get_payment_by_id
from keyboards import get_cancel_keyboard, get_back_keyboard, get_payment_keyboard


class TicketStates(StatesGroup):
    waiting_for_ticket_numbers = State()


tickets_router = Router()

# Словарь для хранения таймеров отмены резервации
reservation_timers = {}
# Словарь для хранения таймеров проверки платежей
payment_check_timers = {}


async def cancel_reservation_after_timeout(user_id: int, message: Message):
    """
    Отменяет резервацию билетов после таймаута и обновляет сообщение.
    """
    try:
        # Ждем 1 минуту
        await asyncio.sleep(60)
        
        # Проверяем, не была ли резервация уже отменена или оплачена
        success, message_text = await cancel_all_reservations(user_id)
        
        if success and "Отменены резервации" in message_text:
            await message.edit_text(
                "⏱ Время резервации истекло. Резервация билетов отменена.",
                reply_markup=get_back_keyboard()
            )
            logger.info(f"Автоматически отменена резервация для пользователя {user_id} по истечении времени")
    except Exception as e:
        logger.error(f"Ошибка при автоматической отмене резервации: {e}")
    finally:
        if user_id in reservation_timers:
            del reservation_timers[user_id]


async def check_payment_status_periodically(payment_id: str, user_id: int, message: Message):
    """
    Периодически проверяет статус платежа и обновляет сообщение.
    """
    try:
        # Проверяем статус платежа каждые 15 секунд в течение 15 минут
        for _ in range(60):  # 15 минут = 60 проверок по 15 секунд
            # Проверяем статус платежа
            payment_info = await check_payment_status(payment_id)
            
            if not payment_info:
                logger.warning(f"Не удалось получить информацию о платеже {payment_id}")
                await asyncio.sleep(15)
                continue
            
            # Если платеж успешен, обновляем статус билетов и сообщение
            if payment_info["status"] == "succeeded":
                async with async_session() as session:
                    success, tickets = await update_tickets_payment_status(session, payment_id, "succeeded")
                    
                    if success:
                        # Получаем информацию о платеже
                        payment_data = await get_payment_by_id(session, payment_id)
                        
                        if payment_data:
                            # Форматируем номера билетов
                            formatted_tickets = format_ticket_numbers(payment_data["tickets"])
                            
                            # Обновляем сообщение
                            await message.edit_text(
                                f"✅ Оплата успешно завершена!\n\n"
                                f"🎟 Оплаченные билеты: {formatted_tickets}\n\n"
                                f"Спасибо за участие в розыгрыше! Желаем удачи! 🍀",
                                parse_mode="Markdown",
                                reply_markup=get_back_keyboard()
                            )
                            
                            logger.info(f"Платеж {payment_id} успешно завершен для пользователя {user_id}")
                            
                            # Удаляем таймер из словаря
                            if payment_id in payment_check_timers:
                                del payment_check_timers[payment_id]
                            
                            return
            
            # Если платеж отменен или не удался, обновляем сообщение
            elif payment_info["status"] in ["canceled", "failed"]:
                await message.edit_text(
                    "❌ Платеж отменен или не удался.\n\n"
                    "Вы можете попробовать снова или выбрать другие билеты.",
                    reply_markup=get_back_keyboard()
                )
                
                logger.info(f"Платеж {payment_id} отменен или не удался для пользователя {user_id}")
                
                # Удаляем таймер из словаря
                if payment_id in payment_check_timers:
                    del payment_check_timers[payment_id]
                
                return
            
            # Ждем 15 секунд перед следующей проверкой
            await asyncio.sleep(15)
        
        # Если платеж не завершен за 15 минут, отменяем резервацию
        await cancel_all_reservations(user_id)
        
        await message.edit_text(
            "⏱ Время ожидания оплаты истекло. Резервация билетов отменена.\n\n"
            "Вы можете попробовать снова или выбрать другие билеты.",
            reply_markup=get_back_keyboard()
        )
        
        logger.info(f"Время ожидания оплаты истекло для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса платежа: {e}")
    finally:
        # Удаляем таймер из словаря
        if payment_id in payment_check_timers:
            del payment_check_timers[payment_id]


@tickets_router.callback_query(F.data == "buy_tickets")
async def buy_ticket(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик нажатия на кнопку "Купить билеты".
    Показывает информацию о призе и доступных билетах.
    """
    user = callback.from_user
    
    # Отменяем таймер, если он существует
    if user.id in reservation_timers:
        reservation_timers[user.id].cancel()
        del reservation_timers[user.id]
    
    await cancel_all_reservations(user.id)
    logger.info(f"Пользователь {user.id} ({user.full_name}) нажал на кнопку 'Купить билеты'")

    prize = await get_active_prize()
    
    if not prize:
        await callback.answer("В данный момент нет активных розыгрышей", show_alert=True)
        return

    available_tickets = await get_available_tickets(prize["id"])
    
    if not available_tickets:
        await callback.answer("К сожалению, нет доступных билетов", show_alert=True)
        return
    
    # Форматируем список доступных билетов
    formatted_tickets = format_ticket_numbers(available_tickets)
    
    # Форматируем цену билета
    formatted_price = format_price(prize["ticket_price"])
    
    # Формируем сообщение с информацией о призе и доступных билетах
    message_text = (
        f"🎁 *{prize['title']}*\n\n"
        f"💰 Стоимость билета: {formatted_price}\n"
        f"🎟 Доступные билеты:\n{formatted_tickets}\n\n"
        f"Введите номера билетов, которые хотите купить (через пробел):"
    )

    await state.update_data(prize_id=prize["id"])

    await state.set_state(TicketStates.waiting_for_ticket_numbers)

    await callback.message.edit_text(
        message_text,
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )

    await callback.answer()


@tickets_router.message(TicketStates.waiting_for_ticket_numbers)
async def process_ticket_numbers(message: Message, state: FSMContext):
    """
    Обработчик ввода номеров билетов.
    Проверяет доступность билетов и резервирует их.
    """
    user = message.from_user
    logger.info(f"Пользователь {user.id} ({user.full_name}) ввел номера билетов: {message.text}")
    
    # Получаем данные из состояния
    state_data = await state.get_data()
    prize_id = state_data.get("prize_id")
    
    if not prize_id:
        await message.answer("Произошла ошибка. Пожалуйста, начните заново.", reply_markup=get_back_keyboard())
        await state.clear()
        return
    
    # Получаем активный розыгрыш
    prize = await get_active_prize()
    
    if not prize or prize["id"] != prize_id:
        await message.answer("Розыгрыш больше не активен.", reply_markup=get_back_keyboard())
        await state.clear()
        return
    
    # Парсим номера билетов из сообщения
    ticket_numbers = await parse_ticket_numbers(message.text)
    
    if not ticket_numbers:
        await message.answer(
            "Не удалось распознать номера билетов. Пожалуйста, введите номера через пробел.",
            reply_markup=get_cancel_keyboard()
        )
        return

    available_tickets = await get_available_tickets(prize_id)
    
    # Проверяем, доступны ли все запрошенные билеты
    unavailable_tickets = [num for num in ticket_numbers if num not in available_tickets]
    if unavailable_tickets:
        # Обновляем список доступных билетов
        available_tickets = await get_available_tickets(prize_id)
        
        # Форматируем списки билетов
        formatted_unavailable = format_ticket_numbers(unavailable_tickets)
        formatted_available = format_ticket_numbers(available_tickets)
        
        await message.answer(
            f"Недоступные билеты: {formatted_unavailable}\n\n"
            f"Доступные билеты: {formatted_available}\n\n"
            f"Пожалуйста, выберите из доступных билетов:",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    # Резервируем билеты
    success, reserved_tickets, message_text = await reserve_tickets(prize_id, user.id, ticket_numbers)
    
    if not success:
        await message.answer(
            f"Ошибка при резервации билетов: {message_text}\n\n"
            f"Пожалуйста, попробуйте еще раз:",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    # Рассчитываем общую стоимость
    total_price = len(reserved_tickets) * float(prize["ticket_price"])
    
    # Форматируем цену и номера билетов
    formatted_total_price = format_price(total_price)
    formatted_tickets = format_ticket_numbers(reserved_tickets)
    
    # Формируем сообщение с информацией о зарезервированных билетах
    success_message = (
        f"🎁 *{prize['title']}*\n\n"
        f"🎟 Зарезервированные билеты: {formatted_tickets}\n"
        f"💰 Общая стоимость: {formatted_total_price}"
    )
    
    # Отправляем сообщение с клавиатурой для оплаты
    sent_message = await message.answer(
        success_message,
        reply_markup=get_payment_keyboard(),
        parse_mode="Markdown"
    )
    
    # Создаем и запускаем таймер для автоматической отмены резервации
    if user.id in reservation_timers:
        # Если уже есть таймер для этого пользователя, отменяем его
        reservation_timers[user.id].cancel()
    
    # Создаем новый таймер
    task = asyncio.create_task(
        cancel_reservation_after_timeout(user.id, sent_message)
    )
    reservation_timers[user.id] = task

    await state.clear()


@tickets_router.callback_query(F.data == "pay_tickets")
async def process_payment(callback: CallbackQuery):
    """
    Обработчик нажатия на кнопку "Оплатить".
    Инициирует процесс оплаты через ЮKassa.
    """
    user = callback.from_user
    logger.info(f"Пользователь {user.id} ({user.full_name}) нажал на кнопку 'Оплатить'")
    
    # Отменяем таймер, если он существует
    if user.id in reservation_timers:
        reservation_timers[user.id].cancel()
        del reservation_timers[user.id]
    
    # Получаем имя бота для формирования return_url
    bot = await callback.bot.get_me()
    bot_username = bot.username
    
    # Инициализируем платеж
    async with async_session() as session:
        payment_info = await init_payment(session, user.id, bot_username)
        
        if not payment_info:
            await callback.answer("Ошибка при инициализации платежа. Пожалуйста, попробуйте позже.", show_alert=True)
            return
        
        # Обновляем сообщение с информацией о платеже
        await callback.message.edit_text(
            f"💳 *Оплата билетов*\n\n"
            f"🎟 Количество билетов: {payment_info['ticket_count']}\n"
            f"💰 Сумма к оплате: {payment_info['formatted_amount']}\n\n"
            f"⏱ Билеты зарезервированы на 15 минут. Пожалуйста, оплатите их в течение этого времени.\n\n"
            f"Для оплаты нажмите на кнопку ниже:",
            parse_mode="Markdown",
            reply_markup=get_payment_keyboard(payment_info["payment_url"])
        )
        
        # Создаем и запускаем таймер для проверки статуса платежа
        payment_id = payment_info["payment_id"]
        
        # Если уже есть таймер для этого платежа, отменяем его
        if payment_id in payment_check_timers:
            payment_check_timers[payment_id].cancel()
        
        # Создаем новый таймер
        task = asyncio.create_task(
            check_payment_status_periodically(payment_id, user.id, callback.message)
        )
        payment_check_timers[payment_id] = task

        await callback.answer()
