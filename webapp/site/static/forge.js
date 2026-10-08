/* Edufayl: «Slaydlar ustaxonasi» — buyurtma tayyorlanayotganda ko'rsatiladigan animatsiya.
 *
 * Bezak emas, haqiqiy jarayonning ko'rinishi: kartochkalar soni — mijoz tanlagan slaydlar soni, sarlavhalar —
 * generator tuzgan reja (`job.live.plan`), to'lgan kartochkalar — yozib bo'lingan slaydlar (`job.live.done`).
 * Reja hali kelmagan bo'lsa, kartochkalar sim-karkas holida turadi va foiz bo'yicha to'ladi.
 *
 *   const f = Edu.forge(el, {topic, mode: 'slides' | 'pages', count});
 *   f.update(job);            // har so'rovda (status, stage, progress, live)
 *   await f.finish('PPTX');   // kartochkalar bitta faylga yig'iladi
 *   f.stop();
 */
(function () {
  'use strict';
  const Edu = (window.Edu = window.Edu || {});
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const tr = (t) => (Edu.tr ? Edu.tr(t) : t);
  const REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Reja kategoriyasi → kartochka ichidagi sxematik ko'rinish
  const SKEL = {
    muqova: 'cover', reja: 'plan', matn_rasm: 'pic', ikki_ustun: 'split', korsatkichlar: 'kpi', jarayon: 'flow',
    vaqt_oqi: 'time', qiyoslash: 'split', jadval: 'table', diagramma: 'chart', tuzilma: 'tree', iqtibos: 'quote',
    formula: 'formula', misol: 'list', kartalar: 'cards', yakun: 'end',
  };
  // Hujjatning tuzilishi (turiga qarab). Varaqlar soni oldindan ma'lum emas: kartochka — bo'lim, varaq emas.
  const BOB = ['Titul varaq', 'Mundarija', 'Kirish qismi', '1-bob', '1-bob', '2-bob', '2-bob', '3-bob', 'Xulosa', 'Adabiyotlar'];
  const PAGE_PARTS = {
    course_work: BOB, diploma_work: BOB, bitiruv_ishi: BOB, dissertatsiya: BOB,
    independent_work: ['Titul varaq', 'Mundarija', 'Kirish qismi', 'Asosiy qism', 'Asosiy qism', 'Asosiy qism', 'Asosiy qism', 'Xulosa', 'Adabiyotlar'],
    referat: ['Titul varaq', 'Mundarija', 'Kirish qismi', 'Asosiy qism', 'Asosiy qism', 'Asosiy qism', 'Asosiy qism', 'Xulosa', 'Adabiyotlar'],
    article: ['Annotatsiya', 'Kirish qismi', 'Usullar', 'Natijalar', 'Muhokama', 'Xulosa', 'Adabiyotlar'],
    thesis: ['Sarlavha', 'Kirish qismi', 'Asosiy qism', 'Xulosa', 'Adabiyotlar'],
  };

  function skel(kind) {
    const l = (w) => `<i class="l" style="width:${w}%"></i>`;
    switch (kind) {
      case 'cover': return `<div class="sk cover">${l(70)}${l(46)}</div>`;
      case 'plan': return `<div class="sk plan">${[1, 2, 3, 4].map((n) => `<span><b>0${n}</b>${l(60 + (n % 2) * 20)}</span>`).join('')}</div>`;
      case 'pic': return `<div class="sk pic"><div>${l(90)}${l(80)}${l(86)}${l(60)}</div><em></em></div>`;
      case 'split': return `<div class="sk split"><div>${l(90)}${l(70)}${l(80)}</div><div>${l(90)}${l(70)}${l(80)}</div></div>`;
      case 'kpi': return `<div class="sk kpi">${[0, 1, 2].map(() => `<span><b></b>${l(70)}</span>`).join('')}</div>`;
      case 'flow': return `<div class="sk flow"><span></span><i>›</i><span></span><i>›</i><span></span></div>`;
      case 'time': return `<div class="sk time"><span></span><span></span><span></span><span></span></div>`;
      case 'table': return `<div class="sk table">${Array(9).fill('<span></span>').join('')}</div>`;
      case 'chart': return `<div class="sk chart">${[38, 62, 48, 84, 70].map((h) => `<b style="--h:${h}%"></b>`).join('')}</div>`;
      case 'tree': return `<div class="sk tree"><span></span><div><span></span><span></span><span></span></div></div>`;
      case 'quote': return `<div class="sk quote"><b>“</b>${l(80)}${l(56)}</div>`;
      case 'formula': return `<div class="sk formula"><b>ƒ(x)</b>${l(60)}</div>`;
      case 'list': return `<div class="sk list">${[86, 72, 80, 64].map((w) => `<span><i class="d"></i>${l(w)}</span>`).join('')}</div>`;
      case 'end': return `<div class="sk end">${l(50)}${l(70)}</div>`;
      case 'page': return `<div class="sk page">${[90, 96, 88, 94, 70, 92, 85, 60].map(l).join('')}</div>`;
      default: return `<div class="sk cards"><span></span><span></span><span></span></div>`;
    }
  }

  // Fondagi yulduzlar turkumi va mavzudan faol kartochkaga uchadigan uchqunlar (Canvas 2D, yengil).
  function sky(canvas, root, getTarget) {
    const ctx = canvas.getContext('2d');
    let w = 0, h = 0, dpr = 1, raf = 0, alive = true, last = 0, spawn = 0;
    const dots = [], sparks = [];
    function size() {
      const r = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = r.width; h = r.height;
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const want = Math.round(Math.min(70, Math.max(26, (w * h) / 9000)));
      while (dots.length < want) dots.push({x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - 0.5) * 12, vy: (Math.random() - 0.5) * 12, r: Math.random() * 1.4 + 0.4});
      dots.length = want;
    }
    function frame(ts) {
      if (!alive) return;
      raf = requestAnimationFrame(frame);
      if (document.hidden) { last = ts; return; }
      const dt = Math.min(0.05, (ts - (last || ts)) / 1000); last = ts;
      ctx.clearRect(0, 0, w, h);
      for (const d of dots) {
        d.x += d.vx * dt; d.y += d.vy * dt;
        if (d.x < 0 || d.x > w) d.vx *= -1;
        if (d.y < 0 || d.y > h) d.vy *= -1;
      }
      ctx.lineWidth = 1;
      for (let i = 0; i < dots.length; i++) {
        for (let j = i + 1; j < dots.length; j++) {
          const a = dots[i], b = dots[j], dx = a.x - b.x, dy = a.y - b.y, q = dx * dx + dy * dy;
          if (q < 9000) { ctx.strokeStyle = `rgba(140,160,255,${(1 - q / 9000) * 0.16})`; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
        }
      }
      for (const d of dots) { ctx.fillStyle = 'rgba(190,205,255,.55)'; ctx.beginPath(); ctx.arc(d.x, d.y, d.r, 0, 6.283); ctx.fill(); }
      // uchqunlar: mavzu → faol kartochka (egri yo'l bo'ylab, iz qoldirib)
      const t = getTarget();
      spawn -= dt;
      if (t && spawn <= 0) {
        spawn = 0.22 + Math.random() * 0.25;
        const bend = (Math.random() - 0.5) * 0.9 * Math.max(120, Math.abs(t.x2 - t.x1));
        sparks.push({x1: t.x1, y1: t.y1, x2: t.x2 + (Math.random() - 0.5) * t.wd * 0.6, y2: t.y2 + (Math.random() - 0.5) * t.ht * 0.5,
          cx: (t.x1 + t.x2) / 2 + bend, cy: Math.min(t.y1, t.y2) - 30 - Math.random() * 40, p: 0, v: 0.55 + Math.random() * 0.4,
          hue: Math.random() < 0.35 ? 'gold' : 'blue'});
      }
      for (let k = sparks.length - 1; k >= 0; k--) {
        const s = sparks[k];
        s.p += s.v * dt;
        if (s.p >= 1) { sparks.splice(k, 1); continue; }
        const at = (p) => {
          const u = 1 - p;
          return [u * u * s.x1 + 2 * u * p * s.cx + p * p * s.x2, u * u * s.y1 + 2 * u * p * s.cy + p * p * s.y2];
        };
        const col = s.hue === 'gold' ? '255,216,74' : '120,160,255';
        for (let m = 0; m < 7; m++) {
          const p = Math.max(0, s.p - m * 0.018), pt = at(p);
          ctx.fillStyle = `rgba(${col},${(1 - m / 7) * 0.9})`;
          ctx.beginPath(); ctx.arc(pt[0], pt[1], (1 - m / 7) * 2.4, 0, 6.283); ctx.fill();
        }
        const head = at(s.p);
        const g = ctx.createRadialGradient(head[0], head[1], 0, head[0], head[1], 9);
        g.addColorStop(0, `rgba(${col},.55)`); g.addColorStop(1, `rgba(${col},0)`);
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(head[0], head[1], 9, 0, 6.283); ctx.fill();
      }
    }
    size();
    const ro = window.ResizeObserver ? new ResizeObserver(size) : null;
    if (ro) ro.observe(canvas); else window.addEventListener('resize', size);
    if (!REDUCED) raf = requestAnimationFrame(frame);
    return () => { alive = false; cancelAnimationFrame(raf); if (ro) ro.disconnect(); else window.removeEventListener('resize', size); };
  }

  Edu.forge = function (root, opts) {
    opts = opts || {};
    const pages = opts.mode === 'pages';
    // Taqdimotda muqova va reja slaydi tanlangan songa qo'shimcha yoziladi (generator ham shunday hisoblaydi).
    const parts = PAGE_PARTS[opts.kind] || BOB;
    let count = pages ? parts.length : Math.max(4, Math.min(40, (parseInt(opts.count, 10) || 10) + 2));
    const unit = pages ? 'sahifa' : 'slayd';
    root.innerHTML = `<div class="forge${pages ? ' pages' : ''}">
      <canvas class="fg-sky" aria-hidden="true"></canvas>
      <div class="fg-in">
        <div class="fg-head">
          <div class="fg-core"><span class="fg-orb" aria-hidden="true"></span><span class="fg-topic">${esc(opts.topic || '')}</span></div>
          <div class="fg-stage"><i></i><span class="fg-st">Navbatda</span></div>
        </div>
        <div class="fg-grid"></div>
        <div class="fg-foot"><div class="fg-bar"><i></i></div>
          <div class="fg-meta"><span class="fg-count"></span><span class="fg-time">00:00</span></div></div>
      </div>
      <div class="fg-final" hidden><div class="fg-file"><b class="fg-ext">PPTX</b><span></span></div></div>
    </div>`;
    const $ = (sel) => root.querySelector(sel);
    const grid = $('.fg-grid'), st = $('.fg-st'), bar = $('.fg-bar i'), cnt = $('.fg-count'), clock = $('.fg-time');
    const forge = $('.forge');
    let cards = [], plan = null, built = 0, active = -1, stage = 'queued', alive = true, pulse = 0;

    function makeCards(n) {
      count = n;
      grid.style.setProperty('--n', n);
      grid.innerHTML = Array.from({length: n}, (_, i) => {
        const part = pages ? parts[i] || '' : '';
        return `<div class="fg-card" style="--i:${i}"><span class="fg-no">${i + 1}</span><div class="fg-ttl">${esc(part)}</div>${skel(pages ? 'page' : i === 0 ? 'cover' : i === 1 ? 'plan' : 'cards')}<span class="fg-ok" aria-hidden="true"></span></div>`;
      }).join('');
      cards = Array.from(grid.children);
      cards.forEach((c, i) => { if (pages || i < 2) c.classList.add('titled'); });
    }
    makeCards(count);

    function setPlan(items) {
      if (pages || plan || !items || !items.length) return;
      plan = items;
      if (items.length !== count) makeCards(items.length);
      items.forEach((it, i) => {
        const c = cards[i];
        setTimeout(() => {
          if (!alive) return;
          const kind = SKEL[it.category] || (i === 0 ? 'cover' : 'cards');
          const old = c.querySelector('.sk'); if (old) old.outerHTML = skel(kind);
          c.querySelector('.fg-ttl').textContent = it.title || '';
          c.classList.add('titled');
        }, REDUCED ? 0 : i * 140);
      });
    }

    function paint() {
      cards.forEach((c, i) => {
        c.classList.toggle('built', i < built);
        c.classList.toggle('writing', i >= built && i < active);
      });
      const pct = Math.round((built / count) * 100);
      // Hujjatda varaqlar soni oldindan ma'lum emas — foiz ko'rsatiladi (taqdimotda slaydlar soni aniq).
      cnt.textContent = pages ? pct + '%' : tr(`${built} / ${count} ${unit}`);
      bar.style.width = Math.max(3, pct) + '%';
    }

    const LABEL = {queued: 'Navbatda', plan: 'Reja tuzilmoqda', writing: pages ? 'Sahifalar yozilmoqda' : 'Slaydlar yozilmoqda',
      images: 'Rasmlar qo‘yilmoqda', render: 'Fayl yig‘ilmoqda', done: 'Tayyor!'};

    function update(job) {
      if (!alive || !job) return;
      const live = job.live || {};
      if (live.plan) setPlan(live.plan);
      stage = job.status === 'queued' ? 'queued' : job.stage || 'writing';
      if (stage === 'writing' && !pages && !plan) stage = 'plan';
      forge.dataset.stage = stage;
      st.textContent = LABEL[stage] || LABEL.writing;
      let b;
      if (stage === 'images' || stage === 'render') b = count;
      else if (live.total) b = Math.round((live.done / live.total) * count);
      else if (pages) b = Math.floor(((job.progress || 0) / 92) * count);
      else b = plan ? Math.floor((Math.max(0, (job.progress || 0) - 5) / 70) * count) : 0;
      built = Math.max(built, Math.min(count, b));     // orqaga qaytmaydi
      active = stage === 'queued' || stage === 'plan' ? -1 : Math.min(count, built + (pages ? 1 : 3));
      paint();
    }

    const t0 = opts.startedAt ? opts.startedAt * 1000 : Date.now();
    // Fayl yig'ilayotganda kartochkalar navbat bilan «tekshiruvdan» o'tadi — animatsiya hech qachon qotmaydi.
    const tick = setInterval(() => {
      const sec = Math.floor((Date.now() - t0) / 1000);
      clock.textContent = String(Math.floor(sec / 60)).padStart(2, '0') + ':' + String(sec % 60).padStart(2, '0');
      if (stage === 'render' || stage === 'images') {
        cards.forEach((c) => c.classList.remove('check'));
        if (cards[pulse % count]) cards[pulse % count].classList.add('check');
        pulse++;
      }
    }, 1000);

    function target() {
      if (stage === 'queued' || stage === 'done') return null;
      const box = forge.getBoundingClientRect(), orb = $('.fg-orb').getBoundingClientRect();
      let el = null;
      if (stage === 'plan') el = cards[(Math.floor(Date.now() / 900)) % count];
      else if (stage === 'images' || stage === 'render') el = cards[(pulse + count - 1) % count];
      else el = cards[Math.min(count - 1, built)];
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {x1: orb.left + orb.width / 2 - box.left, y1: orb.top + orb.height / 2 - box.top,
        x2: r.left + r.width / 2 - box.left, y2: r.top + r.height / 2 - box.top, wd: r.width, ht: r.height};
    }
    const stopSky = sky($('.fg-sky'), forge, target);

    function finish(ext) {
      return new Promise((resolve) => {
        if (!alive) return resolve();
        stage = 'done'; built = count; active = -1; paint();
        st.textContent = LABEL.done; forge.dataset.stage = 'done';
        $('.fg-ext').textContent = ext || 'PPTX';
        $('.fg-file span').textContent = pages ? (opts.label || '') : tr(`${count} ${unit}`);
        if (REDUCED) { $('.fg-final').hidden = false; return resolve(); }
        const g = grid.getBoundingClientRect();
        cards.forEach((c) => {
          const r = c.getBoundingClientRect();
          c.style.setProperty('--dx', (g.left + g.width / 2 - (r.left + r.width / 2)) + 'px');
          c.style.setProperty('--dy', (g.top + g.height / 2 - (r.top + r.height / 2)) + 'px');
        });
        forge.classList.add('gather');
        setTimeout(() => { $('.fg-final').hidden = false; forge.classList.add('burst'); }, 900 + count * 25);
        setTimeout(resolve, 2300 + count * 25);
      });
    }

    function fail() { stage = 'done'; forge.classList.add('failed'); }
    function stop() { alive = false; clearInterval(tick); stopSky(); }
    paint();
    return {update, finish, fail, stop};
  };
})();
