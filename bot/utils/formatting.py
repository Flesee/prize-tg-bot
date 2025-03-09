from typing import Union


def format_price(price: Union[float, int, str]) -> str:
    """
    Форматирует цену в красивый вид.
    """
    try:
        price_float = float(price)
        
        # Проверяем, есть ли копейки
        if price_float == int(price_float):
            # Если копеек нет, выводим целое число
            return f"{int(price_float):,} ₽".replace(",", " ")
        else:
            return f"{price_float:,.2f} ₽".replace(",", " ").replace(".", ",")
    except (ValueError, TypeError):
        return f"{price} ₽"


def format_ticket_numbers(ticket_numbers: list[int]) -> str:
    """
    Форматирует список номеров билетов в красивый вид.
    """
    if not ticket_numbers:
        return ""
    
    # Сортируем номера билетов
    sorted_numbers = sorted(ticket_numbers)
    
    # Преобразуем все номера в строки и соединяем пробелами
    return " ".join(str(num) for num in sorted_numbers)