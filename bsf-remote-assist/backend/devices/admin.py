from django.contrib import admin
from .models import Device
@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display=('name','hostname','ip_address','unit','group','online','approved','last_seen')
    list_filter=('online','approved','unit','group')
    search_fields=('name','hostname','ip_address')
