import React, { useEffect, useRef, useState } from 'react';
import { api, formatCode } from './api.js';

const PLATFORM_LABEL = {
  'windows-x64': 'Windows (64-bit)', 'windows-x86': 'Windows (32-bit)', 'windows-arm64': 'Windows (ARM64)', 'linux-x64': 'Linux (x64)',
};
const CAP_LABEL = { desktop: 'view and control your screen', terminal: 'open a command prompt', files: 'transfer files', chat: 'chat with you', reboot: 'restart your computer' };

function guessPlatform() {
  const ua = navigator.userAgent;
  if (/Windows/.test(ua)) return /ARM64/.test(ua) ? 'windows-arm64' : 'windows-x64';
  if (/Linux/.test(ua)) return 'linux-x64';
  return 'windows-x64';
}

// The remote user's side: enter code -> review and approve -> download agent -> click Connect -> session.
export default function Join({ code: initialCode }) {
  const [code, setCode] = useState(initialCode || '');
  const [token, setToken] = useState(() => sessionStorage.getItem('techguardinas-join-token') || '');
  const [info, setInfo] = useState(null);
  const [name, setName] = useState('');
  const [accept, setAccept] = useState(false);
  const [msg, setMsg] = useState('');
  const timer = useRef(null);

  const status = async (t) => {
    try { setInfo(await api.get(`/api/join/${t}/status/`)); } catch { sessionStorage.removeItem('techguardinas-join-token'); setToken(''); setInfo(null); }
  };
  useEffect(() => {
    if (!token) return undefined;
    status(token);
    timer.current = setInterval(() => status(token), 3000);
    return () => clearInterval(timer.current);
  }, [token]);

  const submitCode = async (e) => {
    e && e.preventDefault(); setMsg('');
    try {
      const r = await api.post('/api/join/', { code });
      sessionStorage.setItem('techguardinas-join-token', r.token);
      setToken(r.token); setInfo(r);
    } catch (err) { setMsg(err.message); }
  };
  useEffect(() => { if (initialCode && !token) submitCode(); }, []);

  const consent = async () => {
    setMsg('');
    try { setInfo(await api.post(`/api/join/${token}/consent/`, { accept: true, name })); } catch (e) { setMsg(e.message); }
  };
  const endIt = async () => {
    if (!window.confirm('End the remote support session now? The technician will be disconnected immediately.')) return;
    setInfo(await api.post(`/api/join/${token}/end/`));
  };

  const box = (children) => <div className="joinpage"><div className="joinbox"><div className="brandmark">TECHGUARDINAS REMOTE</div><p className="muted">Remote support</p>{children}</div></div>;

  if (!token || !info) return box(<form onSubmit={submitCode}>
    <h2>Enter your session code</h2>
    <p>Your technician gave you a 9-digit code.</p>
    <input className="codeinput" inputMode="numeric" autoFocus placeholder="123 456 789" value={code} onChange={(e) => setCode(e.target.value)} data-testid="join-code" />
    <button className="primary big">Continue</button>
    {msg && <div className="notice error">{msg}</div>}
  </form>);

  const ended = !['WAITING', 'READY', 'ACTIVE'].includes(info.status);
  if (ended) return box(<>
    <h2>Session ended</h2>
    <p>{info.end_reason || 'This support session is no longer active.'}</p>
    <p className="muted">The technician no longer has any access to your computer. Close the support agent window now (click Disconnect / close it); nothing was installed.</p>
    <button onClick={() => { sessionStorage.removeItem('techguardinas-join-token'); setToken(''); setInfo(null); setCode(''); }}>Start over</button>
  </>);

  if (!info.consented) return box(<>
    <h2>Remote support request</h2>
    <p><b>{info.technician}</b> is requesting a remote support session (code {formatCode(info.code)}).</p>
    <p>If you approve, the technician will be able to:</p>
    <ul>{info.capabilities.map((c) => <li key={c}>{CAP_LABEL[c] || c}</li>)}</ul>
    <p className="muted">You will be asked again on your screen before your desktop, a command prompt or file access is opened. You can end the session at any time from this page or from the bar at the top of your screen.</p>
    <input placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} data-testid="join-name" />
    <label className="check"><input type="checkbox" checked={accept} onChange={(e) => setAccept(e.target.checked)} data-testid="join-accept" /> I authorize this remote support session</label>
    <button className="primary big" disabled={!accept} onClick={consent} data-testid="join-approve">Approve</button>
    {msg && <div className="notice error">{msg}</div>}
  </>);

  const primary = guessPlatform();
  return box(<>
    {!info.connected ? <>
      <h2>Download and run the support agent</h2>
      <ol className="steps">
        <li>Download the support agent from this internal server.</li>
        <li>Run it. Nothing is installed: click <b>Connect</b> in the window that opens.</li>
        <li>Keep it open during the session. Closing it ends the session.</li>
      </ol>
      <a className="btn primary big" href={`/api/join/${token}/agent/${primary}/`} data-testid="join-download">Download for {PLATFORM_LABEL[primary]}</a>
      <p className="muted">Other platforms: {info.platforms.filter((p) => p !== primary).map((p) => <a key={p} href={`/api/join/${token}/agent/${p}/`}> {PLATFORM_LABEL[p]} </a>)}</p>
      <div className="notice">Waiting for your computer to connect…</div>
    </> : <>
      <h2>Connected</h2>
      <p>Your computer is connected to <b>{info.technician}</b>. When the technician opens your screen you will be asked to allow it.</p>
      <div className="notice">Session in progress</div>
    </>}
    <button className="danger" onClick={endIt} data-testid="join-end">End session</button>
  </>);
}
