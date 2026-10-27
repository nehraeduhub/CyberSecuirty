from django.contrib import admin
from .models import Device


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('name', 'hostname', 'ip_address', 'group', 'online', 'approved', 'removed', 'last_seen')
    list_filter = ('online', 'approved', 'removed', 'group')
    search_fields = ('name', 'hostname', 'ip_address', 'mesh_node_id')
