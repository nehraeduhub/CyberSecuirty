// Screens for the brand reels B1 (website tour), B3 (handbooks), B4 (Cyber Safety Portal), B5 (training),
// from the local site copy. Every ₹ amount is hidden (no prices in reels). Also copies the 43 handbook covers
// (cover-01 … cover-43) for the cover wall. Usage: SITE=<website-classic dir> node tools/capture-brand.js <out dir> [base url]
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const [OUT, B = 'http://127.0.0.1:8110'] = process.argv.slice(2);
const SITE = process.env.SITE || path.resolve(__dirname, '..', '..', '..');
const HIDE = '.fixed.bottom-5.right-5,#tg-fab,button.fixed{display:none!important}';
const meta = {};
const PAGES = [
  // name, url, capture height (css px), marks {key: selector}, optional action before the shot
  ['home', '/', 1500, { hero: 'main h1, main h2' }],
  ['menu', '/', 844, { ctf: 'header .overflow-y-auto >> text=CTF Portal', pdf: 'header .overflow-y-auto >> text=PDF Store', training: 'header .overflow-y-auto >> text=Training Programs', helpline: 'header .overflow-y-auto >> text=Cyber fraud helpline' },
    async (p) => { await p.click('button[aria-label="Toggle menu"]'); await p.waitForTimeout(700); }],
  ['training', '/training', 4300, { first: ['text=Learn Web Server & Web Hosting', 'card'], sophos: ['text=Learn Sophos Firewall', 'card'], awareness: ['text=Cyber Awareness Session Booking', 'card'] }],
  ['course', '/courses/sophos-firewall.html', 1700, { stats: 'text=6 Weeks', learn: 'text=WHAT YOU WILL LEARN' }],
  ['checkout', '/courses/payment.html?course=Learn%20Sophos%20Firewall&amount=499', 1600, { coupon: '#coupon-box', apply: '#coupon-apply', name: '#name' }],
  ['ctfhome', '/ctf', 1400, { stats: 'text=ROOMS', create: 'text=Create a student account', only: 'text=Students only' }],
  ['pdfstore', '/pdf-store', 1900, { look: ['text=/^\\W*Look inside$/', 'card'], title: 'text=Cyber Security Handbook Series' }],
  ['book', '/pdf-store/firewall-security', 2100, { cover: 'main img', inside: ["text=What’s inside", 'card'], upi: 'text=1. Pay by UPI', dl: 'text=3. Download your PDF' }],
  ['portal', '/cyber-portal', 4400, { stats: 'text=150+', mobile: ['text=Mobile Number Lookup', 'card'], email: ['text=Email Breach Check', 'card'], pass: ['text=Password Breach Check', 'card'], govt: 'text=Government Services & Resources', deepfake: ['text=Photo Forensics & Deepfake Check', 'card'] }],
  ['support', '/cyber-crime-support', 1800, { form: 'text=Fill the Form', type: 'select', wa: 'text=SEND VIA WHATSAPP' }],
  ['threat', '/threat-intel', 1600, { stats: 'text=Active Threats' }],
  ['events', '/events', 1600, { next: 'text=NEXT EVENT' }],
];
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  const c = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  await c.route(/^(?!http:\/\/127\.0\.0\.1)/, (r) => r.abort());
  const p = await c.newPage();
  for (const [name, url, h, marks, act] of PAGES) {
    await p.goto(B + url); await p.waitForTimeout(2200);
    if (act) await act(p);
    await p.addStyleTag({ content: HIDE });
    if (!act) {   // scroll through once so scroll-reveal sections are shown, then back to the top
      for (let y = 0; y < h; y += 350) { await p.evaluate((y) => window.scrollTo(0, y), y); await p.waitForTimeout(120); }
      await p.waitForTimeout(600); await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(400);
    }
    const hidden = await p.evaluate(() => { let n = 0;
      for (const e of document.querySelectorAll('body *')) if (/₹/.test(e.textContent) && e.offsetHeight > 0 && e.offsetHeight < 70) { e.style.visibility = 'hidden'; n++; }
      for (const e of document.querySelectorAll('.qr, img[src*="qr" i]')) { e.style.filter = 'blur(12px)'; n++; }   // payment QR never readable
      return n; });
    const rects = {};
    for (const [k, m] of Object.entries(marks)) {
      const [sel, mode] = Array.isArray(m) ? m : [m, ''];   // 'card': grow to the surrounding card
      const r = await p.locator(sel).first().evaluate((el, mode) => {
        const need = mode === 'card' ? [250, 70] : [120, 0];
        let c = el; while (c.parentElement && (c.offsetWidth < need[0] || c.offsetHeight < need[1])) c = c.parentElement;
        const q = c.getBoundingClientRect(); return { x: q.x, y: q.y + scrollY, w: q.width, h: q.height }; }, mode).catch(() => null);
      if (r) rects[k] = r; else console.log('  missing', name, k);
    }
    const full = await p.evaluate(() => document.documentElement.scrollHeight), hh = Math.min(h, full);
    await p.screenshot({ path: path.join(OUT, name + '.png'), fullPage: !act, clip: { x: 0, y: act ? 0 : 0, width: 390, height: act ? 844 : hh } });
    meta[name] = { h: act ? 844 : hh, rects }; console.log(name, hh, Object.keys(rects).join(','), hidden ? `(hid ${hidden})` : '');
  }
  const books = JSON.parse(fs.readFileSync(path.join(SITE, 'public/api/store-books.json'), 'utf8')).sort((a, b) => a.series - b.series);
  for (const bk of books) {
    const n = 'cover-' + String(bk.series).padStart(2, '0');
    fs.copyFileSync(path.join(SITE, 'public', bk.cover), path.join(OUT, n + '.png')); meta[n] = { h: 0, rects: {} };
  }
  fs.writeFileSync(path.join(OUT, 'shots.json'), JSON.stringify(meta, null, 1));
  await b.close();
})();
