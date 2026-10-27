"""Remote-support session lifecycle.

The portal is the authorization and audit layer; MeshCentral is the remote-control engine.
Technicians never hold standing rights on any endpoint: each technician has a MeshCentral
account with *no* device rights, and the portal grants rights on exactly one device for the
lifetime of one authorized session, then removes them and tears down any live tunnels.
"""
import hashlib
import io
import logging
import secrets
import ssl
import tarfile
import urllib.request
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from access.models import TechnicianDevicePermission
from remote_bridge import meshapi
from remote_bridge.meshapi import MeshError, MeshSession
from security.models import MFAMethod
from security.views import consume_stepup
from .models import AuditLog, RemoteSession

log = logging.getLogger('techguardinas')

SUPPORT_ROLES = ('TECHNICIAN', 'ADMIN', 'SUPERADMIN')
ADMIN_ROLES = ('ADMIN', 'SUPERADMIN')
ALL_CAPS = ('desktop', 'terminal', 'files', 'chat', 'reboot')
VIEWMODES = {'general': 10, 'desktop': 11, 'terminal': 12, 'files': 13, 'events': 16}
VIEW_CAP = {'desktop': 'desktop', 'terminal': 'terminal', 'files': 'files', 'general': 'desktop', 'events': 'desktop'}

# Agent-side consent/session events (MeshCentral meshcore.js MeshServerLogEx ids)
CONSENT_EVENTS = {
    27: ('terminal', 'accepted'), 28: ('terminal', 'rejected'),
    30: ('desktop', 'accepted'), 34: ('desktop', 'rejected'),
    40: ('files', 'accepted'), 41: ('files', 'rejected'),
}
LOCAL_USER_CLOSED_DESKTOP = 29

# Agent packages offered to the remote user: MeshCentral agent id, file suffix
AGENT_PLATFORMS = {
    'windows-x64': (4, '.exe'),
    'windows-x86': (3, '.exe'),
    'windows-arm64': (43, '.exe'),
    'linux-x64': (6, '.tar.gz'),
}


class PolicyError(Exception):
    def __init__(self, message, status=403):
        super().__init__(message)
        self.status = status


def client_ip(request):
    if request is None:
        return None
    # NGINX (the only path into the backend container) sets X-Real-IP.
    return request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR')


def audit(actor, action, obj=None, request=None, ip=None, **details):
    target_type, target_id = '', ''
    if obj is not None:
        target_type = obj.__class__.__name__
        target_id = str(getattr(obj, 'pk', ''))
    AuditLog.objects.create(actor=actor if (actor is not None and getattr(actor, 'pk', None)) else None,
                            action=action, target_type=target_type, target_id=target_id,
                            source_ip=ip or client_ip(request), details=details)


def mesh_username(user):
    return f'tgtech-{user.pk}'


def user_can_support(user):
    return bool(user and user.is_active and user.portal_enabled and user.role in SUPPORT_ROLES)


def mfa_enabled(user):
    return MFAMethod.objects.filter(user=user, enabled=True).exists()


def device_permission(user, device):
    """Effective capabilities of `user` on an unattended `device`, or None when not authorized."""
    if not user_can_support(user) or not device.approved or device.removed:
        return None
    if user.role in ADMIN_ROLES:
        return {'desktop': True, 'chat': True, 'files': True, 'terminal': True, 'reboot': True, 'source': 'role:' + user.role}
    perms = list(TechnicianDevicePermission.objects.filter(user=user, can_connect=True, device=device)) + \
        list(TechnicianDevicePermission.objects.filter(user=user, can_connect=True, device__isnull=True,
                                                       group__name=device.group, group__active=True))
    if not perms:
        return None
    return {
        'desktop': True, 'chat': True,
        'files': any(p.can_file_transfer for p in perms),
        'terminal': any(p.can_terminal for p in perms),
        'reboot': any(p.can_reboot for p in perms),
        'source': ','.join(f'perm:{p.pk}' for p in perms),
    }


def mesh_rights(caps):
    rights = (meshapi.RIGHT_REMOTECONTROL | meshapi.RIGHT_NOAMT | meshapi.RIGHT_NOREGISTRY | meshapi.RIGHT_NOSOFTWARE)
    if caps.get('chat'):
        rights |= meshapi.RIGHT_CHATNOTIFY
    if not caps.get('terminal'):
        rights |= meshapi.RIGHT_NOTERMINAL
    if not caps.get('files'):
        rights |= meshapi.RIGHT_NOFILES
    if caps.get('reboot'):
        rights |= meshapi.RIGHT_RESETOFF
    return rights


def _new_code():
    for _ in range(50):
        code = str(secrets.randbelow(900_000_000) + 100_000_000)
        if not RemoteSession.objects.filter(code=code).exists():
            return code
    raise PolicyError('Unable to allocate a session code', 503)


def _require_mfa(user, grant, required):
    if not required:
        return False
    if not mfa_enabled(user):
        raise PolicyError('MFA is required for this connection. Enroll an authenticator under Settings first.')
    if not grant or not consume_stepup(user, grant, 'REMOTE_CONNECT'):
        raise PolicyError('A valid MFA verification is required for this connection.')
    return True


def join_url(session):
    return f"{settings.PORTAL_PUBLIC_URL.rstrip('/')}/join/{session.code}"


# ---------------------------------------------------------------------------
# Session creation
# ---------------------------------------------------------------------------
def create_attended(tech, request=None, stepup_grant=None):
    if not user_can_support(tech):
        audit(tech, 'ACCESS_DENIED', request=request, mode='ATTENDED', reason='role or account status')
        raise PolicyError('Your account is not permitted to start remote support.')
    mfa = _require_mfa(tech, stepup_grant, settings.ATTENDED_REQUIRE_MFA)
    caps = {c: (c in settings.ATTENDED_CAPABILITIES) for c in ALL_CAPS}
    caps['desktop'] = True
    code = _new_code()
    flags = meshapi.MESH_FLAG_RECORD_SESSIONS if settings.MESH_SESSION_RECORDING else 0
    with MeshSession() as s:
        group_id = s.create_mesh(f'TechGuardinas-ATT-{code}', desc=f'Attended support session {code} ({tech.username})',
                                 consent=settings.MESH_CONSENT_ATTENDED, flags=flags)
        s.ensure_user(mesh_username(tech), realname=tech.get_full_name() or tech.username)
    now = timezone.now()
    session = RemoteSession.objects.create(
        code=code, technician=tech, mode='ATTENDED', status='WAITING',
        expires_at=now + timedelta(minutes=settings.ATTENDED_CODE_TTL_MINUTES),
        mfa_verified=mfa, capabilities=caps, mesh_group_id=group_id, mesh_user=mesh_username(tech),
        authorization={'role': tech.role, 'policy': 'attended', 'consent_flags': settings.MESH_CONSENT_ATTENDED,
                       'recording': settings.MESH_SESSION_RECORDING},
    )
    audit(tech, 'SESSION_CREATED', session, request, mode='ATTENDED', code=code,
          expires_at=session.expires_at.isoformat(), capabilities=caps)
    return session


def authorize_unattended(tech, device, request=None, stepup_grant=None):
    caps = device_permission(tech, device)
    if caps is None:
        audit(tech, 'ACCESS_DENIED', device, request, mode='UNATTENDED', reason='no permission / device not approved / account not enabled')
        raise PolicyError('You are not authorized for this device.')
    mfa = _require_mfa(tech, stepup_grant, settings.UNATTENDED_REQUIRE_MFA)
    if not device.mesh_node_id:
        raise PolicyError('Device is not linked to a MeshCentral agent.', 409)
    rights = mesh_rights(caps)
    with MeshSession() as s:
        nodes = [n for n in s.nodes(device.mesh_group_id or None) if n['_id'] == device.mesh_node_id]
        if not nodes:
            raise PolicyError('The device agent is not registered with the remote engine.', 409)
        if not meshapi.connected(nodes[0]):
            raise PolicyError('The device is offline.', 409)
        s.ensure_user(mesh_username(tech), realname=tech.get_full_name() or tech.username)
        s.set_device_rights(device.mesh_node_id, meshapi.user_id(mesh_username(tech)), rights)
    now = timezone.now()
    session = RemoteSession.objects.create(
        code=_new_code(), technician=tech, device=device, mode='UNATTENDED', status='READY',
        authorized_at=now, deadline_at=now + timedelta(minutes=settings.SESSION_MAX_MINUTES),
        mfa_verified=mfa, capabilities={k: bool(caps.get(k)) for k in ALL_CAPS},
        mesh_node_id=device.mesh_node_id, mesh_user=mesh_username(tech),
        target_name=device.name, target_os=device.os, target_ip=device.ip_address or '',
        authorization={'role': tech.role, 'source': caps['source'], 'mesh_rights': rights, 'mfa': mfa},
    )
    audit(tech, 'SESSION_AUTHORIZED', session, request, mode='UNATTENDED', device_id=str(device.pk),
          device=device.name, capabilities=session.capabilities, mfa=mfa, mesh_rights=rights)
    return session


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def _bind_attended_node(s, session, node, others):
    rights = mesh_rights(session.capabilities)
    if others:
        s.remove_devices([n['_id'] for n in others])
    s.set_device_rights(node['_id'], meshapi.user_id(session.mesh_user), rights)
    now = timezone.now()
    session.mesh_node_id = node['_id']
    session.target_name = (node.get('rname') or node.get('name') or '')[:255]
    session.target_os = (node.get('osdesc') or '')[:255]
    session.target_ip = (node.get('ip') or '')[:64]
    session.status = 'READY'
    session.authorized_at = now
    session.deadline_at = now + timedelta(minutes=settings.SESSION_MAX_MINUTES)
    session.authorization = {**session.authorization, 'mesh_rights': rights}
    session.save()
    audit(None, 'REMOTE_AGENT_CONNECTED', session, ip=session.customer_ip, code=session.code,
          target=session.target_name, os=session.target_os, ip_reported=session.target_ip, extra_agents_removed=len(others))


def refresh(session):
    """Reconcile a session with MeshCentral: bind the attended device, detect disconnects, enforce limits."""
    if not session.is_open:
        return session
    now = timezone.now()
    if session.deadline_at and now >= session.deadline_at:
        end_session(session, 'SYSTEM', 'Maximum session duration reached')
        return session
    if session.status == 'WAITING' and session.expires_at and now >= session.expires_at:
        session.status = 'EXPIRED'
        session.ended_at = now
        session.ended_by = 'SYSTEM'
        session.end_reason = 'Invitation expired before the remote user connected'
        session.save()
        _cleanup_mesh(session)
        audit(None, 'SESSION_EXPIRED', session, code=session.code)
        return session
    if not user_can_support(session.technician):
        end_session(session, 'SYSTEM', 'Technician account disabled')
        return session
    if session.mode == 'UNATTENDED':
        device = session.device
        if device is None or device_permission(session.technician, device) is None:
            end_session(session, 'SYSTEM', 'Authorization revoked')
            return session
    try:
        with MeshSession() as s:
            if session.mode == 'ATTENDED':
                nodes = s.nodes(session.mesh_group_id)
                if not session.mesh_node_id:
                    online = [n for n in nodes if meshapi.connected(n)]
                    if online and session.customer_consent_at:
                        with transaction.atomic():
                            locked = RemoteSession.objects.select_for_update().get(pk=session.pk)
                            if not locked.mesh_node_id and locked.status == 'WAITING':
                                _bind_attended_node(s, locked, online[0], online[1:])
                        session.refresh_from_db()
                    return session
                node = next((n for n in nodes if n['_id'] == session.mesh_node_id), None)
            else:
                node = next((n for n in s.nodes(session.device.mesh_group_id or None) if n['_id'] == session.mesh_node_id), None)
    except MeshError as e:
        log.warning('refresh %s: %s', session.pk, e)
        return session
    online = bool(node and meshapi.connected(node))
    md = dict(session.metadata or {})
    changed = md.get('device_online') != online
    md['device_online'] = online
    if online:
        md.pop('offline_since', None)
    elif 'offline_since' not in md:
        md['offline_since'] = now.isoformat()
        changed = True
    if changed:
        session.metadata = md
        session.save(update_fields=['metadata'])
        audit(None, 'DEVICE_ONLINE' if online else 'DEVICE_OFFLINE', session, node=session.target_name)
    if session.mode == 'ATTENDED' and not online:
        offline_for = (now - datetime.fromisoformat(md['offline_since'])).total_seconds()
        if node is None or offline_for >= settings.ATTENDED_OFFLINE_GRACE_SECONDS:
            end_session(session, 'REMOTE_USER', 'Remote user closed the support agent or disconnected')
    return session


def _require_open(session, user):
    if session.technician_id != user.pk:
        raise PolicyError('Session not found', 404)
    refresh(session)
    if session.status not in ('READY', 'ACTIVE'):
        raise PolicyError(f'Session is {session.status.lower()}.', 409)
    if not user_can_support(user):
        raise PolicyError('Your account is not permitted to use remote support.')


def console_url(session, user, view='desktop', request=None):
    if view not in VIEWMODES:
        raise PolicyError('Unknown console view', 400)
    _require_open(session, user)
    cap = VIEW_CAP[view]
    if not session.capabilities.get(cap):
        audit(user, 'ACCESS_DENIED', session, request, view=view, reason='capability not granted')
        raise PolicyError(f'{view} is not permitted for this session.')
    url = meshapi.console_url(session.mesh_user, session.mesh_node_id, VIEWMODES[view])
    if session.status == 'READY':
        session.status = 'ACTIVE'
        session.started_at = timezone.now()
        session.save(update_fields=['status', 'started_at'])
        audit(user, 'SESSION_STARTED', session, request, code=session.code, target=session.target_name)
    audit(user, 'CONSOLE_OPENED', session, request, view=view)
    return url


def chat_url(session, user, request=None):
    _require_open(session, user)
    if not session.capabilities.get('chat'):
        raise PolicyError('Chat is not permitted for this session.')
    with MeshSession(username=session.mesh_user) as s:
        s.mesh_messenger(session.mesh_node_id)
    audit(user, 'CHAT_OPENED', session, request)
    return meshapi.messenger_url(session.mesh_user, session.mesh_node_id, session.target_name or 'Remote user')


def reboot(session, user, request=None):
    _require_open(session, user)
    if not session.capabilities.get('reboot'):
        audit(user, 'ACCESS_DENIED', session, request, action='reboot', reason='capability not granted')
        raise PolicyError('Reboot is not permitted for this session.')
    with MeshSession() as s:
        s.power(session.mesh_node_id, meshapi.POWER_RESET)
    session.metadata = {**session.metadata, 'reboot_requested_at': timezone.now().isoformat()}
    session.save(update_fields=['metadata'])
    audit(user, 'DEVICE_REBOOT', session, request, target=session.target_name)


# ---------------------------------------------------------------------------
# Termination
# ---------------------------------------------------------------------------
def _kill_tunnels(s, node_id, userid):
    """Close every live relay tunnel (desktop, terminal, files) the agent holds for `userid`."""
    js = ("var n=0;for(var i in tunnels){var t=tunnels[i];if(t.userid=='%s'&&t.s){try{t.s.end()}catch(e){};n++}};n" % userid)
    s.send('msg', type='console', nodeid=meshapi.full_node_id(node_id), value='eval "%s"' % js)


def _collect_events(s, session):
    try:
        events = s.events(session.mesh_node_id, 300)
    except MeshError:
        return
    since = (session.created_at - timedelta(seconds=5)).strftime('%Y-%m-%dT%H:%M:%S')
    keep, consent = [], {}
    for e in events:
        t = e.get('time') or ''
        if isinstance(t, str) and t < since:
            continue
        msgid = e.get('msgid')
        if msgid in CONSENT_EVENTS:
            feature, decision = CONSENT_EVENTS[msgid]
            consent.setdefault(feature, decision)
        keep.append({'time': t, 'msgid': msgid, 'msg': (e.get('msg') or '')[:300], 'user': e.get('username', '')})
    session.metadata = {**session.metadata, 'mesh_events': keep[:200], 'remote_consent': consent,
                        'closed_by_local_user': any(k.get('msgid') == LOCAL_USER_CLOSED_DESKTOP for k in keep)}


def _revoke(s, session):
    """Remove the technician's rights and close live connections. Every step runs even if an earlier one
    fails; the first failure is re-raised so the session is flagged for retry by the worker."""
    uid = meshapi.user_id(session.mesh_user)
    steps = []
    # A node that no longer exists (attended group deleted, device removed) has no rights left to revoke.
    node_exists = bool(session.mesh_node_id) and any(n['_id'] == session.mesh_node_id for n in s.nodes())
    if node_exists:
        steps += [lambda: s.remove_device_rights(session.mesh_node_id, uid),
                  lambda: s.end_desktop(session.mesh_node_id, uid),
                  lambda: _kill_tunnels(s, session.mesh_node_id, uid),
                  lambda: _collect_events(s, session)]
    still_open = RemoteSession.objects.filter(technician=session.technician, status__in=('READY', 'ACTIVE')).exclude(pk=session.pk).exists()
    if not still_open:
        steps.append(lambda: s.close_user_sessions(uid))
    first_error = None
    for step in steps:
        try:
            step()
        except MeshError as e:
            first_error = first_error or e
    if first_error:
        raise first_error


def _remove_attended_group(s, group_id):
    """Delete an attended session's group (and with it the device record).

    MeshCentral cannot stop a connect-only agent remotely (it refuses process exit in agent mode), so the
    remote user's on-demand agent stays open, idle, until they close it. It holds no technician rights,
    and if it reconnects MeshCentral may "undelete" the group; sweep_attended_groups() removes it again."""
    s.delete_mesh(group_id)


def _cleanup_mesh(session):
    if session.mode != 'ATTENDED' or not session.mesh_group_id:
        return
    try:
        with MeshSession() as s:
            _remove_attended_group(s, session.mesh_group_id)
        session.metadata = {**session.metadata, 'mesh_group_deleted': True}
        session.save(update_fields=['metadata'])
    except MeshError as e:
        log.warning('cleanup %s: %s', session.pk, e)


def sweep_attended_groups():
    """Delete attended groups that no open session owns (e.g. after a crash or an agent that reconnected)."""
    open_groups = set(RemoteSession.objects.filter(mode='ATTENDED', status__in=RemoteSession.OPEN_STATUSES)
                      .values_list('mesh_group_id', flat=True))
    with MeshSession() as s:
        for g in s.meshes():
            if g.get('name', '').startswith('TechGuardinas-ATT-') and g['_id'] not in open_groups:
                _remove_attended_group(s, g['_id'])
                audit(None, 'ATTENDED_GROUP_SWEPT', None, group=g['name'])


def end_session(session, ended_by, reason, actor=None, outcome='', request=None):
    with transaction.atomic():
        session = RemoteSession.objects.select_for_update().get(pk=session.pk)
        if not session.is_open:
            return session
        session.status = 'ENDED'
        session.ended_at = timezone.now()
        session.ended_by = ended_by
        session.end_reason = reason[:255]
        if outcome:
            session.outcome = outcome[:4000]
        session.save()
    revoke_error = None
    if session.mesh_user and session.mesh_node_id:
        try:
            with MeshSession() as s:
                _revoke(s, session)
        except MeshError as e:
            revoke_error = str(e)
    session.metadata = {**session.metadata, 'revoke_pending': bool(revoke_error)}
    if revoke_error:
        session.metadata['revoke_error'] = revoke_error
    session.save(update_fields=['metadata'])
    _cleanup_mesh(session)
    audit(actor, 'SESSION_ENDED', session, request, ended_by=ended_by, reason=reason,
          duration_seconds=int((session.ended_at - (session.started_at or session.created_at)).total_seconds()),
          remote_consent=session.metadata.get('remote_consent'), revoke_error=revoke_error)
    return session


def retry_pending_revocations():
    for session in RemoteSession.objects.filter(status__in=('ENDED', 'EXPIRED', 'DENIED', 'FAILED'), metadata__revoke_pending=True)[:50]:
        try:
            with MeshSession() as s:
                _revoke(s, session)
            session.metadata = {**session.metadata, 'revoke_pending': False, 'revoke_retried_at': timezone.now().isoformat()}
            session.save(update_fields=['metadata'])
            _cleanup_mesh(session)
            audit(None, 'REVOCATION_COMPLETED', session)
        except MeshError as e:
            log.warning('revocation retry %s: %s', session.pk, e)


# ---------------------------------------------------------------------------
# Remote user (attended) side
# ---------------------------------------------------------------------------
def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def session_for_token(token):
    if not token or len(token) > 128:
        return None
    return RemoteSession.objects.filter(mode='ATTENDED', customer_token_hash=hash_token(token)).first()


def issue_customer_token(session, ip):
    if session.customer_consent_at:
        raise PolicyError('This session code has already been used.', 409)
    token = secrets.token_urlsafe(32)
    session.customer_token_hash = hash_token(token)
    session.customer_ip = ip
    session.save(update_fields=['customer_token_hash', 'customer_ip'])
    audit(None, 'REMOTE_USER_OPENED_INVITATION', session, ip=ip, code=session.code)
    return token


def record_consent(session, name, ip):
    if session.status != 'WAITING' or (session.expires_at and timezone.now() >= session.expires_at):
        raise PolicyError('This invitation is no longer valid.', 410)
    if not session.customer_consent_at:
        session.customer_consent_at = timezone.now()
        session.customer_name = (name or '').strip()[:150]
        session.customer_ip = ip
        session.save(update_fields=['customer_consent_at', 'customer_name', 'customer_ip'])
        audit(None, 'REMOTE_USER_CONSENTED', session, ip=ip, name=session.customer_name,
              technician=session.technician.username, capabilities=session.capabilities)
    return session


def _mesh_fetch(url):
    ctx = meshapi._ssl_context()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx))
    with opener.open(url, timeout=60) as r:
        return r.read()


def agent_package(mesh_group_id, platform, install_flags, base_name):
    """Return (filename, bytes) of the official MeshCentral agent bound to `mesh_group_id`."""
    if platform not in AGENT_PLATFORMS:
        raise PolicyError('Unsupported platform', 400)
    agent_id, suffix = AGENT_PLATFORMS[platform]
    if platform.startswith('windows'):
        data = _mesh_fetch(meshapi.agent_download_url(mesh_group_id, agent_id, install_flags))
        return base_name + suffix, data
    # Linux: agent binary plus its .msh settings file and a launcher
    binary = _mesh_fetch(meshapi.agent_download_url(mesh_group_id, agent_id, install_flags))
    msh = _mesh_fetch(meshapi.mesh_settings_url(mesh_group_id))
    if install_flags:
        msh = msh.rstrip(b'\r\n') + b'\r\nInstallFlags=%d\r\n' % install_flags
    launcher = (b'#!/bin/sh\ncd "$(dirname "$0")"\n'
                + (b'exec ./meshagent connect\n' if install_flags == 1 else b'exec sudo ./meshagent -fullinstall\n'))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for name, content, mode in (('meshagent', binary, 0o755), ('meshagent.msh', msh, 0o644), ('start.sh', launcher, 0o755)):
            info = tarfile.TarInfo(f'{base_name}/{name}')
            info.size, info.mode, info.mtime = len(content), mode, int(timezone.now().timestamp())
            tar.addfile(info, io.BytesIO(content))
    return base_name + suffix, buf.getvalue()


def customer_agent(session, platform):
    if not session.customer_consent_at:
        raise PolicyError('Approve the session before downloading the support agent.', 403)
    if session.status not in ('WAITING', 'READY', 'ACTIVE') or session.mesh_node_id:
        raise PolicyError('This invitation is no longer valid.', 410)
    # InstallFlags=1: interactive "Connect" only; nothing is installed on the remote PC.
    name, data = agent_package(session.mesh_group_id, platform, 1, f'TechGuardinas-Remote-Support-{session.code}')
    audit(None, 'REMOTE_USER_DOWNLOADED_AGENT', session, ip=session.customer_ip, platform=platform, bytes=len(data))
    return name, data
