import React, { useEffect, useRef, useState } from 'react';
import { api, fmtTime, fmtDuration, formatCode, navigate } from './api.js';

const ADMIN = ['ADMIN', 'SUPERADMIN'];
const REVIEW = ['ADMIN', 'SUPERADMIN', 'AUDITOR'];
const SUPPORT = ['TECHNICIAN', 'ADMIN', 'SUPERADMIN'];

function nav(me) {
  const items = [['/', 'Dashboard']];
  if (SUPPORT.includes(me.role)) items.push(['/support', 'Start Remote Support'], ['/devices', 'Unattended Access']);
  items.push(['/sessions', 'Sessions']);
  if (REVIEW.includes(me.role)) items.push(['/audit', 'Audit Log']);
  if (ADMIN.includes(me.role)) items.push(['/admin/devices', 'Device Approval'], ['/admin/groups', 'Groups & Agents'],
    ['/admin/permissions', 'Permissions'], ['/admin/users', 'Users']);
  items.push(['/settings', 'Settings']);
  return items;
}

export function Panel({ title, actions, children }) {
  return <div className="panel"><div className="panelhead"><h2>{title}</h2><div className="row">{actions}</div></div>{children}</div>;
}

function Status({ s }) {
  return <span className={'badge st-' + s.toLowerCase()}>{s}</span>;
}

function Online({ online }) {
  return <span className={online ? 'online' : 'offline'}>{online ? '● Online' : '○ Offline'}</span>;
}

// Asks for a TOTP code and exchanges it for a single-use step-up grant.
async function stepUp(me) {
  if (!me.mfa_enabled) throw new Error('MFA is required for this connection. Configure an authenticator under Settings first.');
  const code = window.prompt('Enter the 6-digit code from your authenticator app to authorize this connection:');
  if (!code) throw new Error('MFA verification cancelled.');
  const g = await api.post('/api/security/stepup/verify/', { code, purpose: 'REMOTE_CONNECT' });
  return g.grant;
}

// ---------------------------------------------------------------- Dashboard
function Dashboard({ me }) {
  const [devices, setDevices] = useState([]);
  const [sessions, setSessions] = useState([]);
  useEffect(() => {
    api.get('/api/devices/').then(setDevices).catch(() => {});
    api.get('/api/sessions/').then(setSessions).catch(() => {});
  }, []);
  const open = sessions.filter((s) => ['WAITING', 'READY', 'ACTIVE'].includes(s.status));
  const authorized = devices.filter((d) => d.can_connect);
  return <>
    {SUPPORT.includes(me.role) && <div className="hero">
      <div className="herocard" onClick={() => navigate('/support')}>
        <h3>Start Remote Support</h3>
        <p>Generate a one-time session code for a user who is at their computer. They approve the connection.</p>
        <button className="primary">Start now</button>
      </div>
      <div className="herocard" onClick={() => navigate('/devices')}>
        <h3>Unattended Access</h3>
        <p>Connect to an authorized managed computer. MFA verification is required.</p>
        <button>{authorized.filter((d) => d.online).length} of {authorized.length} authorized devices online</button>
      </div>
    </div>}
    <div className="cards">
      <div><small>Authorized devices</small><strong>{authorized.length}</strong></div>
      <div><small>Online</small><strong>{authorized.filter((d) => d.online).length}</strong></div>
      <div><small>Open sessions</small><strong>{open.length}</strong></div>
      <div><small>MFA</small><strong>{me.mfa_enabled ? 'Enabled' : 'Not set'}</strong></div>
    </div>
    {open.length > 0 && <Panel title="Your open sessions"><SessionTable sessions={open} /></Panel>}
  </>;
}

// ------------------------------------------------------ Attended support
function StartSupport({ me }) {
  const [session, setSession] = useState(null);
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const timer = useRef(null);

  const poll = (id) => {
    clearInterval(timer.current);
    timer.current = setInterval(async () => {
      try { setSession(await api.get(`/api/sessions/${id}/`)); } catch (e) { setMsg(e.message); }
    }, 2500);
  };
  useEffect(() => () => clearInterval(timer.current), []);
  useEffect(() => { if (session && !['WAITING', 'READY', 'ACTIVE'].includes(session.status)) clearInterval(timer.current); }, [session]);

  const start = async () => {
    setBusy(true); setMsg('');
    try {
      const body = me.policy.attended_mfa ? { stepup_grant: await stepUp(me) } : {};
      const s = await api.post('/api/sessions/attended/', body);
      setSession(s); poll(s.id);
    } catch (e) { setMsg(e.message); } finally { setBusy(false); }
  };
  const cancel = async () => {
    if (!window.confirm('Cancel this support session?')) return;
    setSession(await api.post(`/api/sessions/${session.id}/end/`, { reason: 'Invitation cancelled by technician' }));
  };
  const copy = (t) => navigator.clipboard && navigator.clipboard.writeText(t);

  if (!session) return <Panel title="Attended remote support">
    <ol className="steps">
      <li>Click <b>Generate session code</b>. The code is valid for {me.policy.attended_ttl_minutes} minutes and works once.</li>
      <li>Give the code or link to the user through an approved internal channel (phone, internal chat, e-mail).</li>
      <li>The user opens the link, reviews and approves the request, then runs the support agent and clicks <b>Connect</b>.</li>
      <li>When their computer appears, open the remote console. The user is asked to allow screen, terminal and file access, and can end the session at any time.</li>
    </ol>
    <button className="primary big" onClick={start} disabled={busy}>{busy ? 'Creating…' : 'Generate session code'}</button>
    {msg && <div className="notice error">{msg}</div>}
  </Panel>;

  const waiting = session.status === 'WAITING';
  const ready = ['READY', 'ACTIVE'].includes(session.status);
  return <Panel title={`Support session ${formatCode(session.code)}`} actions={<Status s={session.status} />}>
    {waiting && <div className="invite">
      <div className="code" data-testid="session-code">{formatCode(session.code)}</div>
      <div className="row"><code className="link" data-testid="join-url">{session.join_url}</code><button onClick={() => copy(session.join_url)}>Copy link</button></div>
      <p className="muted">Expires {fmtTime(session.expires_at)}. Share only through an approved internal channel.</p>
      <div className="progress">
        <div className={session.customer_consent_at ? 'done' : 'now'}>1. User opens the link and approves {session.customer_consent_at && `— ${session.customer_name || 'approved'} at ${fmtTime(session.customer_consent_at)}`}</div>
        <div className={session.customer_consent_at ? 'now' : ''}>2. User runs the support agent and clicks Connect</div>
        <div>3. Computer connected</div>
      </div>
    </div>}
    {ready && <div className="connected">
      <h3>Connected: {session.target_name}</h3>
      <p className="muted">{session.target_os} · {session.target_ip} · user: {session.customer_name || '—'}</p>
      <button className="primary big" onClick={() => navigate(`/console/${session.id}`)} data-testid="open-console">Open remote console</button>
    </div>}
    {!waiting && !ready && <div className="notice">Session {session.status.toLowerCase()}: {session.end_reason}</div>}
    <div className="row">
      {(waiting || ready) && <button className="danger" onClick={cancel}>{waiting ? 'Cancel invitation' : 'End session'}</button>}
      {!waiting && !ready && <button onClick={() => setSession(null)}>New session</button>}
    </div>
    {msg && <div className="notice error">{msg}</div>}
  </Panel>;
}

// ------------------------------------------------------ Unattended access
function Devices({ me }) {
  const [devices, setDevices] = useState([]);
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState('');
  const load = () => api.get('/api/devices/').then(setDevices).catch((e) => setMsg(e.message));
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, []);
  const connect = async (d) => {
    setBusy(d.id); setMsg('');
    try {
      const body = { device_id: d.id };
      if (me.policy.unattended_mfa) body.stepup_grant = await stepUp(me);
      const s = await api.post('/api/sessions/unattended/', body);
      navigate(`/console/${s.id}`);
    } catch (e) { setMsg(e.message); } finally { setBusy(''); }
  };
  const list = devices.filter((d) => d.approved && !d.removed && d.can_connect);
  return <Panel title="Authorized devices" actions={<button onClick={load}>Refresh</button>}>
    {msg && <div className="notice error">{msg}</div>}
    <table><thead><tr><th>Device</th><th>Group</th><th>IP</th><th>Status</th><th>Permitted</th><th></th></tr></thead>
      <tbody>{list.map((d) => <tr key={d.id}>
        <td><b>{d.name}</b><small>{d.os}</small></td><td>{d.group}</td><td>{d.ip_address || '—'}</td>
        <td><Online online={d.online} /><small>{d.online ? '' : `last seen ${fmtTime(d.last_seen)}`}</small></td>
        <td className="caps">{Object.entries(d.capabilities).filter(([, v]) => v).map(([k]) => <span key={k}>{k}</span>)}</td>
        <td><button className="primary" disabled={!d.online || busy === d.id} onClick={() => connect(d)}>{busy === d.id ? 'Authorizing…' : 'Connect'}</button></td>
      </tr>)}</tbody></table>
    {!list.length && <p className="muted">No devices are authorized for your account. Device access is granted by an administrator.</p>}
  </Panel>;
}

// ------------------------------------------------------ Sessions
export function SessionTable({ sessions, showTech }) {
  return <table><thead><tr><th>Code</th><th>Mode</th><th>Target</th>{showTech && <th>Technician</th>}<th>Status</th><th>Started</th><th>Duration</th><th>Ended by</th><th></th></tr></thead>
    <tbody>{sessions.map((s) => <tr key={s.id}>
      <td>{formatCode(s.code)}</td><td>{s.mode}</td><td>{s.target_name || '—'}</td>{showTech && <td>{s.technician}</td>}
      <td><Status s={s.status} /></td><td>{fmtTime(s.started_at || s.created_at)}</td>
      <td>{s.started_at ? fmtDuration(s.started_at, s.ended_at) : '—'}</td><td>{s.ended_by || ''}</td>
      <td>{['READY', 'ACTIVE'].includes(s.status) ? <button className="primary" onClick={() => navigate(`/console/${s.id}`)}>Console</button>
        : <button onClick={() => navigate(`/sessions/${s.id}`)}>Details</button>}</td>
    </tr>)}</tbody></table>;
}

function Sessions({ me }) {
  const [all, setAll] = useState(false);
  const [sessions, setSessions] = useState([]);
  useEffect(() => { api.get('/api/sessions/' + (all ? '?all=1' : '')).then(setSessions).catch(() => {}); }, [all]);
  return <Panel title={all ? 'All sessions' : 'My sessions'} actions={REVIEW.includes(me.role) &&
    <label className="check"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> All technicians</label>}>
    <SessionTable sessions={sessions} showTech={all} />
  </Panel>;
}

function SessionDetail({ id }) {
  const [s, setS] = useState(null);
  const [msg, setMsg] = useState('');
  useEffect(() => { api.get(`/api/sessions/${id}/`).then(setS).catch((e) => setMsg(e.message)); }, [id]);
  if (msg) return <div className="notice error">{msg}</div>;
  if (!s) return <p className="muted">Loading…</p>;
  const rows = [
    ['Session code', formatCode(s.code)], ['Mode', s.mode], ['Status', s.status], ['Technician', s.technician],
    ['Target device', `${s.target_name || '—'} (${s.target_os || '—'}, ${s.target_ip || '—'})`],
    ['Authorization', s.mode === 'ATTENDED' ? `Remote user consent: ${s.customer_name || '—'} at ${fmtTime(s.customer_consent_at)}` : `Device permission${s.mfa_verified ? ' + MFA step-up' : ''}`],
    ['On-screen consent (agent)', Object.entries(s.remote_consent || {}).map(([k, v]) => `${k}: ${v}`).join(', ') || '—'],
    ['Capabilities enabled', Object.entries(s.capabilities).filter(([, v]) => v).map(([k]) => k).join(', ')],
    ['Recording', s.recording ? 'Enabled' : 'Off'],
    ['Created', fmtTime(s.created_at)], ['Console opened', fmtTime(s.started_at)], ['Ended', fmtTime(s.ended_at)],
    ['Duration', s.started_at ? fmtDuration(s.started_at, s.ended_at) : '—'],
    ['Ended by', `${s.ended_by || '—'} ${s.end_reason ? '— ' + s.end_reason : ''}`], ['Outcome', s.outcome || '—'],
  ];
  return <>
    <Panel title="Session record"><table className="kv"><tbody>{rows.map(([k, v]) => <tr key={k}><th>{k}</th><td>{v}</td></tr>)}</tbody></table></Panel>
    <Panel title="Audit trail"><table><thead><tr><th>Time</th><th>Action</th><th>Actor</th><th>Source IP</th><th>Details</th></tr></thead>
      <tbody>{s.audit.map((a, i) => <tr key={i}><td>{fmtTime(a.created_at)}</td><td>{a.action}</td><td>{a.actor__username || 'system / remote user'}</td><td>{a.source_ip || ''}</td><td><code>{JSON.stringify(a.details)}</code></td></tr>)}</tbody></table></Panel>
    <Panel title="Remote engine events"><table><thead><tr><th>Time</th><th>Event</th><th>User</th></tr></thead>
      <tbody>{(s.mesh_events || []).map((e, i) => <tr key={i}><td>{fmtTime(e.time)}</td><td>{e.msg}</td><td>{e.user}</td></tr>)}</tbody></table></Panel>
  </>;
}

// ------------------------------------------------------ Audit log
function Audit() {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState('');
  const load = () => api.get('/api/audit/' + (q ? `?q=${encodeURIComponent(q)}` : '')).then(setRows).catch(() => {});
  useEffect(() => { load(); }, []);
  return <Panel title="Audit log" actions={<><input placeholder="Search user or details" value={q} onChange={(e) => setQ(e.target.value)} /><button onClick={load}>Search</button></>}>
    <table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th><th>Source IP</th><th>Details</th></tr></thead>
      <tbody>{rows.map((a) => <tr key={a.id}><td>{fmtTime(a.time)}</td><td>{a.actor || 'system / remote user'}</td><td>{a.action}</td>
        <td>{a.target_type} {a.target_type === 'RemoteSession' ? <a href={`/sessions/${a.target_id}`} onClick={(e) => { e.preventDefault(); navigate(`/sessions/${a.target_id}`); }}>view</a> : ''}</td>
        <td>{a.source_ip || ''}</td><td><code>{JSON.stringify(a.details)}</code></td></tr>)}</tbody></table>
  </Panel>;
}

// ------------------------------------------------------ Administration
function AdminDevices() {
  const [devices, setDevices] = useState([]);
  const [msg, setMsg] = useState('');
  const load = () => api.get('/api/devices/').then(setDevices).catch((e) => setMsg(e.message));
  useEffect(() => { load(); }, []);
  const sync = async () => { try { const r = await api.post('/api/devices/sync/'); setMsg(`Synchronised: ${r.seen} devices, ${r.new} new.`); load(); } catch (e) { setMsg(e.message); } };
  const approve = async (d, approved) => { await api.post(`/api/devices/${d.id}/approve/`, { approved }); load(); };
  return <Panel title="Device approval" actions={<button onClick={sync}>Sync from remote engine</button>}>
    <p className="muted">Devices appear here when the TechGuardinas Remote agent is installed from a group's installer. A device cannot be accessed until it is approved here <b>and</b> a technician is granted permission for it or its group.</p>
    {msg && <div className="notice">{msg}</div>}
    <table><thead><tr><th>Device</th><th>Group</th><th>IP</th><th>Status</th><th>Approval</th><th></th></tr></thead>
      <tbody>{devices.map((d) => <tr key={d.id}><td><b>{d.name}</b><small>{d.os}</small></td><td>{d.group}</td><td>{d.ip_address || '—'}</td>
        <td>{d.removed ? <span className="offline">Removed</span> : <Online online={d.online} />}</td>
        <td>{d.approved ? <span className="badge st-ready">APPROVED</span> : <span className="badge st-waiting">PENDING</span>}</td>
        <td>{d.approved ? <button className="danger" onClick={() => approve(d, false)}>Revoke</button> : <button className="primary" onClick={() => approve(d, true)}>Approve</button>}</td></tr>)}</tbody></table>
  </Panel>;
}

function AdminGroups() {
  const [groups, setGroups] = useState([]);
  const [form, setForm] = useState({ name: '', description: '', auto_approve: false, record_sessions: false });
  const [msg, setMsg] = useState('');
  const load = () => api.get('/api/access/groups/').then(setGroups).catch((e) => setMsg(e.message));
  useEffect(() => { load(); }, []);
  const create = async (e) => { e.preventDefault(); try { await api.post('/api/access/groups/', form); setForm({ ...form, name: '', description: '' }); load(); } catch (err) { setMsg(err.message); } };
  const toggle = async (g, field) => { await api.post(`/api/access/groups/${g.id}/`, { [field]: !g[field] }); load(); };
  return <>
    <Panel title="Create device group">
      <form className="formrow" onSubmit={create}>
        <input placeholder="Group name, e.g. HQ-IT" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <label className="check"><input type="checkbox" checked={form.record_sessions} onChange={(e) => setForm({ ...form, record_sessions: e.target.checked })} /> Record sessions</label>
        <label className="check"><input type="checkbox" checked={form.auto_approve} onChange={(e) => setForm({ ...form, auto_approve: e.target.checked })} /> Auto-approve new devices</label>
        <button className="primary">Create group</button>
      </form>
      {msg && <div className="notice error">{msg}</div>}
    </Panel>
    <Panel title="Groups and agent installers">
      <p className="muted">Download the official MeshCentral agent for a group from this internal server. The installer contains only the internal server address and the group identity. For silent deployment run <code>TechGuardinas-Remote-Agent-&lt;group&gt;.exe -fullinstall</code> (see the GPO deployment guide).</p>
      <table><thead><tr><th>Group</th><th>Devices</th><th>Recording</th><th>Auto-approve</th><th>Active</th><th>Agent installer</th></tr></thead>
        <tbody>{groups.map((g) => <tr key={g.id}><td><b>{g.name}</b><small>{g.description}</small></td><td>{g.devices}</td>
          <td><button onClick={() => toggle(g, 'record_sessions')}>{g.record_sessions ? 'On' : 'Off'}</button></td>
          <td><button onClick={() => toggle(g, 'auto_approve')}>{g.auto_approve ? 'Yes' : 'No'}</button></td>
          <td><button onClick={() => toggle(g, 'active')}>{g.active ? 'Yes' : 'No'}</button></td>
          <td className="row">{['windows-x64', 'windows-x86', 'windows-arm64', 'linux-x64'].map((p) => <a key={p} className="btn" href={`/api/access/groups/${g.id}/agent/${p}/`}>{p}</a>)}</td></tr>)}</tbody></table>
    </Panel>
  </>;
}

function AdminPermissions() {
  const [perms, setPerms] = useState([]);
  const [users, setUsers] = useState([]);
  const [groups, setGroups] = useState([]);
  const [devices, setDevices] = useState([]);
  const [form, setForm] = useState({ user_id: '', target: '', can_connect: true, can_file_transfer: false, can_terminal: false, can_reboot: false });
  const [msg, setMsg] = useState('');
  const load = () => {
    api.get('/api/access/permissions/').then(setPerms);
    api.get('/api/access/users/').then(setUsers);
    api.get('/api/access/groups/').then(setGroups);
    api.get('/api/devices/').then(setDevices);
  };
  useEffect(() => { load(); }, []);
  const save = async (e) => {
    e.preventDefault(); setMsg('');
    const [kind, id] = form.target.split(':');
    try {
      await api.post('/api/access/permissions/set/', { user_id: form.user_id, [kind === 'g' ? 'group_id' : 'device_id']: id,
        can_connect: form.can_connect, can_file_transfer: form.can_file_transfer, can_terminal: form.can_terminal, can_reboot: form.can_reboot });
      load();
    } catch (err) { setMsg(err.message); }
  };
  const del = async (p) => { if (window.confirm('Remove this permission?')) { await api.post(`/api/access/permissions/${p.id}/delete/`); load(); } };
  const flag = (k, label) => <label className="check"><input type="checkbox" checked={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.checked })} /> {label}</label>;
  return <>
    <Panel title="Grant unattended access">
      <form className="formrow" onSubmit={save}>
        <select value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })}><option value="">Technician…</option>
          {users.filter((u) => u.role === 'TECHNICIAN').map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}</select>
        <select value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })}><option value="">Group or device…</option>
          <optgroup label="Groups">{groups.map((g) => <option key={g.id} value={`g:${g.id}`}>{g.name}</option>)}</optgroup>
          <optgroup label="Devices">{devices.filter((d) => d.approved).map((d) => <option key={d.id} value={`d:${d.id}`}>{d.name} ({d.group})</option>)}</optgroup></select>
        {flag('can_connect', 'Connect')}{flag('can_file_transfer', 'File transfer')}{flag('can_terminal', 'Terminal')}{flag('can_reboot', 'Reboot')}
        <button className="primary">Save</button>
      </form>
      {msg && <div className="notice error">{msg}</div>}
      <p className="muted">Administrators can connect to any approved device. Technicians only to devices granted here. Every unattended connection also requires MFA step-up when enabled by policy.</p>
    </Panel>
    <Panel title="Current permissions">
      <table><thead><tr><th>Technician</th><th>Scope</th><th>Connect</th><th>Files</th><th>Terminal</th><th>Reboot</th><th></th></tr></thead>
        <tbody>{perms.map((p) => <tr key={p.id}><td>{p.username}</td><td>{p.group ? `Group: ${p.group}` : `Device: ${p.device}`}</td>
          {['can_connect', 'can_file_transfer', 'can_terminal', 'can_reboot'].map((k) => <td key={k}>{p[k] ? 'Yes' : '—'}</td>)}
          <td><button className="danger" onClick={() => del(p)}>Remove</button></td></tr>)}</tbody></table>
    </Panel>
  </>;
}

function AdminUsers({ me }) {
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({ username: '', password: '', role: 'TECHNICIAN', email: '' });
  const [msg, setMsg] = useState('');
  const load = () => api.get('/api/access/users/').then(setUsers).catch((e) => setMsg(e.message));
  useEffect(() => { load(); }, []);
  const create = async (e) => { e.preventDefault(); setMsg(''); try { await api.post('/api/users/', form); setForm({ username: '', password: '', role: 'TECHNICIAN', email: '' }); setMsg('User created.'); load(); } catch (err) { setMsg(err.message); } };
  const provision = async () => { const ad = window.prompt('AD username (sAMAccountName) to provision:'); if (!ad) return; try { await api.post('/api/access/users/provision/', { ad_username: ad, role: 'TECHNICIAN' }); load(); } catch (e) { setMsg(e.message); } };
  const act = async (u, a) => { try { await api.post(`/api/access/users/${u.id}/${a}/`); load(); } catch (e) { setMsg(e.message); } };
  return <>
    <Panel title="Create local user" actions={<button onClick={provision}>Provision AD user</button>}>
      <form className="formrow" onSubmit={create}>
        <input placeholder="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
        <input type="password" placeholder="Initial password (min 12 chars)" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <input placeholder="E-mail (optional)" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          {['TECHNICIAN', 'AUDITOR', ...(me.role === 'SUPERADMIN' ? ['ADMIN', 'SUPERADMIN'] : [])].map((r) => <option key={r}>{r}</option>)}</select>
        <button className="primary">Create</button>
      </form>
      {msg && <div className="notice">{msg}</div>}
    </Panel>
    <Panel title="Portal users">
      <table><thead><tr><th>User</th><th>Source</th><th>Role</th><th>Status</th><th>Last login</th><th></th></tr></thead>
        <tbody>{users.map((u) => <tr key={u.id}><td>{u.ad_username || u.username}</td><td>{u.auth_source}</td><td>{u.role}</td>
          <td>{u.portal_enabled && u.is_active ? 'ENABLED' : 'DISABLED / PENDING'}</td><td>{fmtTime(u.last_login)} <small>{u.last_login_ip}</small></td>
          <td>{u.portal_enabled ? <button className="danger" onClick={() => act(u, 'disable')}>Disable</button> : <button onClick={() => act(u, 'approve')}>Enable</button>}</td></tr>)}</tbody></table>
    </Panel>
  </>;
}

// ------------------------------------------------------ Settings
function Settings({ me, reloadMe }) {
  const [enroll, setEnroll] = useState(null);
  const [code, setCode] = useState('');
  const [msg, setMsg] = useState('');
  const [dir, setDir] = useState(null);
  useEffect(() => { if (ADMIN.includes(me.role)) api.get('/api/directory/').then(setDir).catch(() => {}); }, []);
  const start = async () => { try { setEnroll(await api.post('/api/security/mfa/enroll/')); } catch (e) { setMsg(e.message); } };
  const verify = async () => { try { await api.post('/api/security/mfa/verify/', { code }); setEnroll(null); setMsg('MFA enabled.'); reloadMe(); } catch (e) { setMsg(e.message); } };
  const saveDir = async () => { try { const r = await api.post('/api/directory/', dir); setMsg(r.message); } catch (e) { setMsg(e.message); } };
  return <>
    <Panel title="Multi-factor authentication">
      <p>Status: <b>{me.mfa_enabled ? 'ENABLED' : 'NOT ENABLED'}</b>. {me.policy.unattended_mfa && 'Required for every unattended connection.'}</p>
      {!me.mfa_enabled && !enroll && <button className="primary" onClick={start}>Configure authenticator</button>}
      {enroll && <div className="mfa">
        <div className="qr" dangerouslySetInnerHTML={{ __html: enroll.qr_svg }} />
        <div><p>Scan with an authenticator app (works offline), or enter the key manually:</p><code>{enroll.secret}</code>
          <div className="formrow"><input placeholder="6-digit code" value={code} onChange={(e) => setCode(e.target.value)} /><button className="primary" onClick={verify}>Verify and enable</button></div></div>
      </div>}
      {msg && <div className="notice">{msg}</div>}
    </Panel>
    {dir && <Panel title="Active Directory / LDAPS (optional)">
      <div className="formcol">
        <input placeholder="ldaps://dc01.example.local:636" value={dir.server_uri} onChange={(e) => setDir({ ...dir, server_uri: e.target.value })} />
        <input placeholder="Bind DN" value={dir.bind_dn} onChange={(e) => setDir({ ...dir, bind_dn: e.target.value })} />
        <input type="password" placeholder="Bind password (leave blank to keep)" onChange={(e) => setDir({ ...dir, bind_password: e.target.value })} />
        <input placeholder="User base DN" value={dir.user_base_dn} onChange={(e) => setDir({ ...dir, user_base_dn: e.target.value })} />
        <label className="check"><input type="checkbox" checked={dir.verify_ssl} onChange={(e) => setDir({ ...dir, verify_ssl: e.target.checked })} /> Verify LDAPS certificate</label>
        <label className="check"><input type="checkbox" checked={dir.enabled} onChange={(e) => setDir({ ...dir, enabled: e.target.checked })} /> Enable AD authentication</label>
        <button className="primary" onClick={saveDir}>Save</button>
      </div>
    </Panel>}
  </>;
}

// ------------------------------------------------------ Shell
export default function Portal({ me, path, onLogout, reloadMe }) {
  const items = nav(me);
  let title = (items.find(([p]) => p === path) || [null, ''])[1];
  let page;
  if (path === '/support') page = <StartSupport me={me} />;
  else if (path === '/devices') page = <Devices me={me} />;
  else if (path === '/sessions') page = <Sessions me={me} />;
  else if (path.startsWith('/sessions/')) { title = 'Session details'; page = <SessionDetail id={path.split('/')[2]} />; }
  else if (path === '/audit') page = <Audit />;
  else if (path === '/admin/devices') page = <AdminDevices />;
  else if (path === '/admin/groups') page = <AdminGroups />;
  else if (path === '/admin/permissions') page = <AdminPermissions />;
  else if (path === '/admin/users') page = <AdminUsers me={me} />;
  else if (path === '/settings') page = <Settings me={me} reloadMe={reloadMe} />;
  else { title = 'Dashboard'; page = <Dashboard me={me} />; }
  return <div className="app">
    <header><div><b>TECHGUARDINAS REMOTE</b><span>Secure Remote Assist</span></div>
      <div className="row">{me.username} <em>{me.role}</em><button className="ghost" onClick={onLogout}>Sign out</button></div></header>
    <main>
      <aside>{items.map(([p, label]) => <a key={p} href={p} className={'nav ' + (path === p ? 'active' : '')}
        onClick={(e) => { e.preventDefault(); navigate(p); }}>{label}</a>)}</aside>
      <section><h1>{title}</h1>{page}</section>
    </main>
  </div>;
}
