from django.contrib import admin
from .models import DeviceGroup, TechnicianDevicePermission


@admin.register(DeviceGroup)
class DeviceGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'active', 'auto_approve', 'record_sessions', 'mesh_group_id')


@admin.register(TechnicianDevicePermission)
class TechnicianDevicePermissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'group', 'device', 'can_connect', 'can_file_transfer', 'can_terminal', 'can_reboot')
