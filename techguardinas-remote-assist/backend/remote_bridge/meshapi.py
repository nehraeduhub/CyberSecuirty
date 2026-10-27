"""MeshCentral control-channel client used by the portal.

The portal talks to MeshCentral over its documented control websocket
(``/control.ashx``), the same channel used by MeshCentral's own web UI and by
``meshctrl.js``. Authentication uses MeshCentral's ``LoginCookieEncryptionKey``:
the portal and MeshCentral share that 80-byte key (a Docker secret), and the
portal mints short-lived AES-256-GCM cookies exactly as MeshCentral does.

Two kinds of cookie are minted:

* ``control_cookie(userid)`` - ``{userid, domainid}``: authenticates a control or
  relay websocket as ``userid`` (used by the backend service account, and by the
  messenger window opened for a technician).
* ``login_cookie(userid, minutes)`` - ``{u, a: 3, expire}``: a one-time style
  login for MeshCentral's web UI (``/?login=...``). The portal only ever mints
  these for the technician's own least-privilege MeshCentral account and only
  after the portal has authorised the session.

The key is equivalent to MeshCentral administrator access. It must only be
readable by the portal backend and MeshCentral containers.
"""
import base64
import json
import os
import re
import secrets
import socket
import ssl
import threading
import time
from urllib.parse import quote

from django.conf import settings

try:
    import websocket  # websocket-client
except ImportError:  # pragma: no cover - dependency is in requirements.txt
    websocket = None

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class MeshError(RuntimeError):
    pass


# MeshCentral device rights (meshuser.js)
RIGHT_REMOTECONTROL = 0x00000008
RIGHT_AGENTCONSOLE = 0x00000010
RIGHT_WAKEDEVICE = 0x00000040
RIGHT_REMOTEVIEWONLY = 0x00000100
RIGHT_NOTERMINAL = 0x00000200
RIGHT_NOFILES = 0x00000400
RIGHT_NOAMT = 0x00000800
RIGHT_LIMITEVENTS = 0x00002000
RIGHT_CHATNOTIFY = 0x00004000
RIGHT_NODESKTOP = 0x00010000
RIGHT_REMOTECOMMAND = 0x00020000
RIGHT_RESETOFF = 0x00040000
RIGHT_DEVICEDETAILS = 0x00100000
RIGHT_NOREGISTRY = 0x00400000
RIGHT_NOSOFTWARE = 0x00800000

# MeshCentral user-consent flags
CONSENT_DESKTOP_NOTIFY = 1
CONSENT_TERMINAL_NOTIFY = 2
CONSENT_FILES_NOTIFY = 4
CONSENT_DESKTOP_PROMPT = 8
CONSENT_TERMINAL_PROMPT = 16
CONSENT_FILES_PROMPT = 32
CONSENT_TOOLBAR = 64

# MeshCentral site rights for the per-technician accounts: no new groups,
# no MeshCmd, no new devices. They hold no device rights until the portal
# grants rights on one device for one session.
SITE_NONEWGROUPS = 0x40
SITE_NOMESHCMD = 0x80
SITE_NONEWDEVICES = 0x1000
TECH_SITE_RIGHTS = SITE_NONEWGROUPS | SITE_NOMESHCMD | SITE_NONEWDEVICES

# Mesh group feature flag: record sessions (used with sessionRecording.onlySelectedDeviceGroups)
MESH_FLAG_RECORD_SESSIONS = 4

# MeshCentral power actions
POWER_OFF = 2
POWER_RESET = 3

_key_cache = {}


def _login_key():
    path = getattr(settings, 'MESH_LOGIN_KEY_FILE', '')
    if not path:
        raise MeshError('MESH_LOGIN_KEY_FILE is not configured')
    if path not in _key_cache:
        try:
            raw = open(path, 'r', encoding='utf-8').read()
        except OSError as e:
            raise MeshError(f'Cannot read MeshCentral login key: {e}')
        raw = re.sub(r'\s+', '', raw)
        try:
            key = bytes.fromhex(raw)
        except ValueError:
            raise MeshError('MeshCentral login key must be hex')
        if len(key) != 80:
            raise MeshError('MeshCentral login key must be 80 bytes (160 hex characters)')
        _key_cache[path] = key
    return _key_cache[path]


def encode_cookie(obj, key=None):
    """Encode like MeshCentral's encodeCookie(): AES-256-GCM, iv|tag|ciphertext, '+'->'@', '/'->'$'."""
    key = key or _login_key()
    payload = dict(obj)
    payload['time'] = int(time.time())
    iv = secrets.token_bytes(12)
    ct_and_tag = AESGCM(key[:32]).encrypt(iv, json.dumps(payload, separators=(',', ':')).encode(), None)
    ct, tag = ct_and_tag[:-16], ct_and_tag[-16:]
    return base64.b64encode(iv + tag + ct).decode().replace('+', '@').replace('/', '$')


def decode_cookie(cookie, key=None):
    key = key or _login_key()
    buf = base64.b64decode(cookie.replace('@', '+').replace('$', '/'))
    iv, tag, ct = buf[:12], buf[12:28], buf[28:]
    return json.loads(AESGCM(key[:32]).decrypt(iv, ct + tag, None))


def domain_id():
    return getattr(settings, 'MESH_DOMAIN', '')


def user_id(username):
    return f'user/{domain_id()}/{username.lower()}'


def full_node_id(node_id):
    return node_id if node_id.startswith('node/') else f'node/{domain_id()}/{node_id}'


def short_id(full_id):
    return full_id.split('/')[-1]


def node_hex(node_id):
    """MeshCentral's web UI accepts a 96-character hex node id in ?gotonode= (avoids '$'/'@' escaping issues)."""
    raw = short_id(full_node_id(node_id)).replace('@', '+').replace('$', '/')
    return base64.b64decode(raw).hex().upper()


def control_cookie(userid):
    return encode_cookie({'userid': userid, 'domainid': domain_id()})


def login_cookie(userid, minutes=1):
    return encode_cookie({'u': userid, 'a': 3, 'expire': int(minutes)})


def _ssl_context():
    ctx = ssl.create_default_context(cafile=getattr(settings, 'MESH_CA_BUNDLE', '') or None)
    if not getattr(settings, 'MESH_TLS_VERIFY', True):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def control_url():
    url = getattr(settings, 'MESH_CONTROL_URL', '')
    if not url:
        base = settings.MESH_PUBLIC_URL.rstrip('/')
        url = base.replace('https://', 'wss://', 1).replace('http://', 'ws://', 1) + '/control.ashx'
    return url


class MeshSession:
    """One authenticated control websocket. Use as a context manager."""

    def __init__(self, username=None, timeout=None):
        if websocket is None:
            raise MeshError('websocket-client is not installed')
        self.username = username or settings.MESH_SERVICE_USER
        self.userid = user_id(self.username)
        self.timeout = timeout or getattr(settings, 'MESH_ACTION_TIMEOUT', 30)
        self.ws = None
        self._backlog = []
        self._lock = threading.Lock()

    def __enter__(self):
        url = control_url() + '?auth=' + quote(control_cookie(self.userid), safe='')
        try:
            # Internal traffic only: open the TCP connection directly so no proxy setting from the
            # environment can divert portal -> MeshCentral traffic.
            hostport = url.split('://', 1)[1].split('/', 1)[0]
            host, _, port = hostport.partition(':')
            secure = url.startswith('wss')
            sock = socket.create_connection((host, int(port or (443 if secure else 80))), timeout=self.timeout)
            if secure:
                sock = _ssl_context().wrap_socket(sock, server_hostname=host)
            self.ws = websocket.create_connection(url, timeout=self.timeout, header=['User-Agent: techguardinas-remote-portal'], socket=sock)
        except Exception as e:
            raise MeshError(f'Cannot connect to MeshCentral control channel: {e}')
        # The server sends 'serverinfo' and 'userinfo' first; 'close' means auth failed.
        first = self._recv_until(lambda m: m.get('action') in ('serverinfo', 'userinfo', 'close'))
        if first.get('action') == 'close':
            self.close()
            raise MeshError(f"MeshCentral rejected the portal credentials ({first.get('cause') or first.get('msg')})")
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None

    def _recv_until(self, predicate):
        for i, m in enumerate(self._backlog):
            if predicate(m):
                return self._backlog.pop(i)
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                raw = self.ws.recv()
            except websocket.WebSocketTimeoutException:
                break
            except Exception as e:
                raise MeshError(f'MeshCentral connection error: {e}')
            if not raw:
                continue
            try:
                m = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if predicate(m):
                return m
            if m.get('action') == 'close':
                raise MeshError(f"MeshCentral closed the session ({m.get('cause') or m.get('msg')})")
            if len(self._backlog) < 200 and m.get('action') not in ('event', 'pong'):
                self._backlog.append(m)
        raise MeshError('Timed out waiting for MeshCentral')

    def send(self, action, **fields):
        self.ws.send(json.dumps({'action': action, **fields}))

    def call(self, action, expect_action=None, check=True, timeout=None, **fields):
        """Send a command and wait for its reply (matched by responseid or tag)."""
        rid = 'techguardinas' + secrets.token_hex(6)
        with self._lock:
            self.send(action, responseid=rid, tag=rid, **fields)
            saved, self.timeout = self.timeout, (timeout or self.timeout)
            try:
                reply = self._recv_until(lambda m: (m.get('responseid') == rid or m.get('tag') == rid)
                                         and (expect_action is None or m.get('action') == expect_action))
            finally:
                self.timeout = saved
        result = reply.get('result')
        if check and isinstance(result, str) and result.lower() not in ('ok', ''):
            raise MeshError(f'MeshCentral {action} failed: {result}')
        return reply

    # ---- read operations -------------------------------------------------
    def meshes(self):
        return self.call('meshes', expect_action='meshes').get('meshes', [])

    def nodes(self, meshid=None):
        fields = {'meshid': meshid} if meshid else {}
        reply = self.call('nodes', expect_action='nodes', **fields)
        out = []
        for gid, nodes in (reply.get('nodes') or {}).items():
            for n in nodes:
                n.setdefault('meshid', gid)
                out.append(n)
        return out

    def users(self):
        return self.call('users', expect_action='users').get('users', [])

    def events(self, nodeid, limit=200):
        return self.call('events', expect_action='events', nodeid=full_node_id(nodeid), limit=limit).get('events', [])

    # ---- groups ------------------------------------------------------------
    def create_mesh(self, name, desc='', consent=0, flags=0):
        reply = self.call('createmesh', meshname=name, meshtype=2, desc=desc, consent=consent, flags=flags)
        return reply['meshid']

    def edit_mesh(self, meshid, **fields):
        return self.call('editmesh', meshid=meshid, **fields)

    def delete_mesh(self, meshid):
        return self.call('deletemesh', meshid=meshid)

    def remove_devices(self, nodeids):
        return self.call('removedevices', nodeids=[full_node_id(n) for n in nodeids])

    # ---- users and rights --------------------------------------------------
    def ensure_user(self, username, realname=''):
        uid = user_id(username)
        if any(u.get('_id') == uid for u in self.users()):
            return uid
        try:
            self.call('adduser', username=username.lower(), realname=realname[:64] or username,
                      randomPassword=True, siteadmin=TECH_SITE_RIGHTS, emailVerified=True)
        except MeshError as e:
            if 'already exists' not in str(e).lower():
                raise
        return uid

    def set_device_rights(self, nodeid, userid, rights):
        return self.call('adddeviceuser', nodeid=full_node_id(nodeid), userids=[userid], rights=int(rights))

    def remove_device_rights(self, nodeid, userid, timeout=10):
        # MeshCentral sends no reply when the node no longer exists, hence the short timeout.
        return self.call('adddeviceuser', timeout=timeout, nodeid=full_node_id(nodeid), userids=[userid], rights=0, remove=True)

    def server_console(self, cmd):
        return self.call('serverconsole', check=False, value=cmd).get('value', '')

    def close_user_sessions(self, userid):
        return self.call('serverconsole', check=False, timeout=10, value='closeusersessions ' + userid).get('value', '')

    def end_desktop(self, nodeid, userid):
        # No reply is sent on success; fire and forget.
        self.send('endDesktopMultiplex', nodeid=full_node_id(nodeid), xuserid=userid)

    def agent_disconnect(self, nodeid):
        self.send('agentdisconnect', nodeid=full_node_id(nodeid), disconnectMode=1)

    # ---- device actions ----------------------------------------------------
    def power(self, nodeid, actiontype):
        return self.call('poweraction', nodeids=[full_node_id(nodeid)], actiontype=int(actiontype))

    def run_commands(self, nodeid, cmds, cmd_type=2, runAsUser=0, reply=True):
        fields = dict(nodeids=[full_node_id(nodeid)], type=int(cmd_type), cmds=cmds, runAsUser=int(runAsUser))
        if reply:
            fields['reply'] = True
        return self.call('runcommands', check=False, **fields)

    def mesh_messenger(self, nodeid):
        self.send('meshmessenger', nodeid=full_node_id(nodeid))


def connected(node):
    """True when the MeshCentral agent for this node is connected."""
    return bool((node.get('conn') or 0) & 1)


def agent_download_url(meshid, agent_id, install_flags):
    """Server-side URL for the official agent with the group's .msh embedded."""
    base = getattr(settings, 'MESH_INTERNAL_URL', '') or settings.MESH_PUBLIC_URL
    return f"{base.rstrip('/')}/meshagents?id={int(agent_id)}&meshid={quote(short_id(meshid), safe='')}&installflags={int(install_flags)}"


def mesh_settings_url(meshid):
    base = getattr(settings, 'MESH_INTERNAL_URL', '') or settings.MESH_PUBLIC_URL
    return f"{base.rstrip('/')}/meshsettings?id={quote(short_id(meshid), safe='')}"


def console_url(username, nodeid, viewmode=11, hide=None):
    """Login URL that opens MeshCentral's device view for one node as the technician account.

    viewmode: 10 general, 11 desktop, 12 terminal, 13 files, 16 events.
    hide: bitmask - 1 header, 2 tab bar, 4 footer, 8 title, 16 left bar, 32 back button.
    """
    if hide is None:
        hide = getattr(settings, 'MESH_CONSOLE_HIDE', 1 | 4 | 16 | 32)
    token = login_cookie(user_id(username), minutes=getattr(settings, 'MESH_LOGIN_TOKEN_MINUTES', 1))
    return (f"{settings.MESH_PUBLIC_URL.rstrip('/')}/?login={quote(token, safe='')}"
            f"&gotonode={node_hex(nodeid)}&viewmode={int(viewmode)}&hide={int(hide)}")


def messenger_url(username, nodeid, title):
    nid = full_node_id(nodeid)
    uid = user_id(username)
    cookie = control_cookie(uid)
    return (f"{settings.MESH_PUBLIC_URL.rstrip('/')}/messenger?id="
            f"meshmessenger/{quote(nid, safe='')}/{quote(uid, safe='')}"
            f"&title={quote(title, safe='')}&auth={quote(cookie, safe='')}")
