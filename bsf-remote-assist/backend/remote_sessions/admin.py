from django.contrib import admin
from .models import RemoteSession, AuditLog
@admin.register(RemoteSession)
class RemoteSessionAdmin(admin.ModelAdmin): list_display=('code','technician','device','mode','status','created_at','started_at','ended_at'); list_filter=('mode','status')
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin): list_display=('actor','action','target_type','source_ip','created_at'); list_filter=('action','target_type'); readonly_fields=('actor','action','target_type','target_id','source_ip','details','created_at')
