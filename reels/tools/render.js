// Renders a finished reel: Hindi voiceover + synced animation + music/SFX + color grade,
// then exports a same-name set to reels/export/:
//    CSJ-Day01-Wedding-Invitation-APK-Fraud.mp4
//    CSJ-Day01-Wedding-Invitation-APK-Fraud-thumbnail.jpg
//    CSJ-Day01-Wedding-Invitation-APK-Fraud-caption.txt
//
//   node tools/render.js                  -> today's crime (rotation, no repeats) and marks it used
//   node tools/render.js <crime-id> [day] -> a specific crime (rotation untouched)
// Env: VOICE=rohan|pratham|priyamvada  SPEED=0.85  FPS=30  NOVOICE=1
// Own recording: put voice/<crime-id>.mp3 and it replaces the AI voice (timeline then uses default pacing).
const fs = require('fs'), path = require('path'), { spawn, execFileSync } = require('child_process');
const { chromium } = require('playwright');
const { pick, markUsed } = require('./pick');
const { CRIMES } = require('../data/crimes.js');
const V = require('../data/voice.js');

const ROOT = path.resolve(__dirname, '..');
const FPS = +(process.env.FPS || 30);
const VOICE = process.env.VOICE || 'rohan', SPEED = process.env.SPEED || '0.85';
// cinematic grade: contrast, teal shadows / warm highlights, saturation, sharpen, light film grain
const GRADE = 'eq=contrast=1.07:saturation=1.18:gamma=0.98,colorbalance=rs=-0.03:bs=0.05:rh=0.04:bh=-0.03,unsharp=5:5:0.6,noise=alls=2:allf=t,format=yuv420p';

const slug = s => s.replace(/[^A-Za-z0-9]+/g, '-').replace(/^-|-$/g, '');

(async () => {
  let [id, day] = process.argv.slice(2);
  let plan, crime;
  if (id) { plan = { id, day: +(day || 1) }; crime = CRIMES.find(c => c.id === id); if (!crime) throw new Error('unknown crime id ' + id); }
  else { plan = pick(); crime = plan.breaking ? JSON.parse(fs.readFileSync(plan.breaking, 'utf8')) : CRIMES.find(c => c.id === plan.id); }
  const dd = String(plan.day).padStart(2, '0');
  const name = `CSJ-Day${dd}-${slug(crime.tag)}`;
  const work = path.join(ROOT, 'output', '.work', name); fs.mkdirSync(work, { recursive: true });
  const exp = path.join(ROOT, 'export'); fs.mkdirSync(exp, { recursive: true });

  // 1) voiceover
  const own = ['mp3', 'm4a', 'wav', 'aac'].map(e => path.join(ROOT, 'voice', `${crime.id}.${e}`)).find(fs.existsSync);
  let durations = null;
  if (!own && !process.env.NOVOICE) {
    const linesFile = path.join(work, 'lines.json');
    fs.writeFileSync(linesFile, JSON.stringify(V.lines(crime)));
    console.log(`voice: synthesizing (${VOICE}, speed ${SPEED}) ...`);
    durations = JSON.parse(execFileSync('python3', [path.join(__dirname, 'voice.py'), linesFile, path.join(work, 'vo'), VOICE, SPEED]).toString());
  }
  const tm = V.timing(crime, durations);
  if (tm.T.end > 120) console.warn(`WARNING: reel is ${tm.T.end.toFixed(1)}s (>120). Use SPEED=0.8 or shorten lines.`);

  // 2) page
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
  page.on('pageerror', e => console.error('pageerror:', e.message));
  await page.addInitScript(([b, d]) => { if (b) window.BREAKING = b; window.DURATIONS = d; }, [plan.breaking ? crime : null, durations]);
  const url = 'file://' + path.join(ROOT, 'template/reel.html') + `?id=${encodeURIComponent(crime.id)}&day=${plan.day}&render=1`;
  await page.goto(url);
  await page.evaluate(() => window.REEL.ready);
  const meta = await page.evaluate(() => ({ duration: window.REEL.duration, events: window.REEL.events, voice: window.REEL.voice, T: window.REEL.T }));

  // 3) audio: music + sfx + voice with ducking
  const evFile = path.join(work, 'audio.json'), mixFile = path.join(work, 'mix.wav');
  const voiceClips = durations ? meta.voice.map(v => ({ t: v.t, file: path.join(work, 'vo', v.key + '.wav') })) : [];
  fs.writeFileSync(evFile, JSON.stringify({ duration: meta.duration, events: meta.events, voice: voiceClips }));
  execFileSync('python3', [path.join(__dirname, 'music.py'), evFile, mixFile], { stdio: 'inherit' });

  // 4) thumbnail (cover frame)
  const thumb = path.join(exp, `${name}-thumbnail.jpg`);
  await page.goto(url + '&thumb=1'); await page.evaluate(() => window.REEL.ready);
  await page.evaluate(() => window.REEL.seek(2.2));
  await page.screenshot({ path: thumb, type: 'jpeg', quality: 93 });
  await page.goto(url); await page.evaluate(() => window.REEL.ready);

  // 5) frames -> ffmpeg (graded)
  const silent = path.join(work, 'video.mp4');
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
    '-vf', GRADE, '-c:v', 'libx264', '-preset', 'medium', '-crf', '23', '-maxrate', '6M', '-bufsize', '12M', '-r', String(FPS), silent], { stdio: ['pipe', 'inherit', 'inherit'] });
  const total = Math.round(meta.duration * FPS), t0 = Date.now();
  for (let i = 0; i < total; i++) {
    await page.evaluate(t => window.REEL.seek(t), i / FPS);
    const buf = await page.screenshot({ type: 'jpeg', quality: 92 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % (FPS * 10) === 0) console.log(`frame ${i}/${total}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  ff.stdin.end(); await new Promise(r => ff.on('close', r));
  await browser.close();

  // 6) mux (own recording gets ducked music via sidechain)
  const final = path.join(exp, `${name}.mp4`);
  const args = ['-y', '-loglevel', 'error', '-i', silent, '-i', mixFile];
  if (own) args.push('-i', own, '-filter_complex',
    '[2:a]aresample=44100,loudnorm=I=-15,asplit=2[v1][v2];[1:a][v1]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[d];[d][v2]amix=inputs=2:normalize=0[a]',
    '-map', '0:v', '-map', '[a]');
  else args.push('-map', '0:v', '-map', '1:a');
  args.push('-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', final);
  execFileSync('ffmpeg', args, { stdio: 'inherit' });

  // 7) SEO caption + voiceover script
  const S = require('./script');
  fs.writeFileSync(path.join(exp, `${name}-caption.txt`), S.caption({ crime, name, day: plan.day, duration: meta.duration }));
  fs.writeFileSync(path.join(work, 'voiceover-script.txt'), S.script({ crime, T: meta.T, duration: meta.duration, voice: meta.voice }));
  if (!id) markUsed(plan);
  console.log(`\ndone in ${((Date.now() - t0) / 1000).toFixed(0)}s  (${meta.duration.toFixed(1)}s reel)`);
  for (const f of [final, thumb, path.join(exp, `${name}-caption.txt`)]) console.log('  ' + f);
})();
