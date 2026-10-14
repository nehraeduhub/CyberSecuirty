import re, secrets, subprocess
from django.conf import settings
from .meshctrl import run, MeshCtrlError

class MeshSSOError(RuntimeError):
    pass

_SAFE = re.compile(r'[^A-Za-z0-9._-]')

def _mesh_username(portal_user):
    base = getattr(portal_user, 'ad_username', '') or getattr(portal_user, 'username', '')
    base = _SAFE.sub('-', base).strip('-').lower()[:48]
    if not base:
        raise MeshSSOError('Portal user has no usable username')
    return f"bsf-{base}-{str(portal_user.id)[:8]}"

def ensure_mesh_user(portal_user, device):
    """Create a least-privilege MeshCentral user and grant it only the device group.
    Requires mesh_group_id to be populated on the BSF device."""
    if not device.mesh_group_id:
        raise MeshSSOError('Device is not mapped to a MeshCentral device group')
    username = _mesh_username(portal_user)
    # We do not persist the random password: portal uses a short-lived login token instead.
    password = secrets.token_urlsafe(32)
    extra = ['--user', username, '--pass', password, '--emailverified', '--remotecontrol', '--managedevices']
    # Do not grant site-admin or broad server rights.
    try:
        run('AddUser', extra, timeout=30)
    except MeshCtrlError as e:
        # Existing user is acceptable; any other error is fatal.
        if 'already' not in str(e).lower() and 'exist' not in str(e).lower():
            raise MeshSSOError(f'MeshCentral user provisioning failed: {e}')
    try:
        run('AddUserToDeviceGroup', ['--id', device.mesh_group_id, '--userid', username, '--remotecontrol'], timeout=30)
    except MeshCtrlError as e:
        if 'already' not in str(e).lower() and 'exist' not in str(e).lower():
            raise MeshSSOError(f'MeshCentral group authorization failed: {e}')
    return username

def create_login_token(mesh_user):
    # Generate the documented short-lived MeshCentral login token on the MeshCentral host.
    # This command must run where the MeshCentral installation is available.
    node_bin = getattr(settings, 'MESH_NODE_BIN', 'node')
    meshcentral_entry = getattr(settings, 'MESH_SERVER_ENTRY', '')
    if not meshcentral_entry:
        raise MeshSSOError('MESH_SERVER_ENTRY is not configured')
    domain = getattr(settings, 'MESH_SSO_DOMAIN', '')
    userid = f'user/{domain}/{mesh_user}'
    cmd = [node_bin, meshcentral_entry, '--logintoken', userid]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
    if p.returncode != 0:
        raise MeshSSOError((p.stderr or p.stdout or 'MeshCentral login-token generation failed').strip()[:1000])
    token = p.stdout.strip().splitlines()[-1].strip()
    if not token or len(token) < 20:
        raise MeshSSOError('MeshCentral returned an invalid login token')
    return token
