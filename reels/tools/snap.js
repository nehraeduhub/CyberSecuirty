// Usage: node tools/snap.js <id> <outdir> t1 t2 ...  -> PNG stills for quick checks
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const [id, out, ...ts] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  p.on('console', m => m.type() === 'error' && console.log('console:', m.text()));
  p.on('pageerror', e => console.log('pageerror:', e.message));
  await p.goto('file://' + path.resolve(__dirname, '../template/reel.html') + `?id=${id}&render=1`);
  await p.evaluate(() => window.REEL.ready);
  for (const t of ts) { await p.evaluate(t => window.REEL.seek(+t), t); await p.screenshot({ path: `${out}/t${t}.png` }); }
  await b.close();
})();
