const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const c = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  await c.route(/^(?!http:\/\/127\.0\.0\.1)/, r => r.abort());
  const p = await c.newPage();
  await p.request.post('http://127.0.0.1:8110/api/users.php?action=login', { data: { username: 'arjun.m', password: 'Student12345' } });
  for (const [u, n] of [['/ctf/firewall', 'room'], ['/ctf/firewall?task=1', 'task']]) {
    await p.goto('http://127.0.0.1:8110' + u); await p.waitForTimeout(2000);
    await p.screenshot({ path: `/tmp/claude-0/-home-user-CyberSecuirty/c5a0c81b-6225-54ab-9b54-16d18c33d48e/scratchpad/look/${n}.png`, fullPage: true });
    console.log(n, await p.evaluate(() => document.documentElement.scrollHeight));
  }
  await b.close();
})();
