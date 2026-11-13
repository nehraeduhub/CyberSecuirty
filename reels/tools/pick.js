// Picks today's crime without repeats.
//  - data/breaking/YYYY-MM-DD.json (same fields as a crimes.js entry) wins if present: a new crime seen in Rajasthan today.
//  - otherwise the next crime from data/crimes.js that is not in data/used.json.
//  - when every crime has been used, the cycle restarts (add new crimes to avoid that).
const fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '..');
const { CRIMES } = require(path.join(ROOT, 'data/crimes.js'));
const USED = path.join(ROOT, 'data/used.json');

function today() {
  const d = new Date(Date.now() + 5.5 * 3600e3); // IST
  return d.toISOString().slice(0, 10);
}
function loadUsed() { try { return JSON.parse(fs.readFileSync(USED, 'utf8')); } catch { return []; } }

function pick(date = today()) {
  const used = loadUsed();
  const already = used.find(u => u.date === date);
  const breakingFile = path.join(ROOT, 'data/breaking', date + '.json');
  if (fs.existsSync(breakingFile)) return { date, id: 'breaking-' + date, breaking: breakingFile, day: already ? already.day : used.length + 1 };
  if (already) return { date, id: already.id, day: already.day };
  const usedIds = new Set(used.map(u => u.id));
  let next = CRIMES.find(c => !usedIds.has(c.id));
  if (!next) { // full cycle done: start over from the least recently used
    const cycle = Math.floor(used.length / CRIMES.length);
    next = CRIMES[used.length % CRIMES.length];
    console.warn(`All ${CRIMES.length} crimes used ${cycle} time(s). Add new ones in data/crimes.js.`);
  }
  return { date, id: next.id, day: used.length + 1 };
}
function markUsed(p) {
  const used = loadUsed();
  if (!used.find(u => u.date === p.date)) { used.push({ date: p.date, id: p.id, day: p.day }); fs.writeFileSync(USED, JSON.stringify(used, null, 2)); }
}
module.exports = { pick, markUsed, today };
if (require.main === module) console.log(pick(process.argv[2]));
