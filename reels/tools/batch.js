// Render several days in parallel:  node tools/batch.js 2 10 [parallel=3]
// Day N uses crime number N from data/crimes.js and records it in data/used.json (so daily rotation continues after).
const { spawn } = require('child_process'), fs = require('fs'), path = require('path');
const { CRIMES } = require('../data/crimes.js');
// also accepts a list:  node tools/batch.js 2,3,4,8-20 [parallel=3]
const argv = process.argv.slice(2);
let days = [], par = 3;
if (/[,-]/.test(argv[0])) { for (const part of argv[0].split(',')) { const [a, b = a] = part.split('-').map(Number); for (let d = a; d <= b; d++) days.push(d); } par = +(argv[1] || 3); }
else { for (let d = +argv[0]; d <= +argv[1]; d++) days.push(d); par = +(argv[2] || 3); }
const USED = path.join(__dirname, '../data/used.json');
const queue = days;
let running = 0, failed = 0;
const start = new Date(Date.now() + 5.5 * 3600e3);
function next() {
  if (!queue.length) { if (!running) { console.log(failed ? `finished with ${failed} failure(s)` : 'ALL DONE'); process.exit(failed ? 1 : 0); } return; }
  const d = queue.shift(), c = CRIMES[d - 1]; running++;
  console.log(`start Day ${d}: ${c.id}`);
  const p = spawn('node', [path.join(__dirname, 'render.js'), c.id, String(d)], { stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, OMP_NUM_THREADS: '1', OPENBLAS_NUM_THREADS: '1' } });
  let log = ''; p.stdout.on('data', x => log += x); p.stderr.on('data', x => log += x);
  p.on('close', code => {
    running--;
    if (code) { failed++; console.log(`FAILED Day ${d}\n${log.slice(-800)}`); }
    else {
      console.log(`done Day ${d}: ${c.id}`);
      const used = fs.existsSync(USED) ? JSON.parse(fs.readFileSync(USED)) : [];
      if (!used.find(u => u.id === c.id)) { used.push({ day: d, id: c.id, rendered: new Date().toISOString().slice(0, 10) }); used.sort((a, b) => a.day - b.day); fs.writeFileSync(USED, JSON.stringify(used, null, 2)); }
    }
    next();
  });
}
for (let i = 0; i < par; i++) next();
