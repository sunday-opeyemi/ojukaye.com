from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core import views

urlpatterns = [
    # Custom admin URLs
    path('admin/quick-fetch/', views.quick_fetch_news, name='quick_fetch_news'),
    path('admin/fetcher/status/', views.get_fetcher_status, name='get_fetcher_status'),
    path('admin/fetcher/save-settings/', views.save_fetcher_settings, name='save_fetcher_settings'),
    path('admin/fetcher/toggle/', views.toggle_auto_fetcher, name='toggle_auto_fetcher'),
    path('admin/fetcher/trigger/', views.trigger_manual_fetch, name='trigger_manual_fetch'),
    path('admin/fetcher/logs/', views.get_fetch_logs, name='get_fetch_logs'),
    path('admin/fetcher/logs/clear/', views.clear_fetch_logs, name='clear_fetch_logs'),
    path('admin/fetcher/schedule/', views.get_fetch_schedule, name='get_fetch_schedule'),
    path('admin/fetcher/schedule/add/', views.add_scheduled_fetch, name='add_scheduled_fetch'),
    path('admin/fetcher/schedule/clear/', views.clear_fetch_schedule, name='clear_fetch_schedule'),
    path('admin/fetcher/statistics/', views.get_fetch_statistics, name='get_fetch_statistics'),
    
    # Default admin
    path('admin/', admin.site.urls),
    
    # Your app URLs
    path('', include('core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)