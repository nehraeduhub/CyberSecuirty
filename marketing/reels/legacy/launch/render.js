const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const DIR = process.argv[2], OUT = process.argv[3], times = process.argv[4] ? process.argv[4].split(',').map(Number) : null;
const FPS = 30, DUR = 60;
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  await p.goto('file://' + path.join(DIR, 'launch.html'));
  await p.evaluate(() => window.ready());
  fs.mkdirSync(OUT, { recursive: true });
  const list = times || Array.from({ length: FPS * DUR }, (_, i) => i / FPS);
  let n = 0;
  for (const t of list) {
    await p.evaluate((t) => window.render(t), t);
    const name = times ? `t${String(t).replace('.', '_')}.jpg` : `f${String(n).padStart(5, '0')}.jpg`;
    await p.screenshot({ path: path.join(OUT, name), type: 'jpeg', quality: 92 });
    n++; if (!times && n % 300 === 0) console.log('frame', n);
  }
  await b.close();
})();
