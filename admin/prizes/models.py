from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError


class TelegramUser(models.Model):
    """Модель пользователя Telegram."""
    telegram_id = models.BigIntegerField(unique=True, verbose_name="Telegram ID")
    full_name = models.CharField(max_length=255, verbose_name="Полное имя")
    username = models.CharField(max_length=255, blank=True, null=True, verbose_name="Имя пользователя")
    is_admin = models.BooleanField(default=False, verbose_name="Администратор")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Пользователь Telegram"
        verbose_name_plural = "Пользователи Telegram"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.full_name} ({self.telegram_id})"
    
    def get_active_prizes(self):
        """Получить активные розыгрыши пользователя."""
        return Prize.objects.filter(tickets__user=self, tickets__is_paid=True).distinct()
    
    def get_tickets_for_prize(self, prize):
        """Получить билеты пользователя для конкретного розыгрыша."""
        return self.tickets.filter(prize=prize, is_paid=True)


class Prize(models.Model):
    """Модель розыгрыша."""
    title = models.CharField(max_length=255, verbose_name="Название приза")
    image = models.ImageField(upload_to='prizes/', blank=True, null=True, verbose_name="Изображение")
    start_date = models.DateTimeField(verbose_name="Дата начала розыгрыша")
    end_date = models.DateTimeField(verbose_name="Дата окончания розыгрыша")
    ticket_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Стоимость билета")
    ticket_count = models.PositiveIntegerField(default=0, verbose_name="Количество билетов")
    is_active = models.BooleanField(default=False, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    chat_message_id = models.BigIntegerField(blank=True, null=True, verbose_name="ID сообщения в чате")

    class Meta:
        verbose_name = "Розыгрыш"
        verbose_name_plural = "Розыгрыши"
        ordering = ['-is_active', '-start_date']

    def __str__(self):
        return self.title

    def clean(self):
        """Проверка на то, что только один розыгрыш может быть активным."""
        if self.is_active:
            active_prizes = Prize.objects.filter(is_active=True).exclude(pk=self.pk)
            if active_prizes.exists():
                raise ValidationError("Может быть активен только один розыгрыш.")
        
        # Проверка, что дата окончания позже даты начала
        if self.end_date and self.start_date and self.end_date <= self.start_date:
            raise ValidationError("Дата окончания должна быть позже даты начала.")
        
        # Проверка, что дата окончания не меньше текущего времени
        if self.end_date and self.end_date <= timezone.now():
            raise ValidationError("Дата окончания должна быть в будущем.")
        
        # Проверка, что стоимость билета не отрицательная
        if self.ticket_price is not None and self.ticket_price < 0:
            raise ValidationError("Стоимость билета не может быть отрицательной.")
        
        # Проверка, что количество билетов положительное
        if self.ticket_count is not None and self.ticket_count <= 0:
            raise ValidationError("Количество билетов должно быть положительным.")
            
        # Проверка на пересечение времени с другими розыгрышами
        overlapping_prizes = Prize.objects.exclude(pk=self.pk).filter(
            models.Q(start_date__lte=self.start_date, end_date__gte=self.start_date) |  # Начало нового розыгрыша внутри существующего
            models.Q(start_date__lte=self.end_date, end_date__gte=self.end_date) |      # Конец нового розыгрыша внутри существующего
            models.Q(start_date__gte=self.start_date, end_date__lte=self.end_date)      # Существующий розыгрыш внутри нового
        )
        
        if overlapping_prizes.exists():
            overlapping_prize = overlapping_prizes.first()
            
            # Явно преобразуем время в московское
            start_date_moscow = timezone.localtime(overlapping_prize.start_date)
            end_date_moscow = timezone.localtime(overlapping_prize.end_date)
            
            raise ValidationError(
                f"Время розыгрыша пересекается с существующим розыгрышем '{overlapping_prize.title}' "
                f"({start_date_moscow.strftime('%d.%m.%Y %H:%M')} - {end_date_moscow.strftime('%d.%m.%Y %H:%M')})"
            )
    
    def save(self, *args, **kwargs):
        """Переопределение метода сохранения для создания билетов."""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Если это новый розыгрыш и указано количество билетов, создаем билеты
        if is_new and self.ticket_count > 0:
            self.create_tickets(self.ticket_count)
    
    def create_tickets(self, count):
        """Создание указанного количества билетов."""
        if count <= 0:
            return []
        
        tickets = []
        for i in range(1, count + 1):
            ticket = Ticket(
                prize=self,
                ticket_number=i,
                is_reserved=False,
                is_paid=False
            )
            tickets.append(ticket)
        
        # Сохраняем все билеты одним запросом
        Ticket.objects.bulk_create(tickets)
        return tickets
        
    def get_participants(self):
        """Получить список участников розыгрыша с их билетами."""
        participants = {}
        
        # Получаем все оплаченные билеты для этого розыгрыша
        tickets = Ticket.objects.filter(prize=self, is_paid=True).select_related('user')
        
        for ticket in tickets:
            if ticket.user:
                user_id = ticket.user.pk
                if user_id not in participants:
                    participants[user_id] = {
                        'user': ticket.user,
                        'tickets': []
                    }
                participants[user_id]['tickets'].append(ticket.ticket_number)
        
        return participants


class Ticket(models.Model):
    """Модель билета."""
    prize = models.ForeignKey(Prize, on_delete=models.CASCADE, related_name="tickets", verbose_name="Розыгрыш")
    user = models.ForeignKey(TelegramUser, on_delete=models.CASCADE, related_name="tickets", verbose_name="Пользователь", blank=True, null=True)
    ticket_number = models.PositiveIntegerField(verbose_name="Номер билета")
    is_reserved = models.BooleanField(default=False, verbose_name="Зарезервирован")
    is_paid = models.BooleanField(default=False, verbose_name="Оплачен")
    reserved_until = models.DateTimeField(blank=True, null=True, verbose_name="Зарезервирован до")
    payment_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="ID платежа")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Билет"
        verbose_name_plural = "Билеты"
        ordering = ['-prize__is_active', '-prize__start_date', 'ticket_number']
        unique_together = ['prize', 'ticket_number']

    def __str__(self):
        prize_title = self.prize.title if self.prize else "Неизвестный розыгрыш"
        return f"Билет {self.ticket_number} - {prize_title}"

    def save(self, *args, **kwargs):
        """Проверка срока резервации."""
        if self.is_reserved and not self.is_paid:
            if not self.reserved_until:
                # Устанавливаем срок резервации на 15 минут от текущего времени
                self.reserved_until = timezone.now() + timezone.timedelta(minutes=15)
            elif timezone.now() > self.reserved_until:
                # Если срок резервации истек, снимаем резервацию
                self.is_reserved = False
                self.reserved_until = None
        
        # Если билет оплачен, снимаем ограничение по времени резервации
        if self.is_paid:
            self.is_reserved = False
            self.reserved_until = None
            
        super().save(*args, **kwargs)


class Payment(models.Model):
    """Модель оплаты."""
    user = models.ForeignKey(TelegramUser, on_delete=models.CASCADE, related_name="payments", verbose_name="Пользователь")
    prize = models.ForeignKey(Prize, on_delete=models.CASCADE, related_name="payments", verbose_name="Розыгрыш")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сумма")
    tickets = models.ManyToManyField(Ticket, related_name="payment", verbose_name="Билеты")
    payment_id = models.CharField(max_length=255, unique=True, verbose_name="ID платежа")
    is_successful = models.BooleanField(default=False, verbose_name="Успешная оплата")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Оплата"
        verbose_name_plural = "Оплаты"
        ordering = ['-created_at']

    def __str__(self):
        return f"Оплата {self.payment_id} - {self.user.full_name}"

    def mark_as_paid(self):
        """Отметить оплату как успешную и обновить статус билетов."""
        self.is_successful = True
        self.save()
        
        # Обновляем статус всех билетов
        for ticket in self.tickets.all():
            ticket.is_paid = True
            ticket.save()


class FAQ(models.Model):
    """Модель для хранения единого текста FAQ."""
    text = models.TextField(verbose_name="Текст FAQ")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "FAQ"
        verbose_name_plural = "FAQ"

    def __str__(self):
        return "Текст FAQ"
    
    def save(self, *args, **kwargs):
        """Переопределение метода сохранения для обеспечения единственности записи."""
        # Если это новая запись и уже есть активная запись, деактивируем все остальные
        if self.is_active:
            FAQ.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs) 