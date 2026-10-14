import uuid
from django.conf import settings
from django.db import models
from devices.models import Device


class RemoteSession(models.Model):
    MODES = [('ATTENDED', 'Attended'), ('UNATTENDED', 'Unattended')]
    STATUSES = [
        ('WAITING', 'Waiting for remote user'),   # attended: invitation issued
        ('READY', 'Authorized, console available'),
        ('ACTIVE', 'Console in use'),
        ('ENDED', 'Ended'),
        ('EXPIRED', 'Invitation expired'),
        ('DENIED', 'Denied'),
        ('FAILED', 'Failed'),
    ]
    OPEN_STATUSES = ('WAITING', 'READY', 'ACTIVE')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=12, unique=True)
    technician = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    device = models.ForeignKey(Device, null=True, blank=True, on_delete=models.PROTECT)
    mode = models.CharField(max_length=20, choices=MODES)
    status = models.CharField(max_length=20, choices=STATUSES, default='WAITING')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)      # attended invitation expiry
    authorized_at = models.DateTimeField(null=True, blank=True)   # rights granted on the endpoint
    started_at = models.DateTimeField(null=True, blank=True)      # first console opened
    ended_at = models.DateTimeField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)     # hard session limit

    # Authorization record
    mfa_verified = models.BooleanField(default=False)
    capabilities = models.JSONField(default=dict, blank=True)
    authorization = models.JSONField(default=dict, blank=True)

    # Remote user (attended)
    customer_token_hash = models.CharField(max_length=64, blank=True)
    customer_name = models.CharField(max_length=150, blank=True)
    customer_consent_at = models.DateTimeField(null=True, blank=True)
    customer_ip = models.GenericIPAddressField(null=True, blank=True)

    # Target endpoint snapshot (kept even if the device record changes later)
    target_name = models.CharField(max_length=255, blank=True)
    target_os = models.CharField(max_length=255, blank=True)
    target_ip = models.CharField(max_length=64, blank=True)

    # MeshCentral binding
    mesh_group_id = models.CharField(max_length=255, blank=True)  # per-session group (attended)
    mesh_node_id = models.CharField(max_length=255, blank=True)
    mesh_user = models.CharField(max_length=128, blank=True)

    ended_by = models.CharField(max_length=20, blank=True)        # TECHNICIAN / REMOTE_USER / SYSTEM / ADMIN
    end_reason = models.CharField(max_length=255, blank=True)
    outcome = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=100, blank=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
