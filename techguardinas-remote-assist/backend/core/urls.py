from django.contrib import admin
from django.urls import path, include
from devices.views import health

urlpatterns = [
    path('api/admin/', admin.site.urls),
    path('api/health/', health),
    path('api/security/', include('security.urls')),
    path('api/', include('accounts.urls')),
    path('api/', include('devices.urls')),
    path('api/', include('remote_sessions.urls')),
    path('api/access/', include('access.urls')),
]
