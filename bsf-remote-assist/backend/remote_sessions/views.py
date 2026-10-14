import secrets
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import RemoteSession, AuditLog
from devices.models import Device
from access.models import TechnicianDevicePermission
from django.conf import settings
from security.views import consume_stepup
from remote_bridge.mesh_sso import ensure_mesh_user, create_login_token, MeshSSOError

def allowed(user,device,action='can_connect'):
    if user.role in ('ADMIN','SUPERADMIN'): return True
    qs=TechnicianDevicePermission.objects.filter(user=user,**{action:True})
    return qs.filter(device=device).exists() or qs.filter(group__name=device.group, group__active=True).exists()

def _session_or_404(request, session_id):
    try:
        return RemoteSession.objects.get(id=session_id, technician=request.user)
    except RemoteSession.DoesNotExist:
        return None

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_session(request):
    mode=request.data.get('mode','ATTENDED'); device_id=request.data.get('device_id'); device=None
    if mode not in ('ATTENDED','UNATTENDED'): return Response({'detail':'Invalid mode'},400)
    if device_id:
        try: device=Device.objects.get(id=device_id,approved=True)
        except Device.DoesNotExist: return Response({'detail':'Device not found or not approved'},404)
        if not allowed(request.user,device): return Response({'detail':'You are not authorized for this device'},403)
    if mode=='UNATTENDED' and request.user.role not in ('ADMIN','SUPERADMIN'):
        # Stage 4 keeps unattended access restricted until step-up MFA is enabled in Stage 5.
        return Response({'detail':'Unattended access requires administrator approval/step-up MFA in the next security stage'},403)
    code=str(secrets.randbelow(900000000)+100000000)
    s=RemoteSession.objects.create(code=code,technician=request.user,device=device,mode=mode)
    AuditLog.objects.create(actor=request.user,action='SESSION_CREATED',target_type='RemoteSession',target_id=str(s.id),source_ip=request.META.get('REMOTE_ADDR'),details={'mode':mode,'code':code,'device_id':str(device.id) if device else None})
    return Response({'session_id':str(s.id),'code':s.code,'status':s.status,'mesh_base_url':settings.MESH_BASE_URL,'device_id':str(device.id) if device else None},201)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_session(request,session_id):
    try: s=RemoteSession.objects.get(id=session_id,technician=request.user)
    except RemoteSession.DoesNotExist: return Response({'detail':'Session not found'},404)
    if s.device and not allowed(request.user,s.device): return Response({'detail':'Not authorized'},403)
    if s.device and not s.device.approved: return Response({'detail':'Device not approved'},403)
    if s.status == 'ENDED': return Response({'detail':'Session already ended'},409)
    if s.mode == 'UNATTENDED' and request.user.role not in ('ADMIN','SUPERADMIN'):
        grant=request.data.get('stepup_grant')
        if not consume_stepup(request.user,grant,'REMOTE_CONNECT'):
            return Response({'detail':'Step-up MFA required for unattended access'},403)
    if s.status == 'ACTIVE': return Response({'ok':True,'mesh_url':s.mesh_launch_url or settings.MESH_BASE_URL,'mesh_node_id':s.device.mesh_node_id if s.device else None})
    s.status='ACTIVE'; s.started_at=timezone.now();
    template=getattr(settings,'MESH_NODE_URL_TEMPLATE','')
    s.mesh_launch_url=(template.format(node_id=s.device.mesh_node_id, device_id=s.device.id) if (template and s.device and s.device.mesh_node_id) else settings.MESH_BASE_URL); s.save(update_fields=['status','started_at','mesh_launch_url'])
    AuditLog.objects.create(actor=request.user,action='SESSION_STARTED',target_type='RemoteSession',target_id=str(s.id),source_ip=request.META.get('REMOTE_ADDR'),details={'mesh_node_id':s.device.mesh_node_id if s.device else ''})
    launch_url = s.mesh_launch_url or settings.MESH_BASE_URL
    if getattr(settings, 'MESH_SSO_ENABLED', False) and s.device and s.device.mesh_node_id:
        try:
            mesh_user = ensure_mesh_user(request.user, s.device)
            token = create_login_token(mesh_user)
            from urllib.parse import urlencode
            launch_url = launch_url.rstrip('/') + '/?'+urlencode({'login': token, 'viewmode': 11, 'node': s.device.mesh_node_id})
            s.mesh_launch_url = launch_url
            s.metadata = {**(s.metadata or {}), 'mesh_user': mesh_user, 'sso': True}
            s.save(update_fields=['mesh_launch_url','metadata'])
        except MeshSSOError as e:
            AuditLog.objects.create(actor=request.user,action='MESH_SSO_FAILED',target_type='RemoteSession',target_id=str(s.id),source_ip=request.META.get('REMOTE_ADDR'),details={'error':str(e)})
            return Response({'detail':str(e)},502)
    return Response({'ok':True,'mesh_url':launch_url,'mesh_node_id':s.device.mesh_node_id if s.device else None})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def end_session(request,session_id):
    try: s=RemoteSession.objects.get(id=session_id,technician=request.user)
    except RemoteSession.DoesNotExist: return Response({'detail':'Session not found'},404)
    s.status='ENDED'; s.ended_at=timezone.now(); s.save(update_fields=['status','ended_at'])
    AuditLog.objects.create(actor=request.user,action='SESSION_ENDED',target_type='RemoteSession',target_id=str(s.id),source_ip=request.META.get('REMOTE_ADDR'),details={})
    return Response({'ok':True})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sessions(request):
    qs=RemoteSession.objects.filter(technician=request.user).order_by('-created_at')[:100]
    return Response(list(qs.values('id','code','mode','status','device_id','created_at','started_at','ended_at')))

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def session_action(request,session_id):
    action=request.data.get('action')
    action_map={'file_transfer':'can_file_transfer','terminal':'can_terminal','reboot':'can_reboot'}
    if action not in action_map:
        return Response({'detail':'Invalid action'},400)
    s=_session_or_404(request,session_id)
    if not s: return Response({'detail':'Session not found'},404)
    if not s.device or not s.device.approved: return Response({'detail':'Device not approved'},403)
    if not allowed(request.user,s.device,action_map[action]): return Response({'detail':f'{action} permission denied'},403)
    if s.status != 'ACTIVE': return Response({'detail':'Session is not active'},409)
    AuditLog.objects.create(actor=request.user,action='SESSION_ACTION',target_type='RemoteSession',target_id=str(s.id),source_ip=request.META.get('REMOTE_ADDR'),details={'action':action,'device_id':str(s.device.id)})
    return Response({'ok':True,'action':action,'mesh_node_id':s.device.mesh_node_id,'message':'Authorization recorded. Use /execute/ for MeshCentral-backed terminal/reboot actions.'})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def session_detail(request,session_id):
    s=_session_or_404(request,session_id)
    if not s: return Response({'detail':'Session not found'},404)
    return Response({'id':str(s.id),'code':s.code,'mode':s.mode,'status':s.status,'device_id':str(s.device_id) if s.device_id else None,'mesh_node_id':s.device.mesh_node_id if s.device else None,'mesh_url':s.mesh_launch_url or settings.MESH_BASE_URL,'created_at':s.created_at,'started_at':s.started_at,'ended_at':s.ended_at})
