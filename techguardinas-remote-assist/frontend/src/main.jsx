import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api, navigate } from './api.js';
import Portal from './Portal.jsx';
import Console from './Console.jsx';
import Join from './Join.jsx';
import './style.css';

function usePath() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const on = () => setPath(window.location.pathname);
    window.addEventListener('popstate', on);
    return () => window.removeEventListener('popstate', on);
  }, []);
  return path;
}

function Login({ onDone }) {
  const [form, setForm] = useState({ username: '', password: '' });
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setMsg('');
    try {
      await api.ensureCsrf();
      await api.post('/api/access/login/', form);
      onDone();
    } catch (err) { setMsg(err.message); } finally { setBusy(false); }
  };
  return (
    <div className="login">
      <form className="loginbox" onSubmit={submit}>
        <div className="brandmark">TECHGUARDINAS REMOTE</div>
        <p className="muted">Secure Remote Assist — authorized personnel only</p>
        <input autoFocus placeholder="Username" autoComplete="username" value={form.username}
          onChange={(e) => setForm({ ...form, username: e.target.value })} />
        <input type="password" placeholder="Password" autoComplete="current-password" value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <button className="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        {msg && <div className="notice error">{msg}</div>}
        <small className="muted">Accounts are created by an administrator. Remote users joining a support
          session do not sign in — open <a href="/join" onClick={(e) => { e.preventDefault(); navigate('/join'); }}>/join</a> and enter the code from your technician.</small>
      </form>
    </div>
  );
}

function App() {
  const path = usePath();
  const [me, setMe] = useState(undefined);
  const loadMe = async () => {
    try { await api.ensureCsrf(); setMe(await api.get('/api/me/')); } catch { setMe(null); }
  };
  useEffect(() => { if (!path.startsWith('/join')) loadMe(); }, [path.startsWith('/join')]);

  if (path.startsWith('/join')) return <Join code={path.split('/')[2] || ''} />;
  if (me === undefined) return <div className="center muted">Loading…</div>;
  if (me === null) return <Login onDone={loadMe} />;
  if (path.startsWith('/console/')) return <Console sessionId={path.split('/')[2]} me={me} />;
  return <Portal me={me} path={path} onLogout={async () => { await api.post('/api/access/logout/'); setMe(null); navigate('/'); }} reloadMe={loadMe} />;
}

createRoot(document.getElementById('root')).render(<App />);
