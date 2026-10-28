/* Manage devices: the DC NOC device list (manager API) with live status;
 * edit name, IP, category, make, model, serial, MAC, location and notes; add
 * devices by IP; set categories or delete in bulk; CSV export.
 * devices.html?edit=<id> opens a device, devices.html?q=<text> searches. */
(function () {
  'use strict';

  var DC = window.DC;
  var el = DC.el, $ = DC.$;

  var COLS = [
    { key: 'sel', label: '' },
    { key: 'state', label: 'Status', sort: true },
    { key: 'name', label: 'Name', sort: true },
    { key: 'ip', label: 'IP address', sort: true },
    { key: 'category', label: 'Category', sort: true },
    { key: 'brand', label: 'Make', sort: true },
    { key: 'model', label: 'Model', sort: true },
    { key: 'serial', label: 'Serial no.', sort: true },
    { key: 'mac', label: 'MAC', sort: true },
    { key: 'location', label: 'Location', sort: true },
    { key: 'last_seen', label: 'Last scan', sort: true },
    { key: 'go', label: 'Actions' }
  ];
  var STATE_LABEL = { up: 'Online', down: 'Offline', unknown: 'Not monitored' };

  var st = { devices: [], status: {}, cats: [], sort: { key: 'ip', dir: 1 }, selected: {}, editing: null };
  var params = new URLSearchParams(location.search);
  if (params.get('q')) $('q').value = params.get('q');

  // ------------------------------------------------------------- loading
  function load() {
    $('app-error').textContent = '';
    $('updated').textContent = 'Loading…';
    return Promise.all([DC.mgr('devices'), loadStatus()]).then(function (r) {
      st.devices = r[0].devices || [];
      st.cats = r[0].category_list || [];
      fillLists();
      render();
      $('updated').textContent = 'Updated ' + new Date().toLocaleTimeString();
      var want = params.get('edit');
      if (want) {
        params.delete('edit');
        var d = st.devices.find(function (x) { return String(x.id) === want; });
        if (d) openEdit(d);
      }
    }).catch(function (e) {
      $('app-error').textContent = 'Could not load the device list: ' + e.message;
      $('updated').textContent = '';
    });
  }

  function loadStatus() {
    return DC.mgr('status').then(function (s) { st.status = s || {}; }).catch(function () {});
  }

  function stateOf(d) {
    var s = st.status[d.ip];
    return !s ? 'unknown' : s.up ? 'up' : 'down';
  }

  function fillLists() {
    var fc = $('f-cat'), cur = fc.value;
    fc.length = 1;
    st.cats.forEach(function (c) {
      var n = st.devices.filter(function (d) { return d.category === c; }).length;
      if (n) fc.appendChild(el('option', { value: c, text: c + ' (' + n + ')' }));
    });
    fc.value = cur;
    [['edit-category', 'Automatic (from make and model)'], ['add-category', 'Automatic (from make and model)']].forEach(function (x) {
      var s = $(x[0]);
      s.length = 0;
      s.appendChild(el('option', { value: '', text: x[1] }));
      st.cats.forEach(function (c) { s.appendChild(el('option', { value: c, text: c })); });
    });
    var bulk = $('bulk-cat');
    bulk.length = 1;
    bulk.appendChild(el('option', { value: '__auto', text: 'Automatic' }));
    st.cats.forEach(function (c) { bulk.appendChild(el('option', { value: c, text: c })); });
    // Suggestions while typing make, model and location
    [['dl-brand', 'brand'], ['dl-model', 'model'], ['dl-location', 'location']].forEach(function (x) {
      var dl = $(x[0]), seen = {};
      dl.textContent = '';
      st.devices.forEach(function (d) { if (d[x[1]] && !seen[d[x[1]]]) { seen[d[x[1]]] = 1; dl.appendChild(el('option', { value: d[x[1]] })); } });
    });
  }

  // ------------------------------------------------------------- render
  function filtered() {
    var q = $('q').value.trim().toLowerCase(), cat = $('f-cat').value, s = $('f-status').value;
    return st.devices.filter(function (d) {
      if (cat && d.category !== cat) return false;
      if (s && stateOf(d) !== s) return false;
      if (!q) return true;
      return [d.name, d.ip, d.category, d.brand, d.model, d.serial, d.mac, d.location, d.notes].join(' ').toLowerCase().indexOf(q) !== -1;
    });
  }

  function sortVal(d, key) {
    if (key === 'ip') return DC.ipNum(d.ip);
    if (key === 'state') return { down: 0, unknown: 1, up: 2 }[stateOf(d)];
    return String(d[key] || '').toLowerCase();
  }

  function renderStats() {
    var n = { all: st.devices.length, up: 0, down: 0, unknown: 0 };
    st.devices.forEach(function (d) { n[stateOf(d)]++; });
    var box = $('stats');
    box.textContent = '';
    [['', n.all, 'Devices'], ['up', n.up, 'Online'], ['down', n.down, 'Offline'], ['unknown', n.unknown, 'Not monitored yet']].forEach(function (s) {
      box.appendChild(el('button', { type: 'button', class: 'stat clickable', onclick: function () { $('f-status').value = s[0]; render(); } }, [
        el('div', { class: 'v' }, [s[0] ? el('span', { class: 'sdot s-' + s[0] }) : null, String(s[1])]),
        el('div', { class: 'l', text: s[2] })
      ]));
    });
  }

  function render() {
    renderStats();
    var head = $('thead');
    head.textContent = '';
    COLS.forEach(function (c) {
      var th = el('th', { scope: 'col' });
      if (c.key === 'sel') {
        th.appendChild(el('input', { type: 'checkbox', 'aria-label': 'Select all shown', onchange: function (e) {
          filtered().forEach(function (d) { if (e.target.checked) st.selected[d.id] = d; else delete st.selected[d.id]; });
          render();
        } }));
      } else if (c.sort) {
        var arrow = st.sort.key === c.key ? (st.sort.dir > 0 ? ' ▲' : ' ▼') : '';
        th.appendChild(el('button', { type: 'button', class: 'sort', text: c.label + arrow, onclick: function () {
          st.sort = { key: c.key, dir: st.sort.key === c.key ? -st.sort.dir : 1 };
          render();
        } }));
        th.setAttribute('aria-sort', st.sort.key === c.key ? (st.sort.dir > 0 ? 'ascending' : 'descending') : 'none');
      } else th.textContent = c.label;
      head.appendChild(th);
    });
    var list = filtered().sort(function (a, b) {
      var x = sortVal(a, st.sort.key), y = sortVal(b, st.sort.key);
      return (x < y ? -1 : x > y ? 1 : 0) * st.sort.dir || DC.ipNum(a.ip) - DC.ipNum(b.ip);
    });
    var body = $('rows');
    body.textContent = '';
    list.forEach(function (d) { body.appendChild(row(d)); });
    $('empty').hidden = list.length > 0;
    $('empty').textContent = st.devices.length ? 'No device matches the filters.'
      : 'No devices yet. Add your networks on Scan & settings and press Scan now, or use Add devices.';
    var n = Object.keys(st.selected).length;
    $('del').disabled = !n;
    $('bulk-cat').disabled = !n;
    $('del').textContent = 'Delete selected' + (n ? ' (' + n + ')' : '');
  }

  function row(d) {
    var s = stateOf(d), x = st.status[d.ip] || {};
    return el('tr', { class: s === 'down' ? 'is-down' : '' }, [
      el('td', {}, [el('input', { type: 'checkbox', 'aria-label': 'Select ' + d.name, checked: st.selected[d.id] ? 'checked' : null,
        onchange: function (e) { if (e.target.checked) st.selected[d.id] = d; else delete st.selected[d.id]; render(); } })]),
      el('td', { class: 'nowrap' }, [el('span', { class: 'sdot s-' + s }), STATE_LABEL[s] + (s === 'up' && x.rtt_ms != null ? ' · ' + x.rtt_ms + ' ms' : '')]),
      el('td', {}, [el('button', { type: 'button', class: 'name-btn', title: 'Edit', text: d.name, onclick: function () { openEdit(d); } })]),
      el('td', { class: 'mono nowrap', text: d.ip }),
      el('td', { class: 'nowrap' }, [d.category, d.locked && d.locked.category ? null : el('span', { class: 'muted small', text: ' auto' })]),
      el('td', { text: d.brand || '' }),
      el('td', { text: d.model || '' }),
      el('td', { class: 'mono', text: d.serial || '' }),
      el('td', { class: 'mono nowrap', text: d.mac || '' }),
      el('td', { text: d.location || '' }),
      el('td', { class: 'nowrap small', text: (d.last_seen || '').replace('T', ' ').slice(0, 16) }),
      el('td', { class: 'nowrap' }, DC.connectButtons(d.ip, d.name).concat([
        el('button', { type: 'button', class: 'go', text: 'Edit', onclick: function () { openEdit(d); } })
      ]))
    ]);
  }

  // ------------------------------------------------------------- edit
  var FIELDS = ['name', 'ip', 'category', 'brand', 'model', 'serial', 'mac', 'location', 'notes'];

  function openEdit(d) {
    st.editing = d;
    var f = $('edit-form');
    f.reset();
    $('edit-title').textContent = 'Edit ' + d.name;
    $('edit-error').textContent = '';
    FIELDS.forEach(function (k) { f[k].value = k === 'category' ? (d.locked && d.locked.category ? d.category : '') : (d[k] || ''); });
    var facts = $('edit-facts');
    facts.textContent = '';
    [['Automatic category', d.locked && d.locked.category ? '' : d.category], ['Found by scan', d.description], ['Firmware', d.firmware],
     ['Device type', d.type], ['Answers SNMP', d.snmp ? 'yes' : ''], ['Added', [(d.first_seen || '').replace('T', ' ').slice(0, 16), d.source === 'glpi' ? 'copied from GLPI' : d.source === 'manual' ? 'by hand' : d.source].filter(Boolean).join(', ')],
     ['Last scan', (d.last_seen || '').replace('T', ' ').slice(0, 16)]].forEach(function (p) {
      if (!p[1]) return;
      facts.appendChild(el('dt', { text: p[0] }));
      facts.appendChild(el('dd', { text: p[1] }));
    });
    $('edit-dialog').showModal();
    f.name.focus();
  }

  $('edit-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var f = e.target, d = st.editing, change = {};
    FIELDS.forEach(function (k) {
      var v = f[k].value.trim();
      var cur = k === 'category' ? (d.locked && d.locked.category ? d.category : '') : (d[k] || '');
      if (v !== cur) change[k] = v;
    });
    if (!Object.keys(change).length) { $('edit-dialog').close(); return; }
    $('edit-save').disabled = true;
    DC.mgr('devices/' + d.id, { method: 'PUT', body: change }).then(function (nd) {
      Object.keys(nd).forEach(function (k) { d[k] = nd[k]; });
      $('edit-dialog').close();
      DC.toast('Saved ' + d.name);
      fillLists();
      render();
    }).catch(function (err) {
      $('edit-error').textContent = err.message;
    }).then(function () { $('edit-save').disabled = false; });
  });
  $('edit-cancel').addEventListener('click', function () { $('edit-dialog').close(); });

  // ------------------------------------------------------------- add
  $('add').addEventListener('click', function () {
    $('add-error').textContent = '';
    $('add-form').reset();
    $('add-dialog').showModal();
  });
  $('add-cancel').addEventListener('click', function () { $('add-dialog').close(); });
  $('add-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var f = e.target, list = [];
    f.lines.value.split(/\n/).forEach(function (line) {
      line = line.trim();
      if (!line || line[0] === '#') return;
      var ip = line.split(/[\s,;]+/)[0], name = line.slice(ip.length).replace(/^[\s,;]+/, '').trim();
      list.push({ ip: ip, name: name || ip, category: f.category.value });
    });
    if (!list.length) { $('add-error').textContent = 'Type at least one IP address.'; return; }
    $('add-save').disabled = true;
    DC.mgr('devices', { method: 'POST', body: { devices: list } }).then(function (r) {
      if (r.error) $('add-error').textContent = 'Added ' + r.added.length + '. Not added:\n' + r.error;
      else { $('add-dialog').close(); DC.toast('Added ' + r.added.length + ' device(s); their status appears within a minute'); }
      load();
    }).catch(function (err) {
      $('add-error').textContent = err.message;
    }).then(function () { $('add-save').disabled = false; });
  });

  // ------------------------------------------------------------- bulk
  function selectedIds() { return Object.keys(st.selected).map(Number); }

  $('bulk-cat').addEventListener('change', function (e) {
    var v = e.target.value, ids = selectedIds();
    e.target.value = '';
    if (!v || !ids.length) return;
    DC.mgr('devices/bulk', { method: 'POST', body: { ids: ids, category: v === '__auto' ? '' : v } }).then(function () {
      DC.toast(ids.length + ' device(s) set to ' + (v === '__auto' ? 'automatic' : v));
      st.selected = {};
      load();
    }, function (err) { DC.toast(err.message, true); });
  });

  $('del').addEventListener('click', function () {
    var list = Object.keys(st.selected).map(function (k) { return st.selected[k]; });
    if (!list.length) return;
    if (!confirm('Delete ' + list.length + ' device(s) from the list?\n\n' + list.slice(0, 15).map(function (d) { return d.name + '  ' + d.ip; }).join('\n') +
      (list.length > 15 ? '\n…' : '') + '\n\nA scan adds them again if they are still on a scanned network.')) return;
    DC.mgr('devices/bulk', { method: 'POST', body: { ids: selectedIds(), delete: true } }).then(function (r) {
      DC.toast('Deleted ' + r.deleted + ' device(s)');
      st.selected = {};
      load();
    }, function (err) { DC.toast(err.message, true); });
  });

  // ------------------------------------------------------------- CSV
  $('csv').addEventListener('click', function () {
    var cols = ['name', 'ip', 'category', 'brand', 'model', 'serial', 'mac', 'location', 'notes', 'last_seen'];
    var lines = [cols.concat(['status']).join(',')].concat(filtered().map(function (d) {
      return cols.map(function (c) { return d[c] || ''; }).concat([stateOf(d)]).map(function (v) {
        v = String(v);
        if (/^[=+\-@]/.test(v)) v = "'" + v;   // no spreadsheet formulas
        return '"' + v.replace(/"/g, '""') + '"';
      }).join(',');
    }));
    var a = el('a', { href: URL.createObjectURL(new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv' })), download: 'dc-devices.csv' });
    document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  });

  // ------------------------------------------------------------- wiring
  ['q', 'f-cat', 'f-status'].forEach(function (id) { $(id).addEventListener('input', render); });
  $('refresh').addEventListener('click', load);
  DC.applyFeatures();
  load();
  setInterval(function () { if (!$('edit-dialog').open) loadStatus().then(render); }, 30000);
})();
