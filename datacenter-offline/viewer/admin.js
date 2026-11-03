/* Admin portal (/admin): sign in, branding (name, subtitle, logo), the
 * category and location lists people pick from, and the admin account. */
(function () {
  'use strict';

  var DC = window.DC;
  var el = DC.el, $ = DC.$;
  var st = { cats: [], locs: [], logo: undefined };   // logo: undefined = unchanged, '' = remove, data URL = new

  function show(signedIn) {
    $('login-view').hidden = signedIn;
    $('app-view').hidden = !signedIn;
  }

  // ------------------------------------------------------------- sign in
  function start() {
    DC.mgr('admin/me').then(function (me) {
      $('who').textContent = me.user;
      $('pw-form').user.value = me.user;
      show(true);
      load();
    }, function () { show(false); $('login-form').user.focus(); });
  }

  $('login-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var f = e.target;
    $('login-error').textContent = '';
    DC.mgr('admin/login', { method: 'POST', body: { user: f.user.value.trim(), password: f.password.value } }).then(function () {
      f.password.value = '';
      start();
    }, function (err) { $('login-error').textContent = err.message; });
  });
  $('logout').addEventListener('click', function () {
    DC.mgr('admin/logout', { method: 'POST', body: {} }).then(function () { show(false); });
  });

  // ------------------------------------------------------------- load
  function load() {
    Promise.all([DC.mgr('branding'), DC.mgr('lists')]).then(function (r) {
      var b = r[0], f = $('brand-form');
      f.name.value = b.name || '';
      f.subtitle.value = b.subtitle || '';
      st.logo = undefined;
      preview(b.logo ? '../' + b.logo : '');
      st.cats = (r[1].categories || []).slice();
      st.locs = (r[1].locations || []).slice();
      renderList('cats', st.cats, true);
      renderList('locs', st.locs, false);
    }).catch(function (e) { DC.toast(e.message, true); });
  }

  // ------------------------------------------------------------- branding
  function preview(src) {
    var p = $('logo-preview');
    p.textContent = '';
    if (src) p.appendChild(el('img', { src: src, alt: 'Logo' }));
    else p.appendChild(el('span', { class: 'noc-logo', 'aria-hidden': 'true' }));
  }

  $('logo-file').addEventListener('change', function (e) {
    var file = e.target.files[0];
    if (!file) return;
    if (file.size > 512 * 1024) { DC.toast('The logo may be at most 512 KB', true); return; }
    var r = new FileReader();
    r.onload = function () { st.logo = r.result; preview(r.result); $('brand-msg').textContent = 'New logo: save to apply'; };
    r.readAsDataURL(file);
  });
  $('logo-remove').addEventListener('click', function () { st.logo = ''; preview(''); $('brand-msg').textContent = 'Logo removed: save to apply'; });

  $('brand-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var f = e.target, body = { name: f.name.value.trim(), subtitle: f.subtitle.value.trim() };
    if (st.logo !== undefined) body.logo = st.logo;
    DC.mgr('admin/branding', { method: 'PUT', body: body }).then(function () {
      $('brand-msg').textContent = 'Saved';
      DC.toast('Branding saved: every page shows it after a reload');
      DC.applyBranding();
      load();
    }, function (err) { $('brand-msg').textContent = ''; DC.toast(err.message, true); });
  });

  // ------------------------------------------------------------- lists
  function renderList(id, list, isCats) {
    var ul = $(id);
    ul.textContent = '';
    list.forEach(function (v, i) {
      var fixed = isCats && v === 'Unknown';
      ul.appendChild(el('li', {}, [
        el('input', { value: v, 'aria-label': (isCats ? 'Category ' : 'Location ') + (i + 1), disabled: fixed ? 'disabled' : null,
          oninput: function (e) { list[i] = e.target.value; dirty(id); } }),
        el('button', { type: 'button', class: 'link-btn', text: '↑', title: 'Move up', 'aria-label': 'Move ' + v + ' up', disabled: i === 0 ? 'disabled' : null,
          onclick: function () { list.splice(i - 1, 0, list.splice(i, 1)[0]); renderList(id, list, isCats); dirty(id); } }),
        el('button', { type: 'button', class: 'link-btn', text: '↓', title: 'Move down', 'aria-label': 'Move ' + v + ' down', disabled: i === list.length - 1 ? 'disabled' : null,
          onclick: function () { list.splice(i + 1, 0, list.splice(i, 1)[0]); renderList(id, list, isCats); dirty(id); } }),
        fixed ? el('span', { class: 'muted small', text: 'always kept' }) :
          el('button', { type: 'button', class: 'link-btn', text: 'Remove', 'aria-label': 'Remove ' + v,
            onclick: function () { list.splice(i, 1); renderList(id, list, isCats); dirty(id); } })
      ]));
    });
    if (!list.length) ul.appendChild(el('li', { class: 'muted small', text: isCats ? 'No categories' : 'No locations yet: location is free text until you add some.' }));
  }
  function dirty(id) { $(id + '-msg').textContent = 'Unsaved changes'; }

  [['cat-add', 'cats', true], ['loc-add', 'locs', false]].forEach(function (x) {
    $(x[0]).addEventListener('submit', function (e) {
      e.preventDefault();
      var v = e.target.v.value.trim(), list = x[2] ? st.cats : st.locs;
      if (!v) return;
      if (list.indexOf(v) !== -1) { DC.toast(v + ' is already in the list', true); return; }
      // New categories go before "Unknown", which stays last
      var at = x[2] && list.indexOf('Unknown') !== -1 ? list.indexOf('Unknown') : list.length;
      list.splice(at, 0, v);
      e.target.reset();
      renderList(x[1], list, x[2]);
      dirty(x[1]);
    });
  });

  function saveLists(which) {
    DC.mgr('admin/lists', { method: 'PUT', body: { categories: st.cats, locations: st.locs } }).then(function (r) {
      st.cats = r.categories.slice();
      st.locs = r.locations.slice();
      renderList('cats', st.cats, true);
      renderList('locs', st.locs, false);
      $('cats-msg').textContent = '';
      $('locs-msg').textContent = '';
      DC.toast(which === 'cats' ? 'Categories saved' : 'Locations saved');
    }, function (err) { DC.toast(err.message, true); });
  }
  $('cats-save').addEventListener('click', function () {
    if (!confirm('Save the category list?\n\nDevices in a removed category go back to an automatic category.')) return;
    saveLists('cats');
  });
  $('locs-save').addEventListener('click', function () { saveLists('locs'); });

  // ------------------------------------------------------------- account
  $('pw-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var f = e.target;
    $('pw-msg').textContent = '';
    if (f.password.value !== f.password2.value) { $('pw-msg').textContent = 'The new passwords differ'; return; }
    DC.mgr('admin/password', { method: 'PUT', body: { user: f.user.value.trim(), current: f.current.value, password: f.password.value } }).then(function () {
      f.reset();
      DC.toast('Changed. Sign in with the new password.');
      show(false);
    }, function (err) { $('pw-msg').textContent = err.message; });
  });

  DC.applyBranding();
  start();
})();
