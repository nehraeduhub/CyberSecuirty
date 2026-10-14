import uuid
from django.conf import settings
from django.db import models
from devices.models import Device
class RemoteSession(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    code=models.CharField(max_length=12,unique=True)
    technician=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    device=models.ForeignKey(Device,null=True,blank=True,on_delete=models.PROTECT)
    mode=models.CharField(max_length=20,choices=[('ATTENDED','Attended'),('UNATTENDED','Unattended')])
    status=models.CharField(max_length=20,choices=[('PENDING','Pending'),('ACTIVE','Active'),('ENDED','Ended'),('DENIED','Denied')],default='PENDING')
    started_at=models.DateTimeField(null=True,blank=True); ended_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    mesh_launch_url=models.URLField(blank=True)
    metadata=models.JSONField(default=dict, blank=True)
class AuditLog(models.Model):
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL)
    action=models.CharField(max_length=100); target_type=models.CharField(max_length=100,blank=True); target_id=models.CharField(max_length=100,blank=True)
    source_ip=models.GenericIPAddressField(null=True,blank=True); details=models.JSONField(default=dict); created_at=models.DateTimeField(auto_now_add=True)
