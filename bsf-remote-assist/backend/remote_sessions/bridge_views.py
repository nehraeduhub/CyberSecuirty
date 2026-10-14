from django.conf import settings
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import RemoteSession, AuditLog
from devices.models import Device
from access.models import TechnicianDevicePermission
from remote_bridge.meshctrl import run_command, power, MeshCtrlError
from security.views import consume_stepup

def allowed(user, device, action='can_connect'):
    if user.role in ('ADMIN','SUPERADMIN'): return True
    qs=TechnicianDevicePermission.objects.filter(user=user, **{action:True})
    return qs.filter(device=device).exists() or qs.filter(group__name=device.group, group__active=True).exists()

def get_session(request, sid):
    try: return RemoteSession.objects.select_related('device').get(id=sid, technician=request.user)
    except RemoteSession.DoesNotExist: return None

def guard(s, user, action):
    if not s or not s.device: return 'Session/device not found'
    if s.status != 'ACTIVE': return 'Session is not active'
    if not s.device.approved: return 'Device not approved'
    field={'terminal':'can_terminal','reboot':'can_reboot'}.get(action)
    if field and not allowed(user,s.device,field): return f'{action} permission denied'
    return None

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def execute(request, session_id):
    s=get_session(request, session_id)
    action=request.data.get('action')
    err=guard(s,request.user,action)
    if err:return Response({'detail':err},403 if 'denied' in err or 'approved' in err else 409)
    try:
        if action=='terminal':
            command=str(request.data.get('command','')).strip()
            if not command or len(command)>4096:return Response({'detail':'A command (max 4096 chars) is required'},400)
            result=run_command(s.device.mesh_node_id,command,2,0)
        elif action=='reboot':
            result=power(s.device.mesh_node_id,3)
        else:
            return Response({'detail':'Use the MeshCentral console for interactive file transfer.'},400)
    except MeshCtrlError as e:
        return Response({'detail':str(e)},502)
    AuditLog.objects.create(actor=request.user,action='MESH_ACTION',target_type='Device',target_id=str(s.device.id),source_ip=request.META.get('REMOTE_ADDR'),details={'session_id':str(s.id),'action':action,'mesh_node_id':s.device.mesh_node_id})
    return Response({'ok':True,'action':action,'result':result})
