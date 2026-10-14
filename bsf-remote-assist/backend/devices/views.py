import hashlib, secrets
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from .models import Device
from remote_sessions.models import AuditLog
from access.models import TechnicianDevicePermission

def health(request): return JsonResponse({'status':'ok','service':'bsf-remote-api','stage':'4'})

def admin_only(user): return user.is_authenticated and user.role in ('ADMIN','SUPERADMIN')

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def device_list(request):
    qs=Device.objects.filter(approved=True).order_by('name')
    if request.user.role not in ('ADMIN','SUPERADMIN'):
        perms=TechnicianDevicePermission.objects.filter(user=request.user, can_connect=True)
        from django.db.models import Q
        device_ids=perms.filter(device__isnull=False).values_list('device_id', flat=True)
        group_names=perms.filter(group__isnull=False, group__active=True).values_list('group__name', flat=True)
        qs=qs.filter(Q(id__in=device_ids) | Q(group__in=group_names))
    return Response(list(qs.values('id','name','hostname','ip_address','os','unit','group','online','approved','agent_enrolled','agent_version','last_seen','mesh_node_id')))

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def enroll_device(request):
    if not admin_only(request.user): return Response({'detail':'Admin only'},403)
    token=secrets.token_urlsafe(32); h=hashlib.sha256(token.encode()).hexdigest()
    d=Device.objects.create(name=request.data.get('name') or request.data.get('hostname') or 'New Device',hostname=request.data.get('hostname',''),unit=request.data.get('unit',''),group=request.data.get('group',''),enrollment_token_hash=h)
    AuditLog.objects.create(actor=request.user,action='DEVICE_ENROLLMENT_CREATED',target_type='DEVICE',target_id=str(d.id),details={'hostname':d.hostname})
    return Response({'device_id':str(d.id),'enrollment_token':token,'warning':'Store this token securely; it is shown once.'},201)

@api_view(['POST'])
@permission_classes([AllowAny])
def heartbeat(request):
    device_id=request.data.get('device_id'); token=request.data.get('token')
    try: d=Device.objects.get(id=device_id)
    except Device.DoesNotExist: return Response({'detail':'Unknown device'},404)
    token_hash = hashlib.sha256(token.encode()).hexdigest() if token else ''
    if token_hash == d.enrollment_token_hash and token_hash:
        # Convert the one-time bootstrap credential into the long-lived device credential.
        d.agent_token_hash = token_hash
        d.enrollment_token_hash = ''
        d.agent_enrolled = True
    elif token_hash != d.agent_token_hash:
        return Response({'detail':'Invalid token'},401)
    d.online=True; d.agent_enrolled=True; d.last_seen=timezone.now(); d.hostname=request.data.get('hostname',d.hostname); d.ip_address=request.data.get('ip_address',d.ip_address); d.agent_last_ip=request.data.get('ip_address',d.agent_last_ip); d.os=request.data.get('os',d.os); d.agent_version=request.data.get('agent_version',d.agent_version); d.save()
    return Response({'ok':True,'approved':d.approved,'device_id':str(d.id),'next_heartbeat_seconds':30})

@api_view(['POST'])
@permission_classes([AllowAny])
def offline(request):
    device_id=request.data.get('device_id'); token=request.data.get('token')
    try: d=Device.objects.get(id=device_id)
    except Device.DoesNotExist: return Response({'detail':'Unknown device'},404)
    if not token or hashlib.sha256(token.encode()).hexdigest()!=d.agent_token_hash: return Response({'detail':'Invalid token'},401)
    d.online=False; d.last_seen=timezone.now(); d.save(update_fields=['online','last_seen','updated_at'])
    return Response({'ok':True})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def approve_device(request, device_id):
    if not admin_only(request.user): return Response({'detail':'Admin only'},403)
    try: d=Device.objects.get(id=device_id)
    except Device.DoesNotExist: return Response({'detail':'Device not found'},404)
    d.approved=True; d.save(update_fields=['approved','updated_at'])
    AuditLog.objects.create(actor=request.user,action='DEVICE_APPROVED',target_type='DEVICE',target_id=str(d.id),details={'name':d.name})
    return Response({'ok':True})
