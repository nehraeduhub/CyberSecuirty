// Minimal same-origin API client. Django session cookie + CSRF header; no third-party HTTP library.
function csrfToken() {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function request(method, path, body) {
  const opts = { method, credentials: 'same-origin', headers: { Accept: 'application/json' } };
  if (method !== 'GET') {
    opts.headers['Content-Type'] = 'application/json';
    opts.headers['X-CSRFToken'] = csrfToken();
    opts.body = JSON.stringify(body || {});
  }
  const res = await fetch(path, opts);
  let data = null;
  try { data = await res.json(); } catch { data = null; }
  if (!res.ok) {
    const msg = (data && (data.detail || data.error)) || `Request failed (${res.status})`;
    throw new ApiError(msg, res.status);
  }
  return data;
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b),
  ensureCsrf: () => request('GET', '/api/access/csrf/'),
};

export function fmtTime(v) {
  if (!v) return '—';
  return new Date(v).toLocaleString();
}

export function fmtDuration(fromIso, toIso) {
  if (!fromIso) return '—';
  const s = Math.max(0, Math.round(((toIso ? new Date(toIso) : new Date()) - new Date(fromIso)) / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return (h ? `${h}h ` : '') + `${m}m ${String(sec).padStart(2, '0')}s`;
}

export function formatCode(code) {
  return code ? code.replace(/(\d{3})(?=\d)/g, '$1 ') : '';
}

export function navigate(path) {
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}
