import uuid
from django.db import models

class Device(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    name=models.CharField(max_length=255)
    hostname=models.CharField(max_length=255,blank=True)
    ip_address=models.GenericIPAddressField(null=True,blank=True)
    os=models.CharField(max_length=100,blank=True)
    unit=models.CharField(max_length=150,blank=True)
    group=models.CharField(max_length=150,blank=True)
    agent_version=models.CharField(max_length=50,blank=True)
    agent_token_hash=models.CharField(max_length=128,blank=True)
    enrollment_token_hash=models.CharField(max_length=128,blank=True)
    agent_enrolled=models.BooleanField(default=False)
    agent_last_ip=models.GenericIPAddressField(null=True,blank=True)
    mesh_node_id=models.CharField(max_length=255,blank=True)
    mesh_group_id=models.CharField(max_length=255,blank=True)
    online=models.BooleanField(default=False)
    last_seen=models.DateTimeField(null=True,blank=True)
    approved=models.BooleanField(default=False)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
