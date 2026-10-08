/* Edufayl: taqdimotni qo'lda tahrirlash (bepul) — matn, diagramma raqamlari, slaydlar tartibi.
 *
 * Server (`/api/v1/jobs/{id}/page/{n}`, `/edit`) sahifani AI siz qayta chizadi. Matn tahririda sahifaning
 * o'zi iframe ichida ochiladi: mijoz ko'rgan bloklar ro'yxati server tuzadigan ro'yxat bilan bir xil
 * (bir xil CSS selektor va bir xil filtr), shuning uchun o'zgarish tartib raqami bilan yuboriladi.
 *
 *   Edu.deckEdit.text(ctx) · Edu.deckEdit.chart(ctx) · Edu.deckEdit.order(ctx)
 *   ctx = {id, n, version, slides, stage, panel, bar, done(nAfter), cancel()}
 */
(function () {
  'use strict';
  const E = window.Edu;
  const api = (id, path, opts) => E.api('/jobs/' + encodeURIComponent(id) + path, opts);
  const spin = '<span class="spin" style="width:16px;height:16px;border-width:2px;border-top-color:#fff;border-color:rgba(255,255,255,.4)"></span>';

  // Server bilan bir xil: ichma-ich bo'lsa faqat tashqisi, diagramma (svg) ichidagisi va bo'shi yo'q.
  const listOf = (doc, sel) => [...doc.querySelectorAll(sel)].filter((el) =>
    !el.closest('svg') && !(el.parentElement && el.parentElement.closest(sel)) && el.textContent.trim());

  function busyBar(bar, text) { bar.innerHTML = `<span class="hint" style="margin:0">${spin.replace('#fff', 'var(--brand)')} &nbsp;${text}</span>`; }

  // ───────────────────────────────────────────── 1. matn
  async function text(ctx) {
    const {id, n, stage, bar} = ctx;
    busyBar(bar, 'Sahifa ochilmoqda…');
    let page;
    try { page = await api(id, '/page/' + n); } catch (e) { E.toast(e.message); ctx.cancel(); return; }
    if (page.locked) { E.toast('Reja sahifasi boshqa sahifalar sarlavhalaridan o‘zi yig‘iladi.'); ctx.cancel(); return; }
    const frame = document.createElement('iframe');
    frame.className = 'ed-frame';
    frame.title = 'Sahifa';
    frame.srcdoc = page.html.replace(/<script\b[\s\S]*?<\/script>/gi, '');
    stage.classList.add('editing');
    stage.appendChild(frame);
    const fit = () => { frame.style.transform = `scale(${stage.clientWidth / 1920})`; };
    fit();
    window.addEventListener('resize', fit);
    const orig = [];
    let list = [];
    const finish = () => { window.removeEventListener('resize', fit); frame.remove(); stage.classList.remove('editing'); };

    frame.onload = () => {
      const doc = frame.contentDocument;
      const st = doc.createElement('style');
      st.textContent = `[data-ed]{outline:3px dashed rgba(36,87,255,.45);outline-offset:6px;border-radius:6px;cursor:text;transition:outline-color .15s,background .15s}
        [data-ed]:hover{outline-color:#2457FF}[data-ed]:focus{outline:4px solid #FFD84A;background:rgba(255,216,74,.14)}
        [data-ed].chg{outline-color:#0F9D6B}`;
      doc.head.appendChild(st);
      list = listOf(doc, page.selector);
      list.forEach((el, k) => { orig[k] = el.innerHTML; el.setAttribute('contenteditable', 'true'); el.setAttribute('spellcheck', 'false'); el.dataset.ed = k; });
      doc.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); if (!e.target.closest('.title')) doc.execCommand('insertLineBreak'); }
        if (e.key === 'Escape') { e.preventDefault(); cancel(); }
      });
      doc.addEventListener('paste', (e) => { e.preventDefault(); doc.execCommand('insertText', false, (e.clipboardData || window.clipboardData).getData('text/plain')); });
      doc.addEventListener('input', (e) => { const el = e.target.closest('[data-ed]'); if (el) el.classList.toggle('chg', el.innerHTML !== orig[el.dataset.ed]); });
      if (list[0]) setTimeout(() => list[0].focus({preventScroll: true}), 60);
      stage.scrollIntoView({behavior: 'smooth', block: 'nearest'});
      bar.innerHTML = `<span class="hint ed-hint">Matnni bosing va o‘zgartiring. Bepul.</span>
        <button type="button" class="btn ghost sm" id="ed-x">Bekor qilish</button><button type="button" class="btn sm" id="ed-ok">Saqlash</button>`;
      bar.querySelector('#ed-x').onclick = cancel;
      bar.querySelector('#ed-ok').onclick = save;
    };
    function cancel() { finish(); ctx.cancel(); }
    async function save() {
      const edits = [];
      list.forEach((el, k) => { if (el.innerHTML !== orig[k]) edits.push({k, html: el.innerHTML}); });
      if (!edits.length) { cancel(); return; }
      busyBar(bar, 'Saqlanmoqda: sahifa qayta chizilmoqda…');
      frame.style.pointerEvents = 'none';
      try {
        await api(id, '/edit', {json: {op: 'text', n, version: ctx.version, count: list.length, edits}});
      } catch (e) {
        frame.style.pointerEvents = '';
        bar.innerHTML = `<span class="note bad" style="flex:1;margin:0">${E.esc(e.message)}</span><button type="button" class="btn ghost sm" id="ed-x">Yopish</button>`;
        bar.querySelector('#ed-x').onclick = cancel;
        return;
      }
      finish();
      E.toast('Saqlandi');
      ctx.done(n);
    }
  }

  // ───────────────────────────────────────────── 2. diagramma
  const KINDS = [['bar', 'Ustunli'], ['line', 'Chiziqli'], ['donut', 'Halqa']];

  async function chart(ctx) {
    const {id, n, panel, bar} = ctx;
    busyBar(bar, 'Diagramma ochilmoqda…');
    let page;
    try { page = await api(id, '/page/' + n); } catch (e) { E.toast(e.message); ctx.cancel(); return; }
    if (!page.charts.length) { E.toast('Bu sahifada diagramma yo‘q.'); ctx.cancel(); return; }
    let k = 0, spec = JSON.parse(JSON.stringify(page.charts[0]));
    bar.innerHTML = ''; bar.hidden = true;
    panel.hidden = false;
    setTimeout(() => panel.scrollIntoView({behavior: 'smooth', block: 'nearest'}), 50);

    function draw() {
      const donut = spec.kind === 'donut';
      if (donut) spec.series = spec.series.slice(0, 1);
      const rows = spec.labels.map((lab, r) => `<tr><td><input class="fld" data-l="${r}" value="${E.esc(lab)}" maxlength="40"></td>${spec.series.map((s, c) =>
        `<td><input class="fld num" inputmode="decimal" data-v="${c}:${r}" value="${E.esc(String(s.values[r] ?? ''))}"></td>`).join('')}
        <td><button type="button" class="ed-del" data-dr="${r}" aria-label="O‘chirish" ${spec.labels.length <= 2 ? 'disabled' : ''}>✕</button></td></tr>`).join('');
      panel.innerHTML = `<div class="ed-head"><b>📊 Diagramma raqamlari</b> <span class="pill ok">Bepul</span>
          ${page.charts.length > 1 ? `<span class="st-chips">${page.charts.map((_, i) => `<button type="button" class="chip sm${i === k ? ' on' : ''}" data-k="${i}">${i + 1}-diagramma</button>`).join('')}</span>` : ''}</div>
        <div class="st-chips" id="ed-kind">${KINDS.map(([key, label]) => `<button type="button" class="chip sm${key === spec.kind ? ' on' : ''}" data-kind="${key}">${label}</button>`).join('')}</div>
        <div class="ed-scroll"><table class="ed-tbl"><thead><tr><th>Yorliq</th>${spec.series.map((s, c) => `<th><input class="fld" data-s="${c}" value="${E.esc(s.name)}" placeholder="Qator nomi" maxlength="40">${spec.series.length > 1 ? `<button type="button" class="ed-del" data-dc="${c}" aria-label="O‘chirish">✕</button>` : ''}</th>`).join('')}<th></th></tr></thead>
          <tbody>${rows}</tbody></table></div>
        <div class="row" style="margin-top:8px"><button type="button" class="btn ghost sm" id="ed-row">+ Qator</button>
          ${donut ? '' : '<button type="button" class="btn ghost sm" id="ed-col">+ Ustun</button>'}</div>
        <div class="ed-two"><label><span class="lab">O‘lchov birligi</span><input class="fld" id="ed-unit" value="${E.esc(spec.unit)}" maxlength="30" placeholder="%, mln so‘m"></label>
          <label><span class="lab">Manba</span><input class="fld" id="ed-src" value="${E.esc(spec.source)}" maxlength="120" placeholder="Statistika agentligi, 2024"></label></div>
        <div id="ed-note"></div>
        <div class="row" style="justify-content:flex-end;margin-top:12px"><button type="button" class="btn ghost sm" id="ed-x">Bekor qilish</button><button type="button" class="btn sm" id="ed-ok">Saqlash</button></div>`;
      const q = (s) => panel.querySelector(s);
      panel.querySelectorAll('[data-k]').forEach((b) => (b.onclick = () => { k = +b.dataset.k; spec = JSON.parse(JSON.stringify(page.charts[k])); draw(); }));
      q('#ed-kind').onclick = (e) => { const b = e.target.closest('[data-kind]'); if (b) { read(); spec.kind = b.dataset.kind; draw(); } };
      panel.querySelectorAll('[data-dr]').forEach((b) => (b.onclick = () => { read(); const r = +b.dataset.dr; spec.labels.splice(r, 1); spec.series.forEach((s) => s.values.splice(r, 1)); draw(); }));
      panel.querySelectorAll('[data-dc]').forEach((b) => (b.onclick = () => { read(); spec.series.splice(+b.dataset.dc, 1); draw(); }));
      q('#ed-row').onclick = () => { read(); if (spec.labels.length >= 24) return; spec.labels.push(''); spec.series.forEach((s) => s.values.push('')); draw(); panel.querySelector(`[data-l="${spec.labels.length - 1}"]`).focus(); };
      if (q('#ed-col')) q('#ed-col').onclick = () => { read(); if (spec.series.length >= 6) return; spec.series.push({name: '', values: spec.labels.map(() => '')}); draw(); };
      q('#ed-x').onclick = () => { panel.hidden = true; panel.innerHTML = ''; ctx.cancel(); };
      q('#ed-ok').onclick = save;
    }
    function read() {
      panel.querySelectorAll('[data-l]').forEach((i) => { spec.labels[+i.dataset.l] = i.value.trim(); });
      panel.querySelectorAll('[data-s]').forEach((i) => { spec.series[+i.dataset.s].name = i.value.trim(); });
      panel.querySelectorAll('[data-v]').forEach((i) => { const [c, r] = i.dataset.v.split(':').map(Number); spec.series[c].values[r] = i.value.trim().replace(',', '.'); });
      const u = panel.querySelector('#ed-unit'), s = panel.querySelector('#ed-src');
      if (u) spec.unit = u.value.trim(); if (s) spec.source = s.value.trim();
    }
    async function save() {
      read();
      const note = panel.querySelector('#ed-note'), ok = panel.querySelector('#ed-ok');
      if (spec.series.some((s) => s.values.some((v) => v === '' || isNaN(Number(v))))) { note.innerHTML = '<div class="note bad">Qiymatlar faqat raqam bo‘lsin.</div>'; return; }
      ok.disabled = true; ok.innerHTML = spin + '&nbsp; Saqlanmoqda…';
      try {
        await api(id, '/edit', {json: {op: 'chart', n, k, version: ctx.version, chart: {...spec, series: spec.series.map((s) => ({name: s.name, values: s.values.map(Number)}))}}});
      } catch (e) { ok.disabled = false; ok.textContent = 'Saqlash'; note.innerHTML = `<div class="note bad">${E.esc(e.message)}</div>`; return; }
      panel.hidden = true; panel.innerHTML = '';
      E.toast('Diagramma yangilandi');
      ctx.done(n);
    }
    draw();
  }

  // ───────────────────────────────────────────── 3. tartib
  function order(ctx) {
    const {id, slides, panel, bar} = ctx;
    const fixed = ctx.hasPlan ? 2 : 1;
    let rows = slides.slice(fixed).map((s) => ({n: s.n, title: s.title}));
    const img = (n) => `/api/v1/jobs/${encodeURIComponent(id)}/slide/${n}?v=${ctx.version}`;
    bar.innerHTML = ''; bar.hidden = true;
    panel.hidden = false;
    setTimeout(() => panel.scrollIntoView({behavior: 'smooth', block: 'nearest'}), 50);
    function draw() {
      const lock = slides.slice(0, fixed).map((s, i) => `<li class="ed-row locked"><img src="${img(s.n)}" alt=""><span class="t"><b>${i + 1}.</b> ${E.esc(s.title || '')}</span>
        <span class="pill soon">${i === 0 ? 'Muqova' : 'Reja — o‘zi yangilanadi'}</span></li>`).join('');
      const items = rows.map((r, i) => `<li class="ed-row"><img src="${img(r.n)}" alt=""><span class="t"><b>${i + fixed + 1}.</b> ${E.esc(r.title || '')}</span>
        <span class="ed-acts"><button type="button" data-a="up" data-i="${i}" aria-label="Yuqoriga" ${i === 0 ? 'disabled' : ''}>↑</button>
        <button type="button" data-a="down" data-i="${i}" aria-label="Pastga" ${i === rows.length - 1 ? 'disabled' : ''}>↓</button>
        <button type="button" data-a="dup" data-i="${i}" aria-label="Nusxa" title="Nusxa">⧉</button>
        <button type="button" data-a="del" data-i="${i}" aria-label="O‘chirish" title="O‘chirish" ${rows.length <= (fixed === 2 ? 2 : 1) ? 'disabled' : ''}>✕</button></span></li>`).join('');
      panel.innerHTML = `<div class="ed-head"><b>⇅ Slaydlar tartibi</b> <span class="pill ok">Bepul</span></div>
        <p class="hint" style="margin:0 0 10px">Joyini almashtiring, nusxa oling yoki keraksizini o‘chiring. Reja sahifasi yangi tartibdan o‘zi yig‘iladi.</p>
        <ol class="ed-list">${lock}${items}</ol><div id="ed-note"></div>
        <div class="row" style="justify-content:flex-end;margin-top:12px"><button type="button" class="btn ghost sm" id="ed-x">Bekor qilish</button><button type="button" class="btn sm" id="ed-ok">Saqlash</button></div>`;
      panel.querySelector('.ed-list').onclick = (e) => {
        const b = e.target.closest('[data-a]'); if (!b) return;
        const i = +b.dataset.i, a = b.dataset.a;
        if (a === 'up' && i > 0) [rows[i - 1], rows[i]] = [rows[i], rows[i - 1]];
        if (a === 'down' && i < rows.length - 1) [rows[i + 1], rows[i]] = [rows[i], rows[i + 1]];
        if (a === 'dup' && rows.length + fixed < 40) rows.splice(i + 1, 0, {...rows[i]});
        if (a === 'del') rows.splice(i, 1);
        draw();
      };
      panel.querySelector('#ed-x').onclick = () => { panel.hidden = true; panel.innerHTML = ''; ctx.cancel(); };
      panel.querySelector('#ed-ok').onclick = save;
    }
    async function save() {
      const ok = panel.querySelector('#ed-ok'), note = panel.querySelector('#ed-note');
      if (rows.map((r) => r.n).join() === slides.slice(fixed).map((s) => s.n).join()) { panel.hidden = true; panel.innerHTML = ''; ctx.cancel(); return; }
      ok.disabled = true; ok.innerHTML = spin + '&nbsp; Saqlanmoqda…';
      try { await api(id, '/edit', {json: {op: 'order', version: ctx.version, order: rows.map((r) => r.n)}}); } catch (e) {
        ok.disabled = false; ok.textContent = 'Saqlash'; note.innerHTML = `<div class="note bad">${E.esc(e.message)}</div>`; return;
      }
      panel.hidden = true; panel.innerHTML = '';
      E.toast('Tartib saqlandi');
      ctx.done(1);
    }
    draw();
  }

  E.deckEdit = {text, chart, order};
})();
