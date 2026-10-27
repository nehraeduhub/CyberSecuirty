import React, { useEffect, useRef, useState } from 'react';
import { api, fmtDuration, formatCode, navigate } from './api.js';

const VIEWS = [['desktop', 'Remote Desktop'], ['terminal', 'Terminal'], ['files', 'Files'], ['events', 'Device Events']];

export default function Console({ sessionId }) {
  const [s, setS] = useState(null);
  const [view, setView] = useState('desktop');
  const [url, setUrl] = useState('');
  const [msg, setMsg] = useState('');
  const [, tick] = useState(0);
  const wasOnline = useRef(true);
  const viewRef = useRef('desktop');
  const frameRef = useRef(null);
  // MeshCentral cancels mousedown on the remote screen, so a click inside the cross-origin frame does not move
  // keyboard focus into it. Focus the frame explicitly so keystrokes reach the remote computer.
  const focusFrame = () => { if (frameRef.current) frameRef.current.focus(); };

  const open = async (v) => {
    setMsg('');
    try {
      const r = await api.post(`/api/sessions/${sessionId}/console/`, { view: v });
      viewRef.current = v; setView(v); setUrl(r.url);
    } catch (e) { setMsg(e.message); }
  };

  const load = async () => {
    try {
      const d = await api.get(`/api/sessions/${sessionId}/`);
      setS(d);
      // Reboot / network loss: when the device comes back, reconnect the console automatically.
      if (d.device_online === false) wasOnline.current = false;
      if (d.device_online && !wasOnline.current) { wasOnline.current = true; open(viewRef.current); }
      if (!['READY', 'ACTIVE'].includes(d.status)) setUrl('');
    } catch (e) { setMsg(e.message); }
  };

  useEffect(() => {
    (async () => { await load(); open('desktop'); })();
    const t = setInterval(load, 3000);
    const c = setInterval(() => tick((x) => x + 1), 1000);
    return () => { clearInterval(t); clearInterval(c); };
  }, [sessionId]);

  const chat = async () => {
    try { const r = await api.post(`/api/sessions/${sessionId}/chat/`); window.open(r.url, 'techguardinas-chat-' + sessionId, 'width=420,height=600'); }
    catch (e) { setMsg(e.message); }
  };
  const reboot = async () => {
    const warn = s.mode === 'ATTENDED' ? '\n\nThe on-demand agent does not survive a reboot: the session will end and the user must reconnect.' : '\n\nThe console reconnects automatically when the device is back online.';
    if (!window.confirm(`Reboot ${s.target_name} now?${warn}`)) return;
    try { await api.post(`/api/sessions/${sessionId}/reboot/`); setMsg('Reboot command sent.'); } catch (e) { setMsg(e.message); }
  };
  const end = async () => {
    const outcome = window.prompt('End session. Outcome / notes for the session record:', 'Resolved');
    if (outcome === null) return;
    try { setS(await api.post(`/api/sessions/${sessionId}/end/`, { outcome })); setUrl(''); } catch (e) { setMsg(e.message); }
  };

  if (!s) return <div className="center muted">{msg || 'Loading session…'}</div>;
  const live = ['READY', 'ACTIVE'].includes(s.status);
  const caps = s.capabilities || {};
  return <div className="console">
    <div className="ctoolbar">
      <div className="cinfo">
        <a href="/" onClick={(e) => { e.preventDefault(); navigate('/'); }} className="back">◀ Portal</a>
        <b data-testid="console-target">{s.target_name || 'Remote computer'}</b>
        <span className="muted">{s.target_os} · {s.target_ip} · {s.mode} · {formatCode(s.code)}</span>
        <span className={s.device_online === false ? 'offline' : 'online'}>{s.device_online === false ? '○ Offline' : '● Online'}</span>
        {live && <span className="muted">⏱ {fmtDuration(s.started_at || s.authorized_at)}{s.deadline_at && ` · ends by ${new Date(s.deadline_at).toLocaleTimeString()}`}</span>}
        {s.recording && <span className="rec">● REC</span>}
      </div>
      {live && <div className="ctabs">
        {VIEWS.filter(([v]) => v === 'events' || caps[v]).map(([v, label]) => <button key={v} className={view === v ? 'active' : ''} onClick={() => open(v)}>{label}</button>)}
        {caps.chat && <button onClick={chat}>Chat</button>}
        {caps.reboot && <button onClick={reboot}>Reboot</button>}
        <button className="danger" onClick={end} data-testid="end-session">End Session</button>
      </div>}
    </div>
    {msg && <div className="notice error cmsg">{msg}</div>}
    {live && url && <div className="cframe">
      <iframe key={url} ref={frameRef} src={url} title="Remote console" allow="clipboard-read; clipboard-write; fullscreen"
        onLoad={focusFrame} onMouseEnter={focusFrame} data-testid="console-frame" />
      {s.device_online === false && <div className="overlay"><div><h2>Device offline</h2><p>Waiting for {s.target_name} to reconnect (for example after a reboot)…</p></div></div>}
    </div>}
    {!live && <div className="ended">
      <h2>Session {s.status.toLowerCase()}</h2>
      <p>{s.end_reason}{s.ended_by && ` (${s.ended_by.replace('_', ' ').toLowerCase()})`}</p>
      <p className="muted">Access rights on the remote computer have been removed and live connections closed.</p>
      <div className="row"><button onClick={() => navigate(`/sessions/${s.id}`)}>View session record</button><button className="primary" onClick={() => navigate('/')}>Back to portal</button></div>
    </div>}
  </div>;
}
