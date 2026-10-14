#!/usr/bin/env python3
"""End-to-end acceptance test for BSF Remote (portal + MeshCentral + real agents).

Drives the real browser UI as administrator, technician and remote user, and two real
MeshCentral agents running on test endpoints with their own X displays. Verifies the
remote-control engine state directly (rights, live tunnels, groups) and writes evidence
(screenshots + JSON report) to $EVIDENCE_DIR.

This is the harness used for the Linux test endpoints described in docs/ACCEPTANCE-TEST.md.
The Windows acceptance procedure is manual and uses the same portal workflow.

Environment (see tests/local-stack/stack.env.example):
  PORTAL_URL, CA_BUNDLE, ADMIN_USER, ADMIN_PASSWORD, EVIDENCE_DIR, AGENT_ROOT,
  PC1_DISPLAY, PC2_DISPLAY, CHROMIUM, BACKEND_DIR (for engine-side verification), MESH_*
"""
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import time
import traceback
from datetime import datetime, timezone

import pyotp
import requests
from playwright.sync_api import sync_playwright

PORTAL = os.environ.get('PORTAL_URL', 'https://remote.bsf.test')
CA = os.environ.get('CA_BUNDLE')
ADMIN = (os.environ.get('ADMIN_USER', 'bsfadmin'), os.environ['ADMIN_PASSWORD'])
EVID = os.environ.get('EVIDENCE_DIR', '/tmp/bsf-evidence')
AGENT_ROOT = os.environ.get('AGENT_ROOT', '/tmp/bsf-agents')
PC1 = os.environ.get('PC1_DISPLAY', ':5')   # attended test PC (remote user present)
PC2 = os.environ.get('PC2_DISPLAY', ':6')   # unattended managed test PC
CHROMIUM = os.environ.get('CHROMIUM', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
CAPSH = os.environ.get('CAPSH', '/usr/sbin/capsh')
TECH1 = ('tech1', 'Tech1-Passw0rd-Long!')
TECH2 = ('tech2', 'Tech2-Passw0rd-Long!')
GROUP = 'HQ-IT'

os.makedirs(EVID, exist_ok=True)
os.makedirs(AGENT_ROOT, exist_ok=True)
RESULTS = []
CONTEXT = {}


# ------------------------------------------------------------------ helpers
def log(msg):
    print(f'[{datetime.now().strftime("%H:%M:%S")}] {msg}', flush=True)


def check(name, ok, detail=''):
    RESULTS.append({'check': name, 'pass': bool(ok), 'detail': detail})
    log(('PASS ' if ok else 'FAIL ') + name + (f' — {detail}' if detail else ''))
    return ok


def wait_for(fn, timeout=60, interval=1.0, what='condition'):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            last = fn()
            if last:
                return last
        except Exception as e:  # noqa: BLE001 - polling
            last = e
        time.sleep(interval)
    raise TimeoutError(f'timed out waiting for {what} (last={last!r})')


class Api:
    def __init__(self, user=None):
        self.s = requests.Session()
        self.s.verify = CA or True
        self.s.trust_env = False
        self.s.get(PORTAL + '/api/access/csrf/')
        if user:
            r = self.post('/api/access/login/', {'username': user[0], 'password': user[1]})
            assert r.ok, r.text

    def _h(self):
        return {'X-CSRFToken': self.s.cookies.get('csrftoken', ''), 'Referer': PORTAL + '/'}

    def get(self, p):
        return self.s.get(PORTAL + p)

    def post(self, p, j=None):
        return self.s.post(PORTAL + p, json=j or {}, headers=self._h())


def xdo(display, *args):
    return subprocess.run(['xdotool', *args], env={'DISPLAY': display}, capture_output=True, text=True).stdout.strip()


def window_titles(display):
    ids = xdo(display, 'search', '--onlyvisible', '--name', '.').split()
    return {i: xdo(display, 'getwindowname', i) for i in ids}


def screen(display, name):
    path = os.path.join(EVID, name)
    subprocess.run(['import', '-window', 'root', path], env={'DISPLAY': display}, check=False)
    return path


def shot(page, name):
    page.screenshot(path=os.path.join(EVID, name))


def answer_consent(display, allow=True, timeout=30):
    """Act as the remote user: click Yes/No on the agent's on-screen consent prompt."""
    wid = wait_for(lambda: next((i for i, t in window_titles(display).items() if 'BSF Remote Support Agent' in t), None),
                   timeout=timeout, what='consent prompt')
    geo = xdo(display, 'getwindowgeometry', wid)
    w, h = map(int, re.search(r'Geometry: (\d+)x(\d+)', geo).groups())
    screen(display, f'remote-consent-prompt-{display[1:]}.png')
    x = int(w * (0.75 if allow else 0.25))
    xdo(display, 'mousemove', '--window', wid, str(x), str(h - 22), 'click', '1')
    return True


def start_agent(pkg_bytes, name, display, mode):
    """Unpack the agent package downloaded from the portal and run it as the endpoint would.
    CAP_SYS_BOOT is dropped so a real 'reboot' command cannot reboot the test host itself."""
    d = os.path.join(AGENT_ROOT, name)
    os.makedirs(d, exist_ok=True)
    tarfile.open(fileobj=io.BytesIO(pkg_bytes)).extractall(d, filter='tar')
    sub = os.path.join(d, os.listdir(d)[0])
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/root', 'DISPLAY': display, 'BSF_TEST_DISPLAY': display}
    p = subprocess.Popen(['setsid', CAPSH, '--drop=cap_sys_boot', '--', '-c', f'exec ./meshagent {mode}'],
                         cwd=sub, env=env, stdout=open(os.path.join(sub, 'agent.log'), 'a'), stderr=subprocess.STDOUT)
    return {'dir': sub, 'proc': p, 'mode': mode, 'display': display}


def stop_agent(agent):
    for pid in subprocess.run(['pgrep', '-x', 'meshagent'], capture_output=True, text=True).stdout.split():
        try:
            if os.readlink(f'/proc/{pid}/cwd') == agent['dir']:
                os.kill(int(pid), 9)
        except OSError:
            pass


def agent_running(agent):
    for pid in subprocess.run(['pgrep', '-x', 'meshagent'], capture_output=True, text=True).stdout.split():
        try:
            if os.readlink(f'/proc/{pid}/cwd') == agent['dir']:
                return True
        except OSError:
            pass
    return False


def restart_agent(agent):
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/root', 'DISPLAY': agent['display'], 'BSF_TEST_DISPLAY': agent['display']}
    agent['proc'] = subprocess.Popen(['setsid', CAPSH, '--drop=cap_sys_boot', '--', '-c', f"exec ./meshagent {agent['mode']}"],
                                     cwd=agent['dir'], env=env, stdout=open(os.path.join(agent['dir'], 'agent.log'), 'a'), stderr=subprocess.STDOUT)


_last_totp = {}


def totp(secret):
    t = pyotp.TOTP(secret)
    code = t.now()
    while _last_totp.get(secret) == code:  # step-up codes are single-use; wait for the next time step
        time.sleep(2)
        code = t.now()
    _last_totp[secret] = code
    return code


# ----------------------------------------------- engine-side verification
def mesh():
    sys.path.insert(0, os.environ['BACKEND_DIR'])
    import django
    from django.conf import settings
    if not settings.configured:
        settings.configure(MESH_LOGIN_KEY_FILE=os.environ['MESH_LOGIN_KEY_FILE'], MESH_PUBLIC_URL=os.environ['MESH_PUBLIC_URL'],
                           MESH_CA_BUNDLE=CA or '', MESH_TLS_VERIFY=True, MESH_SERVICE_USER=os.environ.get('MESH_SERVICE_USER', 'bsf-portal-svc'),
                           MESH_DOMAIN='', MESH_ACTION_TIMEOUT=20)
        django.setup()
    from remote_bridge import meshapi
    return meshapi


def agent_tunnels(node_id):
    m = mesh()
    with m.MeshSession() as s:
        s.send('msg', type='console', nodeid=node_id, value='tunnels')
        r = s._recv_until(lambda x: x.get('action') == 'msg' and x.get('type') == 'console' and x.get('value'))
        return r['value']


def node_links(node_id):
    m = mesh()
    with m.MeshSession() as s:
        n = next((x for x in s.nodes() if x['_id'] == node_id), None)
        return (n or {}).get('links', {}), n


# ------------------------------------------------------------------ UI flows
def ui_login(page, user):
    page.goto(PORTAL + '/')
    page.get_by_placeholder('Username').fill(user[0])
    page.get_by_placeholder('Password').fill(user[1])
    page.get_by_role('button', name='Sign in').click()
    page.get_by_role('button', name='Sign out').wait_for(timeout=15000)


def go(page, path):
    page.evaluate(f"window.history.pushState({{}}, '', '{path}'); window.dispatchEvent(new PopStateEvent('popstate'))")
    page.wait_for_timeout(800)


def console_frame(page):
    page.wait_for_selector('[data-testid=console-frame]', timeout=20000)
    page.wait_for_timeout(1500)
    return page.frame_locator('[data-testid=console-frame]'), mesh_frame(page)


def mesh_frame(page):
    host = os.environ.get('MESH_PUBLIC_URL', 'https://mesh.')
    frames = [f for f in page.frames if f != page.main_frame and f.url.startswith(host)]
    if not frames:
        raise LookupError('no MeshCentral frame; frames=' + ', '.join(f.url[:80] for f in page.frames))
    return frames[0]


def frame_eval(page, js):
    loc = page.frame_locator('[data-testid=console-frame]').locator('html')
    return loc.evaluate(f'() => ({js})', timeout=5000)


def desktop_connect(page, pre_click=None):
    wait_for(lambda: frame_eval(page, "!!(document.getElementById('connectbutton1') && !document.getElementById('connectbutton1').disabled)"),
             30, what='desktop connect button')
    frame_eval(page, "document.getElementById('connectbutton1').click()")
    if pre_click:
        pre_click()
    wait_for(lambda: frame_eval(page, "document.getElementById('deskstatus').textContent") == 'Connected', 40, what='desktop connected')
    page.wait_for_timeout(3000)


def type_on_remote(page, text):
    canvas = page.frame_locator('[data-testid=console-frame]').locator('#Desk')
    bb = canvas.bounding_box()
    # The test PC's input box is centred at (640, 440) of a 1280x800 screen. Move the pointer into the console
    # first, as a user does (the portal focuses the console frame on mouse-enter), then click and type.
    x, y = bb['x'] + bb['width'] * 640 / 1280, bb['y'] + bb['height'] * 440 / 800
    page.mouse.move(x - 50, y - 50)
    page.mouse.move(x, y, steps=5)
    page.mouse.click(x, y)
    page.wait_for_timeout(500)
    page.keyboard.type(text, delay=80)
    page.wait_for_timeout(1500)


# ================================================================== scenario
def main():
    started = datetime.now(timezone.utc)
    CONTEXT['portal'] = PORTAL
    CONTEXT['network'] = subprocess.run(['ip', '-brief', 'addr'], capture_output=True, text=True).stdout
    CONTEXT['routes'] = subprocess.run(['ip', 'route'], capture_output=True, text=True).stdout
    try:
        r = requests.get('https://example.com', timeout=5)
        internet = f'reachable (HTTP {r.status_code})'
    except Exception as e:  # noqa: BLE001
        internet = f'unreachable: {type(e).__name__}'
    CONTEXT['internet_check'] = internet
    log(f'Internet check from test host: {internet}')

    admin = Api(ADMIN)
    check('Portal health and admin login', admin.get('/api/me/').json().get('role') == 'SUPERADMIN')

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM)

        external = []
        internal_hosts = {re.sub(r'^https?://', '', PORTAL).split('/')[0],
                          re.sub(r'^https?://', '', os.environ.get('MESH_PUBLIC_URL', '')).split('/')[0]}

        def note_request(req):
            host = re.sub(r'^[a-z]+://', '', req.url).split('/')[0].split(':')[0]
            if req.url.startswith(('http', 'ws')) and host not in internal_hosts:
                external.append(req.url)

        def ctx():
            c = browser.new_context(ignore_https_errors=not CA, viewport={'width': 1500, 'height': 950}, accept_downloads=True)
            c.on('request', note_request)
            CONTEXT.setdefault('_contexts', []).append(c)
            return c

        try:
            # ---------------------------------------------------------- admin setup (UI)
            ac = ctx(); ap = ac.new_page()
            ui_login(ap, ADMIN)
            shot(ap, '01-admin-dashboard.png')
            go(ap, '/admin/users')
            for u in (TECH1, TECH2):
                if not any(x['username'] == u[0] for x in admin.get('/api/access/users/').json()):
                    ap.get_by_placeholder('Username').fill(u[0])
                    ap.get_by_placeholder('Initial password (min 12 chars)').fill(u[1])
                    ap.get_by_role('button', name='Create').click()
                    ap.wait_for_timeout(1000)
            users = {x['username']: x for x in admin.get('/api/access/users/').json()}
            check('Admin created technician accounts in the portal', 'tech1' in users and 'tech2' in users)
            go(ap, '/admin/groups')
            if not any(g['name'] == GROUP for g in admin.get('/api/access/groups/').json()):
                ap.get_by_placeholder('Group name, e.g. HQ-IT').fill(GROUP)
                ap.locator('label.check', has_text='Record sessions').locator('input').check()
                ap.get_by_role('button', name='Create group').click()
                ap.wait_for_timeout(1500)
            group = next(g for g in admin.get('/api/access/groups/').json() if g['name'] == GROUP)
            check('Device group created and linked to a MeshCentral device group', group['linked'], json.dumps(group))
            shot(ap, '02-admin-groups-agent-installers.png')

            # Agent installer from the internal portal (Windows build verified for embedded internal URL)
            win = admin.get(f"/api/access/groups/{group['id']}/agent/windows-x64/")
            msh_ok = win.ok and win.content[:2] == b'MZ' and b'MeshServer=wss://' in win.content
            server_line = re.search(rb'MeshServer=([^\r\n]+)', win.content)
            check('Windows agent installer served by internal portal with internal server URL embedded', msh_ok,
                  server_line.group(1).decode() if server_line else 'no MeshServer line')
            pkg = admin.get(f"/api/access/groups/{group['id']}/agent/linux-x64/")
            check('Managed agent package downloaded from portal', pkg.ok, f'{len(pkg.content)} bytes')

            # ---------------------------------------------------------- unattended endpoint registers
            pc2 = start_agent(pkg.content, 'pc2-managed', PC2, 'run')
            dev = wait_for(lambda: next((d for d in admin.get('/api/devices/').json() if d['group'] == GROUP and d['online'] and not d['removed']), None),
                           90, 2, 'managed device to register')
            CONTEXT['pc2_device'] = dev
            check('Managed endpoint registered with internal MeshCentral and appears in portal', bool(dev), f"{dev['name']} {dev['os']}")
            check('Newly registered device is NOT approved (pending)', dev['approved'] is False)

            # Before approval nobody can connect, even with the agent installed.
            r = admin.post('/api/sessions/unattended/', {'device_id': dev['id']})
            check('Connect refused while device is pending approval (agent installed is not enough)',
                  r.status_code == 403 and 'not authorized' in r.text, r.text)

            go(ap, '/admin/devices')
            ap.wait_for_timeout(1000)
            shot(ap, '03-admin-device-pending.png')
            ap.get_by_role('button', name='Approve').first.click()
            ap.wait_for_timeout(1500)
            check('Administrator approved the device', next(d for d in admin.get('/api/devices/').json() if d['id'] == dev['id'])['approved'])

            go(ap, '/admin/permissions')
            ap.wait_for_timeout(1000)
            ap.locator('select').nth(0).select_option(label='tech1')
            ap.locator('select').nth(1).select_option(value=f"g:{group['id']}")
            for label in ('File transfer', 'Terminal', 'Reboot'):
                box = ap.locator('label.check', has_text=label).locator('input')
                if not box.is_checked():
                    box.check()
            ap.get_by_role('button', name='Save').click()
            ap.wait_for_timeout(1000)
            shot(ap, '04-admin-permissions.png')
            perms = admin.get('/api/access/permissions/').json()
            check('tech1 granted group permission (connect, files, terminal, reboot)',
                  any(p['username'] == 'tech1' and p['group'] == GROUP and p['can_terminal'] and p['can_reboot'] for p in perms))

            # ---------------------------------------------------------- negative authorization checks
            t2 = Api(TECH2)
            check('Unauthorized technician does not see the device', all(d['id'] != dev['id'] for d in t2.get('/api/devices/').json()))
            r = t2.post('/api/sessions/unattended/', {'device_id': dev['id']})
            check('Unauthorized technician is refused by the server', r.status_code == 403, r.text)
            t1 = Api(TECH1)
            r = t1.post('/api/sessions/unattended/', {'device_id': dev['id']})
            check('Authorized technician without MFA step-up is refused', r.status_code == 403, r.text)

            # Engine level: the technician MeshCentral accounts hold no standing device rights.
            m = mesh()
            with m.MeshSession() as s:
                gid = next(g['_id'] for g in s.meshes() if g['name'] == f'BSF-{GROUP}')
                node = next(n for n in s.nodes(gid) if m.connected(n))
            node_id = node['_id']
            CONTEXT['pc2_node'] = node_id
            tech_links = [k for k in (node.get('links') or {}) if k.startswith('user//bsftech-')]
            check('No technician MeshCentral account has standing rights on the endpoint', not tech_links, str(node.get('links')))

            # ---------------------------------------------------------- tech1 enrolls MFA (UI)
            tc = ctx(); tp = tc.new_page()
            ui_login(tp, TECH1)
            go(tp, '/settings')
            secret = None
            if not t1.get('/api/me/').json()['mfa_enabled']:
                tp.get_by_role('button', name='Configure authenticator').click()
                secret = tp.locator('.mfa code').inner_text(timeout=10000).strip()
                shot(tp, '05-tech-mfa-enrollment.png')
                tp.get_by_placeholder('6-digit code').fill(totp(secret))
                tp.get_by_role('button', name='Verify and enable').click()
                tp.wait_for_timeout(1500)
                CONTEXT['tech1_totp_secret_file'] = os.path.join(EVID, '.tech1-totp')
                open(CONTEXT['tech1_totp_secret_file'], 'w').write(secret)
            else:
                secret = open(os.path.join(EVID, '.tech1-totp')).read().strip()
            check('Technician enrolled TOTP MFA', t1.get('/api/me/').json()['mfa_enabled'])

            # ---------------------------------------------------------- UNATTENDED SESSION
            go(tp, '/devices')
            tp.wait_for_timeout(2000)
            shot(tp, '06-tech-authorized-devices.png')
            tp.once('dialog', lambda d: d.accept(totp(secret)))
            tp.get_by_role('button', name='Connect').first.click()
            tp.wait_for_url(re.compile(r'.*/console/.*'), timeout=30000)
            sid = tp.url.rsplit('/', 1)[-1]
            CONTEXT['unattended_session'] = sid
            check('Unattended connect authorized after MFA step-up; console opened', True, sid)
            links, _ = node_links(node_id)
            tech1_uid = next((k for k in links if k.startswith('user//bsftech-')), None)
            check('Rights granted on exactly this endpoint for the session (device-level link)', bool(tech1_uid), str(links))

            desktop_connect(tp)
            shot(tp, '07-unattended-remote-desktop.png')
            check('Remote desktop of PC-2 visible in browser console (frame connected)', True)
            type_on_remote(tp, 'unattended-ok')
            title_ok = wait_for(lambda: any('PC2 typed:unattended-ok' in t for t in window_titles(PC2).values()), 15, what='typed text on PC-2')
            screen(PC2, '08-pc2-screen-after-typing.png')
            check('Keyboard and mouse input reached PC-2 (window title changed on the endpoint)', bool(title_ok))

            # Terminal
            tp.get_by_role('button', name='Terminal').click()
            tp.wait_for_timeout(2500)
            wait_for(lambda: frame_eval(tp, "!!(document.getElementById('connectbutton2') && !document.getElementById('connectbutton2').disabled)"), 30, what='terminal button')
            frame_eval(tp, "document.getElementById('connectbutton2').click()")
            wait_for(lambda: frame_eval(tp, "document.getElementById('termstatus').textContent") == 'Connected', 30, what='terminal connected')
            tp.wait_for_timeout(2500)
            tp.frame_locator('[data-testid=console-frame]').locator('#termarea3xdiv').click()
            tp.keyboard.type('echo BSF-TERMINAL-$((6*7)) && hostname\n', delay=40)
            out = wait_for(lambda: (lambda t: t if 'BSF-TERMINAL-42' in t else None)(
                frame_eval(tp, "(document.querySelector('#termarea3xdiv .xterm-rows')||{}).innerText||''")), 20, what='terminal output')
            shot(tp, '09-unattended-terminal.png')
            check('Remote terminal executed a command on PC-2', 'BSF-TERMINAL-42' in out)

            # Files
            tp.get_by_role('button', name='Files').click()
            tp.wait_for_timeout(2500)
            wait_for(lambda: frame_eval(tp, "!!document.getElementById('p13Connect')"), 20, what='files tab')
            if frame_eval(tp, "document.getElementById('p13Status').textContent") != 'Connected':
                frame_eval(tp, "document.getElementById('p13Connect').click()")
            listing = wait_for(lambda: (lambda t: t if len(t) > 20 else None)(frame_eval(tp, "document.getElementById('p13files').innerText")), 30, what='file listing')
            shot(tp, '10-unattended-files.png')
            check('Remote file browser connected (file transfer channel)', bool(listing), listing[:120].replace('\n', ' '))

            # Chat
            with tp.expect_popup(timeout=15000) as pop:
                tp.get_by_role('button', name='Chat').click()
            chat = pop.value
            chat.wait_for_load_state()
            chat.wait_for_timeout(2500)
            shot(chat, '11-chat-window.png')
            check('Chat window opened against MeshCentral messenger for this device', 'messenger' in chat.url)
            chat.close()

            # Reboot + reconnect
            tp.get_by_role('button', name='Remote Desktop').click()
            tp.wait_for_timeout(2000)
            tp.once('dialog', lambda d: d.accept())
            tp.get_by_role('button', name='Reboot').click()
            tp.wait_for_timeout(3000)
            with m.MeshSession() as s:
                ev = s.events(node_id, 50)
            check('Reboot command delivered to the agent (agent logged power action 3)',
                  any(e.get('msgid') == 25 or 'power action=3' in (e.get('msg') or '') for e in ev))
            # The test endpoint cannot actually reboot (CAP_SYS_BOOT dropped); simulate the restart.
            stop_agent(pc2)
            wait_for(lambda: tp.locator('.overlay').is_visible(), 40, what='offline overlay')
            shot(tp, '12-console-device-offline.png')
            check('Console shows device offline during restart', True)
            restart_agent(pc2)
            wait_for(lambda: not tp.locator('.overlay').is_visible(), 90, 2, 'device back online')
            tp.wait_for_timeout(3000)
            desktop_connect(tp)
            shot(tp, '13-console-reconnected.png')
            check('Console reconnected automatically after the endpoint came back', True)

            # Technician ends session
            tp.once('dialog', lambda d: d.accept('Resolved - unattended test'))
            tp.get_by_test_id('end-session').click()
            tp.get_by_text('Access rights on the remote computer have been removed').wait_for(timeout=20000)
            shot(tp, '14-unattended-ended.png')
            time.sleep(2)
            links, _ = node_links(node_id)
            check('Rights removed from endpoint at session end', not any(k.startswith('user//bsftech-') for k in links), str(links))
            tun = agent_tunnels(node_id)
            check('No live tunnels remain for the technician on the endpoint', 'bsftech-' not in tun, tun.strip())
            r = t1.post(f'/api/sessions/{sid}/console/', {'view': 'desktop'})
            check('Console cannot be reopened after the session ended', r.status_code == 409, r.text)
            det = admin.get(f'/api/sessions/{sid}/').json()
            CONTEXT['unattended_record'] = det
            check('Session record: technician, device, MFA, capabilities, times, outcome',
                  det['technician'] == 'tech1' and det['target_name'] and det['mfa_verified'] and det['started_at'] and det['ended_at']
                  and det['outcome'].startswith('Resolved') and det['capabilities'].get('terminal'), json.dumps({k: det[k] for k in ('status', 'ended_by', 'end_reason', 'capabilities')}))

            # Mid-session revocation: admin removes approval while a session is open -> server ends it.
            tp.once('dialog', lambda d: d.accept(totp(secret)))
            go(tp, '/devices'); tp.wait_for_timeout(1500)
            tp.get_by_role('button', name='Connect').first.click()
            tp.wait_for_url(re.compile(r'.*/console/.*'), timeout=30000)
            sid2 = tp.url.rsplit('/', 1)[-1]
            desktop_connect(tp)
            admin.post(f"/api/devices/{dev['id']}/approve/", {'approved': False})
            tp.get_by_text('Access rights on the remote computer have been removed').wait_for(timeout=40000)
            det2 = admin.get(f'/api/sessions/{sid2}/').json()
            tun = agent_tunnels(node_id)
            check('Revoking device approval terminates an open session immediately', det2['status'] == 'ENDED' and 'bsftech-' not in tun,
                  f"{det2['end_reason']} / tunnels: {tun.strip()}")
            admin.post(f"/api/devices/{dev['id']}/approve/", {'approved': True})

            # ---------------------------------------------------------- ATTENDED SESSION
            go(tp, '/'); go(tp, '/support')
            tp.get_by_role('button', name='Generate session code').click()
            code = tp.get_by_test_id('session-code').inner_text(timeout=20000).replace(' ', '')
            join_url = tp.get_by_test_id('join-url').inner_text()
            shot(tp, '15-attended-code-generated.png')
            check('Attended session code generated (9 digits, time-limited, internal URL)', re.fullmatch(r'\d{9}', code) and join_url.startswith(PORTAL), join_url)
            att = next(x for x in t1.get('/api/sessions/').json() if x['code'] == code)
            CONTEXT['attended_session'] = att['id']

            uc = ctx(); up = uc.new_page()   # remote user's browser: no portal account
            up.goto(join_url)
            up.get_by_test_id('join-name').wait_for(timeout=20000)
            shot(up, '16-remote-user-request.png')
            up.get_by_test_id('join-name').fill('Remote User One')
            up.get_by_test_id('join-accept').check()
            up.get_by_test_id('join-approve').click()
            up.get_by_text('Download and run the support agent').wait_for(timeout=15000)
            shot(up, '17-remote-user-download.png')
            # The remote user downloads the agent package for their platform from the internal portal.
            with up.expect_download() as dl:
                up.get_by_role('link', name='Linux (x64)').click()
            path = dl.value.path()
            check('Remote user downloaded the session agent from the internal portal', os.path.getsize(path) > 100000, dl.value.suggested_filename)
            # A second person cannot reuse the code once it has been approved.
            r = Api().post('/api/join/', {'code': code})
            check('Session code cannot be reused by anyone else after approval', r.status_code in (404, 409), r.text)
            pc1 = start_agent(open(path, 'rb').read(), f'pc1-attended-{code}', PC1, 'connect')
            tp.get_by_test_id('open-console').wait_for(timeout=60000)
            shot(tp, '18-technician-sees-remote-computer.png')
            up.get_by_text('Connected', exact=True).wait_for(timeout=15000)
            shot(up, '19-remote-user-connected.png')
            check('Technician sees the remote computer after the user clicked Connect', True)
            tp.get_by_test_id('open-console').click()
            tp.wait_for_url(re.compile(r'.*/console/.*'), timeout=20000)
            console_frame(tp)
            desktop_connect(tp, pre_click=lambda: answer_consent(PC1, allow=True))
            shot(tp, '20-attended-remote-desktop.png')
            screen(PC1, '21-pc1-privacy-bar.png')
            check('Remote user approved on-screen consent; desktop connected', True)
            type_on_remote(tp, 'attended-ok')
            check('Keyboard/mouse control on PC-1', bool(wait_for(lambda: any('PC1 typed:attended-ok' in t for t in window_titles(PC1).values()), 15, what='typed text PC-1')))

            # Terminal request denied by the remote user
            tp.get_by_role('button', name='Terminal').click()
            tp.wait_for_timeout(2500)
            wait_for(lambda: frame_eval(tp, "!!(document.getElementById('connectbutton2') && !document.getElementById('connectbutton2').disabled)"), 30, what='terminal button')
            frame_eval(tp, "document.getElementById('connectbutton2').click()")
            answer_consent(PC1, allow=False)
            tp.wait_for_timeout(4000)
            shot(tp, '22-attended-terminal-denied.png')

            # Remote user ends the session from the join page
            up.once('dialog', lambda d: d.accept())
            up.get_by_test_id('join-end').click()
            up.get_by_text('Session ended').wait_for(timeout=20000)
            shot(up, '23-remote-user-ended.png')
            tp.get_by_text('Access rights on the remote computer have been removed').wait_for(timeout=30000)
            shot(tp, '24-technician-sees-ended.png')
            det = wait_for(lambda: (lambda d: d if d.get('remote_consent') else None)(admin.get(f"/api/sessions/{att['id']}/").json()),
                           45, 2, 'session record finalised')
            CONTEXT['attended_record'] = det
            check('Remote user terminated the session; technician console closed', det['status'] == 'ENDED' and det['ended_by'] == 'REMOTE_USER', det['end_reason'])
            check('Agent-side consent outcomes recorded (desktop accepted, terminal rejected)',
                  det['remote_consent'].get('desktop') == 'accepted' and det['remote_consent'].get('terminal') == 'rejected', json.dumps(det['remote_consent']))
            def group_gone():
                with m.MeshSession() as s:
                    return not any(g['name'] == f'BSF-ATT-{code}' for g in s.meshes())
            check('Per-session MeshCentral group deleted at session end', wait_for(group_gone, 45, 2, 'group deletion'))
            stop_agent(pc1)

            # Attended #2: remote user closes the agent -> session ends automatically
            go(tp, '/'); go(tp, '/support')
            tp.get_by_role('button', name='Generate session code').click()
            code2 = tp.get_by_test_id('session-code').inner_text(timeout=20000).replace(' ', '')
            u2 = Api()
            j = u2.post('/api/join/', {'code': code2}).json()
            u2.post(f"/api/join/{j['token']}/consent/", {'accept': True, 'name': 'Remote User Two'})
            pkg2 = u2.get(f"/api/join/{j['token']}/agent/linux-x64/").content
            pc1b = start_agent(pkg2, f'pc1-attended-{code2}', PC1, 'connect')
            tp.get_by_test_id('open-console').wait_for(timeout=60000)
            stop_agent(pc1b)
            s2 = next(x for x in t1.get('/api/sessions/').json() if x['code'] == code2)
            det = wait_for(lambda: (lambda d: d if d['status'] == 'ENDED' else None)(admin.get(f"/api/sessions/{s2['id']}/").json()), 120, 3, 'auto end')
            check('Closing the agent on the remote PC ends the session', det['ended_by'] == 'REMOTE_USER', det['end_reason'])

            # Attended #3: technician cancels before connect; code becomes invalid
            go(tp, '/support')
            tp.get_by_role('button', name='New session').click()
            tp.get_by_role('button', name='Generate session code').click()
            code3 = tp.get_by_test_id('session-code').inner_text(timeout=20000).replace(' ', '')
            tp.once('dialog', lambda d: d.accept())
            tp.get_by_role('button', name='Cancel invitation').click()
            tp.wait_for_timeout(1500)
            r = Api().post('/api/join/', {'code': code3})
            check('Cancelled invitation code is rejected', r.status_code == 404, r.text)
            r = Api().post('/api/join/', {'code': '000000000'})
            check('Unknown code rejected', r.status_code == 404)

            # ---------------------------------------------------------- audit
            go(ap, '/audit')
            ap.wait_for_timeout(2000)
            shot(ap, '25-audit-log.png')
            go(ap, f"/sessions/{att['id']}")
            ap.wait_for_timeout(2000)
            ap.screenshot(path=os.path.join(EVID, '26-attended-session-record.png'), full_page=True)
            go(ap, f"/sessions/{sid}")
            ap.wait_for_timeout(2000)
            ap.screenshot(path=os.path.join(EVID, '27-unattended-session-record.png'), full_page=True)
            actions = {a['action'] for a in admin.get('/api/audit/').json()}
            needed = {'SESSION_CREATED', 'REMOTE_USER_CONSENTED', 'REMOTE_AGENT_CONNECTED', 'SESSION_AUTHORIZED', 'SESSION_STARTED',
                      'CONSOLE_OPENED', 'DEVICE_REBOOT', 'SESSION_ENDED', 'ACCESS_DENIED', 'DEVICE_APPROVED', 'PERMISSION_CHANGED'}
            check('Audit log contains the full lifecycle', needed <= actions, f'missing: {sorted(needed - actions)}')
            CONTEXT['external_requests'] = sorted(set(external))
            check('Browsers made no request to any host other than the two internal servers', not external, ', '.join(sorted(set(external))[:10]))
        except BaseException:
            for i, c in enumerate(CONTEXT.get('_contexts', [])):
                for j, pg in enumerate(c.pages):
                    try:
                        pg.screenshot(path=os.path.join(EVID, f'zz-failure-{i}-{j}.png'))
                        log(f'failure page {i}-{j}: {pg.url} frames={[f.url[:70] for f in pg.frames]}')
                    except Exception:  # noqa: BLE001
                        pass
            raise
        browser.close()

    CONTEXT['started'] = started.isoformat()
    CONTEXT['finished'] = datetime.now(timezone.utc).isoformat()


if __name__ == '__main__':
    code = 0
    try:
        main()
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        check('Scenario completed without error', False, f'{type(e).__name__}: {e}')
        code = 1
    CONTEXT.pop('_contexts', None)
    report = {'results': RESULTS, 'context': CONTEXT,
              'passed': sum(r['pass'] for r in RESULTS), 'failed': sum(not r['pass'] for r in RESULTS)}
    with open(os.path.join(EVID, 'report.json'), 'w') as f:
        json.dump(report, f, indent=2, default=str)
    log(f"{report['passed']} passed, {report['failed']} failed — evidence in {EVID}")
    sys.exit(1 if report['failed'] else code)
