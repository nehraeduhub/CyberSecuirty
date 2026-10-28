/* SSH terminal in a browser tab: xterm.js <-> WebSocket (/api/ssh) <-> the
 * manager, which opens the SSH session to the device. ssh.html?host=IP[&port=22][&name=…] */
(function () {
  'use strict';

  var DC = window.DC;
  var $ = DC.$, el = DC.el;
  var q = new URLSearchParams(location.search);
  var host = q.get('host') || '', port = q.get('port') || '22', name = q.get('name') || host;
  var st = { ws: null, term: null, fit: null, keyState: '', connected: false, pending: null };

  var label = name && name !== host ? name + ' (' + host + (port !== '22' ? ':' + port : '') + ')' : host + (port !== '22' ? ':' + port : '');
  $('target').textContent = label;
  $('target2').textContent = label;
  document.title = 'SSH ' + (name || host) + ' | DC NOC';

  function setState(kind, text) {
    var map = { up: ['st-up', 's-up', '✓'], down: ['st-down', 's-down', '✕'], unknown: ['st-unknown', 's-unknown', '…'] };
    var m = map[kind];
    $('state').className = 'state ' + m[0];
    $('state').firstElementChild.className = 'sico ' + m[1];
    $('state').firstElementChild.textContent = m[2];
    $('state-text').textContent = text;
  }

  function showError(text) {
    $('ssh-error').textContent = text;
    $('ssh-form').hidden = false;
    $('term').hidden = true;
    $('ssh-go').disabled = false;
    $('reconnect').hidden = false;
    setState('down', 'Not connected');
  }

  // ------------------------------------------------------------- socket
  function open() {
    if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) { showError('No device given: open SSH from the Monitor or Manage devices page.'); return; }
    $('ssh-error').textContent = '';
    $('hostkey').hidden = true;
    $('reconnect').hidden = true;
    $('ssh-go').disabled = true;
    st.connected = false;
    setState('unknown', 'Connecting…');
    var url = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/api/ssh?host=' + encodeURIComponent(host) +
      '&port=' + encodeURIComponent(port);
    var ws = new WebSocket(url);
    ws.binaryType = 'arraybuffer';
    st.ws = ws;
    var gotMessage = false;
    ws.onmessage = function (ev) {
      gotMessage = true;
      if (typeof ev.data !== 'string') { if (st.term) st.term.write(new Uint8Array(ev.data)); return; }
      var m;
      try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (m.type === 'status') setState('unknown', m.text);
      else if (m.type === 'hostkey') hostKey(m);
      else if (m.type === 'error') { st.connected = false; showError(m.text); }
      else if (m.type === 'ready') ready();
      else if (m.type === 'closed') { st.connected = false; setState('down', m.text || 'Session ended'); $('reconnect').hidden = false; if (st.term) st.term.write('\r\n\x1b[90m[' + (m.text || 'Session ended') + ']\x1b[0m\r\n'); }
    };
    ws.onclose = function () {
      if (!gotMessage) { showError('Could not open the SSH connection. Check that ' + host + ' is in the device list and the DC NOC server is running.'); return; }
      if (st.connected) {
        st.connected = false;
        setState('down', 'Disconnected');
        $('reconnect').hidden = false;
        if (st.term) st.term.write('\r\n\x1b[90m[Disconnected]\x1b[0m\r\n');
      }
    };
  }

  function hostKey(m) {
    st.keyState = m.state;
    var box = $('hostkey');
    box.textContent = '';
    box.hidden = false;
    box.className = 'hostkey ' + (m.state === 'new' ? 'new' : 'ok');
    if (m.state === 'new') {
      box.appendChild(el('strong', { text: 'First connection to this device.' }));
      box.appendChild(el('span', { text: ' Its key fingerprint is ' }));
      box.appendChild(el('code', { text: m.fingerprint }));
      box.appendChild(el('span', { text: '. Connecting trusts this key; you are warned if it ever changes.' }));
    } else if (m.state === 'known') {
      box.appendChild(el('span', { text: 'Device key verified ' }));
      box.appendChild(el('code', { text: m.fingerprint }));
    }
    setState('unknown', 'Waiting for login');
    $('ssh-go').disabled = m.state === 'changed';
    if (st.pending && m.state !== 'changed') { var p = st.pending; st.pending = null; sendLogin(p.user, p.password); return; }
    var f = $('ssh-form');
    (f.user.value ? f.password : f.user).focus();
  }

  // ------------------------------------------------------------- terminal
  function ensureTerm() {
    if (st.term) return;
    st.term = new window.Terminal({
      cursorBlink: true, fontSize: 14, scrollback: 5000,
      fontFamily: 'Consolas, "Cascadia Mono", "DejaVu Sans Mono", monospace',
      theme: { background: '#05090c', foreground: '#dfeeec', cursor: '#00e5d4', selectionBackground: '#1d4b47' }
    });
    st.fit = new window.FitAddon.FitAddon();
    st.term.loadAddon(st.fit);
    st.term.open($('term'));
    st.term.onData(function (d) {
      if (st.ws && st.ws.readyState === 1 && st.connected) st.ws.send(JSON.stringify({ type: 'data', data: d }));
    });
    window.addEventListener('resize', resize);
  }

  function resize() {
    if (!st.term || $('term').hidden) return;
    st.fit.fit();
    if (st.ws && st.ws.readyState === 1 && st.connected) st.ws.send(JSON.stringify({ type: 'resize', cols: st.term.cols, rows: st.term.rows }));
  }

  function ready() {
    st.connected = true;
    $('ssh-form').hidden = true;
    setState('up', 'Connected');
    resize();
    st.term.focus();
  }

  function sendLogin(user, password) {
    $('ssh-error').textContent = '';
    $('term').hidden = false;
    ensureTerm();
    st.term.reset();
    st.fit.fit();
    setState('unknown', 'Logging in…');
    $('ssh-go').disabled = true;
    st.ws.send(JSON.stringify({ type: 'login', user: user, password: password,
      trust: st.keyState === 'new', cols: st.term.cols, rows: st.term.rows }));
  }

  $('ssh-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var f = e.target, user = f.user.value.trim(), password = f.password.value;
    f.password.value = '';
    // After a failed login the device connection is closed: reconnect, then log in
    if (!st.ws || st.ws.readyState !== 1) { st.pending = { user: user, password: password }; open(); return; }
    sendLogin(user, password);
  });
  $('reconnect').addEventListener('click', function () { if (st.term) st.term.reset(); $('term').hidden = true; $('ssh-form').hidden = false; open(); });

  open();
})();
