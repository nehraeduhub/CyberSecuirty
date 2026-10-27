from django.urls import path
from . import views

urlpatterns = [
    path('devices/', views.device_list),
    path('devices/sync/', views.sync),
    path('devices/<uuid:device_id>/approve/', views.approve_device),
]
