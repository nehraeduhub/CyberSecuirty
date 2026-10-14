import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from devices.services import sync_devices
from remote_sessions.models import RemoteSession
from remote_sessions.services import refresh, retry_pending_revocations, sweep_attended_groups

log = logging.getLogger('bsf')


class Command(BaseCommand):
    help = ('Background worker: binds attended devices, expires invitations, enforces session limits, '
            'ends sessions whose device/technician authorization was revoked, retries failed revocations '
            'and synchronises the device inventory from MeshCentral.')

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--interval', type=int, default=5)
        parser.add_argument('--sync-every', type=int, default=30)

    def handle(self, *args, **opts):
        last_sync = 0
        while True:
            close_old_connections()
            for s in RemoteSession.objects.filter(status__in=RemoteSession.OPEN_STATUSES).select_related('technician', 'device'):
                try:
                    refresh(s)
                except Exception:
                    log.exception('refresh failed for %s', s.pk)
            try:
                retry_pending_revocations()
            except Exception:
                log.exception('revocation retry failed')
            if time.monotonic() - last_sync >= opts['sync_every']:
                for task in (sync_devices, sweep_attended_groups):
                    try:
                        task()
                    except Exception as e:
                        log.warning('%s failed: %s', task.__name__, e)
                last_sync = time.monotonic()
            if opts['once']:
                return
            time.sleep(opts['interval'])
