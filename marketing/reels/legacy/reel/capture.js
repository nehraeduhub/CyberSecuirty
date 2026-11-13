const { chromium } = require('playwright');
const fs = require('fs');
const B = 'http://127.0.0.1:8110', OUT = process.argv[2];
const HIDE = '.fixed.bottom-5.right-5{display:none!important} #tg-fab{display:none!important}';
const meta = {};
(async () => {
  const b = await chromium.launch();
  const ctx = async (user, mobile = true) => {
    const c = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2.5, isMobile: mobile, hasTouch: mobile });
    await c.route(/^(?!http:\/\/127\.0\.0\.1)/, r => r.abort());
    const p = await c.newPage();
    if (user) await p.request.post(B + '/api/users.php?action=login', { data: { username: user, password: 'Student12345' } });
    return p;
  };
  // Full-page screenshot plus the page-y rectangles of named elements.
  const shot = async (p, name, marks = {}, wait = 1500) => {
    await p.waitForTimeout(wait);
    await p.addStyleTag({ content: HIDE });
    await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(300);
    // Measure at the size the full-page screenshot will use, so positions match the image.
    const fullH = await p.evaluate(() => document.documentElement.scrollHeight);
    await p.setViewportSize({ width: 390, height: fullH }); await p.waitForTimeout(500);
    const rects = {};
    for (const [k, sel] of Object.entries(marks)) {
      const r = await p.locator(sel).first().evaluate((el) => { const b = el.getBoundingClientRect(); return { x: b.x, y: b.y + window.scrollY, w: b.width, h: b.height }; }).catch(() => null);
      if (r) rects[k] = r;
    }
    const h = await p.evaluate(() => document.documentElement.scrollHeight);
    await p.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
    await p.setViewportSize({ width: 390, height: 844 });
    meta[name] = { h, rects }; console.log(name, h, Object.keys(rects).join(','));
  };
  let p = await ctx();
  await p.goto(B + '/'); await p.waitForTimeout(1500);
  await p.click('button[aria-label="Toggle menu"]');
  await shot(p, 'menu', { ctf: 'header .overflow-y-auto button:has-text("CTF Portal")' }, 700);
  await p.goto(B + '/account.html?next=/ctf#register');
  await shot(p, 'register', { tab: 'text=Request account', form: '#auth' });
  p = await ctx('arjun.m');
  await p.goto(B + '/ctf');
  await shot(p, 'ctfhome', { free: 'text=Free access: task 1 of every room', room: 'a[href="/ctf/fundamentals"]' });
  await p.goto(B + '/ctf/fundamentals');
  await shot(p, 'room', { t1: 'a[href*="task=1"]', t2: 'a[href*="task=2"]' });
  await p.goto(B + '/ctf/plans');
  await shot(p, 'plans', { monthly: 'text=Monthly plan', annual: 'text=Annual plan' });
  // The checkout's full-page capture comes out 414px wide under mobile emulation, so use a plain 390px window.
  p = await ctx('arjun.m', false);
  await p.goto(B + '/courses/payment.html?ctf=annual'); await p.waitForTimeout(1500);
  await p.fill('#phone', '9811100011');
  await shot(p, 'checkout', { plans: '#ctf-pick', details: '#name', coupon: '#coupon-box', cont: '#step1 button[type=submit]' }, 300);
  await p.click('#step1 button[type=submit]'); await p.waitForTimeout(800);
  await shot(p, 'upi', { qr: '#step2 .qr', paid: '#paid', amount: '#pay-amount' }, 300);
  await p.click('#paid'); await p.waitForTimeout(500);
  await p.fill('#utr', '412345678901'); await p.check('#agree'); await p.check('#agree-terms');
  await shot(p, 'utr', { utr: '#utr', submit: '#submit' }, 300);
  fs.writeFileSync(`${OUT}/meta.json`, JSON.stringify(meta, null, 1));
  await b.close();
})();
