/* NOC Monitor: live up/down of every device by category, offline list and
 * device board. Read-only and open without sign-in (unless switched off on
 * the Scan & settings page). Data: /api/monitor (manager), every 10 s. */
(function () {
  'use strict';

  var DC = window.DC;
  var el = DC.el, $ = DC.$;
  var REFRESH_MS = 10000;
  var SVGNS = 'http://www.w3.org/2000/svg';

  // 24px line icons, one per category (stroke = currentColor)
  var ICONS = {
    'Firewall': 'M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z M9 12h6 M12 9v6',
    'Load balancer': 'M12 4v5 M5 20v-4h14v4 M12 9l-7 7 M12 9l7 7 M12 9v7 M9 4h6',
    'Router': 'M3 14h18v5H3z M7 16.5h.01 M11 16.5h.01 M8 14l-2-6 M16 14l2-6 M5 8a7 7 0 0114 0',
    'Switch': 'M3 8h18v8H3z M6 12h1 M9 12h1 M12 12h1 M15 12h1 M18 12h0',
    'Wireless': 'M2 9a15 15 0 0120 0 M5 12.5a10 10 0 0114 0 M8.5 16a5 5 0 017 0 M12 19.5h.01',
    'Server': 'M4 4h16v6H4z M4 14h16v6H4z M7 7h.01 M7 17h.01 M11 7h6 M11 17h6',
    'Storage': 'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6 M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
    'Management': 'M7 7h10v10H7z M10 3v4 M14 3v4 M10 17v4 M14 17v4 M3 10h4 M3 14h4 M17 10h4 M17 14h4',
    'Power': 'M13 2L4 14h7l-1 8 9-12h-7l1-8z',
    'Printer': 'M6 9V3h12v6 M4 9h16v8h-2 M6 17H4v-8 M6 14h12v7H6z',
    'Phone': 'M8 2h8a1 1 0 011 1v18a1 1 0 01-1 1H8a1 1 0 01-1-1V3a1 1 0 011-1z M11 18h2',
    'Other': 'M21 8l-9-5-9 5v8l9 5 9-5V8z M3 8l9 5 9-5 M12 13v8',
    'Unknown': 'M9 9a3 3 0 115 2c-1 .7-2 1.3-2 3 M12 18h.01 M12 2a10 10 0 100 20 10 10 0 000-20z'
  };

  var STATE_LABEL = { up: 'Online', down: 'Offline', unknown: 'Not monitored' };
  var ICON_CHAR = { up: '✓', down: '✕', unknown: '?' };

  var st = { data: null, filter: { q: '', cat: '', st: '' }, prevDown: null, timer: null };

  function icon(cat) {
    var svg = document.createElementNS(SVGNS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('class', 'cat-ico');
    svg.setAttribute('aria-hidden', 'true');
    (ICONS[cat] || ICONS.Other).split(' M').forEach(function (d, i) {
      var p = document.createElementNS(SVGNS, 'path');
      p.setAttribute('d', (i ? 'M' : '') + d);
      svg.appendChild(p);
    });
    return svg;
  }

  function stateBadge(state) {
    return el('span', { class: 'state st-' + state }, [
      el('span', { class: 'sico s-' + state, 'aria-hidden': 'true', text: ICON_CHAR[state] }),
      STATE_LABEL[state]
    ]);
  }

  function duration(s) {
    if (s == null) return 'no reply seen';
    if (s < 60) return 'under 1 min';
    if (s < 3600) return Math.floor(s / 60) + ' min';
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    return h + ' h' + (m ? ' ' + m + ' min' : '');
  }

  function pct(n, d) { return d ? (Math.floor(n / d * 1000) / 10).toFixed(1) + '%' : '–'; }

  // ------------------------------------------------------------- data
  function poll() {
    try { var t = sessionStorage.getItem('dcv-token'); if (t) DC.token = t; } catch (e) { /* no storage */ }
    DC.mgr('monitor').then(function (d) {
      st.data = d;
      $('mon-error').textContent = d.error ? 'Device list: ' + d.error : '';
      live(true);
      notifyNewDown(d);
      render();
    }).catch(function (e) {
      live(false, e.status === 401 ? 'Sign in required' : 'Connection lost – retrying');
      if (e.status === 401) {
        $('mon-error').textContent = '';
        $('mon-error').appendChild(el('span', {}, ['The public monitor is switched off. ', el('a', { href: 'devices.html', text: 'Sign in' }), ' first.']));
      }
    }).then(function () {
      clearTimeout(st.timer);
      st.timer = setTimeout(poll, REFRESH_MS);
    });
  }

  function live(ok, text) {
    $('live').className = 'live' + (ok ? '' : ' bad');
    $('live-text').textContent = ok ? 'LIVE · ' + new Date().toLocaleTimeString() : text;
  }

  function notifyNewDown(d) {
    var down = {};
    d.devices.forEach(function (x) { if (x.state === 'down') down[x.ip] = x; });
    if (st.prevDown) {
      var fresh = Object.keys(down).filter(function (ip) { return !st.prevDown[ip]; });
      if (fresh.length) DC.toast(fresh.length === 1 ? down[fresh[0]].name + ' (' + fresh[0] + ') went offline' : fresh.length + ' devices went offline', true);
      st.fresh = {};
      fresh.forEach(function (ip) { st.fresh[ip] = 1; });
    }
    st.prevDown = down;
  }

  // ------------------------------------------------------------- render
  function render() {
    var d = st.data, t = d.totals;
    var monitored = t.up + t.down;
    $('k-total').textContent = t.total;
    $('k-total-s').textContent = d.categories.length + ' categor' + (d.categories.length === 1 ? 'y' : 'ies');
    $('k-up').textContent = t.up;
    $('k-up-s').textContent = pct(t.up, t.total) + ' of all devices';
    $('k-down').textContent = t.down;
    $('k-down-s').textContent = t.down ? 'needs attention' : 'nothing offline';
    $('kpi-down').classList.toggle('alarm', t.down > 0);
    $('k-avail').textContent = pct(t.up, monitored);
    $('k-unknown').textContent = t.unknown;
    document.title = (t.down ? '(' + t.down + ' DOWN) ' : '') + 'Network Monitor | DC NOC';
    $('gen').textContent = 'Data from ' + new Date(d.generated * 1000).toLocaleTimeString() + '.';

    renderCats(d);
    renderDown(d);
    fillCatFilter(d);
    renderBoard(d);
  }

  function renderCats(d) {
    var box = $('cats');
    box.textContent = '';
    if (!d.categories.length) {
      box.appendChild(el('p', { class: 'muted', text: 'No devices yet: add networks on Scan & settings and press Scan now, or add devices under Manage devices.' }));
      return;
    }
    d.categories.forEach(function (c) {
      var selected = st.filter.cat === c.name;
      var chip = c.down ? el('span', { class: 'chip-st st-down' }, [el('span', { class: 'sico s-down', 'aria-hidden': 'true', text: '✕' }), c.down + ' offline'])
        : c.up ? el('span', { class: 'chip-st st-up' }, [el('span', { class: 'sico s-up', 'aria-hidden': 'true', text: '✓' }), 'All online'])
        : el('span', { class: 'chip-st st-unknown' }, [el('span', { class: 'sico s-unknown', 'aria-hidden': 'true', text: '?' }), 'Not monitored']);
      if (c.down === 0 && c.up && c.unknown) chip = el('span', { class: 'chip-st st-up' }, [el('span', { class: 'sico s-up', 'aria-hidden': 'true', text: '✓' }), 'Online']);
      var bar = el('div', { class: 'hbar-stack', 'aria-hidden': 'true' });
      [['up', c.up], ['down', c.down], ['unknown', c.unknown]].forEach(function (p) {
        if (p[1]) bar.appendChild(el('span', { class: 'seg-' + p[0], style: 'flex:' + p[1] }));
      });
      box.appendChild(el('button', {
        type: 'button', class: 'cat' + (c.down ? ' has-down' : '') + (selected ? ' sel' : ''), 'aria-pressed': String(selected),
        'aria-label': c.name + ': ' + c.up + ' online, ' + c.down + ' offline, ' + c.unknown + ' not monitored, of ' + c.total,
        onclick: function () { st.filter.cat = selected ? '' : c.name; $('f-cat').value = st.filter.cat; render(); }
      }, [
        el('div', { class: 'cat-top' }, [icon(c.name), el('span', { class: 'cat-name', text: c.name }), chip]),
        el('div', { class: 'cat-num' }, [el('strong', { text: String(c.up) }), el('span', { class: 'muted', text: ' / ' + c.total + ' online' })]),
        bar
      ]));
    });
  }

  function renderDown(d) {
    var list = d.devices.filter(function (x) { return x.state === 'down'; }).sort(function (a, b) {
      var x = a.down_for_s == null ? Infinity : a.down_for_s, y = b.down_for_s == null ? Infinity : b.down_for_s;
      return x - y;   // most recent first
    });
    $('down-count').textContent = list.length ? list.length + ' offline' : '';
    $('down-count').className = 'badge' + (list.length ? ' bad' : '');
    var ul = $('down-list');
    ul.textContent = '';
    if (!list.length) {
      ul.appendChild(el('li', { class: 'all-good' }, [el('span', { class: 'sico s-up big', 'aria-hidden': 'true', text: '✓' }),
        el('span', {}, [el('strong', { text: 'All monitored devices are online' }), el('span', { class: 'muted small', text: ' ' + (d.totals.up || 0) + ' answering ping' })])]));
      return;
    }
    list.forEach(function (x) {
      ul.appendChild(el('li', { class: st.fresh && st.fresh[x.ip] ? 'new' : '' }, [
        el('span', { class: 'sico s-down', 'aria-hidden': 'true', text: '✕' }),
        el('div', { class: 'dl-main' }, [
          el('strong', { class: 'dl-name', text: x.name, title: x.name }),
          el('span', { class: 'mono small', text: x.ip }),
          el('span', { class: 'muted small', text: x.category })
        ]),
        el('div', { class: 'dl-time' }, [el('span', { class: 'muted small', text: 'offline' }), el('strong', { text: duration(x.down_for_s) })])
      ]));
    });
  }

  function fillCatFilter(d) {
    var sel = $('f-cat');
    sel.length = 1;
    d.categories.forEach(function (c) { sel.appendChild(el('option', { value: c.name, text: c.name + ' (' + c.total + ')' })); });
    sel.value = st.filter.cat;
  }

  function matches(x) {
    var f = st.filter;
    if (f.cat && x.category !== f.cat) return false;
    if (f.st && x.state !== f.st) return false;
    if (!f.q) return true;
    return [x.name, x.ip, x.brand, x.model, x.serial, x.mac, x.category].join(' ').toLowerCase().indexOf(f.q) !== -1;
  }

  function renderBoard(d) {
    var board = $('board');
    board.textContent = '';
    var shown = 0;
    var order = { down: 0, unknown: 1, up: 2 };
    d.categories.forEach(function (c) {
      var list = d.devices.filter(function (x) { return x.category === c.name && matches(x); })
        .sort(function (a, b) { return order[a.state] - order[b.state] || a.name.localeCompare(b.name, undefined, { numeric: true }); });
      if (!list.length) return;
      shown += list.length;
      var grid = el('div', { class: 'tiles' });
      list.forEach(function (x) { grid.appendChild(tile(x)); });
      board.appendChild(el('div', { class: 'group' }, [
        el('h3', { class: 'group-h' }, [icon(c.name), c.name, el('span', { class: 'muted small', text: ' ' + c.up + ' / ' + c.total + ' online' + (c.down ? ' · ' + c.down + ' offline' : '') })]),
        grid
      ]));
    });
    $('empty').hidden = shown > 0 || !d.devices.length;
    $('empty').textContent = 'No device matches the filters.';
  }

  function tile(x) {
    var meta = [x.brand, x.model].filter(Boolean).join(' ');
    return el('article', { class: 'tile t-' + x.state + (st.fresh && st.fresh[x.ip] ? ' new' : '') }, [
      el('div', { class: 'tile-top' }, [stateBadge(x.state),
        el('span', { class: 'mono small muted', text: x.state === 'up' && x.rtt_ms != null ? x.rtt_ms + ' ms'
          : x.state === 'down' ? duration(x.down_for_s) : '' })]),
      el('div', { class: 'tile-name', title: x.name, text: x.name }),
      el('div', { class: 'mono small', text: x.ip }),
      el('div', { class: 'muted small tile-meta', title: meta, text: meta || ' ' }),
      el('div', { class: 'tile-go' }, DC.connectButtons(x.ip, x.name, x.glpi_url))
    ]);
  }

  // ------------------------------------------------------------- controls
  $('q').addEventListener('input', function (e) { st.filter.q = e.target.value.trim().toLowerCase(); if (st.data) render(); });
  $('f-cat').addEventListener('change', function (e) { st.filter.cat = e.target.value; if (st.data) render(); });
  document.querySelectorAll('[data-st]').forEach(function (b) {
    b.addEventListener('click', function () {
      st.filter.st = b.getAttribute('data-st');
      document.querySelectorAll('[data-st]').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
      if (st.data) render();
    });
  });
  $('fullscreen').addEventListener('click', function () {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen();
  });
  function tick() { $('clock').textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
  tick();
  setInterval(tick, 1000);

  DC.applyFeatures();
  poll();
})();
