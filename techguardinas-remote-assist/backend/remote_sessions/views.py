from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from devices.models import Device
from remote_bridge.meshapi import MeshError
from . import services
from .models import AuditLog, RemoteSession
from .services import PolicyError, audit, client_ip

REVIEW_ROLES = ('ADMIN', 'SUPERADMIN', 'AUDITOR')


def _err(e):
    if isinstance(e, MeshError):
        return Response({'detail': f'Remote engine error: {e}'}, 502)
    return Response({'detail': str(e)}, e.status)


def _dt(v):
    return v.isoformat() if v else None


def serialize(s, include_events=False):
    md = s.metadata or {}
    data = {
        'id': str(s.id), 'code': s.code, 'mode': s.mode, 'status': s.status,
        'technician': s.technician.username,
        'device_id': str(s.device_id) if s.device_id else None,
        'target_name': s.target_name, 'target_os': s.target_os, 'target_ip': s.target_ip,
        'capabilities': s.capabilities, 'mfa_verified': s.mfa_verified,
        'created_at': _dt(s.created_at), 'expires_at': _dt(s.expires_at), 'authorized_at': _dt(s.authorized_at),
        'started_at': _dt(s.started_at), 'ended_at': _dt(s.ended_at), 'deadline_at': _dt(s.deadline_at),
        'customer_name': s.customer_name, 'customer_consent_at': _dt(s.customer_consent_at),
        'ended_by': s.ended_by, 'end_reason': s.end_reason, 'outcome': s.outcome,
        'device_online': md.get('device_online'), 'remote_consent': md.get('remote_consent', {}),
        'recording': bool((s.authorization or {}).get('recording')),
    }
    if s.mode == 'ATTENDED':
        data['join_url'] = services.join_url(s)
    if include_events:
        data['mesh_events'] = md.get('mesh_events', [])
        data['authorization'] = s.authorization
        data['audit'] = list(AuditLog.objects.filter(target_type='RemoteSession', target_id=str(s.id))
                             .order_by('created_at').values('action', 'created_at', 'source_ip', 'details', 'actor__username'))
    return data


def _own_session(request, session_id):
    try:
        s = RemoteSession.objects.select_related('technician', 'device').get(id=session_id)
    except RemoteSession.DoesNotExist:
        return None
    if s.technician_id == request.user.pk or request.user.role in REVIEW_ROLES:
        return s
    return None


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_attended(request):
    try:
        s = services.create_attended(request.user, request, request.data.get('stepup_grant'))
    except (PolicyError, MeshError) as e:
        return _err(e)
    return Response(serialize(s), 201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_unattended(request):
    try:
        device = Device.objects.get(id=request.data.get('device_id'))
    except (Device.DoesNotExist, ValueError, Exception):
        return Response({'detail': 'Device not found'}, 404)
    try:
        s = services.authorize_unattended(request.user, device, request, request.data.get('stepup_grant'))
    except (PolicyError, MeshError) as e:
        return _err(e)
    return Response(serialize(s), 201)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sessions(request):
    qs = RemoteSession.objects.select_related('technician')
    if not (request.GET.get('all') and request.user.role in REVIEW_ROLES):
        qs = qs.filter(technician=request.user)
    return Response([serialize(s) for s in qs[:200]])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def session_detail(request, session_id):
    s = _own_session(request, session_id)
    if not s:
        return Response({'detail': 'Session not found'}, 404)
    if s.technician_id == request.user.pk:
        services.refresh(s)
        s.refresh_from_db()
    return Response(serialize(s, include_events=True))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def console(request, session_id):
    s = _own_session(request, session_id)
    if not s:
        return Response({'detail': 'Session not found'}, 404)
    try:
        url = services.console_url(s, request.user, str(request.data.get('view', 'desktop')), request)
    except (PolicyError, MeshError) as e:
        return _err(e)
    return Response({'url': url})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def chat(request, session_id):
    s = _own_session(request, session_id)
    if not s:
        return Response({'detail': 'Session not found'}, 404)
    try:
        return Response({'url': services.chat_url(s, request.user, request)})
    except (PolicyError, MeshError) as e:
        return _err(e)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reboot(request, session_id):
    s = _own_session(request, session_id)
    if not s:
        return Response({'detail': 'Session not found'}, 404)
    try:
        services.reboot(s, request.user, request)
    except (PolicyError, MeshError) as e:
        return _err(e)
    return Response({'ok': True})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def end(request, session_id):
    s = _own_session(request, session_id)
    if not s:
        return Response({'detail': 'Session not found'}, 404)
    is_admin = request.user.role in ('ADMIN', 'SUPERADMIN')
    if s.technician_id != request.user.pk and not is_admin:
        return Response({'detail': 'Only the technician or an administrator can end this session'}, 403)
    by = 'TECHNICIAN' if s.technician_id == request.user.pk else 'ADMIN'
    reason = str(request.data.get('reason') or ('Ended by technician' if by == 'TECHNICIAN' else 'Terminated by administrator'))
    s = services.end_session(s, by, reason, actor=request.user, outcome=str(request.data.get('outcome', '')), request=request)
    return Response(serialize(s))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def audit_log(request):
    if request.user.role not in REVIEW_ROLES:
        return Response({'detail': 'Administrator or auditor role required'}, 403)
    qs = AuditLog.objects.select_related('actor')
    if request.GET.get('action'):
        qs = qs.filter(action=request.GET['action'])
    if request.GET.get('q'):
        qs = qs.filter(details__icontains=request.GET['q']) | qs.filter(actor__username__icontains=request.GET['q'])
    rows = qs.order_by('-created_at')[:500]
    return Response([{'id': a.id, 'time': a.created_at, 'actor': a.actor.username if a.actor else None, 'action': a.action,
                      'target_type': a.target_type, 'target_id': a.target_id, 'source_ip': a.source_ip, 'details': a.details} for a in rows])


# ---------------------------------------------------------------------------
# Remote user (no portal account). Authorised by the invitation code, then a
# per-browser token returned by /api/join/.
# ---------------------------------------------------------------------------
def _throttled(request):
    key = f'join-attempts:{client_ip(request)}'
    n = cache.get(key, 0)
    if n >= settings.JOIN_MAX_ATTEMPTS:
        return True
    cache.set(key, n + 1, 600)
    return False


def _public(s):
    return {'code': s.code, 'status': s.status, 'technician': s.technician.get_full_name() or s.technician.username,
            'expires_at': _dt(s.expires_at), 'capabilities': [k for k, v in s.capabilities.items() if v],
            'consented': bool(s.customer_consent_at), 'connected': bool(s.mesh_node_id),
            'ended_by': s.ended_by, 'end_reason': s.end_reason,
            'platforms': list(services.AGENT_PLATFORMS.keys())}


@api_view(['POST'])
@permission_classes([AllowAny])
def join(request):
    if _throttled(request):
        return Response({'detail': 'Too many attempts. Try again in 10 minutes.'}, 429)
    code = ''.join(ch for ch in str(request.data.get('code', '')) if ch.isdigit())
    s = RemoteSession.objects.select_related('technician').filter(mode='ATTENDED', code=code).first()
    if not s or s.status != 'WAITING' or (s.expires_at and s.expires_at <= timezone.now()):
        audit(None, 'JOIN_FAILED', request=request, code=code[:12])
        return Response({'detail': 'This code is not valid or has expired. Ask your technician for a new code.'}, 404)
    try:
        token = services.issue_customer_token(s, client_ip(request))
    except PolicyError as e:
        return _err(e)
    return Response({'token': token, **_public(s)})


@api_view(['GET'])
@permission_classes([AllowAny])
def join_status(request, token):
    s = services.session_for_token(token)
    if not s:
        return Response({'detail': 'Not found'}, 404)
    services.refresh(s)
    s.refresh_from_db()
    return Response(_public(s))


@api_view(['POST'])
@permission_classes([AllowAny])
def join_consent(request, token):
    s = services.session_for_token(token)
    if not s:
        return Response({'detail': 'Not found'}, 404)
    if request.data.get('accept') is not True:
        return Response({'detail': 'Consent is required to continue.'}, 400)
    try:
        services.record_consent(s, request.data.get('name', ''), client_ip(request))
    except PolicyError as e:
        return _err(e)
    return Response(_public(s))


@api_view(['GET'])
@permission_classes([AllowAny])
def join_agent(request, token, platform):
    s = services.session_for_token(token)
    if not s:
        return Response({'detail': 'Not found'}, 404)
    try:
        name, data = services.customer_agent(s, platform)
    except (PolicyError, MeshError) as e:
        return _err(e)
    resp = HttpResponse(data, content_type='application/octet-stream')
    resp['Content-Disposition'] = f'attachment; filename="{name}"'
    resp['Cache-Control'] = 'no-store'
    return resp


@api_view(['POST'])
@permission_classes([AllowAny])
def join_end(request, token):
    s = services.session_for_token(token)
    if not s:
        return Response({'detail': 'Not found'}, 404)
    s = services.end_session(s, 'REMOTE_USER', 'Remote user ended the session from the support page', request=request)
    return Response(_public(s))
