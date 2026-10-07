/* Edufayl kabineti: Yaratish, Hujjatlarim, Hamyon */
(function () {
  'use strict';
  const E = window.Edu;
  const view = document.getElementById('view');
  let me = null, catalog = null, pollTimer = null;

  const STYLE_LOOK = {
    toza: 'background:#fff', jurnal: 'background:#F4EFE6', blok: 'background:#0F2A3F',
    kontur: 'background:#fff;outline:2px solid #0C1226;outline-offset:-4px', qorongu: 'background:#111',
  };
  const STYLE_NOTE = {toza: 'Matn va rasm', jurnal: 'Nashr ko‘rinishi', blok: 'Kartochkalar', kontur: 'Chiziqli', qorongu: 'Qorong‘u fon'};

  function setTab(name) {
    document.querySelectorAll('[data-tab]').forEach((a) => a.classList.toggle('on', a.dataset.tab === name));
  }
  function stopPoll() { if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; } }
  function route() {
    stopPoll();
    const name = (location.hash.replace(/^#\/?/, '').split('?')[0]) || 'create';
    setTab(name);
    if (name === 'docs') return docs();
    if (name === 'wallet') return wallet();
    return create();
  }

  async function refreshBalance() {
    me = await E.me(true);
    E.header('app');
  }

  // ───────────────────────────────────────────────────────────── Yaratish
  const BOT_ONLY = ['Loyiha ishi', 'Kitob tarjimasi'];
  const TOPIC_HINT = {
    premium_presentation: "Masalan: Kiberxavfsizlik va shaxsiy ma'lumotlar himoyasi", simple_presentation: 'Masalan: Amir Temur davri',
    independent_work: "Masalan: Iqtisodiyotda raqamlashtirish", referat: "Masalan: Globallashuv va iqtisodiyot",
    article: "Masalan: Sun'iy intellektning ta'limdagi o'rni", thesis: "Masalan: Yoshlar tadbirkorligini qo'llab-quvvatlash",
    course_work: "Masalan: Korxonada xarajatlarni boshqarish", diploma_work: "Masalan: Bank xizmatlarini raqamlashtirish",
    bitiruv_ishi: "Masalan: Kichik biznesni rivojlantirish yo'llari",
    dissertatsiya: "Masalan: Innovatsion iqtisodiyotning nazariy asoslari",
  };
  const LANG_LABEL = {uz: "O'zbek (lotin)", ru: 'Русский', en: 'English'};

  function create() {
    let topic0 = '';
    try { topic0 = sessionStorage.getItem('edu_topic') || ''; sessionStorage.removeItem('edu_topic'); } catch (e) {}
    const kinds = catalog.kinds;
    let active = (location.hash.split('?')[1] || '').replace('kind=', '') || 'premium_presentation';
    if (!kinds.find((k) => k.key === active)) active = 'premium_presentation';
    renderForm(active, topic0);
  }

  function renderForm(key, topic0) {
    const kind = catalog.kinds.find((k) => k.key === key);
    const opt = kind.options || {};
    const s = {style: 'toza', theme: '', count: 10, template: 'template_20', icons: true, plan: false, size: (opt.sizes && opt.sizes[0] && opt.sizes[0].key) || '', extras: new Set()};
    const bot = catalog.bot;
    const $ = (id) => document.getElementById(id);

    const chips = catalog.kinds.map((k) => `<button type="button" class="chip ${k.key === key ? 'on' : ''}" data-kind="${E.esc(k.key)}">${E.esc(k.label)}</button>`).join('') +
      BOT_ONLY.map((t) => `<a class="chip soon" target="_blank" rel="noopener" href="https://t.me/${E.esc(bot)}">${t} <small>botda</small></a>`).join('');

    const langSel = (langs) => `<div style="flex:1;min-width:150px"><label class="lab" for="lang">Til</label>
      <select class="fld" id="lang">${langs.map((l) => `<option value="${E.esc(l.key || l)}">${E.esc(l.label || LANG_LABEL[l] || l)}</option>`).join('')}</select></div>`;
    const field = (id, label, hint, extra) => `<div style="margin-top:18px"><label class="lab" for="${id}">${label}${hint ? ` <span style="font-weight:500;color:var(--mute)">(${hint})</span>` : ''}</label>${extra}</div>`;

    let fields = `<label class="lab" for="topic">Mavzu</label>
      <textarea class="fld" id="topic" rows="3" maxlength="300" placeholder="${E.esc(TOPIC_HINT[key] || '')}" required>${E.esc(topic0)}</textarea>`;

    if (opt.form === 'presentation') {
      fields += `<div class="row" style="margin-top:18px;align-items:flex-start">${langSel(catalog.languages)}
        <div style="flex:2;min-width:250px"><label class="lab" for="size">Slaydlar soni</label>
          <select class="fld" id="size">${catalog.premium_prices.map((p) => `<option value="${p.slides}" ${p.slides === s.count ? 'selected' : ''}>${p.slides} slayd — ${E.fmt(p.price)} so‘m</option>`).join('')}</select></div></div>
        <div style="margin-top:18px"><div class="lab">Uslub</div>
          <div class="styles" id="styles">${catalog.styles.map((st) => `<button type="button" class="styl ${st.key === s.style ? 'on' : ''}" data-k="${E.esc(st.key)}"><div class="sl" style="${STYLE_LOOK[st.key] || ''}"></div>${E.esc(st.label)}</button>`).join('')}</div></div>
        <div style="margin-top:18px"><div class="lab">Rang <span style="font-weight:500;color:var(--mute)">(ixtiyoriy: bo'sh qolsa mavzuga mos tanlanadi)</span></div>
          <div class="swatches" id="themes"><button type="button" class="sw auto on" data-k="" title="Avtomatik">Avto</button>${catalog.themes.map((t) => `<button type="button" class="sw" data-k="${E.esc(t.key)}" title="${E.esc(t.label)}" style="background:linear-gradient(135deg,${E.esc(t.background)} 50%,${E.esc(t.accent)} 50%)"></button>`).join('')}</div></div>`
        + field('author', 'Muallif ismi', 'muqovaga yoziladi', '<input class="fld" id="author" maxlength="80" placeholder="Ism Familiya">')
        + field('prefs', 'Istaklar', 'ixtiyoriy', '<textarea class="fld" id="prefs" rows="2" maxlength="1000" placeholder="Masalan: investorlar uchun, ko\'proq vizual, qisqa va ta\'sirli"></textarea>');
    } else if (opt.form === 'simple_presentation') {
      fields += `<div class="row" style="margin-top:18px;align-items:flex-start">${langSel(opt.languages)}
        <div style="flex:2;min-width:250px"><label class="lab" for="size">Slaydlar soni</label>
          <select class="fld" id="size">${opt.sizes.map((z) => `<option value="${E.esc(z.key)}">${E.esc(z.label)} — ${E.fmt(z.price)}</option>`).join('')}</select></div></div>
        <div style="margin-top:18px"><div class="lab">Orqa fon</div>
          <div class="tpls" id="tpls">${catalog.templates.map((t) => `<button type="button" class="tpl ${t.id === s.template ? 'on' : ''}" data-id="${E.esc(t.id)}" title="${E.esc(t.name)}"><img loading="lazy" alt="${E.esc(t.name)}" src="${E.esc(t.url)}"><span>${E.esc(t.name)}</span></button>`).join('')}</div></div>
        <div class="row" style="margin-top:18px"><button type="button" class="chip on" id="t-icons">Ikonkalar</button><button type="button" class="chip" id="t-plan">Reja slaydi</button></div>`
        + field('author', 'Muallif ismi', 'muqovaga yoziladi', '<input class="fld" id="author" maxlength="80" placeholder="Ism Familiya">');
    } else if (opt.form === 'thesis') {
      fields += `<div class="row" style="margin-top:18px">${langSel(opt.languages)}</div>`
        + field('author', 'Muallif ismi', '', '<input class="fld" id="author" maxlength="80" placeholder="Ism Familiya" required>')
        + field('univ', 'Universitet', '', '<input class="fld" id="univ" maxlength="120" required>')
        + field('fac', 'Fakultet', 'ixtiyoriy', '<input class="fld" id="fac" maxlength="120">')
        + field('grp', 'Guruh', 'ixtiyoriy', '<input class="fld" id="grp" maxlength="40">');
    } else {
      fields += `<div class="row" style="margin-top:18px;align-items:flex-start">${langSel(opt.languages)}
        <div style="flex:2;min-width:250px"><label class="lab" for="size">Hajmi</label>
          <select class="fld" id="size">${opt.sizes.map((z) => `<option value="${E.esc(z.key)}">${E.esc(z.label)} — ${E.fmt(z.price)} so‘m</option>`).join('')}</select></div></div>`
        + (opt.plan_styles ? field('pstyle', 'Reja usuli', '', `<select class="fld" id="pstyle">${opt.plan_styles.map((p) => `<option value="${E.esc(p.key)}" ${p.key === 'murakkab' ? 'selected' : ''}>${E.esc(p.label)}</option>`).join('')}</select>`) : '')
        + (opt.extras && opt.extras.length ? `<div style="margin-top:18px"><div class="lab">Qo'shimchalar</div><div class="row" id="extras">${opt.extras.map((x) => `<button type="button" class="chip" data-x="${E.esc(x.key)}">${E.esc(x.label)}${x.price ? ` <small>+${E.fmt(x.price)}</small>` : ''}</button>`).join('')}</div></div>` : '')
        + field('author', 'Muallif ismi', 'muqovaga yoziladi', '<input class="fld" id="author" maxlength="80" placeholder="Ism Familiya">');
    }

    view.innerHTML = `
      <div class="types" id="types">${chips}</div>
      <form class="cols" id="cf" autocomplete="off">
        <div class="card panel">${fields}</div>
        <div class="card panel" style="position:sticky;top:90px">
          <b style="font-size:17px">Buyurtma</b>
          <div style="margin-top:14px">
            <div class="sum"><span style="color:var(--mute)">${E.esc(kind.label)}</span><b id="s-count"></b></div>
            <div class="sum"><span style="color:var(--mute)">Narx</span><b id="s-price"></b></div>
            <div class="sum"><span style="color:var(--mute)">Balansingiz</span><b id="s-bal"></b></div>
          </div>
          <div id="s-note" style="margin-top:12px"></div>
          <button class="btn block" id="go" type="submit" style="margin-top:16px">Yaratish</button>
          <p class="hint" style="text-align:center;margin-top:12px">Taxminan ${opt.eta_minutes || 3} daqiqa${kind.heavy ? ' (katta hujjatlar navbat bilan tayyorlanadi)' : ''}. Tayyor fayl Telegramga ham yuboriladi.</p>
        </div>
      </form>`;

    const price = () => {
      if (opt.form === 'presentation') return (catalog.premium_prices.find((p) => p.slides === s.count) || {}).price || 0;
      if (opt.form === 'thesis') return opt.price;
      if (opt.form === 'simple_presentation') return (opt.sizes.find((x) => x.key === s.size) || opt.sizes[0]).price;
      const z = opt.sizes.find((x) => x.key === s.size) || opt.sizes[0];
      return z.price + (opt.extras || []).filter((x) => s.extras.has(x.key)).reduce((a, x) => a + x.price, 0);
    };
    function summary() {
      const p = price(), bal = me.balance;
      $('s-count').textContent = opt.form === 'presentation' ? s.count + ' slayd' : opt.form === 'thesis' ? 'Tezis' : ((opt.sizes.find((x) => x.key === s.size) || {}).label || '');
      $('s-price').textContent = E.fmt(p) + ' so‘m';
      $('s-bal').textContent = E.fmt(bal) + ' so‘m';
      $('s-note').innerHTML = bal >= p ? '' :
        `<div class="note wait">Yetmaydi: yana <b>${E.fmt(p - bal)} so‘m</b> kerak. <a class="link" href="#/wallet">Hamyonni to‘ldirish</a></div>`;
    }
    $('types').onclick = (e) => { const b = e.target.closest('[data-kind]'); if (b) renderForm(b.dataset.kind, ($('topic') || {}).value || ''); };
    if ($('size')) $('size').onchange = (e) => { if (opt.form === 'presentation') s.count = parseInt(e.target.value, 10); else s.size = e.target.value; summary(); };
    if ($('styles')) $('styles').onclick = (e) => {
      const b = e.target.closest('.styl'); if (!b) return; s.style = b.dataset.k;
      document.querySelectorAll('#styles .styl').forEach((x) => x.classList.toggle('on', x === b));
    };
    if ($('themes')) $('themes').onclick = (e) => {
      const b = e.target.closest('.sw'); if (!b) return; s.theme = b.dataset.k;
      document.querySelectorAll('#themes .sw').forEach((x) => x.classList.toggle('on', x === b));
    };
    if ($('tpls')) $('tpls').onclick = (e) => {
      const b = e.target.closest('.tpl'); if (!b) return; s.template = b.dataset.id;
      document.querySelectorAll('#tpls .tpl').forEach((x) => x.classList.toggle('on', x === b));
    };
    if ($('t-icons')) $('t-icons').onclick = (e) => { s.icons = !s.icons; e.currentTarget.classList.toggle('on', s.icons); };
    if ($('t-plan')) $('t-plan').onclick = (e) => { s.plan = !s.plan; e.currentTarget.classList.toggle('on', s.plan); };
    if ($('extras')) $('extras').onclick = (e) => {
      const b = e.target.closest('[data-x]'); if (!b) return;
      s.extras.has(b.dataset.x) ? s.extras.delete(b.dataset.x) : s.extras.add(b.dataset.x);
      b.classList.toggle('on', s.extras.has(b.dataset.x)); summary();
    };
    summary();

    $('cf').onsubmit = async (ev) => {
      ev.preventDefault();
      const btn = $('go');
      btn.disabled = true; btn.innerHTML = '<span class="spin" style="width:16px;height:16px;border-width:2px;border-top-color:#fff;border-color:rgba(255,255,255,.4)"></span>&nbsp; Yuborilmoqda…';
      const val = (id) => ($(id) ? $(id).value : '');
      let params = {topic: val('topic'), language: val('lang'), author: val('author')};
      if (opt.form === 'presentation') Object.assign(params, {slide_count: s.count, style: s.style, theme: s.theme, preferences: val('prefs')});
      else if (opt.form === 'simple_presentation') Object.assign(params, {slide_count: parseInt(s.size || (opt.sizes[0] || {}).key, 10), template: s.template, icons: s.icons, plan_slide: s.plan});
      else if (opt.form === 'thesis') Object.assign(params, {university: val('univ'), faculty: val('fac'), group: val('grp')});
      else Object.assign(params, {size: s.size, extras: [...s.extras], plan_style: val('pstyle')});
      try {
        const res = await E.api('/jobs', {json: {kind: key, params}});
        me.balance = res.balance;
        E.header('app');
        E.toast('Buyurtma qabul qilindi');
        location.hash = '#/docs';
      } catch (e) {
        btn.disabled = false; btn.textContent = 'Yaratish';
        $('s-note').innerHTML = `<div class="note bad">${E.esc(e.message)}${e.code === 'no_balance' ? ' <a class="link" href="#/wallet">Hamyonni to‘ldirish</a>' : ''}</div>`;
        if (e.code === 'auth') E.login();
      }
    };
  }

  // ─────────────────────────────────────────────────────────── Hujjatlarim
  async function docs() {
    view.innerHTML = '<span class="spin"></span>';
    async function load() {
      let data;
      try { data = await E.api('/jobs'); } catch (e) { view.innerHTML = `<div class="note bad">${E.esc(e.message)}</div>`; return; }
      const jobs = data.jobs;
      const active = jobs.some((j) => j.status === 'queued' || j.status === 'running');
      view.innerHTML = `
        <div class="card" style="overflow:hidden">
          <div style="padding:18px 20px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
            <b style="font-size:18px">Hujjatlarim</b>
            <span class="hint" style="margin:0">Fayllar ${data.ttl_hours} soat saqlanadi, keyin o‘chiriladi.</span>
          </div>
          ${jobs.length ? jobs.map(jobRow).join('') : `<div style="padding:34px 20px;text-align:center;color:var(--mute)">Hali buyurtma yo‘q. <a class="link" href="#/create">Birinchi taqdimotni yarating</a></div>`}
        </div>`;
      if (active) pollTimer = setTimeout(async () => { await refreshBalance(); load(); }, 3000);
    }
    load();
  }

  function jobRow(j) {
    const left = Math.max(0, Math.round((j.expires_at * 1000 - Date.now()) / 3600000));
    let status = '', action = '';
    if (j.status === 'done') {
      status = `<span class="pill ok">Tayyor</span> <span class="hint">${left} soat qoldi</span>`;
      action = j.ready ? `<a class="btn sm" href="/api/v1/jobs/${E.esc(j.id)}/file">Yuklab olish</a>` : '';
    } else if (j.status === 'failed') {
      status = `<span class="pill bad">Bajarilmadi</span><div class="hint" style="margin-top:6px">${E.esc(j.error)}</div>`;
    } else {
      status = `<span class="pill wait">${E.esc(j.stage_text || 'Navbatda')}</span><div class="bar"><i style="width:${Math.max(4, j.progress)}%"></i></div>`;
    }
    return `<div class="job"><div><div class="t">${E.esc(j.title)}</div><div class="hint" style="margin:2px 0 0">${E.esc(kindLabel(j.kind))} · ${E.fmt(j.price)} so‘m</div></div><div>${status}</div><div>${action}</div></div>`;
  }
  function kindLabel(k) { const f = (catalog.kinds || []).find((x) => x.key === k); return f ? f.label : k; }

  // ───────────────────────────────────────────────────────────────── Hamyon
  async function wallet() {
    view.innerHTML = '<span class="spin"></span>';
    let w;
    try { w = await E.api('/wallet'); } catch (e) { view.innerHTML = `<div class="note bad">${E.esc(e.message)}</div>`; return; }
    const receipt = w.methods.find((m) => m.key === 'receipt');
    let amount = 0, started = '';
    const stamp = () => new Date().toLocaleString('sv-SE', {timeZone: 'Asia/Tashkent'}).replace(' ', 'T');

    view.innerHTML = `
      <div class="cols">
        <div class="card panel">
          <div class="row" style="justify-content:space-between"><b style="font-size:18px">Balansni to‘ldirish</b><span class="bal">${E.fmt(w.balance)} so‘m</span></div>
          <div class="row" style="margin-top:16px">
            ${w.methods.map((m) => `<span class="chip ${m.key === 'receipt' ? 'on' : 'soon'}">${E.esc(m.label)}${m.enabled ? '' : ' <small>tez orada</small>'}</span>`).join('')}
          </div>

          <div style="margin-top:22px"><div class="lab">1. Summani tanlang</div>
            <div class="row" id="presets">${w.presets.map((p) => `<button type="button" class="chip" data-v="${p}">${E.fmt(p)}</button>`).join('')}</div>
            <input class="fld" id="amount" inputmode="numeric" placeholder="Boshqa summa (so'm)" style="margin-top:10px;max-width:260px"></div>

          <div style="margin-top:22px"><div class="lab">2. Pulni kartalardan biriga o‘tkazing</div>
            ${receipt.cards.map((c) => `<div class="cardno"><span>${E.esc(c)}</span><button type="button" class="link" data-copy="${E.esc(c.replace(/ /g, ''))}">Nusxalash</button></div>`).join('')}
            <div class="hint">Qabul qiluvchi: ${E.esc(receipt.owner)}</div></div>

          <div style="margin-top:22px"><div class="lab">3. To‘lov chekini yuklang</div>
            <div class="drop" id="drop"><div style="font-weight:700">Chekni shu yerga tashlang yoki tanlang</div>
              <div class="hint">Rasm, PDF yoki DOCX · 12 MB gacha. Eng yaxshisi: to‘lov tarixidagi asl kvitansiya (sana, qabul qiluvchi karta va ID ko‘rinsin).</div>
              <input type="file" id="file" accept="image/*,.pdf,.docx" style="margin-top:12px"></div>
            <div id="r-out" style="margin-top:14px"></div></div>
        </div>

        <div class="card panel">
          <b style="font-size:17px">So‘nggi to‘lovlar</b>
          ${w.history.length ? `<table class="hist" style="margin-top:8px"><tr><th>Sana</th><th>Summa</th><th>Holat</th></tr>${w.history.map((h) => `<tr><td>${E.esc(h.created_at)}</td><td>${E.fmt(h.amount)}</td><td>${statusPill(h.status)}</td></tr>`).join('')}</table>`
            : '<p class="hint" style="margin-top:10px">Hali to‘lov yo‘q.</p>'}
          <div class="note wait" style="margin-top:18px">Chek tekshirilgach summa hisobga qo‘shiladi. Admin tasdig‘i kerak bo‘lsa, natija Telegramga ham keladi.</div>
        </div>
      </div>`;

    const $ = (id) => document.getElementById(id);
    function setAmount(v, fromPreset) {
      amount = v; started = v ? stamp() : '';
      $('amount').value = fromPreset ? '' : $('amount').value;
      document.querySelectorAll('#presets .chip').forEach((c) => c.classList.toggle('on', parseInt(c.dataset.v, 10) === v));
    }
    $('presets').onclick = (e) => { const b = e.target.closest('.chip'); if (b) setAmount(parseInt(b.dataset.v, 10), true); };
    $('amount').oninput = (e) => setAmount(parseInt(e.target.value.replace(/\D/g, ''), 10) || 0, false);
    view.querySelectorAll('[data-copy]').forEach((b) => (b.onclick = () => E.copy(b.dataset.copy)));

    async function send(file) {
      if (!amount) { $('r-out').innerHTML = '<div class="note bad">Avval summani tanlang yoki kiriting.</div>'; return; }
      $('r-out').innerHTML = '<span class="spin"></span> &nbsp;Chek tekshirilmoqda…';
      const form = new FormData();
      form.append('amount', String(amount)); form.append('started', started); form.append('file', file, file.name);
      try {
        const r = await E.api('/wallet/receipt', {form});
        const cls = r.credited ? 'ok' : (r.pending ? 'wait' : 'bad');
        $('r-out').innerHTML = `<div class="note ${cls}" style="white-space:pre-line">${E.esc(r.message || 'Qabul qilindi')}</div>`;
        if (r.credited) { await refreshBalance(); wallet(); }
        else me.balance = r.balance;
      } catch (e) { $('r-out').innerHTML = `<div class="note bad">${E.esc(e.message)}</div>`; }
      $('file').value = '';
    }
    $('file').onchange = (e) => { if (e.target.files[0]) send(e.target.files[0]); };
    const drop = $('drop');
    ['dragenter', 'dragover'].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.add('over'); }));
    ['dragleave', 'drop'].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.remove('over'); }));
    drop.addEventListener('drop', (e) => { const f = e.dataTransfer.files[0]; if (f) send(f); });
  }
  function statusPill(s) {
    return s === 'approved' ? '<span class="pill ok">Tasdiqlandi</span>' : s === 'rejected' ? '<span class="pill bad">Rad etildi</span>' : '<span class="pill wait">Kutilmoqda</span>';
  }

  // ───────────────────────────────────────────────────────────────── boshlash
  (async function init() {
    me = await E.me();
    if (!me) {
      view.innerHTML = `<div class="card panel" style="max-width:520px;margin:20px auto;text-align:center">
        <h2 style="margin:0 0 8px">Telegram orqali kiring</h2>
        <p style="color:#4A5272;margin:0 0 18px">Balans, buyurtmalar va fayllar bot bilan umumiy. Parol kerak emas.</p>
        <button class="btn" id="lg">Telegram orqali kirish</button></div>`;
      document.getElementById('lg').onclick = () => E.login();
      E.header('app');
      return;
    }
    try { catalog = await E.api('/catalog'); } catch (e) { view.innerHTML = `<div class="note bad">${E.esc(e.message)}</div>`; return; }
    E.header('app');
    window.addEventListener('hashchange', route);
    route();
  })();
})();
