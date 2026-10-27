from django.contrib.auth.models import AbstractUser
from django.db import models
class PortalUser(AbstractUser):
    class Role(models.TextChoices):
        SUPERADMIN='SUPERADMIN','Super Admin'; ADMIN='ADMIN','Admin'; TECHNICIAN='TECHNICIAN','Technician'; AUDITOR='AUDITOR','Auditor'
    role=models.CharField(max_length=20,choices=Role.choices,default=Role.TECHNICIAN)
    ad_username=models.CharField(max_length=150,blank=True,unique=True,null=True)
    auth_source=models.CharField(max_length=10, choices=[('LOCAL','Local'),('AD','Active Directory')], default='LOCAL')
    ad_dn=models.CharField(max_length=500,blank=True)
    portal_enabled=models.BooleanField(default=False)
    created_by=models.ForeignKey('self',null=True,blank=True,on_delete=models.SET_NULL,related_name='provisioned_users')
    last_login_ip=models.GenericIPAddressField(null=True,blank=True)
    def __str__(self): return self.username


class DirectoryProvider(models.Model):
    name=models.CharField(max_length=120, unique=True, default='Active Directory')
    enabled=models.BooleanField(default=False)
    server_uri=models.CharField(max_length=500, blank=True)
    bind_dn=models.CharField(max_length=500, blank=True)
    bind_password_enc=models.TextField(blank=True)
    user_base_dn=models.CharField(max_length=500, blank=True)
    group_dn=models.CharField(max_length=500, blank=True)
    verify_ssl=models.BooleanField(default=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    def __str__(self): return self.name
