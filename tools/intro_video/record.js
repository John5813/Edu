// Tanishtiruv videosi: haqiqiy saytni brauzerda bosib, ekrandan yozib oladi (CDP screencast).
// Har sahnaning boshlanish vaqti marks.json ga yoziladi — keyin ovoz uzunligiga moslanadi.
//   node record.js <desktop|mobile> <chiqish papkasi>
const { chromium } = require(process.env.PW_CORE || 'playwright');
const fs = require('fs'), path = require('path');
const MODE = process.argv[2] || 'desktop';
const OUT = process.argv[3];
const B = 'http://127.0.0.1:8798';
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
    toast(name, tag) { let t = document.getElementById('vtoast'); if (!t) { t = document.createElement('div'); t.id = 'vtoast'; document.documentElement.appendChild(t); }
      t.innerHTML = '<b>' + (tag || 'PPTX') + '</b> ' + name + ' &nbsp;✓'; requestAnimationFrame(() => t.classList.add('on')); setTimeout(() => t.classList.remove('on'), 3200); },
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mk); else mk();
})();`;

(async () => {
  fs.mkdirSync(path.join(OUT, 'frames'), { recursive: true });
  // Screencast faqat shu bayroq bilan yuqori zichlikda (1920×1080 / 1080×1920) yozadi.
  const b = await chromium.launch({ ...(process.env.CHROME ? { executablePath: process.env.CHROME } : {}), args: [`--force-device-scale-factor=${VIEW.dsf}`] });
  const ctx = await b.newContext({ viewport: { width: VIEW.width, height: VIEW.height }, deviceScaleFactor: VIEW.dsf, locale: 'uz-UZ',
    isMobile: false, hasTouch: false, acceptDownloads: true });   // isMobile bo'lsa screencast kichik (CSS piksel) kadr beradi
  // Sessiya cookie'si qo'yilmaydi: sayt botdagi «Ochish» havolasi orqali kiradi (haqiqiy /go oqimi).
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
  const cast = () => cdp.send('Page.startScreencast', { format: 'jpeg', quality: 90, maxWidth: W, maxHeight: H, everyNthFrame: 1 }).catch(() => {});   // allaqachon yozilayotgan bo'lsa — davom
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

  const post = (url) => page.evaluate((u) => fetch(u, { method: 'POST' }).then((r) => r.json()), url);
  const TITLE = 'Raqamli iqtisodiyot: O‘zbekiston tajribasi';

  // ── 01 Botdan saytga
  await nav('/demo/bot');
  await wait(400);
  mark('01');
  await wait(1300);
  await click('#k-pres', { after: 1400, scroll: false });
  await moveTo('.msg:last-child', 700);
  await wait(1500);
  await click('#open', { after: 0, scroll: false });
  await page.waitForURL(/#yaratish|\/$/, { timeout: 20000 });
  await page.waitForFunction(() => window.__studioReady, null, { timeout: 20000 });
  await cast();
  await wait(1200);
  await moveTo('#actions', 900);
  await wait(900);

  // ── 02 Taqdimot turi
  mark('02');
  await scrollTo('#ptypes', 'center');
  for (const t of ['info', 'modern', 'classic', '3d']) { await moveTo(`#ptypes [data-t="${t}"]`, 650); await wait(700); }
  await click('#ptypes [data-t=modern]', { after: 700 });

  // ── 03 Mavzu va manba
  mark('03');
  await click('#topic', { after: 300 });
  await typeIn('#topic', TITLE, 55);
  await page.waitForSelector('#srcs');
  await wait(700);
  await scrollTo('#st-lang', 'center');
  await moveTo('#auto-note', 700);
  await wait(700);
  await click('#srcs [data-k=text]', { after: 800 });
  await moveTo('#srcs [data-k=file]', 500);
  await moveTo('#srcs [data-k=url]', 500);
  await click('#srcs [data-k=ai]', { after: 500 });

  // ── 04 Ko'rinish
  mark('04');
  await scrollTo('#styles', 'center');
  await click('#styles [data-k=jurnal]', { after: 700 });
  await click('#colors [data-c=binafsha]', { after: 800 });
  await scrollTo('#photos', 'center');
  await moveTo('#photos [data-k=web]', 600);
  await click('#photos [data-k=mix]', { after: 600 });
  if (await page.locator('#thx .thx').count() > 1) {
    await scrollTo('#thx', 'center');
    await page.waitForSelector('#thx .thx:not(.none)', { timeout: 8000 }).catch(() => {});
    await click('#thx .thx:not(.none) >> nth=0', { after: 1200, scroll: false });
  }
  if (await page.locator('#st-anim').count()) {
    await scrollTo('#st-anim', 'center');
    await click('#st-anim [data-v="1"]', { after: 900 });
  }

  // ── 05 Slaydlar soni
  mark('05');
  await scrollTo('#c-num', 'center');
  await click('#c-minus', { after: 600 });
  await click('#c-minus', { after: 800 });
  await moveTo(MOBILE ? '.st-total' : '#s-price', 700);
  await wait(900);
  await scrollTo('#author', 'center');
  await click('#author', { after: 200, scroll: false });
  await typeIn('#author', 'Ali Valiyev', 60);
  await wait(600);
  await click('#go', { after: 0, block: 'center' });

  // ── 06 To'lov
  await page.waitForURL(/#\/wallet/, { timeout: 20000 });
  await page.waitForSelector('#pend .note', { timeout: 20000 });
  await cast();
  mark('06');
  await wait(900);
  await moveTo('#pend .note', 900);
  await wait(1400);
  await moveTo('#amount', 700);
  await wait(600);
  for (const id of ['#click-pay', '#payme-pay', '#uzum-pay']) { await moveTo(id, 550); await wait(350); }
  await moveTo('#hd-pay', 800);
  await page.evaluate(() => window.__cur.tap());
  await wait(900);
  await moveTo('#click-pay', 700);
  await page.evaluate(() => window.__cur.tap());
  await wait(300);
  const paid = await post('/demo/pay');
  await page.evaluate((s) => window.__cur.toast(s, 'Click'), (paid.paid || 0).toLocaleString('ru-RU').replace(/,/g, ' ') + ' so‘m to‘landi');
  await wait(800);

  // ── 07 Buyurtma o'zi boshlanadi
  await page.waitForSelector('#pend .note.ok, #forge-anim', { timeout: 20000 });
  mark('07');
  await page.waitForSelector('#forge-anim', { timeout: 20000 });
  await wait(4200);
  await nav('/');                       // sahifani yopib, qayta kirgandek
  await page.waitForSelector('.forge .fg-card', { timeout: 20000 });
  await moveTo('.fg-orb', 900);
  await page.waitForSelector('.forge-act a.btn', { timeout: 240000 });
  await wait(1200);

  // ── 08 Natija
  mark('08');
  await click('.forge-act a.btn >> nth=0', { after: 200 });
  await page.waitForSelector('#simg');
  await cast();
  await wait(1000);
  await click('#next', { after: 1100, scroll: false });
  await click('#next', { after: 1100, scroll: false });
  await click('#t-text', { after: 400 });
  await page.waitForSelector('.ed-frame');
  await toTop('#stage', MOBILE ? 70 : 78);
  await wait(500);
  const fr = page.frameLocator('.ed-frame');
  await click(fr.locator('[data-ed="0"]'), { scroll: false, after: 300 });
  await page.keyboard.press('End');
  await wait(200);
  await page.keyboard.press('Backspace');
  await page.keyboard.type(' va nega muhim?', { delay: 70 });
  await wait(700);
  await click('#ed-ok', { after: 300 });
  await page.waitForFunction(() => !document.querySelector('.ed-frame') && document.getElementById('simg'), null, { timeout: 60000 });
  await cast();
  await wait(1400);

  // ── 09 Diagramma va tartib
  mark('09');
  await click('#thumbs .th[data-n="5"]', { after: 900, scroll: false });
  await click('#t-chart', { after: 600 });
  await page.waitForSelector('.ed-tbl');
  await wait(600);
  await click('[data-v="0:4"]', { after: 200 });
  await page.keyboard.press('Control+A');
  await page.keyboard.type('240', { delay: 110 });
  await wait(600);
  await click('#ed-ok', { after: 300 });
  await page.waitForFunction(() => !document.querySelector('.ed-tbl') && document.getElementById('simg'), null, { timeout: 60000 });
  await cast();
  await toTop('#stage', MOBILE ? 70 : 78);
  await wait(1200);
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
  await wait(700);
  await click('#vtext', { after: 200 });
  await typeIn('#vtext', 'Doirasimon diagramma qilib ber', 55);
  await moveTo('#vnote', 700);
  await wait(1300);

  // ── 11 Yuklab olish va bot
  mark('11');
  await click('#vclose', { after: 400 });
  await scrollTo('.vtop', 'start');
  const [dl] = await Promise.all([page.waitForEvent('download').catch(() => null), click('.vtop a.btn', { after: 100, scroll: false })]);
  await page.evaluate((name) => window.__cur.toast(name), dl ? dl.suggestedFilename() : 'Taqdimot.pptx');
  await wait(2200);
  await moveTo('#tg-back', 900);
  await page.evaluate(() => window.__cur.tap());
  await wait(300);
  await nav('/demo/bot?file=' + encodeURIComponent(TITLE));
  await wait(3200);

  // ── 12 Boshqa xizmatlar
  mark('12');
  await page.evaluate(() => { try { sessionStorage.removeItem('edu_draft'); sessionStorage.removeItem('edu_live_job'); } catch (e) {}
    return fetch('/api/v1/draft', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ draft: { topic: '' } }) }); });   // qoralama tozalansin
  await nav('/');
  await page.waitForFunction(() => window.__studioReady, null, { timeout: 20000 });
  await wait(400);
  await click('#kind-chips [data-kind=course_work]', { after: 400 });
  await click('#topic', { after: 200 });
  await typeIn('#topic', 'Korxonada xarajatlarni boshqarish', 45);
  await page.waitForSelector('#st-size');
  await wait(500);
  await scrollTo('#st-size', 'center');
  await click('#st-size [data-v] >> nth=1', { after: 600 });
  await click('#extras [data-x=tables]', { after: 500 });
  await scrollTo('#kind-chips', 'center');
  for (const k of ['independent_work', 'referat', 'article', 'thesis', 'diploma_work', 'dissertatsiya']) {
    await click(`#kind-chips [data-kind=${k}]`, { after: 650, scroll: MOBILE });
  }
  await wait(500);

  // ── 13 Tayyor mavzular
  await post('/demo/pay?add=30000');    // do'kon xaridi uchun balans (videoda ko'rinmaydi)
  mark('13');
  await nav('/shop');
  await wait(1000);
  await page.evaluate(() => window.scrollTo({ top: 360, behavior: 'smooth' }));
  await wait(1200);
  await click('#grid a.card >> nth=1', { after: 300 });
  await page.waitForLoadState('networkidle'); await cast();
  await wait(1000);
  await moveTo('.buy-price', 700);
  await wait(400);
  await click('a.buy', { after: 0 });
  await page.waitForSelector('#b-go', { timeout: 20000 });
  await cast();
  await wait(1000);
  await click('#b-go', { after: 0 });
  await page.waitForURL(/#\/docs/, { timeout: 20000 });
  await wait(1200);
  await moveTo('#view', 800);
  await wait(1200);

  // ── 14 Yakun
  mark('14');
  await page.evaluate(() => { try { sessionStorage.removeItem('edu_draft'); sessionStorage.removeItem('edu_live_job'); } catch (e) {}
    return fetch('/api/v1/draft', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ draft: { topic: '' } }) }); });   // qoralama tozalansin
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
