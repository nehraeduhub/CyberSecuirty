/* Scan & settings: networks and SNMP credentials the collector uses, scan
 * options, feature switches, and "Scan now" with live progress. Everything is
 * stored by the manager API (settings.json on the server). */
(function () {
  'use strict';

  var DC = window.DC;
  var el = DC.el, $ = DC.$;

  var FEATURES = [
    ['public_monitor', 'Monitor page without sign-in', 'Anyone who can open the portal sees the live status (read-only); changes always need sign-in'],
    ['monitor_unidentified', 'Show status of unidentified devices', 'Ping devices that did not answer SNMP too'],
    ['inventory', 'Inventory tab', 'Charts, network map and collection details'],
    ['grafana', 'Status tab (Grafana)', 'Up/down history, ports, traffic and hardware health dashboards'],
    ['racks', 'Racks tab', 'Rooms and rack elevations from GLPI'],
    ['library', 'Learning library link', 'Back link to the NehraEduHub website'],
    ['servers', 'Collect servers over SSH / WinRM', 'Uses REMOTES in collector/collector.conf'],
    ['vmware', 'Collect VMware (ESXi / vCenter)', 'Uses ESX_HOSTS in collector/collector.conf']
  ];

  var st = { s: null, admin: false, dirty: false, poll: null, waitingScan: false };

  function markDirty() {
    st.dirty = true;
    $('save').disabled = !st.admin;
    $('dirty').textContent = 'Unsaved changes';
  }

  // ------------------------------------------------------------- load
  function load() {
    return Promise.all([DC.mgr('settings'), DC.mgr('whoami')]).then(function (r) {
      st.s = r[0];
      st.admin = !!r[1].admin;
      $('who').textContent = r[1].name + ' (' + r[1].profile + ')';
      $('readonly').hidden = st.admin;
      st.dirty = false;
      $('dirty').textContent = '';
      $('save').disabled = true;
      render();
    }).catch(function (e) {
      if (e.status === 401) { DC.logout(true); return; }
      $('save-error').textContent = 'Could not load the settings: ' + e.message;
    });
  }

  // ------------------------------------------------------------- render
  function toggle(checked, label, onchange) {
    return el('input', { type: 'checkbox', checked: checked ? 'checked' : null, 'aria-label': label, disabled: st.admin ? null : 'disabled', onchange: onchange });
  }

  function removeBtn(label, fn) {
    return el('button', { type: 'button', class: 'link-btn', 'aria-label': label, title: label, text: 'Remove', disabled: st.admin ? null : 'disabled', onclick: fn });
  }

  function render() {
    var s = st.s;
    // Networks
    var nb = $('nets');
    nb.textContent = '';
    s.networks.forEach(function (n, i) {
      nb.appendChild(el('tr', {}, [
        el('td', {}, [toggle(n.enabled, 'Scan ' + n.network, function (e) { n.enabled = e.target.checked; markDirty(); })]),
        el('td', { class: 'mono', text: n.network }),
        el('td', { text: n.name || '' }),
        el('td', {}, [removeBtn('Remove ' + n.network, function () { s.networks.splice(i, 1); markDirty(); render(); })])
      ]));
    });
    $('nets-empty').hidden = s.networks.length > 0;

    // Credentials
    var cb = $('creds');
    cb.textContent = '';
    s.snmp.forEach(function (c, i) {
      var who = c.version === '3'
        ? c.username + ' (' + (c.authprotocol ? c.authprotocol.toUpperCase() : 'no auth') + (c.privprotocol ? ' + ' + c.privprotocol.toUpperCase() : '') + ')'
        : 'community ' + (c.community || '');
      cb.appendChild(el('tr', {}, [
        el('td', {}, [toggle(c.enabled, 'Use credential ' + (i + 1), function (e) { c.enabled = e.target.checked; markDirty(); })]),
        el('td', { text: c.name || 'Credential ' + (i + 1) }),
        el('td', { text: 'v' + c.version }),
        el('td', { class: 'mono', text: who }),
        el('td', {}, [removeBtn('Remove credential ' + (i + 1), function () { s.snmp.splice(i, 1); markDirty(); render(); })])
      ]));
    });
    $('creds-empty').hidden = s.snmp.length > 0;

    // Options
    [['o-interval', 'interval_minutes'], ['o-threads', 'threads'], ['o-timeout', 'timeout']].forEach(function (o) {
      var inp = $(o[0]);
      inp.value = s.scan[o[1]];
      inp.disabled = !st.admin;
      inp.oninput = function () { s.scan[o[1]] = parseInt(inp.value, 10) || 0; markDirty(); };
    });

    // Features
    var fb = $('features');
    fb.textContent = '';
    FEATURES.forEach(function (f) {
      var id = 'feat-' + f[0];
      fb.appendChild(el('label', { class: 'toggle', for: id }, [
        el('input', { id: id, type: 'checkbox', checked: s.features[f[0]] ? 'checked' : null, disabled: st.admin ? null : 'disabled',
          onchange: function (e) { s.features[f[0]] = e.target.checked; markDirty(); } }),
        el('span', {}, [el('strong', { text: f[1] }), el('span', { class: 'muted small', text: f[2] })])
      ]));
    });

    document.querySelectorAll('#net-form input, #net-form button, #cred-form input, #cred-form select, #cred-form button, #scan-now')
      .forEach(function (x) { x.disabled = !st.admin; });
  }

  // ------------------------------------------------------------- edits
  $('net-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var f = e.target, v = f.network.value.trim();
    if (!v) return;
    if (st.s.networks.some(function (n) { return n.network === v; })) { DC.toast(v + ' is already in the list', true); return; }
    st.s.networks.push({ network: v, name: f.name.value.trim(), enabled: true });
    f.reset();
    markDirty();
    render();
  });

  function showVersion() {
    var v = $('cred-form').version.value;
    document.querySelectorAll('#cred-form [data-v]').forEach(function (l) {
      l.hidden = v === '3' ? l.getAttribute('data-v') !== '3' : l.getAttribute('data-v') !== '12';
    });
  }
  $('cred-form').version.addEventListener('change', showVersion);
  $('cred-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var f = e.target, v = f.version.value, c = { version: v, name: f.name.value.trim(), enabled: true };
    if (v === '3') {
      if (!f.username.value.trim()) { DC.toast('Type the SNMPv3 user name', true); return; }
      c.username = f.username.value.trim();
      if (f.authpassword.value) { c.authprotocol = f.authprotocol.value; c.authpassword = f.authpassword.value; }
      if (f.privpassword.value && f.privprotocol.value) { c.privprotocol = f.privprotocol.value; c.privpassword = f.privpassword.value; }
    } else {
      if (!f.community.value.trim()) { DC.toast('Type the community', true); return; }
      c.community = f.community.value.trim();
    }
    st.s.snmp.push(c);
    f.reset();
    showVersion();
    markDirty();
    render();
  });

  function save() {
    $('save-error').textContent = '';
    $('save').disabled = true;
    return DC.mgr('settings', { method: 'PUT', body: st.s }).then(function (s) {
      st.s = s;
      st.dirty = false;
      $('dirty').textContent = '';
      DC.toast('Saved. The next scan uses these settings.');
      render();
      DC.applyFeatures();
    }).catch(function (e) {
      $('save').disabled = false;
      $('save-error').textContent = e.message;
      throw e;
    });
  }
  $('save').addEventListener('click', function () { save().catch(function () {}); });

  window.addEventListener('beforeunload', function (e) {
    if (st.dirty) { e.preventDefault(); e.returnValue = ''; }
  });

  // ------------------------------------------------------------- find networks
  $('find-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var box = $('find-result'), router = e.target.router.value.trim();
    box.textContent = 'Asking ' + router + '…';
    var go = st.dirty ? save() : Promise.resolve();
    go.then(function () {
      return DC.mgr('find-networks', { method: 'POST', body: { router: router } });
    }).then(function (r) {
      box.textContent = '';
      if (r.error && !(r.networks || []).length) { box.appendChild(el('p', { class: 'error', text: r.error })); return; }
      var have = {};
      st.s.networks.forEach(function (n) { have[n.network] = 1; });
      var fresh = r.networks.filter(function (n) { return !have[n.network]; });
      var list = el('ul', { class: 'found' });
      r.networks.forEach(function (n) {
        var b = el('button', { type: 'button', class: 'link-btn', text: have[n.network] ? 'Added' : 'Add', disabled: have[n.network] ? 'disabled' : null });
        b.addEventListener('click', function () { addFound(n); b.textContent = 'Added'; b.disabled = true; });
        list.appendChild(el('li', {}, [el('span', { class: 'mono', text: n.network }), el('span', { class: 'muted small', text: ' ' + n.source + ' ' }), b]));
      });
      box.appendChild(list);
      if (fresh.length > 1) {
        box.appendChild(el('button', { type: 'button', class: 'btn ghost', text: 'Add all ' + fresh.length, onclick: function () {
          fresh.forEach(addFound);
          box.querySelectorAll('.found .link-btn').forEach(function (b) { b.textContent = 'Added'; b.disabled = true; });
        } }));
      }
    }).catch(function (err) {
      box.textContent = '';
      box.appendChild(el('p', { class: 'error', text: err.message }));
    });
  });

  function addFound(n) {
    if (st.s.networks.some(function (x) { return x.network === n.network; })) return;
    st.s.networks.push({ network: n.network, name: 'found (' + n.source + ')', enabled: true });
    markDirty();
    render();
  }

  // ------------------------------------------------------------- scan
  function fmtTime(iso) { return iso ? new Date(iso).toLocaleString() : ''; }

  function pollStatus() {
    return fetch('../collector/status.json', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; })
      .then(function (s) {
        var box = $('scan-state'), steps = $('scan-steps');
        steps.textContent = '';
        if (!s) { box.textContent = st.waitingScan ? 'Scan requested, starting…' : 'No scan has run yet.'; return; }
        var running = s.state === 'running';
        if (running) st.waitingScan = false;
        box.textContent = st.waitingScan ? 'Scan requested, starting in a few seconds…'
          : running ? 'Scanning since ' + fmtTime(s.started) + '…'
          : 'Last scan finished ' + fmtTime(s.finished) + '. Next one within ' + (s.interval_minutes || '?') + ' minutes.';
        (s.steps || []).forEach(function (x) {
          steps.appendChild(el('li', {}, [
            el('span', { class: 'status-ico s-' + (x.status === 'ok' ? 'ok' : x.status === 'warning' ? 'warning' : 'error'), text: x.status === 'ok' ? '✓' : '!' }),
            el('span', { class: 'step-name', text: x.name }),
            el('span', { class: 'muted small', text: x.files + ' found, ' + x.sent + ' saved' }),
            x.detail ? el('span', { class: 'step-detail', text: x.detail }) : null
          ]));
        });
        // Poll fast while something is happening
        clearTimeout(st.poll);
        st.poll = setTimeout(pollStatus, running || st.waitingScan ? 4000 : 30000);
      });
  }

  $('scan-now').addEventListener('click', function () {
    var go = st.dirty ? save() : Promise.resolve();
    go.then(function () { return DC.mgr('scan', { method: 'POST' }); }).then(function () {
      st.waitingScan = true;
      DC.toast('Scan requested');
      pollStatus();
    }).catch(function (e) { DC.toast('Could not start the scan: ' + e.message, true); });
  });

  DC.initAuth({
    onReady: function () { load(); pollStatus(); },
    onLogout: function () { clearTimeout(st.poll); }
  });
})();
