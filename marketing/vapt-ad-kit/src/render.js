// Renders the VAPT reel (reel.html) with Playwright, 30 fps JPEG frames.
// Usage: node render.js <work dir with timeline.json> <frames dir> [from,to | t1;t2;... | cover <file.jpg>]
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const [WORK, OUT, arg, coverFile] = process.argv.slice(2);
const FPS = 30, SRC = __dirname;
(async () => {
  const T = JSON.parse(fs.readFileSync(path.join(WORK, 'timeline.json'), 'utf8'));
  const SUBS = JSON.parse(fs.readFileSync(path.join(SRC, 'subs.json'), 'utf8'));
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  const errs = []; p.on('pageerror', (e) => errs.push(String(e)));
  await p.addInitScript(([t, s]) => { window.__T = t; window.__S = s; }, [T, SUBS]);
  await p.goto('file://' + path.join(SRC, 'reel.html'));
  await p.evaluate(() => { T = window.__T; SUBS = window.__S; window.ready(); });
  await p.evaluate(() => document.fonts.ready);
  fs.mkdirSync(OUT, { recursive: true });
  if (arg === 'cover') {
    await p.evaluate(() => window.renderCover()); await p.waitForTimeout(200);
    await p.screenshot({ path: coverFile, type: 'jpeg', quality: 92 });
  } else if (arg && arg.includes(';')) {
    for (const t of arg.split(';').map(Number)) {
      await p.evaluate((t) => window.render(t), t);
      await p.screenshot({ path: path.join(OUT, `t${String(t).replace('.', '_')}.jpg`), type: 'jpeg', quality: 80 });
    }
  } else {
    const n = Math.ceil(T.total * FPS), [from, to] = arg ? arg.split(',').map(Number) : [0, n];
    for (let i = from; i < Math.min(to, n); i++) {
      await p.evaluate((t) => window.render(t), i / FPS);
      await p.screenshot({ path: path.join(OUT, `f${String(i).padStart(5, '0')}.jpg`), type: 'jpeg', quality: 90 });
    }
  }
  if (errs.length) { console.error('PAGE ERRORS:', errs.slice(0, 5).join('\n')); process.exitCode = 1; }
  await b.close();
})();
