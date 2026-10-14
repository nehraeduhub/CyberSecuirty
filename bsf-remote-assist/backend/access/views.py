from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from devices.models import Device
from remote_bridge import meshapi
from remote_bridge.meshapi import MeshError, MeshSession
from remote_sessions.services import PolicyError, agent_package, audit, client_ip
from .models import DeviceGroup, TechnicianDevicePermission

User = get_user_model()
ADMIN_ROLES = ('SUPERADMIN', 'ADMIN')
PERM_FLAGS = ('can_connect', 'can_file_transfer', 'can_terminal', 'can_reboot')


def _admin(request):
    return request.user.is_authenticated and request.user.role in ADMIN_ROLES


def _forbidden():
    return Response({'detail': 'Admin only'}, 403)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
@ensure_csrf_cookie
def csrf(request):
    return JsonResponse({'csrfToken': get_token(request)})


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    username = str(request.data.get('username') or '').strip()
    password = str(request.data.get('password') or '')
    ip = client_ip(request)
    key = f'login-fail:{ip}:{username.lower()}'
    if cache.get(key, 0) >= settings.LOGIN_MAX_ATTEMPTS:
        audit(None, 'LOGIN_LOCKED', request=request, username=username)
        return Response({'detail': 'Too many failed attempts. Try again in 15 minutes.'}, 429)
    user = authenticate(request, username=username, password=password)
    if user is None:
        cache.set(key, cache.get(key, 0) + 1, 900)
        audit(None, 'LOGIN_FAILED', request=request, username=username)
        return Response({'detail': 'Invalid credentials or portal access not approved'}, 401)
    cache.delete(key)
    login(request, user)
    user.last_login_ip = ip
    user.save(update_fields=['last_login_ip'])
    audit(user, 'LOGIN', request=request)
    return Response({'ok': True, 'username': user.username, 'role': user.role})


@api_view(['POST'])
@permission_classes([AllowAny])
def logout_view(request):
    if request.user.is_authenticated:
        audit(request.user, 'LOGOUT', request=request)
    logout(request)
    return Response({'ok': True})


# ---------------------------------------------------------------------------
# Users (administrator controlled; no self-registration)
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def users(request):
    if not _admin(request):
        return _forbidden()
    return Response(list(User.objects.order_by('username').values(
        'id', 'username', 'ad_username', 'email', 'role', 'portal_enabled', 'is_active', 'auth_source', 'last_login', 'last_login_ip')))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def provision_user(request):
    if not _admin(request):
        return _forbidden()
    ad_username = str(request.data.get('ad_username') or '').strip()
    if not ad_username:
        return Response({'detail': 'ad_username required'}, 400)
    if User.objects.filter(ad_username__iexact=ad_username).exists() or User.objects.filter(username__iexact=ad_username).exists():
        return Response({'detail': 'User already provisioned'}, 409)
    role = request.data.get('role', 'TECHNICIAN')
    if role not in User.Role.values:
        return Response({'detail': 'Invalid role'}, 400)
    if role in ADMIN_ROLES and request.user.role != 'SUPERADMIN':
        return Response({'detail': 'Only SUPERADMIN can create administrators'}, 403)
    u = User.objects.create(username=ad_username, ad_username=ad_username, role=role, portal_enabled=False,
                            is_active=True, auth_source='AD', created_by=request.user)
    u.set_unusable_password()
    u.save()
    audit(request.user, 'USER_PROVISIONED', u, request, ad_username=ad_username, role=role)
    return Response({'id': u.id, 'username': u.username, 'role': u.role, 'portal_enabled': False}, 201)


def _user_or_404(user_id):
    return User.objects.filter(pk=user_id).first()


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def approve_user(request, user_id):
    if not _admin(request):
        return _forbidden()
    u = _user_or_404(user_id)
    if not u:
        return Response({'detail': 'User not found'}, 404)
    u.portal_enabled = True
    u.is_active = True
    u.save(update_fields=['portal_enabled', 'is_active'])
    audit(request.user, 'USER_APPROVED', u, request, username=u.username)
    return Response({'ok': True})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def disable_user(request, user_id):
    if not _admin(request):
        return _forbidden()
    u = _user_or_404(user_id)
    if not u:
        return Response({'detail': 'User not found'}, 404)
    if u.pk == request.user.pk:
        return Response({'detail': 'You cannot disable your own account'}, 400)
    u.portal_enabled = False
    u.save(update_fields=['portal_enabled'])
    audit(request.user, 'USER_DISABLED', u, request, username=u.username)
    # Open sessions are terminated by the session worker on its next pass (refresh() checks account status).
    from remote_sessions.models import RemoteSession
    from remote_sessions.services import end_session
    for s in RemoteSession.objects.filter(technician=u, status__in=RemoteSession.OPEN_STATUSES):
        end_session(s, 'ADMIN', 'Technician account disabled', actor=request.user, request=request)
    return Response({'ok': True})


# ---------------------------------------------------------------------------
# Device groups (each maps to a MeshCentral device group)
# ---------------------------------------------------------------------------
def _group_row(g):
    return {'id': g.id, 'name': g.name, 'description': g.description, 'active': g.active, 'auto_approve': g.auto_approve,
            'record_sessions': g.record_sessions, 'linked': bool(g.mesh_group_id),
            'devices': Device.objects.filter(group=g.name, removed=False).count()}


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def groups(request):
    if not _admin(request):
        return _forbidden()
    if request.method == 'GET':
        return Response([_group_row(g) for g in DeviceGroup.objects.order_by('name')])
    name = str(request.data.get('name') or '').strip()
    if not name or len(name) > 100:
        return Response({'detail': 'name required (max 100 characters)'}, 400)
    if DeviceGroup.objects.filter(name__iexact=name).exists():
        return Response({'detail': 'Group already exists'}, 409)
    g = DeviceGroup(name=name, description=str(request.data.get('description', ''))[:1000],
                    auto_approve=bool(request.data.get('auto_approve', False)),
                    record_sessions=bool(request.data.get('record_sessions', settings.MESH_SESSION_RECORDING)))
    try:
        with MeshSession() as s:
            g.mesh_group_id = s.create_mesh(f'BSF-{name}', desc=g.description or f'BSF Remote managed devices: {name}',
                                            consent=settings.MESH_CONSENT_UNATTENDED,
                                            flags=meshapi.MESH_FLAG_RECORD_SESSIONS if g.record_sessions else 0)
    except MeshError as e:
        return Response({'detail': f'Remote engine error: {e}'}, 502)
    g.save()
    audit(request.user, 'GROUP_CREATED', g, request, name=g.name, auto_approve=g.auto_approve, record_sessions=g.record_sessions)
    return Response(_group_row(g), 201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_group(request, group_id):
    if not _admin(request):
        return _forbidden()
    g = DeviceGroup.objects.filter(pk=group_id).first()
    if not g:
        return Response({'detail': 'Group not found'}, 404)
    for f in ('active', 'auto_approve', 'record_sessions'):
        if f in request.data:
            setattr(g, f, bool(request.data[f]))
    if 'record_sessions' in request.data and g.mesh_group_id:
        try:
            with MeshSession() as s:
                s.edit_mesh(g.mesh_group_id, flags=meshapi.MESH_FLAG_RECORD_SESSIONS if g.record_sessions else 0)
        except MeshError as e:
            return Response({'detail': f'Remote engine error: {e}'}, 502)
    g.save()
    audit(request.user, 'GROUP_UPDATED', g, request, **{f: getattr(g, f) for f in ('active', 'auto_approve', 'record_sessions')})
    return Response(_group_row(g))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def group_agent(request, group_id, platform):
    """Official MeshCentral agent installer for a managed group (for GPO / software deployment)."""
    if not _admin(request):
        return _forbidden()
    g = DeviceGroup.objects.filter(pk=group_id).first()
    if not g or not g.mesh_group_id:
        return Response({'detail': 'Group not found or not linked to the remote engine'}, 404)
    safe = ''.join(c for c in g.name if c.isalnum() or c in '-_')[:40] or 'group'
    try:
        # InstallFlags=2: background service only (no "connect" mode), suitable for unattended endpoints.
        name, data = agent_package(g.mesh_group_id, platform, 2, f'BSF-Remote-Agent-{safe}')
    except (PolicyError, MeshError) as e:
        return Response({'detail': str(e)}, getattr(e, 'status', 502))
    audit(request.user, 'AGENT_INSTALLER_DOWNLOADED', g, request, platform=platform, bytes=len(data))
    resp = HttpResponse(data, content_type='application/octet-stream')
    resp['Content-Disposition'] = f'attachment; filename="{name}"'
    resp['Cache-Control'] = 'no-store'
    return resp


# ---------------------------------------------------------------------------
# Technician permissions (per group or per device)
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def permissions(request):
    if not _admin(request):
        return _forbidden()
    rows = TechnicianDevicePermission.objects.select_related('user', 'group', 'device')
    return Response([{'id': p.id, 'user_id': p.user_id, 'username': p.user.username,
                      'group_id': p.group_id, 'group': p.group.name if p.group else None,
                      'device_id': str(p.device_id) if p.device_id else None, 'device': p.device.name if p.device else None,
                      **{f: getattr(p, f) for f in PERM_FLAGS}} for p in rows])


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_permission(request):
    if not _admin(request):
        return _forbidden()
    d = request.data
    u = User.objects.filter(pk=d.get('user_id')).first()
    g = DeviceGroup.objects.filter(pk=d.get('group_id')).first() if d.get('group_id') else None
    dev = Device.objects.filter(pk=d.get('device_id')).first() if d.get('device_id') else None
    if not u or not (g or dev) or (g and dev):
        return Response({'detail': 'user_id and exactly one of group_id / device_id are required'}, 400)
    if u.role == 'AUDITOR':
        return Response({'detail': 'Auditors cannot be granted remote access'}, 400)
    perm, created = TechnicianDevicePermission.objects.get_or_create(user=u, group=g, device=dev)
    for f in PERM_FLAGS:
        if f in d:
            setattr(perm, f, bool(d[f]))
        elif created and f == 'can_connect':
            perm.can_connect = True
    perm.save()
    audit(request.user, 'PERMISSION_CHANGED', perm, request, user=u.username, group=g.name if g else None,
          device=dev.name if dev else None, **{f: getattr(perm, f) for f in PERM_FLAGS})
    return Response({'id': perm.id, 'created': created})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def delete_permission(request, perm_id):
    if not _admin(request):
        return _forbidden()
    perm = TechnicianDevicePermission.objects.select_related('user').filter(pk=perm_id).first()
    if not perm:
        return Response({'detail': 'Not found'}, 404)
    audit(request.user, 'PERMISSION_REMOVED', perm, request, user=perm.user.username,
          group=perm.group.name if perm.group else None, device=perm.device.name if perm.device else None)
    perm.delete()
    return Response({'ok': True})
