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
            ticket_numbers = " ".join([f"{t.ticket_number}" for t in tickets])
            html += f"<li><strong>{prize.title}</strong>: Билеты - {ticket_numbers}</li>"
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
    list_display = ('title', 'start_date', 'end_date', 'ticket_price', 'ticket_count', 'is_active', 'tickets_sold')
    search_fields = ('title',)
    list_filter = ('is_active', 'start_date', 'end_date')
    readonly_fields = ('created_at', 'updated_at', 'tickets_sold', 'is_active', 'participants_display')
    inlines = [TicketInline]
    
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
        ('Участники', {
            'fields': ('participants_display', 'tickets_sold')
        }),
        ('Информация', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def tickets_sold(self, obj):
        """Количество проданных билетов."""
        return obj.tickets.filter(is_paid=True).count()
    tickets_sold.short_description = "Продано билетов"
    
    def participants_display(self, obj):
        """Отображение участников розыгрыша с их билетами."""
        participants = obj.get_participants()
        
        if not participants:
            return "Нет участников"
        
        html = "<ul>"
        for participant_data in participants.values():
            user = participant_data['user']
            tickets = participant_data['tickets']
            
            # Используем username, если есть, иначе telegram_id
            if user.username:
                display_name = f"{user.username}"
            else:
                display_name = f"{user.telegram_id}"
            
            # Сортируем билеты для лучшего отображения
            sorted_tickets = sorted(tickets)
            tickets_str = " ".join([str(t) for t in sorted_tickets])
            
            html += f"<li><strong>{display_name}</strong> - {tickets_str}</li>"
        html += "</ul>"
        
        return format_html(html)
    participants_display.short_description = "Участники розыгрыша"
    
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
    list_display = ('__str__', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Основная информация', {
            'fields': ('text', 'is_active')
        }),
        ('Информация', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def has_add_permission(self, request):
        """Проверка разрешения на добавление записи."""
        # Если уже есть запись, запрещаем создание новых
        return not FAQ.objects.exists() 