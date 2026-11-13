// Screens for B2 "How to enroll for the CTF portal" from the local site copy (demo student arjun.m, no plan).
// Every ₹ amount is hidden and the payment QR is blurred. Usage: node tools/capture-enroll.js <out dir> [base url]
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const [OUT, B = 'http://127.0.0.1:8110'] = process.argv.slice(2);
const HIDE = '.fixed.bottom-5.right-5,#tg-fab,button.fixed{display:none!important} .qr,.qr img,img[src*="qr" i]{filter:blur(14px)!important}';
const meta = {};
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  const ctx = async (user, mobile = true) => {
    const c = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: mobile, hasTouch: mobile });
    await c.route(/^(?!http:\/\/127\.0\.0\.1)/, (r) => r.abort());
    const p = await c.newPage();
    if (user) { const r = await p.request.post(B + '/api/users.php?action=login', { data: { username: user, password: 'Student12345' } }); if (!r.ok()) throw new Error('login: ' + await r.text()); }
    return p;
  };
  const shot = async (p, name, marks, h, top = true) => {
    await p.addStyleTag({ content: HIDE });
    if (top) { for (let y = 0; y < h; y += 350) { await p.evaluate((y) => window.scrollTo(0, y), y); await p.waitForTimeout(100); } await p.evaluate(() => window.scrollTo(0, 0)); }
    await p.waitForTimeout(400);
    const hid = await p.evaluate(() => { let n = 0;
      for (const e of document.querySelectorAll('body *')) {
        if (/₹/.test(e.textContent) && e.offsetHeight > 0 && e.offsetHeight < 70) { e.style.visibility = 'hidden'; n++; }
        // payee name, UPI ID and payment note are blurred like the QR
        if (/(UPI ID|Paying to|Payment note)/.test(e.textContent) && e.offsetHeight > 0 && e.offsetHeight < 60) e.style.filter = 'blur(7px)';
      } return n; });
    const rects = {};
    for (const [k, m] of Object.entries(marks)) {
      const [sel, mode] = Array.isArray(m) ? m : [m, ''];
      const r = await p.locator(sel).first().evaluate((el, mode) => { const need = mode === 'card' ? [250, 70] : [120, 0];
        let c = el; while (c.parentElement && (c.offsetWidth < need[0] || c.offsetHeight < need[1])) c = c.parentElement;
        const q = c.getBoundingClientRect(); return { x: q.x, y: q.y + scrollY, w: q.width, h: q.height }; }, mode).catch(() => null);
      if (r) rects[k] = r; else console.log('  missing', name, k);
    }
    const full = await p.evaluate(() => document.documentElement.scrollHeight), hh = top ? Math.min(h, full) : 844;
    await p.screenshot({ path: path.join(OUT, name + '.png'), fullPage: top, clip: { x: 0, y: 0, width: 390, height: hh } });
    meta[name] = { h: hh, rects }; console.log(name, hh, Object.keys(rects).join(','), hid ? `(hid ${hid})` : '');
  };
  let p = await ctx();
  await p.goto(B + '/'); await p.waitForTimeout(1500);
  await p.click('button[aria-label="Toggle menu"]'); await p.waitForTimeout(700);
  await shot(p, 'menu', { ctf: 'header .overflow-y-auto >> text=CTF Portal' }, 844, false);
  await p.goto(B + '/ctf'); await p.waitForTimeout(1800);
  await shot(p, 'gate', { signin: 'main >> text=Sign in', create: 'text=Create a student account' }, 1400);
  p = await ctx('arjun.m');
  await p.goto(B + '/ctf'); await p.waitForTimeout(1800);
  await shot(p, 'ctfhome', { free: 'text=Free access: task 1 of every room', room: ['a[href="/ctf/fundamentals"]', 'card'] }, 1700);
  await p.goto(B + '/ctf/fundamentals'); await p.waitForTimeout(1800);
  await shot(p, 'room', { t1: 'a[href*="task=1"]' }, 1300);
  await p.goto(B + '/ctf/plans'); await p.waitForTimeout(1800);
  await shot(p, 'plans', { monthly: ['text=Monthly plan', 'card'], annual: ['text=Annual plan', 'card'] }, 1700);
  p = await ctx('arjun.m', false);          // the checkout's full-page capture needs a plain 390px window
  await p.goto(B + '/courses/payment.html?ctf=annual'); await p.waitForTimeout(1500);
  await p.fill('#phone', '9811100011');
  await shot(p, 'checkout', { plans: '#ctf-pick', coupon: '#coupon-box', cont: '#step1 button[type=submit]' }, 1600);
  await p.click('#step1 button[type=submit]'); await p.waitForTimeout(900);
  await shot(p, 'upi', { qr: '#step2 .qr', paid: '#paid' }, 1700);
  await p.click('#paid'); await p.waitForTimeout(600);
  await p.fill('#utr', '412345678901'); await p.check('#agree').catch(() => {}); await p.check('#agree-terms').catch(() => {});
  await shot(p, 'utr', { utr: '#utr', submit: '#submit' }, 1700);
  fs.writeFileSync(path.join(OUT, 'shots.json'), JSON.stringify(meta, null, 1));
  await b.close();
})();
