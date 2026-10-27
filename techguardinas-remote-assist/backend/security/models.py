from django.conf import settings
from django.db import models
import uuid

class MFAMethod(models.Model):
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='mfa')
    secret=models.CharField(max_length=64)
    enabled=models.BooleanField(default=False)
    verified_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

class StepUpGrant(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    purpose=models.CharField(max_length=64)
    expires_at=models.DateTimeField()
    used=models.BooleanField(default=False)
    created_at=models.DateTimeField(auto_now_add=True)
