import json, os, subprocess
from django.conf import settings

class MeshCtrlError(RuntimeError): pass

def _base_args():
    path = getattr(settings, 'MESHCTRL_PATH', '')
    if not path: raise MeshCtrlError('MESHCTRL_PATH is not configured')
    args = [path]
    url = getattr(settings, 'MESHCTRL_URL', '') or getattr(settings, 'MESH_BASE_URL', '')
    if url: args += ['--url', url]
    user = getattr(settings, 'MESH_ADMIN_USER', '')
    password = getattr(settings, 'MESH_ADMIN_PASSWORD', '')
    keyfile = getattr(settings, 'MESH_LOGIN_KEY_FILE', '')
    if keyfile:
        args += ['--loginkeyfile', keyfile]
        if user: args += ['--loginuser', user]
    elif user and password:
        args += ['--loginuser', user, '--loginpass', password]
    else: raise MeshCtrlError('MeshCentral service credentials/key are not configured')
    return args

def run(action, extra=None, timeout=30):
    cmd = _base_args() + [action] + (extra or [])
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if p.returncode != 0:
        raise MeshCtrlError((p.stderr or p.stdout or 'meshctrl failed').strip()[:2000])
    raw = p.stdout.strip()
    try: return json.loads(raw)
    except Exception: return {'raw': raw}

def device_info(node_id): return run('DeviceInfo', ['--id', node_id, '--json'])
def list_devices(): return run('ListDevices', ['--json'])
def run_command(node_id, command, command_type=2, run_as_user=0):
    return run('RunCommand', ['--id', node_id, '--type', str(command_type), '--cmds', command, '--runasuser', str(run_as_user), '--json'], timeout=60)
def power(node_id, action_type):
    return run('DevicePower', ['--id', node_id, '--actiontype', str(action_type), '--json'])
