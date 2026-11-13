const { chromium } = require('playwright');
const B = 'http://127.0.0.1:8110', OUT = process.argv[2];
const HIDE = '.fixed.bottom-5.right-5{display:none!important} #tg-fab{display:none!important}';
(async () => {
  const b = await chromium.launch();
  const c = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1.5 });
  await c.route(/^(?!http:\/\/127\.0\.0\.1)/, r => r.abort());
  const p = await c.newPage();
  await p.request.post(B + '/api/users.php?action=login', { data: { username: 'arjun.m', password: 'Student12345' } });
  for (const [name, url] of [['home', '/'], ['ctf', '/ctf'], ['training', '/training'], ['products', '/products'], ['pdf', '/pdf-store'], ['portal', '/cyber-portal']]) {
    await p.goto(B + url); await p.waitForTimeout(2500);
    await p.addStyleTag({ content: HIDE }); await p.waitForTimeout(300);
    await p.screenshot({ path: `${OUT}/${name}.jpg`, type: 'jpeg', quality: 90 });
    console.log(name);
  }
  await b.close();
})();
