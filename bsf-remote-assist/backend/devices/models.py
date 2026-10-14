import uuid
from django.db import models


class Device(models.Model):
    """An endpoint running the official MeshCentral agent in a managed (unattended) device group.
    Records are created by synchronisation with MeshCentral and must be approved by an administrator
    before any technician can be authorized to connect."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    hostname = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    os = models.CharField(max_length=255, blank=True)
    unit = models.CharField(max_length=150, blank=True)
    group = models.CharField(max_length=150, blank=True)  # DeviceGroup.name
    agent_version = models.CharField(max_length=50, blank=True)
    mesh_node_id = models.CharField(max_length=255, blank=True, db_index=True)
    mesh_group_id = models.CharField(max_length=255, blank=True)
    online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(null=True, blank=True)
    approved = models.BooleanField(default=False)
    removed = models.BooleanField(default=False)  # no longer present in MeshCentral
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self): return self.name
