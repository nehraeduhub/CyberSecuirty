/* DC Viewer - read-only data centre view built on the GLPI REST API.
 * Served by the portal container, which proxies /apirest.php to GLPI on the
 * same origin, so no CORS setup or external libraries are needed (offline). */
(function () {
  'use strict';

  var DC = window.DC;
  var el = DC.el, $ = DC.$, fetchAll = DC.fetchAll, byId = DC.byId, glpiForm = DC.glpiForm;
  var U_PX = 18;

  // Itemtypes GLPI can mount in a rack, and how they are coloured
  var KIND = {
    Computer: 'server', NetworkEquipment: 'network', PDU: 'power',
    PassiveDCEquipment: 'passive', Enclosure: 'other', Peripheral: 'other', Monitor: 'other'
  };
  var LABEL = {
    Computer: 'Server', NetworkEquipment: 'Network device', PDU: 'PDU / UPS',
    PassiveDCEquipment: 'Passive device', Enclosure: 'Enclosure', Peripheral: 'Peripheral', Monitor: 'Monitor'
  };
  var ARROW = { 1: '↑', 2: '→', 3: '↓', 4: '←' }; // N E S W
  var PDU_SIDE = { 1: 'left', 2: 'right', 3: 'top', 4: 'bottom' };

  var state = {
    data: null, roomId: null, rackId: null, face: 0,
    selected: null, query: ''
  };

  function load() {
    $('app-error').textContent = '';
    $('updated').textContent = 'Loading…';
    return Promise.all([
      fetchAll('Datacenter'), fetchAll('DCRoom'), fetchAll('Rack'),
      fetchAll('Item_Rack'), fetchAll('PDU_Rack'), fetchAll('State')
    ]).then(function (r) {
      var data = {
        dcs: byId(r[0]), rooms: byId(r[1]), racks: byId(r[2]),
        mounts: r[3], pduMounts: r[4], states: byId(r[5]), items: {}, models: {}
      };
      var types = {};
      data.mounts.forEach(function (m) { types[m.itemtype] = true; });
      if (data.pduMounts.length) types.PDU = true;
      var names = Object.keys(types);
      return Promise.all(names.map(function (t) {
        return Promise.all([fetchAll(t), fetchAll(t + 'Model')]).then(function (res) {
          data.items[t] = byId(res[0]);
          data.models[t] = byId(res[1]);
        });
      })).then(function () { return data; });
    }).then(function (data) {
      state.data = data;
      $('updated').textContent = 'Updated ' + new Date().toLocaleTimeString();
      render();
    }).catch(handleError);
  }

  function handleError(e) {
    DC.loadError(e, $('app-error'), $('updated'));
  }

  // ---------------------------------------------------------- helpers
  function itemOf(t, id) { return (state.data.items[t] || {})[id]; }

  function modelOf(t, item) {
    if (!item) return null;
    return (state.data.models[t] || {})[item[t.toLowerCase() + 'models_id']];
  }

  function unitsOf(t, item) {
    var m = modelOf(t, item);
    return Math.max(1, (m && parseInt(m.required_units, 10)) || 1);
  }

  function rackMounts(rackId) {
    return state.data.mounts.filter(function (m) { return m.racks_id === rackId; }).map(function (m) {
      var item = itemOf(m.itemtype, m.items_id);
      var model = modelOf(m.itemtype, item);
      return {
        mount: m, itemtype: m.itemtype, item: item, model: model,
        units: unitsOf(m.itemtype, item),
        depth: model ? parseFloat(model.depth) || 1 : 1
      };
    });
  }

  function rackStats(rack) {
    var mounts = rackMounts(rack.id);
    var used = 0, power = 0, weight = 0;
    mounts.forEach(function (d) {
      used += d.mount.hpos ? d.units / 2 : d.units;
      if (d.model && d.itemtype !== 'PDU') power += parseInt(d.model.power_consumption, 10) || 0;
      if (d.model) weight += parseInt(d.model.weight, 10) || 0;
    });
    var units = parseInt(rack.number_units, 10) || 42;
    return {
      mounts: mounts, units: units, used: used, pct: used / units,
      power: power, maxPower: parseInt(rack.max_power, 10) || 0,
      weight: weight, maxWeight: parseInt(rack.max_weight, 10) || 0
    };
  }

  function level(pct) { return pct > 0.8 ? 'hi' : pct >= 0.5 ? 'mid' : 'lo'; }

  function matches(item) {
    if (!state.query || !item) return false;
    var q = state.query.toLowerCase();
    return ((item.name || '') + ' ' + (item.serial || '') + ' ' + (item.otherserial || ''))
      .toLowerCase().indexOf(q) !== -1;
  }

  // ----------------------------------------------------------- render
  function render() {
    renderRoomSelect();
    renderStats();
    renderFloor();
    renderRack();
    renderDetail();
    saveHash();
  }

  function roomsSorted() {
    return Object.values(state.data.rooms).sort(function (a, b) {
      return (a.name || '').localeCompare(b.name || '');
    });
  }

  function renderRoomSelect() {
    var sel = $('room-select');
    sel.innerHTML = '';
    var rooms = roomsSorted();
    if (!rooms.length) {
      sel.appendChild(el('option', { text: 'No server rooms yet' }));
      return;
    }
    if (!state.data.rooms[state.roomId]) state.roomId = rooms[0].id;
    rooms.forEach(function (r) {
      var dc = state.data.dcs[r.datacenters_id];
      var opt = el('option', { value: r.id, text: (dc ? dc.name + ' / ' : '') + r.name });
      if (r.id === state.roomId) opt.selected = true;
      sel.appendChild(opt);
    });
  }

  function roomRacks() {
    return Object.values(state.data.racks).filter(function (r) { return r.dcrooms_id === state.roomId; });
  }

  function renderStats() {
    var box = $('stats');
    box.innerHTML = '';
    var racks = roomRacks();
    var u = 0, used = 0, devices = 0, power = 0, maxPower = 0;
    racks.forEach(function (r) {
      var s = rackStats(r);
      u += s.units; used += s.used; devices += s.mounts.length; power += s.power; maxPower += s.maxPower;
    });
    [
      [racks.length, 'Racks in room'],
      [devices, 'Mounted devices'],
      [u ? Math.round(used / u * 100) + '%' : '–', 'Rack space used (' + used + ' / ' + u + ' U)'],
      [maxPower ? Math.round(power / maxPower * 100) + '%' : power + ' W',
        'Planned power' + (maxPower ? ' (' + power + ' / ' + maxPower + ' W)' : '')]
    ].forEach(function (s) {
      box.appendChild(el('div', { class: 'stat' }, [
        el('div', { class: 'v', text: String(s[0]) }), el('div', { class: 'l', text: s[1] })
      ]));
    });
  }

  function renderFloor() {
    var room = state.data.rooms[state.roomId];
    var floor = $('floor');
    floor.innerHTML = '';
    $('unplaced').innerHTML = '';
    if (!room) {
      $('room-title').textContent = 'Floor plan';
      floor.appendChild(el('p', { class: 'muted', text: 'Create a data centre and server room in GLPI (Management > Data centers), or import racks.csv.' }));
      renderSearch();
      return;
    }
    $('room-title').textContent = room.name + ' floor plan';
    var cols = parseInt(room.vis_cols, 10) || 10;
    var rows = parseInt(room.vis_rows, 10) || 6;
    floor.style.gridTemplateColumns = 'repeat(' + cols + ', minmax(46px, 1fr))';

    var grid = {}, unplaced = [];
    roomRacks().forEach(function (r) {
      var p = String(r.position || '').split(',');
      var x = parseInt(p[0], 10), y = parseInt(p[1], 10);
      if (p.length === 2 && x >= 1 && y >= 1 && x <= cols && y <= rows) grid[x + ',' + y] = r;
      else unplaced.push(r);
    });

    for (var y = 1; y <= rows; y++) {
      for (var x = 1; x <= cols; x++) {
        var rack = grid[x + ',' + y];
        floor.appendChild(rack ? rackTile(rack) : el('div', { class: 'cell', 'aria-hidden': 'true' }));
      }
    }

    if (unplaced.length) {
      $('unplaced').appendChild(el('div', { class: 'list-block' }, [
        el('h3', { text: 'Racks without a floor position' }),
        el('div', { class: 'chips' }, unplaced.map(function (r) {
          return el('button', { class: 'chip', type: 'button', text: r.name, onclick: function () { selectRack(r.id); } });
        }))
      ]));
    }
    renderSearch();
  }

  function rackTile(rack) {
    var s = rackStats(rack);
    var hit = state.query && s.mounts.some(function (d) { return matches(d.item); });
    var cls = 'rack-tile ' + level(s.pct) + (rack.id === state.rackId ? ' sel' : '') + (hit ? ' match' : '');
    return el('button', {
      class: cls, type: 'button',
      title: rack.name + ' – ' + s.used + '/' + s.units + ' U used',
      'aria-label': rack.name + ', ' + Math.round(s.pct * 100) + '% used',
      onclick: function () { selectRack(rack.id); }
    }, [
      el('span', { class: 'dir', text: ARROW[rack.room_orientation] || '' }),
      el('span', { text: shortName(rack.name) })
    ]);
  }

  // Long names don't fit a floor tile: show the last part (e.g. DEL1-HALLA-R01 -> R01)
  function shortName(name) {
    name = name || '';
    if (name.length <= 7) return name;
    var parts = name.split(/[-_ .]/).filter(Boolean);
    return parts.length > 1 ? parts[parts.length - 1] : name.slice(-7);
  }

  function renderSearch() {
    var box = $('search-results');
    box.innerHTML = '';
    if (!state.query) return;
    var hits = [];
    state.data.mounts.forEach(function (m) {
      var item = itemOf(m.itemtype, m.items_id);
      if (matches(item)) hits.push({ itemtype: m.itemtype, item: item, rackId: m.racks_id });
    });
    state.data.pduMounts.forEach(function (m) {
      var item = itemOf('PDU', m.pdus_id);
      if (matches(item)) hits.push({ itemtype: 'PDU', item: item, rackId: m.racks_id });
    });
    box.appendChild(el('div', { class: 'list-block' }, [
      el('h3', { text: hits.length + ' device(s) match “' + state.query + '”' }),
      el('div', { class: 'chips' }, hits.slice(0, 60).map(function (h) {
        var rack = state.data.racks[h.rackId];
        return el('button', {
          class: 'chip', type: 'button',
          text: h.item.name + (rack ? ' → ' + rack.name : ''),
          onclick: function () {
            if (rack) state.roomId = rack.dcrooms_id;
            state.rackId = h.rackId;
            state.selected = { itemtype: h.itemtype, id: h.item.id };
            render();
          }
        });
      }))
    ]));
  }

  function renderRack() {
    var rack = state.data.racks[state.rackId];
    var box = $('rack'), meta = $('rack-meta');
    box.innerHTML = ''; meta.innerHTML = '';
    $('pdu-left').innerHTML = ''; $('pdu-right').innerHTML = '';
    if (!rack) {
      $('rack-title').textContent = 'Select a rack';
      box.style.height = '0';
      box.hidden = true;
      return;
    }
    box.hidden = false;
    var s = rackStats(rack);
    $('rack-title').innerHTML = '';
    $('rack-title').appendChild(el('a', { href: glpiForm('Rack', rack.id), target: '_blank', rel: 'noopener', text: rack.name }));

    meta.appendChild(meter('Space', s.used, s.units, 'U'));
    if (s.maxPower) meta.appendChild(meter('Power', s.power, s.maxPower, 'W'));
    if (s.maxWeight) meta.appendChild(meter('Weight', s.weight, s.maxWeight, 'kg'));

    box.style.height = (s.units * U_PX + 2) + 'px';
    for (var u = 1; u <= s.units; u++) {
      box.appendChild(el('div', {
        class: 'u-row', text: String(u),
        style: 'top:' + ((s.units - u) * U_PX) + 'px;height:' + U_PX + 'px'
      }));
    }

    s.mounts.forEach(function (d) {
      var onFace = (parseInt(d.mount.orientation, 10) || 0) === state.face;
      // Full-depth kit mounted on the other face still blocks this face
      if (!onFace && d.depth < 1) return;
      var pos = parseInt(d.mount.position, 10) || 1;
      var top = (s.units - (pos + d.units - 1)) * U_PX;
      var name = d.item ? d.item.name : d.itemtype + ' #' + d.mount.items_id;
      var hpos = parseInt(d.mount.hpos, 10) || 0;
      var cls = 'dev t-' + (KIND[d.itemtype] || 'other') +
        (hpos === 1 ? ' half-left' : hpos === 2 ? ' half-right' : '') +
        (onFace ? '' : ' ghost') +
        (isSelected(d.itemtype, d.mount.items_id) ? ' sel' : '') +
        (matches(d.item) ? ' match' : '');
      box.appendChild(el('button', {
        class: cls, type: 'button',
        style: 'top:' + (top + 1) + 'px;height:' + (d.units * U_PX - 2) + 'px',
        title: name + (onFace ? '' : ' (mounted on the other face)'),
        onclick: function () { select(d.itemtype, d.mount.items_id); }
      }, [
        el('span', { text: name }),
        el('span', { class: 'u-tag', text: 'U' + pos + (d.units > 1 ? '–' + (pos + d.units - 1) : '') })
      ]));
    });

    state.data.pduMounts.filter(function (m) { return m.racks_id === rack.id; }).forEach(function (m) {
      var side = PDU_SIDE[m.side];
      var item = itemOf('PDU', m.pdus_id);
      // Left/right are from the front; swap when looking at the rear
      if (state.face === 1 && (side === 'left' || side === 'right')) side = side === 'left' ? 'right' : 'left';
      var target = side === 'right' ? $('pdu-right') : $('pdu-left');
      target.appendChild(el('button', {
        class: 'pdu', type: 'button', text: item ? item.name : 'PDU #' + m.pdus_id,
        title: 'PDU on ' + PDU_SIDE[m.side] + ' side',
        onclick: function () { select('PDU', m.pdus_id); }
      }));
    });
  }

  function meter(label, val, max, unit) {
    var pct = max ? val / max : 0;
    return el('div', { class: 'meter' }, [
      el('span', { class: 'muted', text: label }),
      el('div', { class: 'bar' }, [el('div', {
        style: 'width:' + Math.min(100, pct * 100) + '%;background:var(--' + level(pct) + ')'
      })]),
      el('span', { text: val + ' / ' + max + ' ' + unit })
    ]);
  }

  function isSelected(t, id) { return state.selected && state.selected.itemtype === t && state.selected.id === id; }

  function renderDetail() {
    var box = $('detail');
    box.innerHTML = '';
    var sel = state.selected;
    var item = sel && itemOf(sel.itemtype, sel.id);
    if (!item) {
      box.className = 'muted';
      box.textContent = 'Click a device in the rack.';
      return;
    }
    box.className = 'detail';
    var model = modelOf(sel.itemtype, item);
    var st = state.data.states[item.states_id];
    var mount = state.data.mounts.find(function (m) { return m.itemtype === sel.itemtype && m.items_id === sel.id; });
    var pdu = sel.itemtype === 'PDU' && state.data.pduMounts.find(function (m) { return m.pdus_id === sel.id; });
    var rack = state.data.racks[(mount || pdu || {}).racks_id];
    var where = '–';
    if (mount) {
      var units = unitsOf(sel.itemtype, item);
      var pos = parseInt(mount.position, 10);
      where = 'U' + pos + (units > 1 ? '–' + (pos + units - 1) : '') + ', ' + (mount.orientation == 1 ? 'rear' : 'front');
    } else if (pdu) {
      where = PDU_SIDE[pdu.side] + ' side';
    }
    var rows = [
      ['Type', LABEL[sel.itemtype] || sel.itemtype],
      ['Model', model ? model.name : '–'],
      ['Serial', item.serial || '–'],
      ['Inventory #', item.otherserial || '–'],
      ['Status', st ? st.name : '–'],
      ['Rack', rack ? rack.name : '–'],
      ['Position', where],
      ['Power', model ? (sel.itemtype === 'PDU' ? (model.max_power || 0) + ' W capacity' : (model.power_consumption || 0) + ' W') : '–'],
      ['Last inventory', item.last_inventory_update || 'manual entry']
    ];
    box.appendChild(el('h3', { text: item.name }));
    box.appendChild(el('dl', {}, rows.reduce(function (acc, r) {
      return acc.concat([el('dt', { text: r[0] }), el('dd', { text: String(r[1]) })]);
    }, [])));
    if (item.comment) box.appendChild(el('p', { class: 'muted', text: item.comment }));
    box.appendChild(el('a', { class: 'btn', href: glpiForm(sel.itemtype, sel.id), target: '_blank', rel: 'noopener', text: 'Open in GLPI' }));
  }

  // ---------------------------------------------------------- actions
  function selectRack(id) {
    state.rackId = id;
    state.selected = null;
    render();
  }

  function select(itemtype, id) {
    state.selected = { itemtype: itemtype, id: id };
    renderRack();
    renderDetail();
    saveHash();
  }

  function saveHash() {
    var h = 'room=' + (state.roomId || '') + '&rack=' + (state.rackId || '') + '&face=' + state.face;
    if (location.hash.slice(1) !== h) history.replaceState(null, '', '#' + h);
  }

  function readHash() {
    var p = new URLSearchParams(location.hash.slice(1));
    state.roomId = parseInt(p.get('room'), 10) || null;
    state.rackId = parseInt(p.get('rack'), 10) || null;
    state.face = p.get('face') === '1' ? 1 : 0;
  }

  function setFace(face) {
    state.face = face;
    document.querySelectorAll('.seg button').forEach(function (b) {
      b.setAttribute('aria-pressed', String(parseInt(b.dataset.face, 10) === face));
    });
    if (state.data) renderRack();
    saveHash();
  }

  var timer = null;

  function startApp() {
    setFace(state.face);
    load();
    clearInterval(timer);
    timer = setInterval(load, DC.refreshMs);
  }

  // ------------------------------------------------------------- init
  readHash();
  $('refresh').addEventListener('click', load);
  $('room-select').addEventListener('change', function (e) {
    state.roomId = parseInt(e.target.value, 10);
    state.rackId = null;
    state.selected = null;
    render();
  });
  var searchTimer = null;
  $('search').addEventListener('input', function (e) {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
      state.query = e.target.value.trim();
      renderFloor();
      renderRack();
    }, 200);
  });
  document.querySelectorAll('.seg button').forEach(function (b) {
    b.addEventListener('click', function () { setFace(parseInt(b.dataset.face, 10)); });
  });

  DC.initAuth({ onReady: startApp, onLogout: function () { clearInterval(timer); } });
})();
