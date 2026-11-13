// Captures the real CTF room page and its free task 1 from the local site copy (see PLAN.md §7).
// Usage: node tools/capture.js <topics.json> <num,num,...> <work dir> [base url]
// Writes <work>/<num>/room.png, task.png and shots.json (positions of the task cards in css px).
// The room image is cut off above the "task is locked" box, so plan prices never appear.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const [TOPICS, NUMS, WORK, BASE = 'http://127.0.0.1:8110'] = process.argv.slice(2);
const topics = JSON.parse(fs.readFileSync(TOPICS, 'utf8'));
const HIDE = '.fixed.bottom-5.right-5,#tg-fab,[aria-label*="hat" i].fixed,button.fixed{display:none!important}';
(async () => {
  const b = await chromium.launch();
  const c = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  await c.route(/^(?!http:\/\/127\.0\.0\.1)/, (r) => r.abort());
  const p = await c.newPage();
  const r = await p.request.post(BASE + '/api/users.php?action=login', { data: { username: 'arjun.m', password: 'Student12345' } });
  if (!r.ok()) throw new Error('demo login failed: ' + (await r.text()));
  for (const num of NUMS.split(',').map(Number)) {
    const t = topics.find((x) => x.num === num), dir = path.join(WORK, String(num));
    fs.mkdirSync(dir, { recursive: true });
    await p.goto(`${BASE}/ctf/${t.slug}`); await p.waitForTimeout(1800);
    await p.addStyleTag({ content: HIDE }); await p.waitForTimeout(200);
    const info = await p.evaluate((titles) => {
      const all = [...document.querySelectorAll('body *')];
      const cards = titles.map((title) => {
        const el = all.find((e) => e.children.length === 0 && e.textContent.trim() === title);
        let c = el; while (c && (c.offsetHeight < 60 || c.offsetWidth < 340)) c = c.parentElement;
        if (!c) return null; const r = c.getBoundingClientRect();
        return { x: r.x, y: r.y + scrollY, w: r.width, h: r.height };
      });
      const lock = all.find((e) => e.children.length === 0 && /This task is locked/.test(e.textContent));
      let lc = lock; while (lc && lc.offsetHeight < 120) lc = lc.parentElement;
      return { cards, cut: lc ? lc.getBoundingClientRect().top + scrollY - 8 : null, h: document.documentElement.scrollHeight };
    }, t.taskTitles);
    const last = info.cards.filter(Boolean).pop();
    const cut = Math.round(Math.min(info.cut || 1e9, last ? last.y + last.h + 24 : 1e9, info.h));
    await p.screenshot({ path: path.join(dir, 'room.png'), fullPage: true, clip: { x: 0, y: 0, width: 390, height: cut } });
    await p.goto(`${BASE}/ctf/${t.slug}?task=1`); await p.waitForTimeout(2500);
    await p.addStyleTag({ content: HIDE }); await p.waitForTimeout(200);
    // Stop above the "Your task" box: only the lesson is shown, never the question's answer field.
    const tcut = await p.evaluate(() => {
      const el = [...document.querySelectorAll('body *')].reverse().find((e) => /^\s*Your task\s*$/.test(e.textContent));
      let c = el; while (c && c.offsetHeight < 100) c = c.parentElement;
      return c ? Math.round(c.getBoundingClientRect().top + scrollY - 12) : 1300;
    });
    await p.screenshot({ path: path.join(dir, 'task.png'), fullPage: true, clip: { x: 0, y: 0, width: 390, height: Math.min(tcut, 1700) } });
    fs.writeFileSync(path.join(dir, 'shots.json'), JSON.stringify({ room: { h: cut, cards: info.cards }, task: { h: Math.min(tcut, 1700) } }, null, 1));
    console.log(num, t.slug, 'room h', cut, 'cards', info.cards.filter(Boolean).length);
  }
  await b.close();
})();
