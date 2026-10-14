from django.urls import path
from . import views

urlpatterns = [
    path('sessions/', views.sessions),
    path('sessions/attended/', views.create_attended),
    path('sessions/unattended/', views.create_unattended),
    path('sessions/<uuid:session_id>/', views.session_detail),
    path('sessions/<uuid:session_id>/console/', views.console),
    path('sessions/<uuid:session_id>/chat/', views.chat),
    path('sessions/<uuid:session_id>/reboot/', views.reboot),
    path('sessions/<uuid:session_id>/end/', views.end),
    path('audit/', views.audit_log),
    path('join/', views.join),
    path('join/<str:token>/status/', views.join_status),
    path('join/<str:token>/consent/', views.join_consent),
    path('join/<str:token>/agent/<str:platform>/', views.join_agent),
    path('join/<str:token>/end/', views.join_end),
]
