/* Shared GLPI REST API client and sign-in for the DC Viewer pages.
 * The portal proxies /apirest.php to GLPI on the same origin, so no CORS or
 * external libraries are needed (works offline). Exposes window.DC. */
(function () {
  'use strict';

  var CFG = window.DC_VIEWER_CONFIG || {};
  var API = CFG.apiUrl || '../apirest.php';
  var GLPI = (CFG.glpiUrl || location.protocol + '//' + location.hostname).replace(/\/$/, '');
  var TOKEN_KEY = 'dcv-token';

  var DC = {
    cfg: CFG,
    glpiUrl: GLPI,
    refreshMs: (CFG.refreshMinutes || 5) * 60000,
    token: null
  };

  DC.$ = function (id) { return document.getElementById(id); };

  // Build DOM safely: text always goes through textContent (GLPI data is untrusted)
  DC.el = function (tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (attrs[k] == null || attrs[k] === false) return;
      if (k === 'class') node.className = attrs[k];
      else if (k === 'text') node.textContent = attrs[k];
      else if (k === 'style') node.style.cssText = attrs[k];
      else if (k.slice(0, 2) === 'on') node.addEventListener(k.slice(2), attrs[k]);
      else node.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) {
      if (c != null) node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return node;
  };

  function store(value) {
    try {
      if (value == null) sessionStorage.removeItem(TOKEN_KEY);
      else sessionStorage.setItem(TOKEN_KEY, value);
    } catch (e) { /* storage unavailable */ }
  }

  function recall() {
    try { return sessionStorage.getItem(TOKEN_KEY); } catch (e) { return null; }
  }

  DC.api = function (path, opts) {
    opts = opts || {};
    var headers = { 'Content-Type': 'application/json' };
    if (DC.token) headers['Session-Token'] = DC.token;
    if (CFG.appToken) headers['App-Token'] = CFG.appToken;
    Object.assign(headers, opts.headers || {});
    var init = { headers: headers, method: opts.method || 'GET' };
    if (opts.body !== undefined) init.body = JSON.stringify(opts.body);
    return fetch(API + '/' + path, init).then(function (r) {
      return r.text().then(function (body) {
        var json = null;
        try { json = body ? JSON.parse(body) : null; } catch (e) { /* not json */ }
        if (!r.ok) {
          var err = new Error(Array.isArray(json) ? json.join(': ') : 'HTTP ' + r.status);
          err.status = r.status;
          err.code = Array.isArray(json) ? json[0] : '';
          throw err;
        }
        return { json: json, headers: r.headers };
      });
    });
  };

  // Every non-deleted object of an itemtype; missing rights give an empty list.
  // extra: more query parameters, e.g. 'expand_dropdowns=true'
  DC.fetchAll = function (itemtype, extra) {
    var out = [], step = 1000;
    function page(start) {
      return DC.api(itemtype + '?is_deleted=0&range=' + start + '-' + (start + step - 1) + (extra ? '&' + extra : ''))
        .then(function (res) {
          out = out.concat(res.json || []);
          var total = parseInt(((res.headers.get('Content-Range') || '/0').split('/')[1]), 10) || 0;
          return start + step < total ? page(start + step) : out;
        })
        .catch(function (e) {
          if (e.code === 'ERROR_RANGE_EXCEED_TOTAL') return out;
          if (e.status === 401 && e.code !== 'ERROR_SESSION_TOKEN_INVALID') return out;
          if (e.status === 403 || e.status === 400) return out;
          throw e;
        });
    }
    return page(0);
  };

  // DC Viewer management API (/api/, the manager container): settings, device
  // status, scan now. Signed in with the same GLPI session.
  DC.mgr = function (path, opts) {
    opts = opts || {};
    var headers = { 'Content-Type': 'application/json' };
    if (DC.token) headers['Session-Token'] = DC.token;
    if (CFG.appToken) headers['App-Token'] = CFG.appToken;
    var init = { headers: headers, method: opts.method || 'GET', cache: 'no-store' };
    if (opts.body !== undefined) init.body = JSON.stringify(opts.body);
    return fetch('../api/' + path, init).then(function (r) {
      return r.text().then(function (body) {
        var json = null;
        try { json = body ? JSON.parse(body) : null; } catch (e) { /* not json */ }
        if (!r.ok) {
          var err = new Error((json && json.error) || 'HTTP ' + r.status +
            (r.status === 502 || r.status === 504 ? ' (manager container not running?)' : ''));
          err.status = r.status;
          throw err;
        }
        return json;
      });
    });
  };

  // Hide the tabs switched off on the Scan & settings page (links marked data-feature)
  DC.applyFeatures = function () {
    return DC.mgr('features').then(function (f) {
      document.querySelectorAll('[data-feature]').forEach(function (a) {
        a.hidden = f[a.getAttribute('data-feature')] === false;
      });
      return f;
    }).catch(function () { return {}; });
  };

  // Short message at the bottom of the page
  DC.toast = function (text, isError) {
    var t = document.getElementById('dc-toast');
    if (!t) {
      t = DC.el('div', { id: 'dc-toast', class: 'toast', role: 'status' });
      document.body.appendChild(t);
    }
    t.textContent = text;
    t.className = 'toast show' + (isError ? ' bad' : '');
    clearTimeout(DC.toast.timer);
    DC.toast.timer = setTimeout(function () { t.className = 'toast'; }, isError ? 8000 : 3500);
  };

  DC.byId = function (list) {
    var m = {};
    list.forEach(function (o) { m[o.id] = o; });
    return m;
  };

  DC.glpiForm = function (itemtype, id) {
    return GLPI + '/front/' + itemtype.toLowerCase() + '.form.php?id=' + id;
  };

  /* Wire the sign-in form shared by every page.
   *   opts.onReady()  called once signed in (and on page load with a saved session)
   *   opts.onLogout() called when signing out or when the session expires */
  DC.initAuth = function (opts) {
    var $ = DC.$;
    $('glpi-link') && ($('glpi-link').href = GLPI + '/');

    function show() {
      $('login-view').hidden = true;
      $('app-view').hidden = false;
      opts.onReady();
    }

    DC.logout = function (expired) {
      if (!expired && DC.token) DC.api('killSession').catch(function () {});
      DC.token = null;
      store(null);
      if (opts.onLogout) opts.onLogout();
      $('app-view').hidden = true;
      $('login-view').hidden = false;
      if (expired) $('login-error').textContent = 'Your session has expired. Please sign in again.';
    };

    $('login-form').addEventListener('submit', function (e) {
      e.preventDefault();
      var f = e.target;
      $('login-error').textContent = '';
      var cred = btoa(unescape(encodeURIComponent(f.user.value + ':' + f.password.value)));
      DC.api('initSession', { headers: { Authorization: 'Basic ' + cred } }).then(function (res) {
        DC.token = res.json.session_token;
        store(DC.token);
        f.password.value = '';
        show();
      }).catch(function (err) {
        $('login-error').textContent = err.status === 401
          ? 'Wrong login or password.'
          : 'Cannot reach the GLPI API (' + err.message + '). Is the REST API enabled for this network?';
      });
    });
    $('logout').addEventListener('click', function () { DC.logout(false); });

    DC.applyFeatures();
    DC.token = recall();
    if (DC.token) show();
    else $('login-view').hidden = false;
  };

  // Shared error handling for data loads
  DC.loadError = function (e, errorEl, statusEl) {
    if (e.status === 401) { DC.logout(true); return; }
    errorEl.textContent = 'Could not load data from GLPI: ' + e.message;
    if (statusEl) statusEl.textContent = '';
  };

  window.DC = DC;
})();
