// Renders a reel to MP4 (1080x1920, 30fps) with synced music/SFX and optional voiceover.
//
//   node tools/render.js                 -> today's crime (rotation, no repeats) and marks it used
//   node tools/render.js <crime-id> [day] -> a specific crime (does not touch the rotation)
//   FPS=30 PREVIEW=1 node tools/render.js -> PREVIEW=1 renders at half size for a fast check
//
// Voiceover: put voice/<crime-id>.mp3 (or .m4a/.wav) and it is mixed over the music automatically.
const fs = require('fs'), path = require('path'), { spawn, execFileSync } = require('child_process');
const { chromium } = require('playwright');
const { pick, markUsed } = require('./pick');

const ROOT = path.resolve(__dirname, '..');
const FPS = +(process.env.FPS || 30);
const PREVIEW = !!process.env.PREVIEW;

(async () => {
  let [id, day] = process.argv.slice(2);
  let plan, breaking = null;
  if (id) plan = { id, day: +(day || 1) };
  else {
    plan = pick();
    if (plan.breaking) breaking = JSON.parse(fs.readFileSync(plan.breaking, 'utf8'));
  }
  const outDir = path.join(ROOT, 'output'); fs.mkdirSync(outDir, { recursive: true });
  const stamp = plan.date ? plan.date + '_' : '';
  const base = path.join(outDir, `${stamp}day${String(plan.day).padStart(2, '0')}_${plan.id}`);

  const browser = await chromium.launch();
  const scale = PREVIEW ? 0.5 : 1;
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: scale });
  page.on('pageerror', e => console.error('pageerror:', e.message));
  if (breaking) await page.addInitScript(b => { window.BREAKING = b; }, breaking);
  const url = 'file://' + path.join(ROOT, 'template/reel.html') + `?id=${encodeURIComponent(plan.id)}&day=${plan.day}&render=1`;
  await page.goto(url);
  await page.evaluate(() => window.REEL.ready);
  const meta = await page.evaluate(() => ({ duration: window.REEL.duration, events: window.REEL.events, crime: window.REEL.crime, T: window.REEL.T }));

  // audio
  const evFile = base + '.events.json', musicFile = base + '.music.wav';
  fs.writeFileSync(evFile, JSON.stringify({ duration: meta.duration, events: meta.events }));
  execFileSync('python3', [path.join(__dirname, 'music.py'), evFile, musicFile], { stdio: 'inherit' });

  // video frames -> ffmpeg
  const silent = base + '.video.mp4';
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
    '-vf', 'scale=1080:1920:flags=lanczos,format=yuv420p', '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-r', String(FPS), silent], { stdio: ['pipe', 'inherit', 'inherit'] });
  const total = Math.round(meta.duration * FPS), t0 = Date.now();
  for (let i = 0; i < total; i++) {
    await page.evaluate(t => window.REEL.seek(t), i / FPS);
    const buf = await page.screenshot({ type: 'jpeg', quality: 92 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % (FPS * 5) === 0) process.stdout.write(`\rframe ${i}/${total}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  ff.stdin.end(); await new Promise(r => ff.on('close', r));
  await browser.close();
  console.log(`\nframes done in ${((Date.now() - t0) / 1000).toFixed(0)}s`);

  // mux (+ optional voiceover with music ducking)
  const voice = ['mp3', 'm4a', 'wav', 'aac'].map(e => path.join(ROOT, 'voice', `${plan.id}.${e}`)).find(fs.existsSync);
  const final = base + '.mp4';
  const args = ['-y', '-loglevel', 'error', '-i', silent, '-i', musicFile];
  if (voice) {
    args.push('-i', voice, '-filter_complex',
      '[2:a]aresample=44100,volume=1.6,asplit=2[v1][v2];[1:a][v1]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck];[duck][v2]amix=inputs=2:normalize=0[a]',
      '-map', '0:v', '-map', '[a]');
  } else args.push('-map', '0:v', '-map', '1:a');
  args.push('-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', final);
  execFileSync('ffmpeg', args, { stdio: 'inherit' });
  [silent, evFile, musicFile].forEach(f => fs.unlinkSync(f));

  fs.writeFileSync(base + '.txt', require('./script').script(meta));
  if (!id) markUsed(plan);
  console.log('reel   :', final, voice ? '(with voiceover)' : '(music only)');
  console.log('script :', base + '.txt');
})();
