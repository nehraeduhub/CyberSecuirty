/* Devices: every device in GLPI with its IP, live up/down status (from the
 * manager API, i.e. Prometheus ping), brand, model, serial and MAC, with
 * rename, add, delete and one-click SSH / RDP / web access. */
(function () {
  'use strict';

  var DC = window.DC;
  var el = DC.el, $ = DC.$;

  var TYPES = [
    { itemtype: 'NetworkEquipment', label: 'Network' },
    { itemtype: 'Computer', label: 'Server' },
    { itemtype: 'PDU', label: 'Power' },
    { itemtype: 'Printer', label: 'Printer' },
    { itemtype: 'Phone', label: 'Phone' },
    { itemtype: 'Peripheral', label: 'Peripheral' },
    { itemtype: 'Unmanaged', label: 'Unidentified' }
  ];
  var LABEL = {};
  TYPES.forEach(function (t) { LABEL[t.itemtype] = t.label; });

  var COLS = [
    { key: 'sel', label: '' },
    { key: 'state', label: 'Status', sort: true },
    { key: 'name', label: 'Name', sort: true },
    { key: 'ip', label: 'IP address', sort: true },
    { key: 'category', label: 'Category', sort: true },
    { key: 'type', label: 'GLPI type', sort: true },
    { key: 'brand', label: 'Brand', sort: true },
    { key: 'model', label: 'Model', sort: true },
    { key: 'serial', label: 'Serial no.', sort: true },
    { key: 'mac', label: 'MAC', sort: true },
    { key: 'seen', label: 'Last scan', sort: true },
    { key: 'go', label: 'Connect' }
  ];

  var state = { devices: [], status: {}, cats: {}, catList: [], admin: false, sort: { key: 'ip', dir: 1 }, selected: {} };
  var timers = [];

  // ------------------------------------------------------------- loading
  function load() {
    $('app-error').textContent = '';
    $('updated').textContent = 'Loading…';
    return Promise.all([
      Promise.all(TYPES.map(function (t) { return DC.fetchAll(t.itemtype, 'expand_dropdowns=true'); })),
      DC.fetchAll('IPAddress'),
      DC.fetchAll('NetworkPort'),
      loadStatus(),
      loadCategories(),
      DC.mgr('whoami').then(function (w) { state.admin = !!w.admin; }, function () {})
    ]).then(function (r) {
      state.devices = build(r[0], r[1], r[2]);
      fillCategoryLists();
      fillTypes();
      render();
      $('updated').textContent = 'Updated ' + new Date().toLocaleTimeString();
    }).catch(function (e) {
      DC.loadError(e, $('app-error'), $('updated'));
    });
  }

  // Category per IP, as on the Monitor page (automatic or chosen here)
  function loadCategories() {
    return DC.mgr('monitor').then(function (m) {
      state.cats = {};
      (m.devices || []).forEach(function (d) { state.cats[d.ip] = { name: d.category, set: d.category_set }; });
      state.catList = m.category_list || [];
    }).catch(function () {});
  }

  function catOf(d) { return (state.cats[d.ip] || {}).name || (d.itemtype === 'Unmanaged' ? 'Unknown' : ''); }

  function fillCategoryLists() {
    var add = $('add-category'), bulk = $('bulk-cat');
    add.length = 0;
    add.appendChild(el('option', { value: '', text: 'Automatic (from brand and model)' }));
    bulk.length = 1;
    bulk.appendChild(el('option', { value: '__auto', text: 'Automatic' }));
    state.catList.forEach(function (c) {
      add.appendChild(el('option', { value: c, text: c }));
      bulk.appendChild(el('option', { value: c, text: c }));
    });
  }

  // Set (or with '' clear) the category of these devices
  function setCategory(list, cat) {
    var ips = list.map(function (d) { return d.ip; }).filter(Boolean);
    if (!ips.length) return Promise.resolve();
    return DC.mgr('categories', { method: 'PUT', body: { ips: ips, category: cat } }).then(function () {
      return loadCategories();
    });
  }

  function loadStatus() {
    return DC.mgr('status').then(function (s) {
      state.status = s || {};
      state.statusError = '';
    }).catch(function (e) {
      if (e.status === 401) return;
      state.statusError = 'Live status unavailable: ' + e.message;
    });
  }

  function ipNum(ip) {
    var p = String(ip || '').split('.');
    return p.length === 4 ? ((+p[0] * 256 + +p[1]) * 256 + +p[2]) * 256 + +p[3] : Infinity;
  }

  function dropdown(v) {
    if (v == null || v === 0 || v === '0' || v === '&nbsp;') return '';
    return String(v);
  }

  function build(items, ips, ports) {
    var ipBy = {}, macBy = {};
    ips.forEach(function (a) {
      if (!a.mainitemtype || !a.name || a.version !== 4 || /^(127\.|169\.254\.|0\.)/.test(a.name)) return;
      var k = a.mainitemtype + ':' + a.mainitems_id;
      (ipBy[k] = ipBy[k] || []).push(a.name);
    });
    ports.forEach(function (p) {
      var k = p.itemtype + ':' + p.items_id;
      if (p.mac && !/^(00:){5}00$/.test(p.mac) && !macBy[k]) macBy[k] = p.mac;
    });
    var out = [];
    TYPES.forEach(function (t, i) {
      items[i].forEach(function (it) {
        if (it.is_template || (t.itemtype === 'Unmanaged' && it.hub)) return;
        var k = t.itemtype + ':' + it.id;
        var list = (ipBy[k] || []).slice().sort(function (a, b) { return ipNum(a) - ipNum(b); });
        if (!list.length && t.itemtype === 'Unmanaged' && it.ip) list = [it.ip];
        var modelKey = Object.keys(it).find(function (x) { return /models_id$/.test(x); });
        out.push({
          key: k, itemtype: t.itemtype, id: it.id,
          name: it.name || list[0] || '(no name)',
          ip: list[0] || '', ips: list,
          type: t.label,
          brand: dropdown(it.manufacturers_id),
          model: dropdown(modelKey ? it[modelKey] : ''),
          serial: it.serial || '',
          mac: macBy[k] || it.mac || '',
          seen: it.last_inventory_update || ''
        });
      });
    });
    return out;
  }

  // up | down | none (not pinged yet / no IP)
  function stateOf(d) {
    var s = d.ip && state.status[d.ip];
    if (!s) return 'none';
    return s.up ? 'up' : 'down';
  }

  // ------------------------------------------------------------- render
  function fillTypes() {
    var sel = $('f-type'), cur = sel.value;
    sel.length = 1;
    TYPES.forEach(function (t) {
      var n = state.devices.filter(function (d) { return d.itemtype === t.itemtype; }).length;
      if (n) sel.appendChild(el('option', { value: t.itemtype, text: t.label + ' (' + n + ')' }));
    });
    sel.value = cur;
  }

  function filtered() {
    var q = $('q').value.trim().toLowerCase();
    var type = $('f-type').value, st = $('f-status').value;
    return state.devices.filter(function (d) {
      if (type && d.itemtype !== type) return false;
      if (st && stateOf(d) !== st) return false;
      if (!q) return true;
      return [d.name, d.ips.join(' '), d.serial, d.mac, d.model, d.brand, d.type, catOf(d)].join(' ').toLowerCase().indexOf(q) !== -1;
    });
  }

  function sortVal(d, key) {
    if (key === 'ip') return ipNum(d.ip);
    if (key === 'state') return { down: 0, none: 1, up: 2 }[stateOf(d)];
    if (key === 'category') return catOf(d).toLowerCase();
    return String(d[key] || '').toLowerCase();
  }

  function renderStats() {
    var n = { all: state.devices.length, up: 0, down: 0, none: 0 };
    state.devices.forEach(function (d) { n[stateOf(d)]++; });
    var box = $('stats');
    box.textContent = '';
    [['', n.all, 'Devices'], ['up', n.up, 'Up'], ['down', n.down, 'Down'], ['none', n.none, 'Not monitored yet']].forEach(function (s) {
      var b = el('button', { type: 'button', class: 'stat clickable', onclick: function () { $('f-status').value = s[0]; render(); } }, [
        el('div', { class: 'v' }, [s[0] ? el('span', { class: 'sdot s-' + s[0] }) : null, String(s[1])]),
        el('div', { class: 'l', text: s[2] })
      ]);
      box.appendChild(b);
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
          filtered().forEach(function (d) { if (e.target.checked) state.selected[d.key] = d; else delete state.selected[d.key]; });
          render();
        } }));
      } else if (c.sort) {
        var arrow = state.sort.key === c.key ? (state.sort.dir > 0 ? ' ▲' : ' ▼') : '';
        th.appendChild(el('button', { type: 'button', class: 'sort', text: c.label + arrow, onclick: function () {
          state.sort = { key: c.key, dir: state.sort.key === c.key ? -state.sort.dir : 1 };
          render();
        } }));
        th.setAttribute('aria-sort', state.sort.key === c.key ? (state.sort.dir > 0 ? 'ascending' : 'descending') : 'none');
      } else {
        th.textContent = c.label;
      }
      head.appendChild(th);
    });

    var list = filtered().sort(function (a, b) {
      var x = sortVal(a, state.sort.key), y = sortVal(b, state.sort.key);
      return (x < y ? -1 : x > y ? 1 : 0) * state.sort.dir || ipNum(a.ip) - ipNum(b.ip);
    });
    var body = $('rows');
    body.textContent = '';
    list.forEach(function (d) { body.appendChild(row(d)); });
    $('empty').hidden = list.length > 0;
    $('empty').textContent = state.devices.length
      ? 'No device matches the filters.'
      : 'No devices yet. Add your networks on the Scan & settings page and press Scan now, or use Add devices.';
    $('del').disabled = !Object.keys(state.selected).length;
    $('bulk-cat').disabled = !state.admin || !Object.keys(state.selected).length;
    $('del').textContent = 'Delete selected' + (Object.keys(state.selected).length ? ' (' + Object.keys(state.selected).length + ')' : '');
    if (state.statusError) $('app-error').textContent = state.statusError;
  }

  function row(d) {
    var st = stateOf(d), s = state.status[d.ip] || {};
    var stText = st === 'up' ? 'Up' + (s.rtt_ms != null ? ' · ' + s.rtt_ms + ' ms' : '') : st === 'down' ? 'Down' : d.ip ? 'Waiting…' : 'No IP';
    return el('tr', { class: st === 'down' ? 'is-down' : '' }, [
      el('td', {}, [el('input', { type: 'checkbox', 'aria-label': 'Select ' + d.name, checked: state.selected[d.key] ? 'checked' : null,
        onchange: function (e) { if (e.target.checked) state.selected[d.key] = d; else delete state.selected[d.key]; render(); } })]),
      el('td', { class: 'nowrap' }, [el('span', { class: 'sdot s-' + st }), stText]),
      el('td', {}, [nameCell(d)]),
      el('td', { class: 'mono nowrap', title: d.ips.join(', '), text: d.ip + (d.ips.length > 1 ? ' +' + (d.ips.length - 1) : '') }),
      el('td', {}, [categoryCell(d)]),
      el('td', { class: 'muted', text: d.type }),
      el('td', { text: d.brand }),
      el('td', { text: d.model }),
      el('td', { class: 'mono', text: d.serial }),
      el('td', { class: 'mono nowrap', text: d.mac }),
      el('td', { class: 'nowrap small', text: d.seen ? d.seen.slice(0, 16) : '' }),
      el('td', { class: 'nowrap' }, connect(d))
    ]);
  }

  function categoryCell(d) {
    var cur = state.cats[d.ip] || {};
    if (!state.admin || !d.ip) return document.createTextNode(catOf(d));
    var sel = el('select', { class: 'cat-select', 'aria-label': 'Category of ' + d.name });
    sel.appendChild(el('option', { value: '', text: (cur.set ? 'Automatic' : catOf(d) + ' (auto)') }));
    state.catList.forEach(function (c) { sel.appendChild(el('option', { value: c, text: c })); });
    sel.value = cur.set ? cur.name : '';
    sel.addEventListener('change', function () {
      setCategory([d], sel.value).then(function () { DC.toast(d.name + ': ' + (sel.value || 'automatic category')); render(); },
        function (e) { DC.toast('Could not set the category: ' + e.message, true); });
    });
    return sel;
  }

  // ------------------------------------------------------------- rename
  function editing() { var a = document.activeElement; return !!(a && a.classList.contains('name-input')); }

  function nameCell(d) {
    var b = el('button', { type: 'button', class: 'name-btn', title: 'Rename', text: d.name });
    b.addEventListener('click', function () {
      var input = el('input', { class: 'name-input', value: d.name, 'aria-label': 'New name for ' + d.ip });
      var done = false;
      function save() {
        if (done) return; done = true;
        var v = input.value.trim();
        if (!v || v === d.name) { render(); return; }
        input.disabled = true;
        DC.api(d.itemtype + '/' + d.id, { method: 'PUT', body: { input: { name: v } } }).then(function () {
          d.name = v;
          DC.mgr('sync', { method: 'POST' }).catch(function () {});
          DC.toast('Renamed to ' + v);
          render();
        }).catch(function (e) {
          DC.toast('Could not rename: ' + e.message, true);
          render();
        });
      }
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') save();
        if (e.key === 'Escape') { done = true; render(); }
      });
      input.addEventListener('blur', save);
      b.replaceWith(input);
      input.focus();
      input.select();
    });
    return b;
  }

  function connect(d) {
    return DC.connectButtons(d.ip, d.name, DC.glpiForm(d.itemtype, d.id));
  }

  // ------------------------------------------------------------- add
  function openAdd() {
    $('add-error').textContent = '';
    $('add-form').reset();
    $('add-dialog').showModal();
  }

  function isIp(s) { return /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.test(s) && s.split('.').every(function (n) { return +n <= 255; }); }

  function addDevices(e) {
    e.preventDefault();
    var f = e.target, cat = f.category.value, err = [], todo = [];
    var type = cat === 'Server' ? 'Computer' : cat === 'Unknown' ? 'Unmanaged' : 'NetworkEquipment';
    var known = {};
    state.devices.forEach(function (d) { d.ips.forEach(function (ip) { known[ip] = d.name; }); });
    f.lines.value.split(/\n/).forEach(function (line, i) {
      line = line.trim();
      if (!line || line[0] === '#') return;
      var ip = line.split(/[\s,;]+/)[0], name = line.slice(ip.length).replace(/^[\s,;]+/, '').trim();
      if (!isIp(ip)) err.push('Line ' + (i + 1) + ': "' + ip + '" is not an IP address');
      else if (known[ip]) err.push(ip + ' is already in the list (' + known[ip] + ')');
      else { known[ip] = name || ip; todo.push({ ip: ip, name: name || ip }); }
    });
    if (err.length) { $('add-error').textContent = err.join('\n'); return; }
    if (!todo.length) { $('add-error').textContent = 'Type at least one IP address.'; return; }
    $('add-save').disabled = true;
    var done = 0, failed = [];
    // One at a time: GLPI handles that best
    todo.reduce(function (p, t) {
      return p.then(function () { return createOne(type, t); }).then(function () { done++; }, function (e2) { failed.push(t.ip + ': ' + e2.message); });
    }, Promise.resolve()).then(function () {
      $('add-save').disabled = false;
      DC.mgr('sync', { method: 'POST' }).catch(function () {});
      if (cat) setCategory(todo, cat).catch(function () {});
      if (failed.length) $('add-error').textContent = 'Added ' + done + ', failed:\n' + failed.join('\n');
      else { $('add-dialog').close(); DC.toast('Added ' + done + ' device(s); their status appears within a minute'); }
      load();
    });
  }

  // The device, then a network port holding its IP address
  function createOne(type, t) {
    return DC.api(type, { method: 'POST', body: { input: { name: t.name, entities_id: 0 } } }).then(function (res) {
      var id = res.json && res.json.id;
      if (!id) throw new Error('GLPI did not return an id');
      return DC.api('NetworkPort', { method: 'POST', body: { input: {
        itemtype: type, items_id: id, instantiation_type: 'NetworkPortEthernet', name: 'management',
        logical_number: 0, NetworkName_name: '', NetworkName__ipaddresses: { '-1': t.ip }, _create_children: 1
      } } });
    });
  }

  // ------------------------------------------------------------- delete
  function deleteSelected() {
    var list = Object.keys(state.selected).map(function (k) { return state.selected[k]; });
    if (!list.length) return;
    if (!confirm('Move ' + list.length + ' device(s) to the GLPI trash?\n\n' + list.slice(0, 15).map(function (d) { return d.name + '  ' + d.ip; }).join('\n') +
      (list.length > 15 ? '\n…' : '') + '\n\nA scan finds them again if they are still on the network.')) return;
    var failed = [];
    list.reduce(function (p, d) {
      return p.then(function () { return DC.api(d.itemtype + '/' + d.id, { method: 'DELETE' }); })
        .then(function () { delete state.selected[d.key]; }, function (e) { failed.push(d.name + ': ' + e.message); });
    }, Promise.resolve()).then(function () {
      DC.mgr('sync', { method: 'POST' }).catch(function () {});
      DC.toast(failed.length ? 'Some could not be deleted: ' + failed.join('; ') : 'Deleted ' + list.length + ' device(s)', !!failed.length);
      load();
    });
  }

  // ------------------------------------------------------------- CSV
  function exportCsv() {
    var cols = ['name', 'ip', 'type', 'brand', 'model', 'serial', 'mac', 'seen'];
    var lines = [cols.concat(['status']).join(',')].concat(filtered().map(function (d) {
      return cols.map(function (c) { return d[c] || ''; }).concat([stateOf(d)]).map(function (v) {
        v = String(v);
        if (/^[=+\-@]/.test(v)) v = "'" + v;   // no spreadsheet formulas
        return '"' + v.replace(/"/g, '""') + '"';
      }).join(',');
    }));
    var a = el('a', { href: URL.createObjectURL(new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv' })), download: 'devices.csv' });
    document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  // ------------------------------------------------------------- wiring
  ['q', 'f-type', 'f-status'].forEach(function (id) { $(id).addEventListener('input', render); });
  $('refresh').addEventListener('click', load);
  $('add').addEventListener('click', openAdd);
  $('add-cancel').addEventListener('click', function () { $('add-dialog').close(); });
  $('add-form').addEventListener('submit', addDevices);
  $('del').addEventListener('click', deleteSelected);
  $('bulk-cat').addEventListener('change', function (e) {
    var v = e.target.value, list = Object.keys(state.selected).map(function (k) { return state.selected[k]; });
    e.target.value = '';
    if (!v) return;
    setCategory(list, v === '__auto' ? '' : v).then(function () {
      DC.toast(list.length + ' device(s) set to ' + (v === '__auto' ? 'automatic' : v));
      render();
    }, function (err) { DC.toast('Could not set the category: ' + err.message, true); });
  });
  $('csv').addEventListener('click', exportCsv);

  DC.initAuth({
    onReady: function () {
      load();
      timers.push(setInterval(function () { loadStatus().then(function () { if (!editing()) render(); }); }, 30000));
      timers.push(setInterval(load, DC.refreshMs));
    },
    onLogout: function () { timers.forEach(clearInterval); timers = []; }
  });
})();
