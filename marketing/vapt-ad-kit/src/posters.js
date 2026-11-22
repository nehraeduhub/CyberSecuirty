// Screenshots every static format of posters.html into <out dir> (PNG, 2x for print-sized A4, else 1x = exact Meta size).
// Usage: node posters.js <out dir>
const { chromium } = require('playwright');
const path = require('path'), fs = require('fs');
const OUT = process.argv[2]; fs.mkdirSync(OUT, { recursive: true });
const SIZES = { portrait: [1080, 1350, 'Feed-Post-4x5-1080x1350'], square: [1080, 1080, 'Feed-Post-Square-1080x1080'],
  story: [1080, 1920, 'Story-Poster-1080x1920'], landscape: [1200, 628, 'Link-Ad-Banner-1200x628'], cover: [1640, 624, 'Facebook-Cover-1640x624'],
  linkedin: [1584, 396, 'LinkedIn-Banner-1584x396'], a4: [1240, 1754, 'Print-Poster-A4'], thumb: [1080, 1920, 'Reel-Cover-1080x1920'],
  c1: [1080, 1080, 'Carousel-1'], c2: [1080, 1080, 'Carousel-2'], c3: [1080, 1080, 'Carousel-3'], c4: [1080, 1080, 'Carousel-4'], c5: [1080, 1080, 'Carousel-5'] };
(async () => {
  const b = await chromium.launch(); let bad = 0;
  for (const [f, [w, h, name]] of Object.entries(SIZES)) {
    const p = await b.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: f === 'a4' ? 2 : 1 });
    p.on('pageerror', (e) => { bad++; console.error(f, String(e)); });
    await p.goto('file://' + path.join(__dirname, 'posters.html') + '?f=' + f);
    await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(150);
    await p.screenshot({ path: path.join(OUT, name + '.png') }); await p.close(); console.log(name);
  }
  await b.close(); process.exitCode = bad ? 1 : 0;
})();
