from django.contrib import admin
from .models import RemoteSession, AuditLog


@admin.register(RemoteSession)
class RemoteSessionAdmin(admin.ModelAdmin):
    list_display = ('code', 'technician', 'mode', 'status', 'target_name', 'created_at', 'started_at', 'ended_at', 'ended_by')
    list_filter = ('mode', 'status', 'ended_by')
    search_fields = ('code', 'target_name', 'technician__username', 'customer_name')
    readonly_fields = [f.name for f in RemoteSession._meta.fields]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor', 'action', 'target_type', 'target_id', 'source_ip')
    list_filter = ('action', 'target_type')
    readonly_fields = ('actor', 'action', 'target_type', 'target_id', 'source_ip', 'details', 'created_at')

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
