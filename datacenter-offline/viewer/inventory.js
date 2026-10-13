/* Inventory dashboard - everything the collector and agents put into GLPI:
 * summary tiles, collection status, charts, a network map built from switch
 * port connections, and a searchable device table. */
(function () {
  'use strict';

  var DC = window.DC;
  var el = DC.el, $ = DC.$;
  var SVGNS = 'http://www.w3.org/2000/svg';
  var DAY = 86400000;
  var TABLE_PAGE = 200;

  // Asset types shown on the dashboard. kind picks the network-map colour.
  var TYPES = [
    { itemtype: 'Computer', label: 'Servers & computers', kind: 'server' },
    { itemtype: 'NetworkEquipment', label: 'Network & power (SNMP)', kind: 'network' },
    { itemtype: 'PDU', label: 'PDUs & UPS', kind: 'power' },
    { itemtype: 'Printer', label: 'Printers', kind: 'other' },
    { itemtype: 'Phone', label: 'IP phones', kind: 'other' },
    { itemtype: 'Peripheral', label: 'Peripherals', kind: 'other' },
    { itemtype: 'Enclosure', label: 'Enclosures', kind: 'other' },
    { itemtype: 'Unmanaged', label: 'Unidentified devices', kind: 'unknown' }
  ];
  var TYPE = {};
  TYPES.forEach(function (t) { TYPE[t.itemtype] = t; });

  var state = { data: null, devices: [], tableAll: false, sort: { key: 'name', dir: 1 } };
  var timer = null;

  // ------------------------------------------------------------- loading
  function load() {
    $('app-error').textContent = '';
    $('updated').textContent = 'Loading…';
    $('dash').classList.add('loading');
    var expand = 'expand_dropdowns=true';
    return Promise.all([
      Promise.all(TYPES.map(function (t) { return DC.fetchAll(t.itemtype, expand); })),
      DC.fetchAll('IPAddress'),
      // Not expanded: expand_dropdowns would also turn items_id into a name
      DC.fetchAll('Item_OperatingSystem'),
      DC.fetchAll('OperatingSystem'),
      DC.fetchAll('Item_Rack'),
      DC.fetchAll('Rack'),
      DC.fetchAll('NetworkPort'),
      DC.fetchAll('NetworkPort_NetworkPort'),
      loadCollectorStatus()
    ]).then(function (r) {
      state.data = {
        items: r[0], ips: r[1], os: r[2], osNames: DC.byId(r[3]), mounts: r[4], racks: DC.byId(r[5]),
        ports: r[6], links: r[7], collector: r[8]
      };
      state.devices = buildDevices(state.data);
      fillTypeFilter();
      render();
      $('updated').textContent = 'Updated ' + new Date().toLocaleTimeString();
    }).catch(function (e) {
      DC.loadError(e, $('app-error'), $('updated'));
    }).then(function () {
      $('dash').classList.remove('loading');
    });
  }

  function loadCollectorStatus() {
    return fetch('../collector/status.json', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
  }

  // GLPI date "YYYY-MM-DD HH:MM:SS" (server local time) -> ms
  function parseDate(s) {
    if (!s) return null;
    var t = Date.parse(String(s).replace(' ', 'T'));
    return isNaN(t) ? null : t;
  }

  function buildDevices(d) {
    var ipByItem = {}, osByItem = {}, rackByItem = {};
    d.ips.forEach(function (ip) {
      if (!ip.mainitemtype || !ip.name) return;
      var k = ip.mainitemtype + ':' + ip.mainitems_id;
      (ipByItem[k] = ipByItem[k] || []).push(ip);
    });
    d.os.forEach(function (o) {
      var os = d.osNames[o.operatingsystems_id];
      if (os) osByItem[o.itemtype + ':' + o.items_id] = os.name;
    });
    d.mounts.forEach(function (m) {
      var rack = d.racks[m.racks_id];
      if (rack) rackByItem[m.itemtype + ':' + m.items_id] = rack.name + ' U' + m.position;
    });

    var out = [];
    TYPES.forEach(function (t, i) {
      d.items[i].forEach(function (it) {
        // Templates and GLPI's virtual "Hub" placeholders are not devices
        if (it.is_template || (t.itemtype === 'Unmanaged' && it.hub)) return;
        var key = t.itemtype + ':' + it.id;
        var ips = [];
        (ipByItem[key] || []).slice().sort(function (a, b) { return a.version - b.version; }).forEach(function (x) {
          if (ips.indexOf(x.name) === -1) ips.push(x.name);
        });
        var modelKey = Object.keys(it).find(function (k) { return /models_id$/.test(k); });
        var seen = parseDate(it.last_inventory_update);
        out.push({
          key: key,
          itemtype: t.itemtype,
          id: it.id,
          name: it.name || '(no name)',
          type: t.label,
          manufacturer: dropdown(it.manufacturers_id),
          model: dropdown(modelKey ? it[modelKey] : ''),
          serial: it.serial || '',
          ip: ips.length ? ips[0] : '',
          ips: ips,
          os: dropdown(osByItem[key]),
          seen: seen,
          created: parseDate(it.date_creation),
          auto: !!seen || it.is_dynamic === 1,
          rack: rackByItem[key] || '',
          status: dropdown(it.states_id)
        });
      });
    });
    return out;
  }

  // Expanded dropdowns are names; unset ones come back as 0 or "&nbsp;"
  function dropdown(v) {
    if (v == null || v === 0 || v === '0' || v === '&nbsp;') return '';
    return String(v);
  }

  // ------------------------------------------------------------- filters
  function fillTypeFilter() {
    var sel = $('f-type');
    var current = sel.value;
    sel.length = 1;
    TYPES.forEach(function (t) {
      var n = state.devices.filter(function (d) { return d.itemtype === t.itemtype; }).length;
      if (n) sel.appendChild(el('option', { value: t.itemtype, text: t.label + ' (' + n + ')' }));
    });
    sel.value = current;
  }

  function seenBucket(d, now) {
    if (!d.seen) return 'manual';
    var age = now - d.seen;
    if (age < DAY) return '1';
    if (age < 7 * DAY) return '7';
    return 'stale';
  }

  function filtered() {
    var type = $('f-type').value, seen = $('f-seen').value;
    var q = $('f-q').value.trim().toLowerCase();
    var now = Date.now();
    return state.devices.filter(function (d) {
      if (type && d.itemtype !== type) return false;
      if (seen) {
        var b = seenBucket(d, now);
        if (seen === '7' ? !(b === '1' || b === '7') : b !== seen) return false;
      }
      if (q) {
        var hay = [d.name, d.serial, d.model, d.manufacturer, d.os, d.rack].concat(d.ips).join(' ').toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
  }

  function setFilter(id, value) {
    $(id).value = value;
    render();
  }

  // -------------------------------------------------------------- render
  function render() {
    if (!state.data) return;
    var rows = filtered();
    renderTiles(rows);
    renderCollector();
    renderCharts(rows);
    renderTopology(rows);
    renderTable(rows);
  }

  function compact(n) {
    return n >= 10000 ? (n / 1000).toFixed(n >= 100000 ? 0 : 1).replace(/\.0$/, '') + 'K' : n.toLocaleString();
  }

  function renderTiles(rows) {
    var now = Date.now();
    var assets = rows.filter(function (d) { return d.itemtype !== 'Unmanaged'; });
    var auto = assets.filter(function (d) { return d.auto; }).length;
    var day = assets.filter(function (d) { return seenBucket(d, now) === '1'; }).length;
    var stale = assets.filter(function (d) { return seenBucket(d, now) === 'stale'; }).length;
    var unknown = rows.length - assets.length;
    var box = $('tiles');
    box.innerHTML = '';
    [
      { v: compact(assets.length), l: 'Devices' },
      { v: assets.length ? Math.round(auto / assets.length * 100) + '%' : '–', l: 'Collected automatically (' + auto + ')' },
      { v: compact(day), l: 'Seen in the last 24 hours' },
      { v: compact(stale), l: 'Not seen for 7+ days', status: stale ? 'warning' : null, filter: ['f-seen', 'stale'] },
      { v: compact(unknown), l: 'Unidentified devices (no SNMP/agent answer)', filter: ['f-type', 'Unmanaged'] }
    ].forEach(function (t) {
      var tile = el(t.filter ? 'button' : 'div', { class: 'stat' + (t.filter ? ' clickable' : ''), type: t.filter ? 'button' : null }, [
        el('div', { class: 'v' }, [t.status ? statusIcon(t.status) : null, t.v]),
        el('div', { class: 'l', text: t.l })
      ]);
      if (!t.filter) tile.removeAttribute('type');
      if (t.filter) tile.addEventListener('click', function () { setFilter(t.filter[0], t.filter[1]); });
      box.appendChild(tile);
    });
  }

  var STATUS_TEXT = { ok: 'OK', warning: 'Warning', error: 'Failed', running: 'Running' };
  var STATUS_ICON = { ok: '✓', warning: '!', error: '✕', running: '↻' };

  function statusIcon(status) {
    return el('span', { class: 'status-ico s-' + status, 'aria-hidden': 'true', text: STATUS_ICON[status] || '?' });
  }

  function renderCollector() {
    var st = state.data.collector;
    var box = $('col-steps');
    box.innerHTML = '';
    if (!st) {
      $('col-when').textContent = '';
      box.appendChild(el('p', { class: 'muted', text: 'No collector status yet. Edit collector/collector.conf with your IP ranges and credentials, then run: docker compose restart collector' }));
      return;
    }
    var fin = Date.parse(st.finished || ''), start = Date.parse(st.started || '');
    var when = st.state === 'running'
      ? 'Collecting now (started ' + new Date(start).toLocaleTimeString() + ')'
      : 'Last run ' + (isNaN(fin) ? '–' : new Date(fin).toLocaleString()) +
        (isNaN(fin) ? '' : ' · next about ' + new Date(fin + st.interval_minutes * 60000).toLocaleTimeString());
    $('col-when').textContent = when;
    if (!st.steps || !st.steps.length) {
      box.appendChild(el('p', { class: 'muted', text: st.state === 'running' ? 'First results appear when the run finishes.' : 'Nothing configured to collect yet.' }));
      return;
    }
    var list = el('ul', { class: 'steps' });
    st.steps.forEach(function (s) {
      list.appendChild(el('li', {}, [
        statusIcon(s.status),
        el('span', { class: 'step-status', text: STATUS_TEXT[s.status] || s.status }),
        el('span', { class: 'step-name', text: s.name }),
        el('span', { class: 'muted', text: s.sent + ' of ' + s.files + ' result(s) sent' }),
        s.detail ? el('span', { class: 'step-detail', text: s.detail }) : null
      ]));
    });
    box.appendChild(list);
  }

  // --------------------------------------------------------------- charts
  function countBy(rows, fn, top) {
    var m = {};
    rows.forEach(function (d) {
      var k = fn(d);
      if (k) m[k] = (m[k] || 0) + 1;
    });
    var list = Object.keys(m).map(function (k) { return { label: k, value: m[k] }; })
      .sort(function (a, b) { return b.value - a.value || a.label.localeCompare(b.label); });
    if (top && list.length > top) {
      var rest = list.slice(top - 1).reduce(function (s, x) { return s + x.value; }, 0);
      list = list.slice(0, top - 1).concat([{ label: 'Other', value: rest, other: true }]);
    }
    return list;
  }

  function renderCharts(rows) {
    var now = Date.now();
    var byType = TYPES.map(function (t) {
      return { label: t.label, value: rows.filter(function (d) { return d.itemtype === t.itemtype; }).length, filter: ['f-type', t.itemtype] };
    }).filter(function (x) { return x.value; });

    var buckets = [['1', 'Last 24 hours'], ['7', '1–7 days ago'], ['stale', 'More than 7 days ago'], ['manual', 'Never (entered manually)']];
    var bySeen = buckets.map(function (b) {
      var f = b[0] === '7' ? null : ['f-seen', b[0]];
      return { label: b[1], value: rows.filter(function (d) { return d.itemtype !== 'Unmanaged' && seenBucket(d, now) === b[0]; }).length, filter: f };
    });

    var assets = rows.filter(function (d) { return d.itemtype !== 'Unmanaged'; });
    chart('type', byType, hbar);
    chart('seen', bySeen, hbar);
    chart('vendor', countBy(assets, function (d) { return d.manufacturer || 'Unknown'; }, 8), hbar);
    chart('os', countBy(assets.filter(function (d) { return d.itemtype === 'Computer'; }), function (d) { return d.os || 'Unknown'; }, 8), hbar);

    var days = [];
    var today = new Date(); today.setHours(0, 0, 0, 0);
    for (var i = 29; i >= 0; i--) {
      var start = today.getTime() - i * DAY;
      days.push({
        label: new Date(start).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
        value: rows.filter(function (d) { return d.created >= start && d.created < start + DAY; }).length
      });
    }
    chart('new', days, columns);
  }

  function chart(name, data, draw) {
    var card = document.querySelector('[data-chart="' + name + '"]');
    var box = card.querySelector('.chart');
    box.innerHTML = '';
    var total = data.reduce(function (s, x) { return s + x.value; }, 0);
    if (!total) {
      box.appendChild(el('p', { class: 'muted empty', text: 'No data for the current filters.' }));
    } else if (card.dataset.view === 'table') {
      box.appendChild(dataTable(data));
    } else {
      draw(box, data);
    }
    var btn = card.querySelector('[data-table]');
    btn.textContent = card.dataset.view === 'table' ? 'Chart' : 'Table';
    btn.onclick = function () {
      card.dataset.view = card.dataset.view === 'table' ? 'chart' : 'table';
      chart(name, data, draw);
    };
  }

  function dataTable(data) {
    return el('table', { class: 'data-table mini' }, [
      el('thead', {}, [el('tr', {}, [el('th', { text: 'Category' }), el('th', { class: 'num', text: 'Devices' })])]),
      el('tbody', {}, data.map(function (r) {
        return el('tr', {}, [el('td', { text: r.label }), el('td', { class: 'num', text: r.value.toLocaleString() })]);
      }))
    ]);
  }

  // Horizontal bars: one series, one colour, value at the tip, click to filter
  function hbar(box, data) {
    var max = Math.max.apply(null, data.map(function (r) { return r.value; }));
    var list = el('div', { class: 'hbars' });
    data.forEach(function (r) {
      var pct = max ? r.value / max * 100 : 0;
      var row = el(r.filter ? 'button' : 'div', { class: 'hbar' + (r.filter ? ' clickable' : '') }, [
        el('span', { class: 'hbar-label', text: r.label }),
        el('span', { class: 'hbar-track' }, [
          el('span', { class: 'hbar-fill', style: 'width:' + Math.max(pct, r.value ? 1 : 0) + '%' }),
          el('span', { class: 'hbar-val', text: r.value.toLocaleString() })
        ])
      ]);
      if (r.filter) {
        row.type = 'button';
        row.addEventListener('click', function () { setFilter(r.filter[0], r.filter[1]); });
      }
      tipOn(row, r.value.toLocaleString(), r.label + (r.filter ? ' · click to filter' : ''));
      list.appendChild(row);
    });
    box.appendChild(list);
  }

  // Integer tick step giving at most 4 intervals: 1, 2, 5, 10, 20, 50...
  function niceStep(max) {
    var raw = Math.max(1, max / 4);
    var p = Math.pow(10, Math.floor(Math.log10(raw)));
    var steps = [1, 2, 5, 10];
    for (var i = 0; i < steps.length; i++) if (steps[i] * p >= raw) return steps[i] * p;
    return 10 * p;
  }

  // Columns over time (SVG): hairline grid, 4px rounded tops, per-column hover
  function columns(box, data) {
    var W = Math.max(box.clientWidth, 320), H = 180, padL = 34, padB = 22, padT = 18;
    var plotW = W - padL - 6, plotH = H - padB - padT;
    var step = niceStep(Math.max.apply(null, data.map(function (r) { return r.value; })));
    var peakVal = Math.max.apply(null, data.map(function (r) { return r.value; }));
    var max = Math.max(step, Math.ceil(peakVal / step) * step);
    var svg = svgEl('svg', { width: W, height: H, viewBox: '0 0 ' + W + ' ' + H, class: 'cols', role: 'img',
      'aria-label': 'New devices per day. Use the Table button for the values.' });
    for (var v = 0; v <= max; v += step) {
      var y = padT + plotH - v / max * plotH;
      svg.appendChild(svgEl('line', { x1: padL, x2: W - 6, y1: y, y2: y, class: v ? 'grid' : 'axis' }));
      var t = svgEl('text', { x: padL - 6, y: y + 4, class: 'tick', 'text-anchor': 'end' });
      t.textContent = String(v);
      svg.appendChild(t);
    }
    var band = plotW / data.length;
    var bw = Math.min(24, Math.max(3, band - 2));
    var peak = data.reduce(function (b, r, i) { return r.value > data[b].value ? i : b; }, 0);
    data.forEach(function (r, i) {
      var x = padL + i * band + (band - bw) / 2;
      var h = r.value / max * plotH;
      var y = padT + plotH - h;
      if (h > 0) svg.appendChild(svgEl('path', { d: roundTop(x, y, bw, h, Math.min(4, bw / 2, h)), class: 'col' }));
      if (i === peak && r.value) {
        var lab = svgEl('text', { x: x + bw / 2, y: y - 5, class: 'val', 'text-anchor': 'middle' });
        lab.textContent = String(r.value);
        svg.appendChild(lab);
      }
      if (i % 7 === 0 || i === data.length - 1) {
        var xl = svgEl('text', { x: x + bw / 2, y: H - 6, class: 'tick', 'text-anchor': 'middle' });
        xl.textContent = r.label;
        svg.appendChild(xl);
      }
      var hit = svgEl('rect', { x: padL + i * band, y: padT, width: band, height: plotH, class: 'hit', tabindex: 0 });
      tipOn(hit, r.value + ' new', r.label);
      svg.appendChild(hit);
    });
    box.appendChild(svg);
  }

  function roundTop(x, y, w, h, r) {
    return 'M' + x + ',' + (y + h) + 'V' + (y + r) + 'Q' + x + ',' + y + ' ' + (x + r) + ',' + y +
      'H' + (x + w - r) + 'Q' + (x + w) + ',' + y + ' ' + (x + w) + ',' + (y + r) + 'V' + (y + h) + 'Z';
  }

  function svgEl(tag, attrs) {
    var n = document.createElementNS(SVGNS, tag);
    Object.keys(attrs || {}).forEach(function (k) { if (attrs[k] != null) n.setAttribute(k, attrs[k]); });
    return n;
  }

  // ------------------------------------------------------------- tooltip
  function tipOn(node, value, label) {
    function show(e) {
      var tip = $('tip');
      tip.innerHTML = '';
      tip.appendChild(el('strong', { text: value }));
      tip.appendChild(el('span', { text: label }));
      tip.hidden = false;
      var r = node.getBoundingClientRect();
      var x = e && e.clientX != null ? e.clientX : r.left + r.width / 2;
      var y = e && e.clientY != null ? e.clientY : r.top;
      var tw = tip.offsetWidth;
      tip.style.left = Math.min(Math.max(8, x - tw / 2), window.innerWidth - tw - 8) + 'px';
      tip.style.top = Math.max(8, y - tip.offsetHeight - 12) + 'px';
    }
    function hide() { $('tip').hidden = true; }
    node.addEventListener('pointermove', show);
    node.addEventListener('focus', function () { show(null); });
    node.addEventListener('pointerleave', hide);
    node.addEventListener('blur', hide);
  }

  // ---------------------------------------------------------- network map
  // Built from GLPI port-to-port connections (LLDP/CDP and switch MAC tables
  // collected over SNMP). Switches are hubs; what plugs into them hangs below.
  function renderTopology(rows) {
    var d = state.data;
    var box = $('topo');
    box.innerHTML = '';
    var legend = $('topo-legend');
    legend.innerHTML = '';
    [['network', 'Network'], ['server', 'Server'], ['power', 'Power'], ['unknown', 'Other / unidentified']].forEach(function (k) {
      legend.appendChild(el('span', { class: 'key' }, [el('i', { class: 'dot k-' + k[0] }), k[1]]));
    });

    var portById = DC.byId(d.ports);
    var devByKey = {};
    state.devices.forEach(function (x) { devByKey[x.key] = x; });
    var visible = {};
    rows.forEach(function (x) { visible[x.key] = true; });

    var edges = [], deg = {};
    d.links.forEach(function (l) {
      var a = portById[l.networkports_id_1], b = portById[l.networkports_id_2];
      if (!a || !b) return;
      var ka = a.itemtype + ':' + a.items_id, kb = b.itemtype + ':' + b.items_id;
      if (ka === kb || !devByKey[ka] || !devByKey[kb]) return;
      edges.push({ a: ka, b: kb, pa: a.name || ('port ' + a.logical_number), pb: b.name || ('port ' + b.logical_number) });
      deg[ka] = (deg[ka] || 0) + 1;
      deg[kb] = (deg[kb] || 0) + 1;
    });

    var connected = Object.keys(deg).length;
    $('topo-note').textContent = edges.length
      ? connected + ' devices linked by ' + edges.length + ' port connection(s). Devices that match the filters are highlighted. ' +
        (state.devices.length - connected) + ' devices have no recorded connection yet.'
      : 'No port connections recorded yet. They appear when the collector inventories managed switches over SNMP ' +
        '(LLDP/CDP neighbours and MAC address tables), or when ports are connected in GLPI.';
    if (!edges.length) return;

    // Hubs: switches (network devices with 2+ links) and anything with many links;
    // single-link network gear (a firewall, an SNMP PDU) hangs below its switch
    var isHub = function (k) { return (devByKey[k].itemtype === 'NetworkEquipment' && deg[k] >= 2) || deg[k] >= 4; };
    var hubs = Object.keys(deg).filter(isHub).sort(function (a, b) { return deg[b] - deg[a]; });
    if (!hubs.length) hubs = [Object.keys(deg).sort(function (a, b) { return deg[b] - deg[a]; })[0]];
    var parent = {};
    edges.forEach(function (e) {
      if (hubs.indexOf(e.a) !== -1 && hubs.indexOf(e.b) === -1 && !parent[e.b]) parent[e.b] = e.a;
      if (hubs.indexOf(e.b) !== -1 && hubs.indexOf(e.a) === -1 && !parent[e.a]) parent[e.a] = e.b;
    });
    Object.keys(deg).forEach(function (k) { if (hubs.indexOf(k) === -1 && !parent[k]) parent[k] = hubs[0]; });

    // Tiers: the hub with most switch-to-switch links is the core (top row);
    // other hubs form the access row; each hub's devices hang below it.
    var hubDeg = {};
    edges.forEach(function (e) {
      if (hubs.indexOf(e.a) !== -1 && hubs.indexOf(e.b) !== -1) {
        hubDeg[e.a] = (hubDeg[e.a] || 0) + 1;
        hubDeg[e.b] = (hubDeg[e.b] || 0) + 1;
      }
    });
    var core = hubs.filter(function (h) { return hubDeg[h]; })
      .sort(function (a, b) { return hubDeg[b] - hubDeg[a] || deg[b] - deg[a]; })[0] || null;
    var leavesOf = function (h) {
      return Object.keys(parent).filter(function (k) { return parent[k] === h; })
        .sort(function (a, b) { return devByKey[a].name.localeCompare(devByKey[b].name); });
    };
    var clusters = [];
    if (core && leavesOf(core).length) clusters.push({ hub: null, leaves: leavesOf(core) });
    hubs.forEach(function (h) { if (h !== core) clusters.push({ hub: h, leaves: leavesOf(h) }); });

    var MAX_LEAVES = 36, COLS = 4, ROW_H = 34, TOP = 40, HUB_GAP = 30;
    // Fit the columns to the card when possible; scroll sideways only when it can't
    var totalCols = clusters.reduce(function (n, c) {
      return n + Math.max(1, Math.min(COLS, c.leaves.slice(0, MAX_LEAVES).length));
    }, 0);
    var avail = (box.clientWidth || 1000) - 40 - HUB_GAP * Math.max(0, clusters.length - 1);
    var CELL_W = Math.max(115, Math.min(160, Math.floor(avail / Math.max(1, totalCols))));
    var hubY = core ? TOP + 100 : TOP, leafY = hubY + 70;
    var pos = {}, overflow = [], level = {};
    var x = 20, height = 0;
    clusters.forEach(function (c) {
      var shown = c.leaves.slice(0, MAX_LEAVES);
      var cols = Math.max(1, Math.min(COLS, shown.length));
      var width = Math.max(CELL_W, cols * CELL_W);
      if (c.hub) { pos[c.hub] = { x: x + width / 2, y: hubY }; level[c.hub] = core ? 1 : 0; }
      shown.forEach(function (k, i) {
        pos[k] = { x: x + (i % cols) * CELL_W + 12, y: leafY + Math.floor(i / cols) * ROW_H };
      });
      if (c.leaves.length > shown.length) overflow.push({ x: x + width / 2, y: leafY + Math.ceil(shown.length / cols) * ROW_H, n: c.leaves.length - shown.length });
      height = Math.max(height, leafY + Math.ceil((shown.length + 1) / cols) * ROW_H);
      x += width + HUB_GAP;
    });
    if (core) { pos[core] = { x: (20 + x - HUB_GAP) / 2, y: TOP }; level[core] = 0; }
    var W = x, H = Math.max(height + 10, 200);

    var svg = svgEl('svg', { width: W, height: H, viewBox: '0 0 ' + W + ' ' + H, class: 'topo-svg', role: 'img',
      'aria-label': 'Network map of ' + connected + ' connected devices. The device table lists every device.' });
    var gEdges = svgEl('g', {}), gNodes = svgEl('g', {});
    svg.appendChild(gEdges);
    svg.appendChild(gNodes);

    edges.forEach(function (e) {
      var p = pos[e.a], q = pos[e.b];
      if (!p || !q) return;
      var dim = !(visible[e.a] && visible[e.b]);
      var line = svgEl('path', {
        d: 'M' + p.x + ',' + p.y + ' C' + p.x + ',' + (p.y + q.y) / 2 + ' ' + q.x + ',' + (p.y + q.y) / 2 + ' ' + q.x + ',' + q.y,
        class: 'edge' + (dim ? ' dim' : '')
      });
      gEdges.appendChild(line);
      var hit = svgEl('path', { d: line.getAttribute('d'), class: 'edge-hit' });
      tipOn(hit, devByKey[e.a].name + ' ↔ ' + devByKey[e.b].name, e.pa + ' ↔ ' + e.pb);
      gEdges.appendChild(hit);
    });

    Object.keys(pos).forEach(function (k) {
      var dev = devByKey[k], p = pos[k], hub = hubs.indexOf(k) !== -1;
      var kind = TYPE[dev.itemtype] ? TYPE[dev.itemtype].kind : 'unknown';
      if (kind === 'other') kind = 'unknown';
      var a = svgEl('a', { href: DC.glpiForm(dev.itemtype, dev.id), target: '_blank', class: 'node' + (visible[k] ? '' : ' dim') });
      a.appendChild(svgEl('circle', { cx: p.x, cy: p.y, r: hub ? 9 : 6, class: 'ring' }));
      a.appendChild(svgEl('circle', { cx: p.x, cy: p.y, r: hub ? 7 : 4.5, class: 'k-' + kind }));
      var top = hub && !level[k];
      var label = svgEl('text', {
        x: p.x + (top ? 0 : hub ? 13 : 9), y: p.y + (top ? -14 : 4),
        class: hub ? 'hub-label' : 'leaf-label', 'text-anchor': top ? 'middle' : 'start'
      });
      label.textContent = trim(dev.name, hub ? 24 : 18);
      a.appendChild(label);
      a.appendChild(svgEl('circle', { cx: p.x, cy: p.y, r: 12, class: 'node-hit' }));
      tipOn(a, dev.name, [dev.type, dev.ip, dev.model].filter(Boolean).join(' · '));
      gNodes.appendChild(a);
    });
    overflow.forEach(function (o) {
      var t = svgEl('text', { x: o.x, y: o.y, class: 'leaf-label', 'text-anchor': 'middle' });
      t.textContent = '+' + o.n + ' more (see table)';
      gNodes.appendChild(t);
    });
    box.appendChild(svg);
  }

  function trim(s, n) { return s.length > n ? s.slice(0, n - 1) + '…' : s; }

  // --------------------------------------------------------------- table
  var COLUMNS = [
    { key: 'name', label: 'Name' },
    { key: 'type', label: 'Type' },
    { key: 'ip', label: 'IP address' },
    { key: 'manufacturer', label: 'Manufacturer' },
    { key: 'model', label: 'Model' },
    { key: 'serial', label: 'Serial' },
    { key: 'os', label: 'Operating system' },
    { key: 'rack', label: 'Rack' },
    { key: 'seen', label: 'Last seen' }
  ];

  function fmtSeen(d) {
    if (!d.seen) return d.itemtype === 'Unmanaged' ? '\u2013' : 'Manual entry';
    var age = Date.now() - d.seen;
    if (age < 3600000) return Math.max(1, Math.round(age / 60000)) + ' min ago';
    if (age < DAY) return Math.round(age / 3600000) + ' h ago';
    return Math.round(age / DAY) + ' days ago';
  }

  function sortRows(rows) {
    var k = state.sort.key, dir = state.sort.dir;
    return rows.slice().sort(function (a, b) {
      var x = a[k], y = b[k];
      if (k === 'seen') { x = x || 0; y = y || 0; return (x - y) * dir; }
      if (k === 'ip') { x = ipNum(x); y = ipNum(y); return (x - y) * dir; }
      return String(x || '￿').localeCompare(String(y || '￿'), undefined, { numeric: true }) * dir;
    });
  }

  function ipNum(ip) {
    var p = /^(\d+)\.(\d+)\.(\d+)\.(\d+)$/.exec(ip || '');
    return p ? ((+p[1] * 256 + +p[2]) * 256 + +p[3]) * 256 + +p[4] : Infinity;
  }

  function renderTable(rows) {
    var sorted = sortRows(rows);
    var shown = state.tableAll ? sorted : sorted.slice(0, TABLE_PAGE);
    var table = $('devices');
    table.innerHTML = '';
    table.appendChild(el('thead', {}, [el('tr', {}, COLUMNS.map(function (c) {
      var active = state.sort.key === c.key;
      return el('th', { 'aria-sort': active ? (state.sort.dir > 0 ? 'ascending' : 'descending') : 'none' }, [
        el('button', {
          type: 'button', class: 'sort',
          onclick: function () {
            state.sort = { key: c.key, dir: active ? -state.sort.dir : (c.key === 'seen' ? -1 : 1) };
            renderTable(filtered());
          }
        }, [c.label, active ? (state.sort.dir > 0 ? ' ▲' : ' ▼') : ''])
      ]);
    }))]));
    var now = Date.now();
    table.appendChild(el('tbody', {}, shown.map(function (d) {
      var stale = d.itemtype !== 'Unmanaged' && seenBucket(d, now) === 'stale';
      return el('tr', {}, [
        el('td', {}, [el('a', { href: DC.glpiForm(d.itemtype, d.id), target: '_blank', rel: 'noopener', text: d.name })]),
        el('td', { text: d.type }),
        el('td', { class: 'mono', text: d.ips.join(', ') }),
        el('td', { text: d.manufacturer }),
        el('td', { text: d.model }),
        el('td', { class: 'mono', text: d.serial }),
        el('td', { text: d.os }),
        el('td', { text: d.rack }),
        el('td', { class: 'nowrap' }, [stale ? statusIcon('warning') : null, fmtSeen(d)])
      ]);
    })));
    $('tbl-count').textContent = shown.length < rows.length
      ? 'Showing ' + shown.length + ' of ' + rows.length.toLocaleString()
      : rows.length.toLocaleString() + ' device(s)';
    $('more').hidden = shown.length >= rows.length;
  }

  function exportCsv() {
    var rows = sortRows(filtered());
    var head = COLUMNS.map(function (c) { return c.label; }).concat(['Auto collected', 'GLPI id']);
    var lines = [head].concat(rows.map(function (d) {
      return [d.name, d.type, d.ips.join(' '), d.manufacturer, d.model, d.serial, d.os, d.rack,
        d.seen ? new Date(d.seen).toISOString() : '', d.auto ? 'yes' : 'no', d.itemtype + ' ' + d.id];
    })).map(function (r) {
      return r.map(function (v) {
        v = String(v == null ? '' : v);
        if (/^[=+\-@]/.test(v)) v = "'" + v; // keep spreadsheets from running formulas
        return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
      }).join(',');
    });
    var blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    var a = el('a', { href: URL.createObjectURL(blob), download: 'dc-inventory-' + new Date().toISOString().slice(0, 10) + '.csv' });
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  }

  // ---------------------------------------------------------------- init
  function startApp() {
    load();
    clearInterval(timer);
    timer = setInterval(load, DC.refreshMs);
  }

  var qTimer = null;
  $('f-type').addEventListener('change', render);
  $('f-seen').addEventListener('change', render);
  $('f-q').addEventListener('input', function () {
    clearTimeout(qTimer);
    qTimer = setTimeout(render, 200);
  });
  $('f-clear').addEventListener('click', function () {
    $('f-type').value = ''; $('f-seen').value = ''; $('f-q').value = '';
    render();
  });
  $('refresh').addEventListener('click', load);
  $('export').addEventListener('click', exportCsv);
  $('more').addEventListener('click', function () { state.tableAll = true; renderTable(filtered()); });
  var resizeTimer = null;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { if (state.data) renderCharts(filtered()); }, 200);
  });

  DC.initAuth({ onReady: startApp, onLogout: function () { clearInterval(timer); } });
})();
