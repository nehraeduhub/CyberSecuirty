from django.urls import path
from . import views
urlpatterns=[path('devices/',views.device_list),path('devices/enroll/',views.enroll_device),path('devices/heartbeat/',views.heartbeat),path('devices/offline/',views.offline),path('devices/<uuid:device_id>/approve/',views.approve_device)]
