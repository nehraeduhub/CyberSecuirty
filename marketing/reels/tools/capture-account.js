// Screens for the "How to create a student account" guide reel (B6), from the local site copy.
// Usage: SITE_DATA=<site>/api/data node tools/capture-account.js <out dir> [base url]
// Needs api/data/mail-config.json with otpEnabled + a valid fromEmail in the local copy so the
// "Sign in with an email code" option shows. otp_send is answered locally (no email is sent).
// Demo data only: Priya Sharma / priya.sharma / priya.s@example.com.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const [OUT, B = 'http://127.0.0.1:8110'] = process.argv.slice(2);
const HIDE = '.fixed.bottom-5.right-5,#tg-fab,button.fixed{display:none!important}';
const meta = {};
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  const ctx = async () => {
    const c = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
    await c.route(/^(?!http:\/\/127\.0\.0\.1)/, (r) => r.abort());
    await c.route('**/api/users.php?action=otp_send', (r) => r.fulfill({ contentType: 'application/json',
      body: JSON.stringify({ ok: true, message: 'If this email belongs to an active student account, a 6-digit code is on its way. Check your inbox and spam folder.', ttl: 600, gap: 60 }) }));
    return c.newPage();
  };
  const shot = async (p, name, marks = {}, h = 844) => {
    await p.addStyleTag({ content: HIDE }); await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(350);
    // no prices in reels: hide any element that shows a ₹ amount
    const hidden = await p.evaluate(() => { let n = 0;
      for (const e of document.querySelectorAll('body *')) if (/₹/.test(e.textContent) && e.offsetHeight > 0 && e.offsetHeight < 70) { e.style.visibility = 'hidden'; n++; }
      return n; });
    if (hidden) console.log('  hid', hidden, 'price element(s) on', name);
    const rects = {};
    for (const [k, sel] of Object.entries(marks)) {
      const r = await p.locator(sel).first().evaluate((el) => { const q = el.getBoundingClientRect(); return { x: q.x, y: q.y + scrollY, w: q.width, h: q.height }; }).catch(() => null);
      if (r) rects[k] = r; else console.log('  missing', name, k);
    }
    await p.screenshot({ path: path.join(OUT, name + '.png'), fullPage: true, clip: { x: 0, y: 0, width: 390, height: h } });
    meta[name] = { h, rects }; console.log(name, Object.keys(rects).join(','));
  };
  let p = await ctx();
  await p.goto(B + '/'); await p.waitForTimeout(1500);
  await p.click('button[aria-label="Toggle menu"]'); await p.waitForTimeout(700);
  await shot(p, 'menu', { acct: 'header .overflow-y-auto >> text=My Account' });
  await p.goto(B + '/account.html'); await p.waitForTimeout(1500);
  await shot(p, 'login', { tabReg: '#tab-register', otp: '#use-otp', user: '#l-user', pass: '#l-pass', btn: '#l-btn' }, 1000);
  await p.click('#tab-register'); await p.waitForTimeout(400);
  const F = { name: '#r-name', email: '#r-email', phone: '#r-phone', user: '#r-user', pass: '#r-pass', pass2: '#r-pass2', agree: '#r-agree', btn: '#r-btn', tab: '#tab-register' };
  await shot(p, 'register', F, 1400);
  await p.fill('#r-name', 'Priya Sharma'); await p.fill('#r-email', 'priya.s@example.com'); await p.fill('#r-phone', '9876500011');
  await p.fill('#r-user', 'priya.sharma'); await p.fill('#r-pass', 'Learn2Hack9'); await p.fill('#r-pass2', 'Learn2Hack9'); await p.check('#r-agree');
  await shot(p, 'register-filled', F, 1400);
  await p.click('#r-btn'); await p.waitForTimeout(1200);
  await shot(p, 'done', { done: '#r-done' }, 900);
  // sign in, option 1: user ID + password
  p = await ctx(); await p.goto(B + '/account.html'); await p.waitForTimeout(1500);
  await p.fill('#l-user', 'priya.sharma'); await p.fill('#l-pass', 'Learn2Hack9');
  await shot(p, 'login-filled', { user: '#l-user', pass: '#l-pass', btn: '#l-btn', otp: '#use-otp' }, 1000);
  // option 2: email code
  await p.click('#use-otp'); await p.waitForTimeout(400);
  await shot(p, 'otp', { email: '#o-email', btn: '#o-btn' }, 1000);
  await p.fill('#o-email', 'priya.s@example.com'); await p.click('#o-btn'); await p.waitForTimeout(800);
  await p.fill('#o-code', '482913'); await p.waitForTimeout(600);
  // filling 6 digits submits by itself; the local copy cannot check a real code, so hide that error
  await p.evaluate(() => { const e = document.getElementById('o-err'); e.textContent = ''; e.style.display = 'none'; document.activeElement.blur(); getSelection().removeAllRanges(); });
  await shot(p, 'otp-code', { email: '#o-email', code: '#o-code', btn: '#o-btn', sent: '#o-sent' }, 1000);
  // signed in: approve the demo request in the local copy, then show Priya's dashboard
  const uf = path.join(process.env.SITE_DATA, 'users.json'), users = JSON.parse(fs.readFileSync(uf, 'utf8'));
  for (const u of users) if (u.username === 'priya.sharma') { u.status = 'approved'; u.approved_at = new Date().toISOString(); }
  fs.writeFileSync(uf, JSON.stringify(users));
  p = await ctx();
  const lr = await p.request.post(B + '/api/users.php?action=login', { data: { username: 'priya.sharma', password: 'Learn2Hack9' } });
  if (!lr.ok()) throw new Error('demo sign-in failed: ' + await lr.text());
  await p.goto(B + '/account.html'); await p.waitForTimeout(1500);
  await shot(p, 'dash', { who: '#d-name' }, 1100);
  await p.goto(B + '/ctf'); await p.waitForTimeout(1800);
  await shot(p, 'ctfhome', { free: 'text=Free access: task 1 of every room' }, 1300);
  fs.writeFileSync(path.join(OUT, 'shots.json'), JSON.stringify(meta, null, 1));
  await b.close();
})();
