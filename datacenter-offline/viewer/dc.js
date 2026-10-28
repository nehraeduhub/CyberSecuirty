/* Shared helpers for the DC Viewer pages: DOM builder, the manager API
 * (/api/ on the same origin), feature switches, toasts and the per-device
 * connect buttons. No external libraries (works offline). Exposes window.DC. */
(function () {
  'use strict';

  var CFG = window.DC_VIEWER_CONFIG || {};
  var DC = { cfg: CFG };

  DC.$ = function (id) { return document.getElementById(id); };

  // Build DOM safely: text always goes through textContent (device data is untrusted)
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

  // The DC NOC API: device list, settings, status, scan now
  DC.mgr = function (path, opts) {
    opts = opts || {};
    var init = { headers: { 'Content-Type': 'application/json' }, method: opts.method || 'GET', cache: 'no-store' };
    if (opts.body !== undefined) init.body = JSON.stringify(opts.body);
    return fetch('../api/' + path, init).then(function (r) {
      return r.text().then(function (body) {
        var json = null;
        try { json = body ? JSON.parse(body) : null; } catch (e) { /* not json */ }
        if (!r.ok) {
          var err = new Error((json && json.error) || 'HTTP ' + r.status +
            (r.status === 502 || r.status === 504 ? ' (manager container not running?)' : ''));
          err.status = r.status;
          err.data = json;
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

  // One-click access: SSH terminal in a new tab, RDP (.rdp file for mstsc),
  // the device's web page, and its edit page
  DC.connectButtons = function (ip, name, editHref) {
    var el = DC.el, out = [];
    if (ip) {
      var sshUrl = 'ssh.html?host=' + encodeURIComponent(ip) + '&name=' + encodeURIComponent(name || ip);
      out.push(el('a', { class: 'go', href: sshUrl, target: '_blank', rel: 'noopener', title: 'SSH to ' + ip + ' in a new tab', text: 'SSH' }));
      out.push(el('button', { type: 'button', class: 'go', title: 'Remote Desktop (mstsc) to ' + ip, text: 'RDP', onclick: function () {
        var file = 'full address:s:' + ip + '\r\nprompt for credentials:i:1\r\nadministrative session:i:0\r\nscreen mode id:i:2\r\n';
        var a = el('a', { href: URL.createObjectURL(new Blob([file], { type: 'application/x-rdp' })),
          download: (name || ip).replace(/[^\w.-]+/g, '_') + '.rdp' });
        document.body.appendChild(a);
        a.click();
        setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
        DC.toast('Open the downloaded ' + a.download + ' to start Remote Desktop');
      } }));
      out.push(el('a', { class: 'go', href: 'https://' + ip + '/', target: '_blank', rel: 'noopener', title: 'Web page of ' + ip, text: 'Web' }));
    }
    if (editHref) out.push(el('a', { class: 'go', href: editHref, title: 'Edit this device', text: 'Edit' }));
    return out;
  };

  DC.ipNum = function (ip) {
    var p = String(ip || '').split('.');
    return p.length === 4 ? ((+p[0] * 256 + +p[1]) * 256 + +p[2]) * 256 + +p[3] : Infinity;
  };

  window.DC = DC;
})();
