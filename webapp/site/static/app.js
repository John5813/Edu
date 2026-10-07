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
  let teardown = null;
  function stopPoll() {
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
    if (teardown) { try { teardown(); } catch (e) { /* tozalash xatosi muhim emas */ } teardown = null; }
  }
  function route() {
    stopPoll();
    const name = (location.hash.replace(/^#\/?/, '').split('?')[0]) || 'create';
    setTab(name.startsWith('job/') ? 'docs' : name);
    if (name.startsWith('job/')) return jobPage(name.slice(4));
    if (name === 'docs') return docs();
    if (name === 'wallet') return wallet();
    if (name === 'profile') return profile();
    if (name === 'welcome') return welcome();
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

  function typeChips(key) {
    return catalog.kinds.map((k) => `<button type="button" class="chip ${k.key === key ? 'on' : ''}" data-kind="${E.esc(k.key)}">${E.esc(k.label)}</button>`).join('') +
      BOT_ONLY.map((t) => `<a class="chip soon" target="_blank" rel="noopener" href="https://t.me/${E.esc(catalog.bot)}">${t} <small>botda</small></a>`).join('');
  }

  function renderForm(key, topic0) {
    const kind = catalog.kinds.find((k) => k.key === key);
    const opt = kind.options || {};
    const s = {size: (opt.sizes && opt.sizes[0] && opt.sizes[0].key) || '', extras: new Set()};
    const bot = catalog.bot;
    const $ = (id) => document.getElementById(id);

    const chips = typeChips(key);
    if (opt.form === 'presentation' || opt.form === 'simple_presentation') return renderPresentation(key, kind, opt, topic0, chips);


    const langSel = (langs) => `<div style="flex:1;min-width:150px"><label class="lab" for="lang">Til</label>
      <select class="fld" id="lang">${langs.map((l) => `<option value="${E.esc(l.key || l)}">${E.esc(l.label || LANG_LABEL[l] || l)}</option>`).join('')}</select></div>`;
    const field = (id, label, hint, extra) => `<div style="margin-top:18px"><label class="lab" for="${id}">${label}${hint ? ` <span style="font-weight:500;color:var(--mute)">(${hint})</span>` : ''}</label>${extra}</div>`;

    let fields = `<label class="lab" for="topic">Mavzu</label>
      <textarea class="fld" id="topic" rows="3" maxlength="300" placeholder="${E.esc(TOPIC_HINT[key] || '')}" required>${E.esc(topic0)}</textarea>`;

    if (opt.form === 'thesis') {
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
      if (opt.form === 'thesis') return opt.price;
      const z = opt.sizes.find((x) => x.key === s.size) || opt.sizes[0];
      return z.price + (opt.extras || []).filter((x) => s.extras.has(x.key)).reduce((a, x) => a + x.price, 0);
    };
    function summary() {
      const p = price(), bal = me.balance;
      $('s-count').textContent = opt.form === 'thesis' ? 'Tezis' : ((opt.sizes.find((x) => x.key === s.size) || {}).label || '');
      $('s-price').textContent = E.fmt(p) + ' so‘m';
      $('s-bal').textContent = E.fmt(bal) + ' so‘m';
      $('s-note').innerHTML = bal >= p ? '' :
        `<div class="note wait">Yetmaydi: yana <b>${E.fmt(p - bal)} so‘m</b> kerak. <a class="link" href="#/wallet">Hamyonni to‘ldirish</a></div>`;
    }
    $('types').onclick = (e) => { const b = e.target.closest('[data-kind]'); if (b) renderForm(b.dataset.kind, ($('topic') || {}).value || ''); };
    if ($('size')) $('size').onchange = (e) => { s.size = e.target.value; summary(); };
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
      if (opt.form === 'thesis') Object.assign(params, {university: val('univ'), faculty: val('fac'), group: val('grp')});
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


  // ───────────────────────────────────────── Taqdimot formasi (botdagi qadamlar bilan bir xil)
  // 1 mavzu va til → 2 manba → 3 dizayn → 4 hajm → 5 muallif va istaklar
  const SOURCES = [
    {key: 'ai', label: '✨ AI o‘zi yozadi', note: 'Faqat mavzu bo‘yicha'},
    {key: 'text', label: '📝 Matn yozaman', note: 'O‘z fikr yoki konspektingiz'},
    {key: 'file', label: '📎 Fayl yuklayman', note: 'PDF, DOCX yoki PPTX'},
    {key: 'url', label: '🔗 Sayt havolasi', note: 'Maqola yoki sahifa'},
  ];
  const PREF_EXAMPLES = ['Investorlar uchun ishonchli', 'Ko‘proq vizual', 'Qisqa va ta’sirli', 'Talabalar uchun sodda tilda', 'Raqam va faktlar ko‘proq'];

  function stepCard(n, title, hint, body) {
    return `<section class="card panel step"><div class="stepno">${n}</div><div class="stepbody">
      <div class="steptitle">${title}${hint ? ` <span class="hint-i">${hint}</span>` : ''}</div>${body}</div></section>`;
  }

  function renderPresentation(key, kind, opt, topic0, chips) {
    const premium = opt.form === 'presentation';
    const $ = (id) => document.getElementById(id);
    const range = catalog.premium_range || {min: 5, max: 30, popular: [10, 15, 20]};
    const priceOf = (n) => (catalog.premium_prices.find((p) => p.slides === n) || {}).price || 0;
    const s = {topic: topic0 || '', lang: '', src: {kind: 'ai', text: '', label: '', words: 0}, style: 'toza', theme: '',
      count: premium ? 10 : parseInt((opt.sizes[0] || {}).key, 10), template: 'template_20', icons: true, plan: false,
      author: (me && me.name) || '', prefs: '', suggest: {language: '', theme: null}};
    const langLabel = (k) => ((catalog.languages.find((l) => l.key === k)) || {}).label || k;
    const themeOf = (k) => catalog.themes.find((t) => t.key === k);

    const langSel = `<label class="lab" for="lang">Taqdimot tili</label>
      <select class="fld" id="lang"><option value="">Avto — mavzuga qarab</option>${catalog.languages.map((l) => `<option value="${E.esc(l.key)}">${E.esc(l.label)}</option>`).join('')}</select>
      <div class="hint" id="auto-note"></div>`;

    const sourceBody = `<div class="srcs" id="srcs">${SOURCES.map((x) => `<button type="button" class="src ${x.key === 'ai' ? 'on' : ''}" data-k="${x.key}"><b>${x.label}</b><small>${x.note}</small></button>`).join('')}</div>
      <div id="src-panel" style="margin-top:14px"></div>
      <div class="hint">Manba bersangiz, taqdimot aynan shu matnga tayanadi. Bermasangiz, AI mavzu bo‘yicha o‘zi yozadi.</div>`;

    let design = '';
    if (premium) {
      design = `<div class="lab">Ko‘rinish uslubi</div>
        <div class="styles" id="styles">${catalog.styles.map((st) => `<button type="button" class="styl ${st.key === s.style ? 'on' : ''}" data-k="${E.esc(st.key)}"><div class="sl" style="${STYLE_LOOK[st.key] || ''}"></div>${E.esc(st.label)}<small>${E.esc(st.note || '')}</small></button>`).join('')}</div>
        <div class="lab" style="margin-top:20px">Rang sxemasi <span class="hint-i">(Avto: mavzuga mos rang tanlanadi)</span></div>
        <div class="thms" id="themes"><button type="button" class="thm on" data-k=""><i class="auto">✨</i><span>Avto</span><small id="auto-theme">mavzuga qarab</small></button>${catalog.themes.map((t) => `<button type="button" class="thm" data-k="${E.esc(t.key)}"><i style="background:linear-gradient(135deg,${E.esc(t.background)} 50%,${E.esc(t.accent)} 50%)"></i><span>${E.esc(t.label.split(' — ')[0])}</span>${t.label.includes(' — ') ? `<small>${E.esc(t.label.split(' — ').slice(1).join(' — '))}</small>` : ''}</button>`).join('')}</div>`;
    } else {
      design = `<div class="lab">Orqa fon <span class="hint-i">(${catalog.templates.length} ta tayyor rasmli shablon)</span></div>
        <div class="tpls" id="tpls">${catalog.templates.map((t) => `<button type="button" class="tpl ${t.id === s.template ? 'on' : ''}" data-id="${E.esc(t.id)}" title="${E.esc(t.name)}"><img loading="lazy" alt="${E.esc(t.name)}" src="${E.esc(t.url)}"><span>${E.esc(t.name)}</span></button>`).join('')}</div>
        <div class="row" style="margin-top:16px"><button type="button" class="chip on" id="t-icons">Ikonkalar</button><button type="button" class="chip" id="t-plan">Reja slaydi</button></div>
        <div class="hint">Ikonkalar — slaydlardagi kichik belgilar. Reja slaydi — muqovadan keyin mundarija.</div>`;
    }

    let size = '';
    if (premium) {
      size = `<div class="counter"><button type="button" class="cbtn" id="c-minus" aria-label="Kamaytirish">−</button>
          <div class="cval"><b id="c-num">${s.count}</b><span>slayd</span></div><button type="button" class="cbtn" id="c-plus" aria-label="Ko‘paytirish">+</button></div>
        <input type="range" id="c-range" min="${range.min}" max="${range.max}" value="${s.count}" style="width:100%;margin-top:14px">
        <div class="row" style="margin-top:10px" id="c-pop">${(range.popular || []).map((n) => `<button type="button" class="chip" data-n="${n}">${n} <small>${E.fmt(priceOf(n))}</small></button>`).join('')}</div>
        <div class="hint">${range.min} dan ${range.max} gacha istalgan son. Muqova va reja slaydi bu songa kirmaydi (kirish va xulosa kiradi).</div>`;
    } else {
      size = `<div class="row" id="c-pop">${opt.sizes.map((z) => `<button type="button" class="chip ${parseInt(z.key, 10) === s.count ? 'on' : ''}" data-n="${E.esc(z.key)}">${E.esc(z.label)} <small>${E.fmt(z.price)} so‘m</small></button>`).join('')}</div>
        <div class="hint">Tayyor rasmli shablonlar ${opt.sizes.map((z) => z.key).join(', ')} slaydda tayyorlanadi. Muqova va reja slaydi bu songa kirmaydi (kirish va xulosa kiradi).</div>`;
    }

    const authorPrefs = `<label class="lab" for="author">Ism-familiya <span class="hint-i">(taqdimotning muqovasiga yoziladi)</span></label>
        <input class="fld" id="author" maxlength="80" placeholder="Ism Familiya" value="${E.esc(s.author)}">
        <label class="lab" for="prefs" style="margin-top:18px">AI ga taqdimot qanday bo‘lishini tushuntiring <span class="hint-i">(ixtiyoriy)</span></label>
        <textarea class="fld" id="prefs" rows="3" maxlength="1000" placeholder="Auditoriya, maqsad, ohang, misollar yoki alohida talablarni erkin yozing."></textarea>
        <div class="row" style="margin-top:8px" id="pref-ex">${PREF_EXAMPLES.map((t) => `<button type="button" class="chip sm" data-t="${E.esc(t)}">+ ${E.esc(t)}</button>`).join('')}</div>`;

    view.innerHTML = `
      <div class="types" id="types">${chips}</div>
      <form class="cols" id="cf" autocomplete="off">
        <div class="steps">
          ${stepCard(1, 'Mavzu va til', '', `<label class="lab" for="topic">Taqdimot mavzusi</label>
            <textarea class="fld" id="topic" rows="2" maxlength="300" placeholder="${E.esc(TOPIC_HINT[key] || '')}" required>${E.esc(s.topic)}</textarea>
            <div style="margin-top:14px">${langSel}</div>`)}
          ${stepCard(2, 'Manba', 'AI nimaga tayanadi', sourceBody)}
          ${stepCard(3, 'Dizayn', premium ? 'uslub va rang' : 'orqa fon', design)}
          ${stepCard(4, 'Slaydlar soni', '', size)}
          ${stepCard(5, 'Muallif va istaklar', '', authorPrefs)}
        </div>
        <div class="side">
          <div class="card panel"><div class="lab">Ko‘rinishi</div><div class="pv" id="pv"></div><div class="hint" id="pv-note"></div></div>
          <div class="card panel" style="margin-top:16px">
            <b style="font-size:17px">Buyurtma</b>
            <div id="sum" style="margin-top:12px"></div>
            <div id="s-note" style="margin-top:12px"></div>
            <button class="btn block" id="go" type="submit" style="margin-top:16px">Yaratish</button>
            <p class="hint" style="text-align:center;margin-top:12px">Taxminan ${opt.eta_minutes || 3} daqiqa. Tayyor fayl Telegramga ham yuboriladi.</p>
          </div>
        </div>
      </form>`;

    const trunc = (t, n) => (t.length > n ? t.slice(0, n - 1) + '…' : t);
    const price = () => (premium ? priceOf(s.count) : ((opt.sizes.find((x) => parseInt(x.key, 10) === s.count) || opt.sizes[0]).price));
    const activeTheme = () => themeOf(s.theme) || themeOf((s.suggest.theme || {}).key) || catalog.themes[0];
    const langShown = () => (s.lang ? langLabel(s.lang) : (s.suggest.language ? langLabel(s.suggest.language) + ' (avto)' : 'Avto'));

    function preview() {
      const pv = $('pv'), title = trunc(s.topic.trim() || 'Taqdimot mavzusi shu yerda', 70), by = s.author.trim();
      if (!premium) {
        const t = catalog.templates.find((x) => x.id === s.template);
        pv.className = 'pv'; pv.style.cssText = `background:#fff url('${t ? t.url : ''}') center/cover`;
        pv.innerHTML = `<div class="pvt" style="color:#0C1226;background:rgba(255,255,255,.78);padding:8px 12px;border-radius:8px;max-width:78%">${E.esc(title)}${by ? `<small>${E.esc(by)}</small>` : ''}</div>`;
        $('pv-note').textContent = t ? 'Orqa fon: ' + t.name : '';
        return;
      }
      const th = activeTheme() || {background: '#fff', accent: '#2457FF', heading: '#0C1226'};
      let bg = th.background, ink = th.heading, extra = '', font = '';
      if (s.style === 'qorongu') { bg = '#111827'; ink = '#fff'; }
      if (s.style === 'jurnal') { font = "font-family:Georgia,'Times New Roman',serif;"; bg = th.background; }
      if (s.style === 'blok') { extra = `<div class="pvblock" style="background:${th.accent}"></div>`; }
      if (s.style === 'kontur') { extra = `<div class="pvframe" style="border-color:${th.heading}"></div>`; }
      pv.className = 'pv'; pv.style.cssText = `background:${bg};${font}`;
      pv.innerHTML = `${extra}<div class="pvbar" style="background:${th.accent}"></div>
        <div class="pvt" style="color:${s.style === 'blok' ? '#fff' : ink}">${E.esc(title)}${by ? `<small style="color:${s.style === 'blok' ? '#fff' : th.accent}">${E.esc(by)}</small>` : ''}</div>`;
      const st = catalog.styles.find((x) => x.key === s.style);
      $('pv-note').textContent = `${st ? st.label : ''} uslubi · ${th.label.split(' — ')[0]}${s.theme ? '' : ' (avto)'}`;
    }

    function summary() {
      const p = price(), bal = me.balance;
      const rows = [['Mavzu', trunc(s.topic.trim() || '—', 60)], ['Til', langShown()],
        ['Manba', s.src.kind === 'ai' ? 'AI o‘zi yozadi' : (s.src.label || (s.src.text ? 'Sizning matningiz' : '—'))],
        premium ? ['Uslub', ((catalog.styles.find((x) => x.key === s.style) || {}).label) || ''] : ['Orqa fon', ((catalog.templates.find((x) => x.id === s.template) || {}).name) || ''],
        premium ? ['Rang', ((activeTheme() || {}).label || '').split(' — ')[0] + (s.theme ? '' : ' (avto)')] : ['Qo‘shimcha', [s.icons ? 'ikonkalar' : '', s.plan ? 'reja slaydi' : ''].filter(Boolean).join(', ') || '—'],
        ['Slaydlar', s.count + ' ta'], ['Muallif', trunc(s.author.trim() || 'ko‘rsatilmaydi', 40)]];
      $('sum').innerHTML = rows.map((r) => `<div class="sum"><span style="color:var(--mute)">${r[0]}</span><b style="text-align:right;max-width:62%">${E.esc(r[1])}</b></div>`).join('') +
        `<div class="sum" style="border-top:1px solid var(--line);padding-top:10px;margin-top:10px"><span style="color:var(--mute)">Narx</span><b>${E.fmt(p)} so‘m</b></div>
         <div class="sum"><span style="color:var(--mute)">Balansingiz</span><b>${E.fmt(bal)} so‘m</b></div>`;
      $('s-note').innerHTML = bal >= p ? '' :
        `<div class="note wait">Yetmaydi: yana <b>${E.fmt(p - bal)} so‘m</b> kerak. <a class="link" href="#/wallet">Hamyonni to‘ldirish</a></div>`;
    }
    const refresh = () => { if ($('pv')) { preview(); summary(); } };

    function setCount(n) {
      s.count = Math.max(range.min, Math.min(range.max, n));
      if ($('c-num')) { $('c-num').textContent = s.count; $('c-range').value = s.count; }
      document.querySelectorAll('#c-pop .chip').forEach((c) => c.classList.toggle('on', parseInt(c.dataset.n, 10) === s.count));
      summary();
    }

    // Mavzu → til va rang tavsiyasi (bot ham shunday tavsiya qiladi)
    let timer = null, seq = 0;
    function suggest() {
      clearTimeout(timer);
      const topic = s.topic.trim();
      if (topic.length < 3) { s.suggest = {language: '', theme: null}; autoNotes(); refresh(); return; }
      timer = setTimeout(async () => {
        const my = ++seq;
        try {
          const r = await E.api('/suggest', {json: {topic}});
          if (my !== seq) return;
          s.suggest = {language: r.language, theme: r.theme};
        } catch (e) { return; }
        autoNotes(); refresh();
      }, 450);
    }
    function autoNotes() {
      const n = $('auto-note');
      if (!n) return;
      n.textContent = !s.lang && s.suggest.language ? `Mavzuga qarab aniqlandi: ${langLabel(s.suggest.language)}. Kerak bo‘lsa, yuqoridan o‘zgartiring.` : '';
      const at = $('auto-theme');
      if (at) at.textContent = s.suggest.theme ? s.suggest.theme.label.split(' — ')[0] : 'mavzuga qarab';
    }

    // Manba paneli
    function srcPanel() {
      const box = $('src-panel'), k = s.src.kind;
      if (k === 'ai') { box.innerHTML = ''; return; }
      if (k === 'text') {
        box.innerHTML = `<textarea class="fld" id="src-text" rows="6" maxlength="60000" placeholder="O‘z matningizni yoki fikrlaringizni shu yerga yozing yoki joylang…">${E.esc(s.src.text)}</textarea>
          <div class="hint" id="src-count"></div>`;
        const area = $('src-text'), count = () => { s.src.words = area.value.trim() ? area.value.trim().split(/\s+/).length : 0; $('src-count').textContent = s.src.words + ' so‘z'; };
        count();
        area.oninput = () => { s.src.text = area.value; s.src.label = ''; count(); summary(); };
        return;
      }
      if (s.src.text && s.src.kind === k) {
        box.innerHTML = `<div class="note ok">✓ ${E.esc(s.src.label)} · ${E.fmt(s.src.words)} so‘z <button type="button" class="link" id="src-clear" style="margin-left:8px">Olib tashlash</button></div>`;
        $('src-clear').onclick = () => { s.src = {kind: k, text: '', label: '', words: 0}; srcPanel(); summary(); };
        return;
      }
      if (k === 'file') {
        box.innerHTML = `<div class="drop" id="src-drop"><div style="font-weight:700">Faylni shu yerga tashlang yoki tanlang</div>
          <div class="hint">PDF, DOCX yoki PPTX · 10 MB gacha</div><input type="file" id="src-file" accept=".pdf,.docx,.pptx" style="margin-top:10px"></div><div id="src-out" style="margin-top:10px"></div>`;
        const send = (f) => upload(() => { const form = new FormData(); form.append('file', f, f.name); return {form}; });
        $('src-file').onchange = (e) => { if (e.target.files[0]) send(e.target.files[0]); };
        const drop = $('src-drop');
        ['dragenter', 'dragover'].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.add('over'); }));
        ['dragleave', 'drop'].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.remove('over'); }));
        drop.addEventListener('drop', (e) => { const f = e.dataTransfer.files[0]; if (f) send(f); });
        return;
      }
      box.innerHTML = `<div class="row"><input class="fld" id="src-url" placeholder="https://..." style="flex:1;min-width:200px"><button type="button" class="btn out sm" id="src-get">Matnni olish</button></div>
        <div class="hint">Bir nechta havolani bo‘sh joy bilan ajratib yozish mumkin (5 tagacha).</div><div id="src-out" style="margin-top:10px"></div>`;
      $('src-get').onclick = () => upload(() => ({json: {urls: $('src-url').value}}));
    }
    async function upload(make) {
      const out = $('src-out'), kindNow = s.src.kind;
      out.innerHTML = '<span class="spin"></span> &nbsp;Matn o‘qilmoqda…';
      try {
        const r = await E.api('/source', make());
        if (s.src.kind !== kindNow) return;
        s.src = {kind: kindNow, text: r.text, label: r.label || (kindNow === 'url' ? 'Sayt' : 'Fayl'), words: r.words};
        srcPanel(); summary();
      } catch (e) {
        out.innerHTML = `<div class="note bad">${E.esc(e.message)}</div>`;
        if (e.code === 'auth') E.login();
      }
    }

    // Hodisalar
    $('types').onclick = (e) => { const b = e.target.closest('[data-kind]'); if (b) renderForm(b.dataset.kind, s.topic); };
    $('topic').oninput = (e) => { s.topic = e.target.value; refresh(); suggest(); };
    $('lang').onchange = (e) => { s.lang = e.target.value; autoNotes(); summary(); };
    $('author').oninput = (e) => { s.author = e.target.value; refresh(); };
    $('prefs').oninput = (e) => { s.prefs = e.target.value; };
    $('pref-ex').onclick = (e) => {
      const b = e.target.closest('[data-t]'); if (!b) return;
      const area = $('prefs'); area.value = (area.value.trim() ? area.value.trim().replace(/[.;,]?$/, '; ') : '') + b.dataset.t; s.prefs = area.value;
    };
    $('srcs').onclick = (e) => {
      const b = e.target.closest('.src'); if (!b || b.dataset.k === s.src.kind) return;
      s.src = {kind: b.dataset.k, text: '', label: '', words: 0};
      document.querySelectorAll('#srcs .src').forEach((x) => x.classList.toggle('on', x === b));
      srcPanel(); summary();
    };
    if ($('styles')) $('styles').onclick = (e) => {
      const b = e.target.closest('.styl'); if (!b) return; s.style = b.dataset.k;
      document.querySelectorAll('#styles .styl').forEach((x) => x.classList.toggle('on', x === b)); refresh();
    };
    if ($('themes')) $('themes').onclick = (e) => {
      const b = e.target.closest('.thm'); if (!b) return; s.theme = b.dataset.k;
      document.querySelectorAll('#themes .thm').forEach((x) => x.classList.toggle('on', x === b)); refresh();
    };
    if ($('tpls')) $('tpls').onclick = (e) => {
      const b = e.target.closest('.tpl'); if (!b) return; s.template = b.dataset.id;
      document.querySelectorAll('#tpls .tpl').forEach((x) => x.classList.toggle('on', x === b)); refresh();
    };
    if ($('t-icons')) $('t-icons').onclick = (e) => { s.icons = !s.icons; e.currentTarget.classList.toggle('on', s.icons); summary(); };
    if ($('t-plan')) $('t-plan').onclick = (e) => { s.plan = !s.plan; e.currentTarget.classList.toggle('on', s.plan); summary(); };
    if ($('c-minus')) {
      $('c-minus').onclick = () => setCount(s.count - 1);
      $('c-plus').onclick = () => setCount(s.count + 1);
      $('c-range').oninput = (e) => setCount(parseInt(e.target.value, 10));
    }
    $('c-pop').onclick = (e) => { const b = e.target.closest('[data-n]'); if (b) setCount(parseInt(b.dataset.n, 10)); };

    teardown = () => { clearTimeout(timer); seq++; };
    autoNotes(); refresh(); if (s.topic) suggest();

    $('cf').onsubmit = async (ev) => {
      ev.preventDefault();
      const btn = $('go'), note = $('s-note');
      const fail = (msg) => { note.innerHTML = `<div class="note bad">${E.esc(msg)}</div>`; };
      if (s.topic.trim().length < 3) return fail('Mavzu kamida 3 ta belgidan iborat bo‘lsin.');
      if (s.src.kind === 'text' && s.src.text.trim().length < 20) return fail('Matn juda qisqa. Ko‘proq yozing yoki «AI o‘zi yozadi» ni tanlang.');
      if ((s.src.kind === 'file' || s.src.kind === 'url') && !s.src.text) return fail(s.src.kind === 'file' ? 'Avval faylni yuklang yoki «AI o‘zi yozadi» ni tanlang.' : 'Avval havoladan matnni oling yoki «AI o‘zi yozadi» ni tanlang.');
      btn.disabled = true; btn.innerHTML = '<span class="spin" style="width:16px;height:16px;border-width:2px;border-top-color:#fff;border-color:rgba(255,255,255,.4)"></span>&nbsp; Yuborilmoqda…';
      const params = {topic: s.topic.trim(), language: s.lang, author: s.author.trim(), preferences: s.prefs.trim(), slide_count: s.count,
        source_text: s.src.kind === 'ai' ? '' : s.src.text, source_label: s.src.kind === 'ai' ? '' : s.src.label};
      if (premium) Object.assign(params, {style: s.style, theme: s.theme});
      else Object.assign(params, {template: s.template, icons: s.icons, plan_slide: s.plan});
      try {
        const res = await E.api('/jobs', {json: {kind: key, params}});
        me.balance = res.balance;
        E.header('app');
        E.toast('Buyurtma qabul qilindi');
        location.hash = '#/job/' + res.job.id;
      } catch (e) {
        btn.disabled = false; btn.textContent = 'Yaratish';
        note.innerHTML = `<div class="note bad">${E.esc(e.message)}${e.code === 'no_balance' ? ' <a class="link" href="#/wallet">Hamyonni to‘ldirish</a>' : ''}</div>`;
        if (e.code === 'auth') E.login();
      }
    };
  }


  // ─────────────────────────────────────────── «AI ishlayapti» animatsiyasi
  // Boshi va oxiri bilinmaydi: hamma harakat davriy va o'rtadan boshlanadi (manfiy kechikish), matn va
  // kursor tinimsiz yuradi. Bu bezak: haqiqiy sayt nomlari ko'rsatilmaydi.
  const AIW_LINES = [['🔎', 'Mavzu bo‘yicha manbalar qidirilmoqda'], ['📖', 'Ilmiy maqolalar o‘qilmoqda'],
    ['📊', 'Statistik ma’lumotlar solishtirilmoqda'], ['🧮', 'Raqamlar tekshirilmoqda'], ['🗂', 'Fikrlar tartibga solinmoqda'],
    ['✍️', 'Matn yozilmoqda'], ['🖼', 'Mos rasm tanlanmoqda'], ['🎨', 'Ranglar uyg‘unlashtirilmoqda'],
    ['📐', 'Joylashuv sozlanmoqda'], ['🔗', 'Boshqa sahifalar bilan bog‘lanmoqda'], ['🧪', 'Natija tekshirilmoqda']];
  const AIW_TABS = ['Ensiklopediya', 'Statistika', 'Ilmiy maqolalar'];

  function aiwSkeleton(kind) {
    const line = (w, hi) => `<i class="ln${hi ? ' hi' : ''}" style="width:${w}%"></i>`;
    const head = `<i class="ln h" style="width:46%"></i>${line(30)}`;
    const paras = [92, 88, 95, 70, 90, 84, 60].map((w, i) => line(w, i % 3 === 1)).join('');
    let block = '';
    if (kind === 1) block = `<div class="bars">${[40, 72, 55, 90, 63, 80].map((h) => `<b style="height:${h}%"></b>`).join('')}</div>`;
    else if (kind === 2) block = `<div class="pic"></div><div class="rowg">${line(28)}${line(36)}${line(22)}</div>`;
    else block = `<div class="tbl">${[0, 1, 2, 3].map(() => `<span></span><span></span><span></span>`).join('')}</div>`;
    const page = `${head}${paras}${block}${paras}${block}`;
    return `<div class="aiw-var v${kind}"><div class="aiw-scroll"><div>${page}</div><div>${page}</div></div></div>`;
  }

  function aiwHtml(label) {
    const feed = AIW_LINES.map((l) => `<div class="fl"><span>${l[0]}</span>${l[1]}<em></em></div>`).join('');
    return `<div class="aiw">
      <div class="aiw-win">
        <div class="aiw-bar"><span class="dots"><i></i><i></i><i></i></span>
          <div class="aiw-tabs">${AIW_TABS.map((t, k) => `<span class="aiw-tab t${k}">${t}</span>`).join('')}</div></div>
        <div class="aiw-url"><span class="mag">⌕</span><span class="typed"></span><span class="caret"></span></div>
        <div class="aiw-page">${[0, 1, 2].map(aiwSkeleton).join('')}<div class="aiw-scan"></div><div class="aiw-cursor"><i></i></div></div>
      </div>
      <div class="aiw-feed"><div class="aiw-feedin"><div>${feed}</div><div>${feed}</div></div></div>
      <div class="aiw-msg"><span class="aiw-dots"><i></i><i></i><i></i></span> ${label || 'AI ishlamoqda'}</div>
    </div>`;
  }

  // Animatsiyani ishga tushiradi; to'xtatuvchi funksiyani qaytaradi.
  function aiwStart(root, topic) {
    const typed = root.querySelector('.typed'), page = root.querySelector('.aiw-page'), cur = root.querySelector('.aiw-cursor');
    if (!typed || !page || !cur) return () => {};
    const base = (topic || 'mavzu').trim().slice(0, 34);
    const queries = ['statistika', 'tadqiqotlar', 'rivojlanishi', 'misollar', 'rasmlar'].map((w) => base + ' ' + E.tr(w));
    let alive = true, qi = 0, ci = 0, dir = 1, timer = null;
    function tick() {
      if (!alive) return;
      const q = queries[qi % queries.length];
      let wait = 55 + Math.random() * 50;
      if (dir === 1) {
        ci++; typed.textContent = q.slice(0, ci);
        if (ci >= q.length) { dir = -1; wait = 1500; }
      } else {
        ci--; typed.textContent = q.slice(0, Math.max(ci, 0)); wait = 22;
        if (ci <= 0) { dir = 1; qi++; wait = 350; }
      }
      timer = setTimeout(tick, wait);
    }
    qi = Math.floor(Math.random() * queries.length); ci = Math.floor(queries[qi % queries.length].length * Math.random());
    tick();
    let raf = 0;
    const phase = Math.random() * 100;
    function move(ts) {
      if (!alive) return;
      const t = ts / 1000 + phase, w = page.clientWidth, h = page.clientHeight;
      const x = w * (0.5 + 0.32 * Math.sin(t * 0.8) + 0.12 * Math.sin(t * 2.1));
      const y = h * (0.5 + 0.34 * Math.sin(t * 0.55 + 1.3) + 0.1 * Math.cos(t * 1.7));
      cur.style.transform = `translate(${x.toFixed(1)}px,${y.toFixed(1)}px)`;
      raf = requestAnimationFrame(move);
    }
    raf = requestAnimationFrame(move);
    return () => { alive = false; clearTimeout(timer); cancelAnimationFrame(raf); };
  }

  // ───────────────────────────────────────────── Taqdimot sahifasi: kutish → varaqlash → o'zgartirish
  async function jobPage(id) {
    view.innerHTML = '<span class="spin"></span>';
    let data;
    try { data = await E.api('/jobs/' + encodeURIComponent(id)); } catch (e) {
      view.innerHTML = `<div class="note bad">${E.esc(e.message)}</div><p><a class="link" href="#/docs">← Hujjatlarim</a></p>`; return;
    }
    const job = data.job;
    if (job.status === 'queued' || job.status === 'running') return jobWaiting(job);
    if (job.status === 'failed') {
      view.innerHTML = `<div class="card panel" style="max-width:640px;margin:10px auto"><span class="pill bad">Bajarilmadi</span>
        <h2 style="margin:12px 0 6px">${E.esc(job.title)}</h2><p style="color:#4A5272">${E.esc(job.error)}</p>
        <a class="btn out" href="#/create">Qayta urinish</a></div>`;
      return;
    }
    let info = {available: false};
    if (job.kind === 'premium_presentation' || job.kind === 'simple_presentation') {
      try { info = await E.api('/jobs/' + encodeURIComponent(id) + '/deck'); } catch (e) { info = {available: false}; }
    }
    if (!info.available) {
      view.innerHTML = `<div class="card panel" style="max-width:640px;margin:10px auto;text-align:center"><span class="pill ok">Tayyor</span>
        <h2 style="margin:12px 0 6px">${E.esc(job.title)}</h2>
        <p style="color:#4A5272">Fayl Telegramga ham yuborilgan.${(job.kind === 'premium_presentation' || job.kind === 'simple_presentation') ? ' Bu taqdimot ko‘rib chiqish uchun saqlanmagan.' : ''}</p>
        <a class="btn" href="/api/v1/jobs/${E.esc(job.id)}/file">Yuklab olish</a>
        <p><a class="link" href="#/docs">← Hujjatlarim</a></p></div>`;
      return;
    }
    return deckViewer(job, info);
  }

  function jobWaiting(job) {
    view.innerHTML = `<div class="card panel" style="max-width:760px;margin:6px auto">
      <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:baseline">
        <h2 style="margin:0;font-size:22px">${E.esc(job.title)}</h2><span class="hint" id="wst" style="margin:0"></span></div>
      <p class="hint" style="margin:6px 0 16px">Taqdimot tayyorlanmoqda. Bu sahifani yopib ketishingiz mumkin: tayyor bo‘lgach «Hujjatlarim» da ko‘rinadi va Telegramga ham keladi.</p>
      <div id="aiw">${aiwHtml('AI taqdimotni tayyorlamoqda')}</div></div>`;
    const stop = aiwStart(view.querySelector('#aiw'), job.title);
    teardown = stop;
    const poll = async () => {
      try {
        const d = await E.api('/jobs/' + encodeURIComponent(job.id));
        const st = document.getElementById('wst'); if (st) st.textContent = d.job.stage_text || '';
        if (d.job.status === 'queued' || d.job.status === 'running') { pollTimer = setTimeout(poll, 2500); return; }
        await refreshBalance();
        stop(); teardown = null;
        if (location.hash === '#/job/' + job.id) jobPage(job.id);
      } catch (e) { pollTimer = setTimeout(poll, 4000); }
    };
    pollTimer = setTimeout(poll, 2500);
  }

  async function deckViewer(job, info) {
    const id = job.id, deck = info.deck, price = info.price;
    const prompts = (catalog.rewrite && catalog.rewrite.prompts) || [];
    const st = {n: 1, version: deck.version, slides: deck.slides, busy: info.busy, panel: false, history: deck.history || []};
    view.innerHTML = `
      <div class="vtop"><a class="link" href="#/docs">← Hujjatlarim</a>
        <div class="vname"><b>${E.esc(job.title)}</b> <span class="hint" id="v-count"></span></div>
        <a class="btn sm" href="/api/v1/jobs/${E.esc(id)}/file">Yuklab olish</a></div>
      <div class="vgrid" id="vgrid">
        <div class="vmain">
          <div class="stage" id="stage"><img id="simg" alt="" draggable="false">
            <button type="button" class="nav prev" id="prev" aria-label="Oldingi">‹</button>
            <button type="button" class="nav next" id="next" aria-label="Keyingi">›</button>
            <span class="num" id="snum"></span><button type="button" class="full" id="sfull" aria-label="To‘liq ekran">⛶</button>
            <div class="stage-ai" id="sai" hidden></div></div>
          <div class="thumbs" id="thumbs"></div>
          <div class="row" style="margin-top:14px;justify-content:space-between">
            ${deck.editable ? `<button type="button" class="btn out" id="edit">✏️ Sahifani o‘zgartirish <small style="opacity:.7;font-weight:700">· ${E.fmt(price)} so‘m</small></button>`
              : '<span class="hint" style="margin:0">Ko‘rinish taxminiy: PowerPoint da biroz farq qilishi mumkin. Sahifani AI ga qayta yozdirish «Zamonaviy taqdimot» da mavjud.</span>'}
            <span class="hint" style="margin:0">Fayl ${Math.max(0, Math.round((info.expires_at * 1000 - Date.now()) / 3600000))} soat saqlanadi.</span></div>
        </div>
        ${deck.editable ? `<aside class="vside card" id="vside" hidden>
          <div class="chathead"><b>AI bilan sahifani o‘zgartirish</b><button type="button" class="link" id="vclose" aria-label="Yopish">✕</button></div>
          <div class="chat" id="chat"></div>
          <div class="chips-row" id="vprompts">${prompts.map((p) => `<button type="button" class="chip sm" data-t="${E.esc(p.text)}">${p.icon} ${E.esc(p.text)}</button>`).join('')}</div>
          <form id="vform" class="chatform"><textarea class="fld" id="vtext" rows="2" maxlength="500" placeholder="Sahifa qanday bo‘lishini yozing…"></textarea>
            <button class="btn" id="vsend" type="submit">Yuborish</button></form>
          <div class="hint" id="vnote" style="margin:8px 0 0">Har bir o‘zgartirish ${E.fmt(price)} so‘m. Natija chiqmasa, pul qaytariladi.</div>
        </aside>` : ''}
      </div>`;
    const $ = (x) => document.getElementById(x);
    const img = (n) => `/api/v1/jobs/${encodeURIComponent(id)}/slide/${n}?v=${st.version}`;
    const total = st.slides.length;
    let stopAnim = null, rewritingN = 0, ctxFor = 0;

    $('thumbs').innerHTML = st.slides.map((sl) => `<button type="button" class="th" data-n="${sl.n}" title="${E.esc(sl.title)}"><img loading="lazy" alt="" src="${img(sl.n)}"><span>${sl.n}</span></button>`).join('');
    function show(n) {
      st.n = Math.max(1, Math.min(total, n));
      $('simg').src = img(st.n); $('snum').textContent = st.n + ' / ' + total; $('v-count').textContent = total + ' sahifa';
      document.querySelectorAll('#thumbs .th').forEach((t) => t.classList.toggle('on', parseInt(t.dataset.n, 10) === st.n));
      const cur = document.querySelector('#thumbs .th.on'); if (cur && cur.scrollIntoView) cur.scrollIntoView({block: 'nearest', inline: 'center'});
      $('prev').disabled = st.n === 1; $('next').disabled = st.n === total;
      const plan = st.n === 2 && total > 3;
      if ($('edit')) {
        $('edit').disabled = plan || !!st.busy;
        $('edit').title = plan ? 'Reja sahifasi boshqa sahifalar sarlavhalaridan o‘zi yig‘iladi' : '';
      }
      overlay();
      if (st.panel && !st.busy && ctxFor !== st.n) context();
    }
    function overlay() {
      const box = $('sai'), on = st.busy && rewritingN === st.n;
      if (on && box.hidden) { box.hidden = false; box.innerHTML = aiwHtml('AI ' + st.n + '-sahifani qayta yozmoqda'); stopAnim = aiwStart(box, (st.slides[st.n - 1] || {}).title || job.title); }
      if (!on && !box.hidden) { box.hidden = true; box.innerHTML = ''; if (stopAnim) { stopAnim(); stopAnim = null; } }
      document.querySelectorAll('#thumbs .th').forEach((t) => t.classList.toggle('busy', !!st.busy && parseInt(t.dataset.n, 10) === rewritingN));
    }
    $('thumbs').onclick = (e) => { const b = e.target.closest('.th'); if (b) show(parseInt(b.dataset.n, 10)); };
    $('prev').onclick = () => show(st.n - 1); $('next').onclick = () => show(st.n + 1);
    $('sfull').onclick = () => { const el = $('stage'); (el.requestFullscreen || el.webkitRequestFullscreen || (() => {})).call(el); };
    const onKey = (e) => {
      if (/^(TEXTAREA|INPUT)$/.test((e.target || {}).tagName || '')) return;
      if (e.key === 'ArrowLeft') show(st.n - 1); else if (e.key === 'ArrowRight') show(st.n + 1);
    };
    document.addEventListener('keydown', onKey);
    let x0 = null;
    $('stage').addEventListener('touchstart', (e) => { x0 = e.touches[0].clientX; }, {passive: true});
    $('stage').addEventListener('touchend', (e) => { if (x0 === null) return; const dx = e.changedTouches[0].clientX - x0; x0 = null; if (Math.abs(dx) > 50) show(st.n + (dx < 0 ? 1 : -1)); }, {passive: true});

    if (!deck.editable) {      // oddiy taqdimot: faqat ko'rish
      teardown = () => document.removeEventListener('keydown', onKey);
      show(1);
      return;
    }

    // ----- chat
    const bubble = (who, html) => { const d = document.createElement('div'); d.className = 'msg ' + who; d.innerHTML = html; $('chat').appendChild(d); $('chat').scrollTop = 1e6; return d; };
    function context() {
      ctxFor = st.n;
      const sl = st.slides[st.n - 1] || {};
      const old = document.getElementById('ctx'); if (old) old.remove();
      if (st.n === 2 && total > 3) {
        const d = bubble('ai', '📋 Reja sahifasi boshqa sahifalar sarlavhalaridan o‘zi yig‘iladi. Kerakli sahifani o‘zgartirsangiz, reja ham yangilanadi.'); d.id = 'ctx'; return;
      }
      const d = bubble('ai', `<b>${st.n}-sahifa</b>${sl.title ? ' · «' + E.esc(sl.title) + '»' : ''}<br>Bu sahifa qanday bo‘lishini yozing yoki pastdagi tayyor iltimoslardan birini tanlang. Qolgan sahifalar hisobga olinadi.`);
      d.id = 'ctx';
    }
    function history() {
      st.history.forEach((h) => { bubble('me', `<small>${h.index}-sahifa</small><br>${E.esc(h.instruction)}`); bubble('ai', `✅ ${h.index}-sahifa yangilandi${h.title ? ' · «' + E.esc(h.title) + '»' : ''}`); });
    }
    function open(flag) {
      st.panel = flag; $('vside').hidden = !flag; $('vgrid').classList.toggle('chat-on', flag);
      if (flag) { if (!$('chat').children.length) history(); if (ctxFor !== st.n) context(); setTimeout(() => $('vtext').focus({preventScroll: false}), 50); }
    }
    $('edit').onclick = () => open(!st.panel);
    $('vclose').onclick = () => open(false);
    $('vprompts').onclick = (e) => { const b = e.target.closest('[data-t]'); if (!b) return; $('vtext').value = b.dataset.t; send(); };
    $('vform').onsubmit = (e) => { e.preventDefault(); send(); };
    $('vtext').onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };

    function lock(on) { $('vsend').disabled = on; $('vtext').disabled = on; document.querySelectorAll('#vprompts .chip').forEach((c) => (c.disabled = on)); $('edit').disabled = on || (st.n === 2 && total > 3); }

    async function send() {
      const text = $('vtext').value.trim();
      if (st.busy) return;
      if (text.length < 3) { $('vnote').innerHTML = '<span style="color:var(--bad)">Sahifa qanday bo‘lishini yozing.</span>'; return; }
      if (st.n === 2 && total > 3) return;
      if (me.balance < price) {
        $('vnote').innerHTML = `<span style="color:var(--bad)">Balans yetmaydi: ${E.fmt(price)} so‘m kerak.</span> <a class="link" href="#/wallet">Hamyonni to‘ldirish</a>`; return;
      }
      const n = st.n;
      $('vtext').value = ''; lock(true);
      bubble('me', `<small>${n}-sahifa</small><br>${E.esc(text)}`);
      const wait = bubble('ai', '<span class="aiw-dots"><i></i><i></i><i></i></span> AI ishlamoqda…');
      let res;
      try { res = await E.api('/jobs/' + encodeURIComponent(id) + '/rewrite', {json: {index: n, instruction: text}}); }
      catch (err) {
        wait.innerHTML = '⚠️ ' + E.esc(err.message) + (err.code === 'no_balance' ? ' <a class="link" href="#/wallet">Hamyonni to‘ldirish</a>' : '');
        lock(false); if (err.code === 'auth') E.login(); return;
      }
      me.balance = res.balance; E.header('app');
      st.busy = res.job.id; rewritingN = n; overlay(); show(st.n);
      const rid = res.job.id;
      const poll = async () => {
        let d;
        try { d = await E.api('/jobs/' + encodeURIComponent(rid)); } catch (err) { pollTimer = setTimeout(poll, 3500); return; }
        const status = d.job.status;
        if (status === 'queued' || status === 'running') { pollTimer = setTimeout(poll, 2200); return; }
        st.busy = null; rewritingN = 0;
        await refreshBalance();
        if (status === 'done') {
          try {
            const fresh = await E.api('/jobs/' + encodeURIComponent(id) + '/deck');
            st.version = fresh.deck.version; st.slides = fresh.deck.slides;
            document.querySelectorAll('#thumbs .th').forEach((t) => { t.querySelector('img').src = img(parseInt(t.dataset.n, 10)); t.title = (st.slides[parseInt(t.dataset.n, 10) - 1] || {}).title || ''; });
          } catch (err) { st.version += 1; }
          wait.innerHTML = `✅ ${n}-sahifa tayyor. Yuklab olish tugmasi yangilangan faylni beradi.`;
          E.toast(n + '-sahifa yangilandi');
        } else {
          wait.innerHTML = '⚠️ ' + E.esc(d.job.error || 'Bajarilmadi');
        }
        ctxFor = 0; lock(false); show(st.n);
      };
      pollTimer = setTimeout(poll, 2200);
    }

    teardown = () => { document.removeEventListener('keydown', onKey); if (stopAnim) stopAnim(); };
    show(1);
    if (st.busy) {   // sahifa qayta ochilganda davom etayotgan o'zgartirish bo'lsa
      lock(true);
      const rid = st.busy; rewritingN = 0; bubble('ai', '<span class="aiw-dots"><i></i><i></i><i></i></span> Avvalgi o‘zgartirish davom etmoqda…');
      open(true);
      const poll = async () => {
        let d; try { d = await E.api('/jobs/' + encodeURIComponent(rid)); } catch (err) { pollTimer = setTimeout(poll, 3500); return; }
        if (d.job.status === 'queued' || d.job.status === 'running') { pollTimer = setTimeout(poll, 2500); return; }
        if (location.hash === '#/job/' + id) jobPage(id);
      };
      pollTimer = setTimeout(poll, 2500);
    }
  }


  // ───────────────────────────────────────────── Xush kelibsiz (birinchi kirish) va Profil
  const AUTH_ERRORS = {
    cancelled: 'Kirish bekor qilindi.', state: 'Kirish seansi eskirgan. Qaytadan urinib ko‘ring.',
    google_failed: 'Google bilan kirib bo‘lmadi. Birozdan keyin qayta urining.', email: 'Google akkauntingizdagi email tasdiqlanmagan.',
    google_off: 'Google bilan kirish hozircha yoqilmagan.', rate: 'Juda ko‘p urinish. Bir daqiqadan keyin qayta urining.',
    google_taken: 'Bu Google akkaunt boshqa akkauntga ulangan.', has_google: 'Sizga allaqachon Google akkaunt ulangan.', auth: 'Avval saytga kiring.'};

  function authErrorToast() {
    const q = new URLSearchParams(location.search), h = (location.hash.split('?')[1] || '');
    const code = q.get('auth_error') || new URLSearchParams(h).get('auth_error');
    if (!code) return;
    E.toast(AUTH_ERRORS[code] || 'Kirishda xatolik yuz berdi.');
    const clean = location.pathname + location.hash.split('?')[0];
    try { history.replaceState(null, '', clean); } catch (e) { /* muhim emas */ }
  }

  function langBlock(current, id) {
    return `<div class="bigl" id="${id}">${E.langs().map((l) => `<button type="button" class="chip ${l.key === current ? 'on' : ''}" data-lang="${l.key}">${l.name}</button>`).join('')}</div>`;
  }

  async function welcome() {
    const cfgMe = await E.me(true);
    if (!cfgMe) { view.innerHTML = ''; return loginCard(); }
    view.innerHTML = `<div class="card panel welcome">
      <h2>Xush kelibsiz!</h2>
      <p style="color:#4A5272;margin:0 0 6px">Hisobingiz ochildi. Qulay tilni tanlang va ismingizni tekshiring: ism taqdimot muqovasiga yoziladi.</p>
      ${langBlock(E.lang(), 'w-langs')}
      <div style="text-align:left"><label class="lab" for="w-name">Ismingiz</label>
        <input class="fld" id="w-name" maxlength="80" value="${E.esc(cfgMe.name)}"></div>
      <button class="btn block" id="w-go" style="margin-top:18px">Davom etish</button>
      <p class="hint" style="margin-top:12px">Telegramni keyinroq profilingizdan ulashingiz mumkin: balans va hujjatlaringiz birlashadi.</p></div>`;
    document.getElementById('w-langs').onclick = (e) => {
      const b = e.target.closest('[data-lang]'); if (!b) return;
      E.setLang(b.dataset.lang);
      document.querySelectorAll('#w-langs [data-lang]').forEach((x) => x.classList.toggle('on', x === b));
    };
    document.getElementById('w-go').onclick = async () => {
      const btn = document.getElementById('w-go'); btn.disabled = true;
      try {
        await E.api('/profile', {json: {name: document.getElementById('w-name').value, language: E.lang()}});
        await refreshBalance();
        location.hash = '#/create';
      } catch (e) { btn.disabled = false; E.toast(e.message); }
    };
  }

  async function profile() {
    view.innerHTML = '<span class="spin"></span>';
    let data;
    try { data = (await E.api('/profile')).profile; } catch (e) {
      if (e.code === 'auth' || e.status === 401) { view.innerHTML = ''; return loginCard(); }
      view.innerHTML = `<div class="note bad">${E.esc(e.message)}</div>`; return;
    }
    const tgRow = data.telegram
      ? `<div class="prow"><div class="who"><span class="ic">${E.TG.replace('currentColor', '#229ED9')}</span><div><b>Telegram</b><small>${data.username ? '@' + E.esc(data.username) : 'Ulangan'}</small></div></div><span class="pill ok">Ulangan</span></div>`
      : `<div class="prow"><div class="who"><span class="ic">${E.TG.replace('currentColor', '#229ED9')}</span><div><b>Telegram</b><small>Ulanmagan: fayl Telegramga ham keladi, bot bilan umumiy balans</small></div></div><button type="button" class="btn sm out" id="p-tg">Telegramni ulash</button></div>`;
    const gRow = data.google
      ? `<div class="prow"><div class="who"><span class="ic">${E.GOOGLE_G}</span><div><b>Google</b><small>${E.esc(data.email)}</small></div></div><span class="pill ok">Ulangan</span></div>`
      : `<div class="prow"><div class="who"><span class="ic">${E.GOOGLE_G}</span><div><b>Google</b><small>Ulanmagan</small></div></div>${data.google_enabled ? '<a class="btn sm out" id="p-g" href="#">Google ni ulash</a>' : '<span class="pill soon">Tez orada</span>'}</div>`;
    view.innerHTML = `<div class="profile">
      <div class="card panel"><b style="font-size:18px">Profil</b>
        <div style="margin-top:16px"><label class="lab" for="p-name">Ism</label>
          <div class="row"><input class="fld" id="p-name" maxlength="80" value="${E.esc(data.name)}" style="flex:1;min-width:180px"><button class="btn sm" id="p-save" type="button">Saqlash</button></div></div>
        <div style="margin-top:20px"><div class="lab">Til</div>${langBlock(data.language, 'p-langs')}
          <div class="hint" style="margin-top:-4px">Sayt va bot shu tilda ochiladi.</div></div>
        <div style="margin-top:14px;display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
          <span><span class="hint" style="margin:0">Balans</span> <b>${E.fmt(data.balance)} so‘m</b></span>
          <a class="btn sm out" href="#/wallet">Hamyonni to‘ldirish</a></div>
      </div>
      <div class="card panel"><b style="font-size:18px">Ulangan akkauntlar</b>
        <div style="margin-top:6px">${gRow}${tgRow}</div>
        <div id="p-note" style="margin-top:10px"></div>
        <button class="btn ghost block" id="p-out" type="button" style="margin-top:16px">Chiqish</button>
      </div></div>`;
    const $ = (x) => document.getElementById(x);
    $('p-save').onclick = async () => {
      try { await E.api('/profile', {json: {name: $('p-name').value}}); await refreshBalance(); E.toast('Saqlandi'); }
      catch (e) { E.toast(e.message); }
    };
    $('p-langs').onclick = async (e) => {
      const b = e.target.closest('[data-lang]'); if (!b) return;
      document.querySelectorAll('#p-langs [data-lang]').forEach((x) => x.classList.toggle('on', x === b));
      await E.chooseLang(b.dataset.lang);
      E.toast('Til saqlandi');
    };
    $('p-out').onclick = () => E.logout();
    if ($('p-g')) $('p-g').onclick = (e) => { e.preventDefault(); location.href = '/api/v1/auth/google/start?intent=attach&lang=' + E.lang(); };
    if ($('p-tg')) $('p-tg').onclick = async () => {
      const note = $('p-note'); note.innerHTML = '<span class="spin"></span>';
      let link;
      try { link = await E.api('/profile/telegram-link', {method: 'POST'}); } catch (e) { note.innerHTML = `<div class="note bad">${E.esc(e.message)}</div>`; return; }
      note.innerHTML = `<div class="note wait">Telegramda botni oching va <b>Start</b> hamda «Ha, ulash» tugmasini bosing. Bu sahifa o‘zi yangilanadi. <a class="link" target="_blank" rel="noopener" href="${E.esc(link.url)}">Botni ochish</a></div>`;
      window.open(link.url, '_blank', 'noopener');
      const until = Date.now() + link.expires_in * 1000;
      const check = async () => {
        if (location.hash !== '#/profile') return;
        try {
          const d = (await E.api('/profile')).profile;
          if (d.telegram) { await refreshBalance(); E.toast('Telegram ulandi'); return profile(); }
        } catch (e) { /* tarmoq: keyingi urinishda */ }
        if (Date.now() < until) pollTimer = setTimeout(check, 3000);
      };
      pollTimer = setTimeout(check, 3000);
    };
  }

  function loginCard() {
    view.innerHTML = `<div class="card panel" style="max-width:520px;margin:20px auto;text-align:center">
      <h2 style="margin:0 0 8px">Kirish yoki ro‘yxatdan o‘tish</h2>
      <p style="color:#4A5272;margin:0 0 18px">Google yoki Telegram bilan kiring. Hisobingiz bo‘lmasa, birinchi kirishda o‘zi ochiladi.</p>
      <button class="btn" id="lg">Davom etish</button></div>`;
    document.getElementById('lg').onclick = () => E.login();
    E.header('app');
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
    const open = ((j.kind === 'premium_presentation' || j.kind === 'simple_presentation') && j.status !== 'failed') ? `<a class="btn sm out" href="#/job/${E.esc(j.id)}">${j.status === 'done' ? 'Ko‘rish' : 'Ochish'}</a> ` : '';
    return `<div class="job"><div><div class="t">${E.esc(j.title)}</div><div class="hint" style="margin:2px 0 0">${E.esc(kindLabel(j.kind))} · ${E.fmt(j.price)} so‘m</div></div><div>${status}</div><div>${open}${action}</div></div>`;
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
    authErrorToast();
    if (!me) { loginCard(); return; }
    try { catalog = await E.api('/catalog'); } catch (e) { view.innerHTML = `<div class="note bad">${E.esc(e.message)}</div>`; return; }
    E.header('app');
    window.addEventListener('hashchange', route);
    route();
  })();
})();
