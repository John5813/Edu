// HTML sahifalarni 960x540 JPEG qiladi: shot_dir.js <html ildizi> <jpg ildizi>
const { chromium } = require(process.env.PW_CORE || 'playwright-core');
const fs = require('fs'), path = require('path');
const [src, dst] = process.argv.slice(2);
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
  const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 0.5 });
  for (const code of fs.readdirSync(src)) {
    fs.mkdirSync(path.join(dst, code), { recursive: true });
    for (const f of fs.readdirSync(path.join(src, code))) {
      const p = await ctx.newPage();
      await p.setContent(fs.readFileSync(path.join(src, code, f), 'utf8'), { waitUntil: 'load' });
      await p.waitForTimeout(250);
      await p.screenshot({ path: path.join(dst, code, f.replace('.html', '.jpg')), type: 'jpeg', quality: 84 });
      await p.close();
    }
    fs.copyFileSync(path.join(dst, code, '1.jpg'), path.join(dst, code, 'thumb.jpg'));
  }
  await b.close();
})();
