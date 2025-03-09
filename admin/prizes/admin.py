from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.contrib import messages
from django.http import HttpResponseRedirect
from .models import TelegramUser, Prize, Ticket, Payment, FAQ
from django.core.exceptions import ValidationError
from django.utils import timezone


class TicketInline(admin.TabularInline):
    model = Ticket
    extra = 0
    readonly_fields = ('created_at', 'updated_at')
    fields = ('ticket_number', 'user', 'is_reserved', 'is_paid', 'reserved_until')
    

class UserTicketsInline(admin.TabularInline):
    model = Ticket
    extra = 0
    readonly_fields = ('prize', 'ticket_number', 'reserved_until', 'remove_user_button')
    fields = ('prize', 'ticket_number', 'is_reserved', 'is_paid', 'reserved_until', 'remove_user_button')
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False
    
    def has_change_permission(self, request, obj=None):
        return True
    
    def remove_user_button(self, obj):
        """Кнопка для удаления пользователя из билета."""
        if obj.pk and obj.user:
            url = reverse('admin:remove-user-from-ticket', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" onclick="return confirm(\'Вы уверены, что хотите удалить пользователя из билета?\');">Забрать билет</a>',
                url
            )
        return "Билет не привязан к пользователю"
    remove_user_button.short_description = "Действия"


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ('telegram_id', 'full_name', 'username', 'is_admin', 'tickets_count', 'created_at')
    search_fields = ('telegram_id', 'full_name', 'username')
    list_filter = ('is_admin', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at', 'active_prizes_display')
    inlines = [UserTicketsInline]
    
    def tickets_count(self, obj):
        """Получить количество билетов пользователя."""
        return obj.tickets.filter(is_paid=True).count()
    tickets_count.short_description = "Количество билетов"
    
    def active_prizes_display(self, obj):
        """Отображение активных розыгрышей пользователя."""
        prizes = obj.get_active_prizes()
        if not prizes:
            return "Нет активных розыгрышей"
        
        html = "<ul>"
        for prize in prizes:
            tickets = obj.get_tickets_for_prize(prize)
            ticket_numbers = ", ".join([f"#{t.ticket_number}" for t in tickets])
            html += f"<li><strong>{prize.title}</strong>: Билеты {ticket_numbers}</li>"
        html += "</ul>"
        return format_html(html)
    active_prizes_display.short_description = "Активные розыгрыши"
    
    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                'ticket/<int:ticket_id>/remove-user/',
                self.admin_site.admin_view(self.remove_user_from_ticket_view),
                name='remove-user-from-ticket',
            ),
        ]
        return custom_urls + urls
    
    def remove_user_from_ticket_view(self, request, ticket_id):
        """Представление для удаления пользователя из билета."""
        ticket = Ticket.objects.get(pk=ticket_id)
        user_id = ticket.user.pk if ticket.user else None
        
        if ticket.user:
            # Сохраняем информацию о пользователе для сообщения
            user_full_name = ticket.user.full_name
            
            # Удаляем пользователя из билета
            ticket.user = None
            ticket.is_reserved = False
            ticket.is_paid = False
            ticket.reserved_until = None
            ticket.save()
            
            self.message_user(
                request, 
                f"Пользователь {user_full_name} удален из билета #{ticket.ticket_number} розыгрыша '{ticket.prize.title}'",
                level=messages.SUCCESS
            )
        else:
            self.message_user(
                request, 
                f"Билет #{ticket.ticket_number} не привязан к пользователю",
                level=messages.WARNING
            )
        
        # Перенаправляем обратно на страницу пользователя
        if user_id:
            return HttpResponseRedirect(reverse('admin:prizes_telegramuser_change', args=[user_id]))
        else:
            return HttpResponseRedirect(reverse('admin:prizes_ticket_changelist'))


@admin.register(Prize)
class PrizeAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_date', 'end_date', 'ticket_price', 'ticket_count', 'is_active', 'winner_display', 'tickets_sold')
    search_fields = ('title',)
    list_filter = ('is_active', 'start_date', 'end_date', 'winner_determined')
    readonly_fields = ('created_at', 'updated_at', 'winner', 'winning_ticket', 'winner_determined', 'determine_winner_button', 'tickets_sold')
    inlines = [TicketInline]
    actions = ['determine_winner_action']
    
    fieldsets = (
        (None, {
            'fields': ('title', 'image')
        }),
        ('Даты', {
            'fields': ('start_date', 'end_date')
        }),
        ('Настройки', {
            'fields': ('ticket_price', 'ticket_count', 'is_active')
        }),
        ('Результаты', {
            'fields': ('winner', 'winning_ticket', 'winner_determined', 'determine_winner_button', 'tickets_sold')
        }),
        ('Информация', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def winner_display(self, obj):
        """Отображение победителя."""
        if obj.winner:
            # Если есть username, используем его
            if obj.winner.username:
                display_name = obj.winner.username
            else:
                # Иначе формируем команду /chat<user_id>
                display_name = f"/chat{obj.winner.telegram_id} (отправьте боту для получения ссылки)"
            
            return f"{display_name} (Билет #{obj.winning_ticket})"
        return "Не определен"
    winner_display.short_description = "Победитель"
    
    def tickets_sold(self, obj):
        """Количество проданных билетов."""
        return obj.tickets.filter(is_paid=True).count()
    tickets_sold.short_description = "Продано билетов"
    
    def determine_winner_action(self, request, queryset):
        """Действие для определения победителя."""
        for prize in queryset:
            try:
                if prize.winner_determined:
                    # Если есть username, используем его
                    if prize.winner.username:
                        display_name = prize.winner.username
                    else:
                        # Иначе формируем команду /chat<user_id>
                        display_name = f"/chat{prize.winner.telegram_id} (отправьте боту для получения ссылки)"
                    
                    self.message_user(
                        request, 
                        f"Победитель для розыгрыша '{prize.title}' уже определен: {display_name} (Билет #{prize.winning_ticket})",
                        level=messages.WARNING
                    )
                    continue
                
                # Проверяем наличие оплаченных билетов
                paid_tickets = prize.tickets.filter(is_paid=True)
                if not paid_tickets.exists():
                    self.message_user(
                        request, 
                        f"Не удалось определить победителя для розыгрыша '{prize.title}'. Нет оплаченных билетов.",
                        level=messages.ERROR
                    )
                    continue
                
                # Определяем победителя
                winner, winning_ticket = prize.determine_winner()
                
                if winner:
                    # Если есть username, используем его
                    if winner.username:
                        display_name = winner.username
                    else:
                        # Иначе формируем команду /chat<user_id>
                        display_name = f"/chat{winner.telegram_id} (отправьте боту для получения ссылки)"
                    
                    self.message_user(
                        request, 
                        f"Победитель для розыгрыша '{prize.title}' определен: {display_name} (Билет #{winning_ticket})",
                        level=messages.SUCCESS
                    )
                else:
                    self.message_user(
                        request, 
                        f"Не удалось определить победителя для розыгрыша '{prize.title}'. Произошла ошибка.",
                        level=messages.ERROR
                    )
            except ValidationError as e:
                self.message_user(
                    request, 
                    f"Ошибка валидации при определении победителя для розыгрыша '{prize.title}': {e}",
                    level=messages.ERROR
                )
            except Exception as e:
                self.message_user(
                    request, 
                    f"Ошибка при определении победителя для розыгрыша '{prize.title}': {e}",
                    level=messages.ERROR
                )
    determine_winner_action.short_description = "Определить победителя"
    
    def determine_winner_button(self, obj):
        """Кнопка для определения победителя внутри формы редактирования."""
        if obj.pk and not obj.winner_determined:
            url = reverse('admin:determine-winner', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}">Определить победителя</a>',
                url
            )
        elif obj.winner_determined:
            # Если есть победитель
            if obj.winner:
                # Если есть username, используем его
                if obj.winner.username:
                    display_name = obj.winner.username
                else:
                    # Иначе формируем команду /chat<user_id>
                    display_name = f"/chat{obj.winner.telegram_id} (отправьте боту для получения ссылки)"
                
                return format_html(
                    '<div style="color: green;">Победитель определен: {} (Билет #{})</div>',
                    display_name,
                    obj.winning_ticket
                )
            else:
                return format_html(
                    '<div style="color: green;">Победитель определен, но информация о нем отсутствует</div>'
                )
        return "Сохраните розыгрыш перед определением победителя"
    determine_winner_button.short_description = "Определение победителя"
    
    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:prize_id>/determine-winner/',
                self.admin_site.admin_view(self.determine_winner_view),
                name='determine-winner',
            ),
        ]
        return custom_urls + urls
    
    def determine_winner_view(self, request, prize_id):
        """Представление для определения победителя."""
        prize = self.get_object(request, prize_id)
        
        if prize.winner_determined:
            # Если есть username, используем его
            if prize.winner.username:
                display_name = prize.winner.username
            else:
                # Иначе формируем команду /chat<user_id>
                display_name = f"/chat{prize.winner.telegram_id} (отправьте боту для получения ссылки)"
            
            self.message_user(
                request, 
                f"Победитель для розыгрыша '{prize.title}' уже определен: {display_name} (Билет #{prize.winning_ticket})",
                level=messages.WARNING
            )
            return HttpResponseRedirect(reverse('admin:prizes_prize_change', args=[prize_id]))
        
        # Проверяем наличие оплаченных билетов
        paid_tickets = prize.tickets.filter(is_paid=True)
        if not paid_tickets.exists():
            self.message_user(
                request, 
                f"Не удалось определить победителя для розыгрыша '{prize.title}'. Нет оплаченных билетов.",
                level=messages.ERROR
            )
            return HttpResponseRedirect(reverse('admin:prizes_prize_change', args=[prize_id]))
        
        try:
            # Определяем победителя
            winner, winning_ticket = prize.determine_winner()
            
            if winner:
                # Если есть username, используем его
                if winner.username:
                    display_name = winner.username
                else:
                    # Иначе формируем команду /chat<user_id>
                    display_name = f"/chat{winner.telegram_id} (отправьте боту для получения ссылки)"
                
                self.message_user(
                    request, 
                    f"Победитель для розыгрыша '{prize.title}' определен: {display_name} (Билет #{winning_ticket})",
                    level=messages.SUCCESS
                )
            else:
                self.message_user(
                    request, 
                    f"Не удалось определить победителя для розыгрыша '{prize.title}'. Произошла ошибка.",
                    level=messages.ERROR
                )
        except ValidationError as e:
            self.message_user(
                request, 
                f"Ошибка валидации при определении победителя для розыгрыша '{prize.title}': {e}",
                level=messages.ERROR
            )
        except Exception as e:
            self.message_user(
                request, 
                f"Ошибка при определении победителя для розыгрыша '{prize.title}': {e}",
                level=messages.ERROR
            )
        
        return HttpResponseRedirect(reverse('admin:prizes_prize_change', args=[prize_id]))
    
    def save_model(self, request, obj, form, change):
        """Переопределение метода сохранения для обработки активации розыгрыша."""
        # Если розыгрыш активируется, деактивируем все остальные
        if obj.is_active:
            Prize.objects.exclude(pk=obj.pk).update(is_active=False)
        super().save_model(request, obj, form, change)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_number', 'prize', 'user', 'is_reserved', 'is_paid', 'reserved_until')
    search_fields = ('ticket_number', 'prize__title', 'user__full_name', 'user__telegram_id')
    list_filter = ('is_reserved', 'is_paid', 'prize', 'prize__is_active')
    readonly_fields = ('created_at', 'updated_at', 'payment_id')
    list_select_related = ('prize', 'user')
    
    def get_queryset(self, request):
        """Оптимизация запросов."""
        queryset = super().get_queryset(request)
        return queryset.select_related('prize', 'user')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('payment_id', 'user', 'prize', 'amount', 'is_successful', 'created_at', 'get_tickets_display')
    search_fields = ('payment_id', 'user__full_name', 'user__telegram_id', 'prize__title')
    list_filter = ('is_successful', 'created_at', 'prize')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('tickets',)
    
    def get_tickets_display(self, obj):
        """Отображение билетов в оплате."""
        tickets = obj.tickets.all()
        if tickets:
            return format_html(", ".join([f"#{t.ticket_number}" for t in tickets]))
        return "Нет билетов"
    get_tickets_display.short_description = "Билеты"


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ('question', 'is_active', 'order', 'created_at')
    search_fields = ('question', 'answer')
    list_filter = ('is_active', 'created_at')
    readonly_fields = ('created_at', 'updated_at')
    list_editable = ('is_active', 'order')
    fieldsets = (
        ('Основная информация', {
            'fields': ('question', 'answer', 'is_active', 'order')
        }),
        ('Информация', {
            'fields': ('created_at', 'updated_at')
        }),
    ) 