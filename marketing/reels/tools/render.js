// Renders a topic reel frame by frame with Playwright (template/topic.html, 30 fps JPEG).
// Usage: node tools/render.js <work/NN> <frames dir> [from,to | t1;t2;... | cover <file.jpg>]
//   from,to  render only frames [from, to) — build.sh runs a few of these in parallel
//   t1;t2    preview stills at those seconds (t5_0.jpg …)
//   cover    the 1080x1920 thumbnail
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const [WORK, OUT, arg, coverFile] = process.argv.slice(2);
const FPS = 30;

(async () => {
  const data = JSON.parse(fs.readFileSync(path.join(WORK, 'data.json'), 'utf8'));
  const w = path.resolve(WORK), url = (f) => 'file://' + path.join(w, f);
  if (data.guide) {   // guide reel: screenshots from tools/capture-<x>.js in work/<guide.shots>/
    const sd = path.resolve(WORK, '..', data.guide.shots), shots = JSON.parse(fs.readFileSync(path.join(sd, 'shots.json'), 'utf8'));
    data.assets = { logo: url('logo.png'), shots, img: Object.fromEntries(Object.keys(shots).map((k) => [k, 'file://' + path.join(sd, k + '.png')])),
      refcover: fs.existsSync(path.join(WORK, 'refcover.png')) ? url('refcover.png') : null };
  } else data.assets = { cover: url('cover.png'), feature: url('feature.png'), room: url('room.png'), task: url('task.png'), logo: url('logo.png'),
    refcover: fs.existsSync(path.join(WORK, 'refcover.png')) ? url('refcover.png') : null,
    shots: JSON.parse(fs.readFileSync(path.join(WORK, 'shots.json'), 'utf8')) };
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  await p.addInitScript((d) => { window.DATA = d; }, data);
  await p.goto('file://' + path.join(__dirname, '..', 'template', data.guide ? 'guide.html' : 'topic.html'));
  await p.evaluate(() => window.ready());
  await p.evaluate(() => document.fonts.ready);
  fs.mkdirSync(OUT, { recursive: true });
  if (arg === 'cover') {
    await p.evaluate(() => window.renderCover()); await p.waitForTimeout(300);
    await p.screenshot({ path: coverFile, type: 'jpeg', quality: 92 });
  } else if (arg && arg.includes(';')) {
    for (const t of arg.split(';').map(Number)) {
      await p.evaluate((t) => window.render(t), t);
      await p.screenshot({ path: path.join(OUT, `t${String(t).replace('.', '_')}.jpg`), type: 'jpeg', quality: 85 });
    }
  } else {
    const n = Math.ceil(data.total * FPS);
    const [from, to] = arg ? arg.split(',').map(Number) : [0, n];
    for (let i = from; i < Math.min(to, n); i++) {
      await p.evaluate((t) => window.render(t), i / FPS);
      await p.screenshot({ path: path.join(OUT, `f${String(i).padStart(5, '0')}.jpg`), type: 'jpeg', quality: 92 });
      if ((i - from) % 300 === 299) console.log(path.basename(WORK), 'frame', i + 1, '/', n);
    }
  }
  await b.close();
})();
