// Tanishtiruv videosi: haqiqiy saytni brauzerda bosib, ekrandan yozib oladi (CDP screencast).
// Har sahnaning boshlanish vaqti marks.json ga yoziladi — keyin ovoz uzunligiga moslanadi.
//   node record.js <desktop|mobile> <chiqish papkasi>
const { chromium } = require(process.env.PW_CORE || 'playwright-core');
const fs = require('fs'), path = require('path');
const MODE = process.argv[2] || 'desktop';
const OUT = process.argv[3];
const B = 'http://127.0.0.1:8798';
const TOK = fs.readFileSync(path.join(__dirname, 'session.txt'), 'utf8').trim();
const MOBILE = MODE === 'mobile';
const VIEW = MOBILE ? { width: 540, height: 960, dsf: 2 } : { width: 1280, height: 720, dsf: 1.5 };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// Ekrandagi kursor va bosish to'lqini (sayt sahifasiga qo'shiladi, sahifa almashsa ham joyida qoladi).
const CURSOR = `(() => {
  const mk = () => {
    if (document.getElementById('vcur')) return;
    const st = document.createElement('style');
    st.textContent = '#vcur{position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;will-change:transform;transition:transform var(--d,700ms) cubic-bezier(.45,.05,.25,1)}' +
      '#vcur svg{display:block;filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))}' +
      '#vcur.tap::after{content:"";position:absolute;left:-14px;top:-14px;width:30px;height:30px;border-radius:50%;background:rgba(255,216,74,.55);animation:vtap .55s ease-out forwards}' +
      '@keyframes vtap{from{transform:scale(.3);opacity:1}to{transform:scale(1.9);opacity:0}}' +
      '#vtoast{position:fixed;right:18px;top:18px;z-index:2147483646;background:#202124;color:#fff;font:600 14px/1.3 system-ui,sans-serif;padding:12px 16px;border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.35);display:flex;gap:10px;align-items:center;transform:translateY(-20px);opacity:0;transition:all .35s}' +
      '#vtoast.on{transform:none;opacity:1}#vtoast b{background:#C8462B;border-radius:6px;padding:4px 6px;font-size:11px}';
    document.documentElement.appendChild(st);
    const c = document.createElement('div'); c.id = 'vcur';
    c.innerHTML = '<svg width="${MOBILE ? 20 : 24}" height="${MOBILE ? 20 : 24}" viewBox="0 0 24 24"><path d="M4 2 L4 20 L9 15.5 L12.5 22.5 L15.5 21 L12 14.2 L19 14 Z" fill="#0C1226" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.documentElement.appendChild(c);
    let p = {x: innerWidth * .62, y: innerHeight * .55};
    try { p = JSON.parse(sessionStorage.getItem('vcur')) || p; } catch (e) {}
    c.style.setProperty('--d', '0ms'); c.style.transform = 'translate(' + p.x + 'px,' + p.y + 'px)';
  };
  window.__cur = {
    move(x, y, ms) { mk(); const c = document.getElementById('vcur'); c.style.setProperty('--d', ms + 'ms'); c.style.transform = 'translate(' + x + 'px,' + y + 'px)'; try { sessionStorage.setItem('vcur', JSON.stringify({x, y})); } catch (e) {} },
    tap() { const c = document.getElementById('vcur'); c.classList.remove('tap'); void c.offsetWidth; c.classList.add('tap'); },
    toast(name) { let t = document.getElementById('vtoast'); if (!t) { t = document.createElement('div'); t.id = 'vtoast'; document.documentElement.appendChild(t); }
      t.innerHTML = '<b>PPTX</b> ' + name + ' &nbsp;✓'; requestAnimationFrame(() => t.classList.add('on')); setTimeout(() => t.classList.remove('on'), 3200); },
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mk); else mk();
})();`;

(async () => {
  fs.mkdirSync(path.join(OUT, 'frames'), { recursive: true });
  // Screencast faqat shu bayroq bilan yuqori zichlikda (1920×1080 / 1080×1920) yozadi.
  const b = await chromium.launch({ executablePath: process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: [`--force-device-scale-factor=${VIEW.dsf}`] });
  const ctx = await b.newContext({ viewport: { width: VIEW.width, height: VIEW.height }, deviceScaleFactor: VIEW.dsf, locale: 'uz-UZ',
    isMobile: false, hasTouch: false, acceptDownloads: true });   // isMobile bo'lsa screencast kichik (CSS piksel) kadr beradi
  await ctx.addCookies([{ name: 'edu_session', value: TOK, url: B }]);
  await ctx.addInitScript(`try{localStorage.setItem('edu_lang','uz')}catch(e){}`);
  await ctx.addInitScript(CURSOR);
  const page = await ctx.newPage();
  page.on('pageerror', (e) => console.log('ERR', e.message));
  const cdp = await ctx.newCDPSession(page);
  const frames = [];
  let n = 0;
  cdp.on('Page.screencastFrame', async ({ data, metadata, sessionId }) => {
    const file = `f${String(n++).padStart(6, '0')}.jpg`;
    fs.writeFileSync(path.join(OUT, 'frames', file), Buffer.from(data, 'base64'));
    frames.push({ t: metadata.timestamp, file });
    try { await cdp.send('Page.screencastFrameAck', { sessionId }); } catch (e) {}
  });
  const W = Math.round(VIEW.width * VIEW.dsf), H = Math.round(VIEW.height * VIEW.dsf);
  const cast = () => cdp.send('Page.startScreencast', { format: 'jpeg', quality: 90, maxWidth: W, maxHeight: H, everyNthFrame: 1 });
  const marks = [];
  const mark = (id) => { marks.push({ id, t: Date.now() / 1000 }); console.log('sahna', id); };

  // ── yordamchilar
  const nav = async (url) => { await page.goto(B + url, { waitUntil: 'networkidle' }); await cast(); await wait(300); };
  const loc = (sel) => (typeof sel === 'string' ? page.locator(sel).first() : sel);
  async function scrollTo(sel, block = 'center') {
    await loc(sel).evaluate((el, block) => el.scrollIntoView({ behavior: 'smooth', block }), block);
    await wait(900);
  }
  async function toTop(sel, offset = 78) {
    await loc(sel).evaluate((el, off) => window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - off, behavior: 'smooth' }), offset);
    await wait(900);
  }
  async function moveTo(sel, ms = 750) {
    const box = await loc(sel).boundingBox();
    if (!box) return;
    await page.evaluate(([x, y, ms]) => window.__cur && window.__cur.move(x, y, ms), [box.x + box.width / 2, box.y + box.height / 2, ms]);
    await wait(ms + 80);
  }
  async function click(sel, opts = {}) {
    if (opts.scroll !== false) {
      const box = await loc(sel).boundingBox();
      if (!box || box.y < 70 || box.y + box.height > VIEW.height - 10) await scrollTo(sel, opts.block || 'center');
    }
    await moveTo(sel, opts.ms || 700);
    await page.evaluate(() => window.__cur && window.__cur.tap());
    await wait(120);
    await loc(sel).click(opts.clickOpts || {});
    await wait(opts.after ?? 450);
  }
  async function typeIn(sel, text, delay = 55) { await loc(sel).pressSequentially(text, { delay }); }

  // ── 01 Kirish
  await nav('/');
  await wait(400);
  mark('01');
  await wait(2200);
  await moveTo('.fan', 1100);
  await wait(900);
  await moveTo('#topic', 1000);
  await wait(1200);

  // ── 02 Mavzu
  mark('02');
  await click('#kind-chips [data-kind=premium_presentation]', { after: 500 });
  await click('#topic', { after: 300 });
  await typeIn('#topic', 'Raqamli iqtisodiyot: O‘zbekiston tajribasi', 60);
  await wait(1800);

  // ── 03 Sozlamalar
  mark('03');
  await scrollTo('#st-lang', 'center');
  await moveTo('#auto-note', 800);
  await wait(1200);
  await click('#srcs [data-k=text]', { after: 900 });
  await moveTo('#srcs [data-k=file]', 600);
  await moveTo('#srcs [data-k=url]', 600);
  await click('#srcs [data-k=ai]', { after: 600 });
  await scrollTo('#styles', 'center');
  await click('#styles [data-k=jurnal]', { after: 700 });
  await click('#styles [data-k=qorongu]', { after: 900 });
  await click("#themes [data-k='binafsha']", { after: 900 });

  // ── 04 Slaydlar soni
  mark('04');
  await scrollTo('#c-num', 'center');
  await click('#c-minus', { after: 700 });
  await click('#c-minus', { after: 900 });
  await moveTo(MOBILE ? '.st-total' : '#s-price', 800);
  await wait(1200);
  await scrollTo('#author', 'center');
  await moveTo('#author', 700);
  await wait(1500);

  // ── 05 Yaratish
  mark('05');
  await click('#go', { after: 300, block: 'center' });
  await page.waitForSelector('.forge .fg-card', { timeout: 20000 });
  await moveTo('.fg-orb', 900);
  await page.waitForSelector('.forge-act a.btn', { timeout: 240000 });
  await wait(1500);

  // ── 06 Natija
  mark('06');
  await click('.forge-act a.btn >> nth=0', { after: 200 });
  await page.waitForSelector('#simg');
  await cast();
  await wait(1200);
  await click('#next', { after: 1300, scroll: false });
  await click('#next', { after: 1400, scroll: false });

  // ── 07 Matnni tahrirlash
  mark('07');
  await click('#t-text', { after: 400 });
  await page.waitForSelector('.ed-frame');
  await toTop('#stage', MOBILE ? 70 : 78);
  await wait(600);
  const fr = page.frameLocator('.ed-frame');
  await click(fr.locator('[data-ed="0"]'), { scroll: false, after: 300 });
  await page.keyboard.press('End');
  await wait(200);
  for (let i = 0; i < 1; i++) await page.keyboard.press('Backspace');
  await page.keyboard.type(' va nega muhim?', { delay: 70 });
  await wait(900);
  await click('#ed-ok', { after: 300 });
  await page.waitForFunction(() => !document.querySelector('.ed-frame') && document.getElementById('simg'), null, { timeout: 60000 });
  await cast();
  await wait(1800);

  // ── 08 Diagramma
  mark('08');
  await click('#thumbs .th[data-n="5"]', { after: 1000, scroll: false });
  await click('#t-chart', { after: 600 });
  await page.waitForSelector('.ed-tbl');
  await wait(700);
  await click('[data-v="0:4"]', { after: 200 });
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
  await page.keyboard.type('240', { delay: 110 });
  await wait(700);
  await click('#ed-ok', { after: 300 });
  await page.waitForFunction(() => !document.querySelector('.ed-tbl') && document.getElementById('simg'), null, { timeout: 60000 });
  await cast();
  await wait(600);
  await toTop('#stage', MOBILE ? 70 : 78);
  await wait(1600);

  // ── 09 Tartib
  mark('09');
  await click('#t-order', { after: 700 });
  await page.waitForSelector('.ed-list');
  await click('.ed-acts [data-a="down"][data-i="1"]', { after: 700 });
  await click('.ed-acts [data-a="dup"][data-i="3"]', { after: 700 });
  await click('#ed-x', { after: 500 });

  // ── 10 AI bilan o'zgartirish
  mark('10');
  await click('#thumbs .th[data-n="6"]', { after: 700, scroll: false });
  await click('#edit', { after: 900 });
  await moveTo('#vprompts', 800);
  await wait(800);
  await click('#vtext', { after: 200 });
  await typeIn('#vtext', 'Doirasimon diagramma qilib ber', 55);
  await moveTo('#vnote', 700);
  await wait(1500);

  // ── 11 Yuklab olish
  mark('11');
  await click('#vclose', { after: 400 });
  await scrollTo('.vtop', 'start');
  const [dl] = await Promise.all([page.waitForEvent('download').catch(() => null), click('.vtop a.btn', { after: 100, scroll: false })]);
  await page.evaluate((name) => window.__cur.toast(name), dl ? dl.suggestedFilename() : 'Taqdimot.pptx');
  await wait(2600);

  // ── 12 Boshqa xizmatlar
  mark('12');
  await nav('/');
  await wait(500);
  await click('#kind-chips [data-kind=course_work]', { after: 400 });
  await click('#topic', { after: 200 });
  await typeIn('#topic', 'Korxonada xarajatlarni boshqarish', 45);
  await page.waitForSelector('#st-size');
  await wait(600);
  await scrollTo('#st-size', 'center');
  await click('#st-size [data-v] >> nth=1', { after: 700 });
  await click('#extras [data-x=tables]', { after: 600 });
  await scrollTo('#kind-chips', 'center');
  for (const k of ['independent_work', 'referat', 'article', 'thesis', 'diploma_work', 'dissertatsiya']) {
    await click(`#kind-chips [data-kind=${k}]`, { after: 750, scroll: MOBILE });
  }
  await wait(600);

  // ── 13 Tayyor mavzular
  mark('13');
  await nav('/shop');
  await wait(1200);
  await page.evaluate(() => window.scrollTo({ top: 360, behavior: 'smooth' }));
  await wait(1400);
  await click('#grid a.card >> nth=1', { after: 300 });
  await page.waitForLoadState('networkidle'); await cast();
  await wait(1200);
  await moveTo('.buy-price', 800);
  await wait(500);
  await moveTo('.buy', 700);
  await wait(900);
  await page.evaluate(() => window.scrollTo({ top: 520, behavior: 'smooth' }));
  await wait(1800);

  // ── 14 Yakun
  mark('14');
  await page.evaluate(() => { try { sessionStorage.removeItem('edu_draft'); sessionStorage.removeItem('edu_live_job'); } catch (e) {} });
  await nav('/');
  await wait(600);
  await moveTo('#topic', 1100);
  await wait(3000);
  mark('end');

  await cdp.send('Page.stopScreencast');
  await wait(300);
  fs.writeFileSync(path.join(OUT, 'frames.json'), JSON.stringify(frames));
  fs.writeFileSync(path.join(OUT, 'marks.json'), JSON.stringify(marks));
  console.log('kadrlar:', frames.length, 'o‘lcham:', W, 'x', H);
  await b.close();
})();
