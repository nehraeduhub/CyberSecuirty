from django.http import JsonResponse
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from access.models import DeviceGroup, TechnicianDevicePermission
from remote_bridge.meshapi import MeshError
from remote_sessions.services import audit, device_permission
from .models import Device
from .services import sync_devices, sync_if_stale

ADMIN_ROLES = ('ADMIN', 'SUPERADMIN')
FIELDS = ('id', 'name', 'hostname', 'ip_address', 'os', 'group', 'online', 'approved', 'removed', 'agent_version', 'last_seen')


def health(request):
    return JsonResponse({'status': 'ok', 'service': 'techguardinas-remote-api'})


def _row(d, user):
    row = {f: getattr(d, f) for f in FIELDS}
    row['id'] = str(d.id)
    caps = device_permission(user, d)
    row['can_connect'] = caps is not None
    row['capabilities'] = {k: v for k, v in (caps or {}).items() if k != 'source'}
    return row


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def device_list(request):
    """Admins see every device (including pending approval). Technicians see only devices they are authorized for."""
    sync_if_stale()
    user = request.user
    if user.role in ADMIN_ROLES:
        qs = Device.objects.all()
    elif user.role == 'AUDITOR':
        qs = Device.objects.filter(approved=True)
    else:
        perms = TechnicianDevicePermission.objects.filter(user=user, can_connect=True)
        qs = Device.objects.filter(approved=True, removed=False).filter(
            Q(id__in=perms.filter(device__isnull=False).values('device_id')) |
            Q(group__in=perms.filter(group__isnull=False, group__active=True).values('group__name')))
    return Response([_row(d, user) for d in qs.order_by('name')])


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync(request):
    if request.user.role not in ADMIN_ROLES:
        return Response({'detail': 'Admin only'}, 403)
    try:
        return Response(sync_devices())
    except MeshError as e:
        return Response({'detail': f'Remote engine error: {e}'}, 502)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def approve_device(request, device_id):
    if request.user.role not in ADMIN_ROLES:
        return Response({'detail': 'Admin only'}, 403)
    try:
        d = Device.objects.get(id=device_id)
    except Device.DoesNotExist:
        return Response({'detail': 'Device not found'}, 404)
    approve = request.data.get('approved', True) is not False
    d.approved = approve
    if request.data.get('unit') is not None:
        d.unit = str(request.data['unit'])[:150]
    d.save(update_fields=['approved', 'unit', 'updated_at'])
    audit(request.user, 'DEVICE_APPROVED' if approve else 'DEVICE_APPROVAL_REVOKED', d, request, name=d.name, group=d.group)
    return Response({'ok': True, 'approved': d.approved})
