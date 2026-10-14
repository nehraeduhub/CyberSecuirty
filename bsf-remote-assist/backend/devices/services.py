import ipaddress
from datetime import datetime
import logging

from django.core.cache import cache
from django.utils import timezone

from access.models import DeviceGroup
from remote_bridge import meshapi
from remote_bridge.meshapi import MeshSession
from remote_sessions.services import audit
from .models import Device

log = logging.getLogger('bsf')


def _ip(value):
    try:
        return str(ipaddress.ip_address(value)) if value else None
    except ValueError:
        return None


def sync_devices():
    """Mirror agents registered in managed MeshCentral groups into the portal device inventory.

    Only groups created by the portal (DeviceGroup.mesh_group_id) are considered, so per-session
    attended groups and anything created manually in MeshCentral are ignored. New devices are not
    approved unless their group is set to auto-approve."""
    groups = {g.mesh_group_id: g for g in DeviceGroup.objects.exclude(mesh_group_id='')}
    if not groups:
        return {'seen': 0, 'new': 0}
    with MeshSession() as s:
        nodes = s.nodes()
    now = timezone.now()
    seen, new = set(), 0
    for n in nodes:
        g = groups.get(n.get('meshid'))
        if g is None:
            continue
        d = Device.objects.filter(mesh_node_id=n['_id']).first()
        created = d is None
        if created:
            d = Device(mesh_node_id=n['_id'], approved=g.auto_approve)
        online = meshapi.connected(n)
        d.name = (n.get('name') or 'device')[:255]
        d.hostname = (n.get('rname') or n.get('name') or '')[:255]
        d.os = (n.get('osdesc') or '')[:255]
        d.ip_address = _ip(n.get('ip')) or d.ip_address
        d.agent_version = str((n.get('agent') or {}).get('core') or (n.get('agent') or {}).get('ver') or '')[:50]
        d.group = g.name
        d.mesh_group_id = g.mesh_group_id
        d.online = online
        d.removed = False
        if online:
            d.last_seen = now
        d.save()
        seen.add(d.pk)
        if created:
            new += 1
            audit(None, 'DEVICE_REGISTERED', d, name=d.name, group=g.name, auto_approved=g.auto_approve)
    for d in Device.objects.exclude(mesh_node_id='').filter(removed=False).exclude(pk__in=seen):
        d.removed = True
        d.online = False
        d.save(update_fields=['removed', 'online', 'updated_at'])
        audit(None, 'DEVICE_REMOVED_FROM_ENGINE', d, name=d.name)
    cache.set('devices-synced', now.isoformat(), 3600)
    return {'seen': len(seen), 'new': new}


def sync_if_stale(max_age_seconds=20):
    if cache.get('devices-sync-lock'):
        return
    last = cache.get('devices-synced')
    if last and (timezone.now() - datetime.fromisoformat(last)).total_seconds() < max_age_seconds:
        return
    cache.set('devices-sync-lock', 1, 30)
    try:
        sync_devices()
    except Exception as e:  # engine unavailable: keep serving the last known state
        log.warning('device sync failed: %s', e)
    finally:
        cache.delete('devices-sync-lock')
