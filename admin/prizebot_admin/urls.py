from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.views.static import serve

# Настройка админки
admin.site.site_header = 'Админ-панель PrizeBot'
admin.site.site_title = 'PrizeBot'
admin.site.index_title = 'Управление розыгрышами'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('prizes/', include('prizes.urls')),
    path('', RedirectView.as_view(url='admin/', permanent=True)),
    
    # Обслуживание медиа-файлов в любом режиме (DEBUG=True или DEBUG=False)
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

# Добавляем обслуживание статических файлов в режиме разработки
# В продакшене статические файлы будет обслуживать WhiteNoise
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) 