import json
import uuid
import base64
from datetime import datetime
import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete

from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, YOOKASSA_API_URL
from models import Order, OrderItem
from services.cart_service import get_cart_items
from utils.logger import logger


async def init_payment(session: AsyncSession, user_id: int, delivery_info: dict):
    """
    Инициализация платежа в системе ЮKassa
    
    Args:
        session: Сессия базы данных
        user_id: ID пользователя
        delivery_info: Информация о доставке
    """
    try:
        # Проверяем, что настройки ЮKassa загружены
        if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
            logger.error(f"Ошибка: Не заданы настройки ЮKassa. SHOP_ID: {YOOKASSA_SHOP_ID}, SECRET_KEY: {YOOKASSA_SECRET_KEY}")
            return None
        else:
            shop_id = YOOKASSA_SHOP_ID
            secret_key = YOOKASSA_SECRET_KEY
            
        # Получаем товары из корзины
        cart_items = await get_cart_items(session, user_id)
        if not cart_items:
            return None
        
        # Рассчитываем общую сумму заказа
        total_amount = sum(item[0].quantity * item[1].price for item in cart_items)
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
                "return_url": "https://t.me/bot_username"
            },
            "description": f"Заказ №{idempotence_key[:8]}",
            "metadata": {
                "user_id": str(user_id)
            }
        }

        auth_string = f"{shop_id}:{secret_key}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {encoded_auth}",
            "Idempotence-Key": idempotence_key,
            "Content-Type": "application/json"
        }
        
        # Логируем данные запроса и заголовки авторизации для отладки
        logger.info(f"Отправка запроса к API ЮKassa: {YOOKASSA_API_URL}/payments")
        logger.info(f"Данные запроса: {data}")
        
        # Отправляем запрос к API ЮKassa
        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(
                f"{YOOKASSA_API_URL}/payments", 
                json=data, 
                headers=headers,
                ssl=True
            ) as response:
                logger.info(f"Статус ответа: {response.status}")
                logger.info(f"Заголовки ответа: {response.headers}")
                
                # Если ответ не в формате JSON, логируем текст ответа
                if 'application/json' not in response.headers.get('Content-Type', ''):
                    text = await response.text()
                    logger.error(f"Ответ не в формате JSON: {text[:500]}")
                    return None
                
                result = await response.json()
                logger.info(f"Тело ответа: {result}")
                
                if result.get("id"):
                    new_order = Order(
                        user_id=user_id,
                        status="pending",
                        username=delivery_info['username'],
                        full_name=delivery_info['full_name'],
                        phone=delivery_info['phone'],
                        address=delivery_info['address'],
                        payment_id=result.get("id"),
                        payment_status=result.get("status"),
                        total_price=total_amount,
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    
                    session.add(new_order)
                    await session.flush()  # Получаем ID заказа

                    for cart_item, product in cart_items:
                        order_item = OrderItem(
                            order_id=new_order.id,
                            product_id=product.id,
                            quantity=cart_item.quantity,
                            price=product.price
                        )
                        session.add(order_item)
                    
                    await session.commit()
                    
                    # Возвращаем информацию о платеже
                    return {
                        "order_id": new_order.id,
                        "payment_id": result.get("id"),
                        "payment_url": result.get("confirmation", {}).get("confirmation_url"),
                        "status": result.get("status"),
                        "amount": total_amount
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
            logger.error(f"Ошибка: Не заданы настройки ЮKassa. SHOP_ID: {YOOKASSA_SHOP_ID}, SECRET_KEY: {YOOKASSA_SECRET_KEY}")
            return None
        else:
            shop_id = YOOKASSA_SHOP_ID
            secret_key = YOOKASSA_SECRET_KEY
            
        # Создаем заголовки для авторизации
        auth_string = f"{shop_id}:{secret_key}"
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
                result = await response.json()
                
                if result.get("id"):
                    return {
                        "status": result.get("status"),
                        "payment_id": result.get("id"),
                        "paid": result.get("paid", False),
                        "amount": float(result.get("amount", {}).get("value", 0))
                    }
                else:
                    logger.error(f"Ошибка при проверке статуса платежа: {result}")
                    return None
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса платежа: {e}")
        return None


async def update_order_payment_status(session: AsyncSession, payment_id: str, status: str):
    """
    Обновление статуса платежа заказа в базе данных
    """
    try:
        # Находим заказ по ID платежа
        query = select(Order).where(Order.payment_id == payment_id)
        result = await session.execute(query)
        order = result.scalars().first()
        
        if order:
            # Обновляем статус платежа
            order.payment_status = status
            
            # Если платеж успешен, обновляем статус заказа
            if status == "succeeded":
                order.status = "paid"
            
            await session.commit()
            logger.info(f"Статус платежа заказа #{order.id} обновлен на {status}")
            return True
        else:
            logger.error(f"Заказ с ID платежа {payment_id} не найден")
            return False
    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса платежа заказа: {e}")
        await session.rollback()
        return False


async def get_order_by_payment_id(session: AsyncSession, payment_id: str):
    """
    Получение заказа по ID платежа
    """
    try:
        # Находим заказ по ID платежа
        query = select(Order).where(Order.payment_id == payment_id)
        result = await session.execute(query)
        order = result.scalars().first()
        
        return order
    except Exception as e:
        logger.error(f"Ошибка при получении заказа по ID платежа: {e}")
        return None


async def delete_unpaid_order(session: AsyncSession, payment_id: str):
    """
    Удаление неоплаченного заказа
    """
    try:
        # Находим заказ по ID платежа
        order = await get_order_by_payment_id(session, payment_id)
        
        if not order:
            logger.error(f"Заказ с ID платежа {payment_id} не найден")
            return False
        
        # Удаляем связанные элементы заказа
        delete_items = delete(OrderItem).where(OrderItem.order_id == order.id)
        await session.execute(delete_items)
        
        # Удаляем сам заказ
        delete_order = delete(Order).where(Order.id == order.id)
        await session.execute(delete_order)
        
        await session.commit()
        logger.info(f"Неоплаченный заказ #{order.id} удален")
        return True
    except Exception as e:
        logger.error(f"Ошибка при удалении неоплаченного заказа: {e}")
        await session.rollback()
        return False
