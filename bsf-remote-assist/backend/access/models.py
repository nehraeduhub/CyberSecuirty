from django.conf import settings
from django.db import models
from devices.models import Device

class DeviceGroup(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class TechnicianDevicePermission(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    group = models.ForeignKey(DeviceGroup, null=True, blank=True, on_delete=models.CASCADE)
    device = models.ForeignKey(Device, null=True, blank=True, on_delete=models.CASCADE)
    can_connect = models.BooleanField(default=True)
    can_file_transfer = models.BooleanField(default=False)
    can_terminal = models.BooleanField(default=False)
    can_reboot = models.BooleanField(default=False)
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(group__isnull=False) | models.Q(device__isnull=False), name='permission_has_target')]
        unique_together = [('user','group','device')]
