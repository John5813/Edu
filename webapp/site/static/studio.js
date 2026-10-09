/* Edufayl bosh sahifasi: yaratish oynasi («studiya»).
 *
 * Mavzu yozilgach oyna kattalashadi va tanlangan xizmatga kerakli hamma narsa shu yerning o'zida so'raladi
 * (ilgari bu alohida /app#/create sahifasida edi). Buyurtma berilgach oyna o'rnida «Slaydlar ustaxonasi»
 * animatsiyasi (forge.js) ochiladi va tayyor bo'lgach natija shu yerda ko'rsatiladi.
 * Kirmagan mehmon ham hamma narsani tanlay oladi: «Yaratish» da kirish so'raladi, tanlovlar saqlanib qoladi.
 */
(function () {
  'use strict';
  const E = window.Edu;
  const $ = (id) => document.getElementById(id);
  const DRAFT = 'edu_draft', LIVE = 'edu_live_job';

  // Bosh sahifadagi qisqa nomlar (katalogdagi to'liq nom o'rniga)
  const SHORT = {premium_presentation: 'Taqdimot', independent_work: 'Mustaqil ish', referat: 'Referat', article: 'Maqola',
    thesis: 'Tezis', course_work: 'Kurs ishi', diploma_work: 'Diplom ishi', bitiruv_ishi: 'Bitiruv ishi', dissertatsiya: 'Dissertatsiya'};
  const TOPIC_HINT = {
    premium_presentation: "Masalan: Kiberxavfsizlik va shaxsiy ma'lumotlar himoyasi",
    independent_work: 'Masalan: Iqtisodiyotda raqamlashtirish', referat: 'Masalan: Globallashuv va iqtisodiyot',
    article: "Masalan: Sun'iy intellektning ta'limdagi o'rni", thesis: "Masalan: Yoshlar tadbirkorligini qo'llab-quvvatlash",
    course_work: 'Masalan: Korxonada xarajatlarni boshqarish', diploma_work: 'Masalan: Bank xizmatlarini raqamlashtirish',
    bitiruv_ishi: "Masalan: Kichik biznesni rivojlantirish yo'llari", dissertatsiya: 'Masalan: Innovatsion iqtisodiyotning nazariy asoslari',
  };
  const DOC_LANG = {uz: "O'zbek (lotin)", ru: 'Русский', en: 'English'};
  const SOURCES = [
    {key: 'ai', label: '✨ AI o‘zi yozadi', note: 'Faqat mavzu bo‘yicha'},
    {key: 'text', label: '📝 Matn yozaman', note: 'O‘z fikr yoki konspektingiz'},
    {key: 'file', label: '📎 Fayl yuklayman', note: 'PDF, DOCX yoki PPTX'},
    {key: 'url', label: '🔗 Sayt havolasi', note: 'Maqola yoki sahifa'},
  ];
  // Matn hajmi: rang alohida tanlanmaydi (mavzuga qarab), uslub ko'rinishni, hajm esa matn va rasm nisbatini belgilaydi.
  const VOLUMES = [
    {key: 'kop', label: '📝 Matn hajmi: ko‘p', short: 'ko‘p', note: 'Har slaydda fikr batafsil ochiladi, har 10 slaydda 4 ta rasm'},
    {key: 'kam', label: '🖼 Matn hajmi: o‘rtacha', short: 'o‘rtacha', note: 'Aniq fikrlar, infografika va rasmlar ko‘proq'},
  ];
  const PREF_EXAMPLES = ['Investorlar uchun ishonchli', 'Ko‘proq vizual', 'Qisqa va ta’sirli', 'Talabalar uchun sodda tilda', 'Raqam va faktlar ko‘proq'];

  let catalog = null, me = null, timer = null, seq = 0, pollTimer = null, forge = null;
  const S = {kind: 'premium_presentation', topic: '', lang: '', src: {kind: 'ai', text: '', label: '', words: 0},
    style: 'toza', volume: 'kop', count: 10, author: '', prefs: '', size: '', extras: [], pstyle: 'murakkab', trial: false,
    univ: '', fac: '', grp: '', suggest: {language: '', theme: null}};

  const kindOf = (k) => catalog && catalog.kinds.find((x) => x.key === k);
  const opt = () => (kindOf(S.kind) || {}).options || {};
  const premium = () => opt().form === 'presentation';
  // Bepul sinov taqdimoti: har akkauntga bir marta (kirmagan mehmonga ham taklif qilinadi — kirgach tekshiriladi).
  const canTrial = () => premium() && !!(catalog && catalog.free_trial) && (!me || me.free_trial);
  const trialOn = () => S.trial && canTrial();
  const trialSlides = () => ((catalog && catalog.free_trial) || {}).slides || 5;
  const trunc = (t, n) => (t.length > n ? t.slice(0, n - 1) + '…' : t);
  const spin = '<span class="spin" style="width:16px;height:16px;border-width:2px;border-top-color:#fff;border-color:rgba(255,255,255,.4)"></span>';

  // ───────────────────────────────────────────── ish turlari
  function chips() {
    const bot = (catalog && catalog.bot) || 'Edufayl_bot';
    $('kind-chips').innerHTML = catalog.kinds.map((k) =>
      `<button type="button" class="chip${k.key === S.kind ? ' on' : ''}" data-kind="${E.esc(k.key)}">${E.esc(SHORT[k.key] || k.label)}</button>`).join('') +
      ['Loyiha ishi', 'Kitob tarjimasi'].map((t) => `<a class="chip soon" data-bot target="_blank" rel="noopener" href="https://t.me/${E.esc(bot)}">${t} <small>botda</small></a>`).join('');
  }
  function pickKind(key, keep) {
    if (!kindOf(key)) return;
    const changed = S.kind !== key;
    S.kind = key;
    const o = opt();
    if (changed || !keep || !(o.sizes || []).some((z) => z.key === S.size)) {
      S.size = (o.sizes && o.sizes[0] && o.sizes[0].key) || '';
      if (changed || !keep) S.extras = [];
    }
    if (o.languages && !premium() && S.lang && !o.languages.some((l) => (l.key || l) === S.lang)) S.lang = '';
    document.querySelectorAll('#kind-chips [data-kind]').forEach((b) => b.classList.toggle('on', b.dataset.kind === key));
    $('topic').placeholder = TOPIC_HINT[key] || '';   // tarjimani i18n.js o'zi qo'yadi
    if (isOpen()) render();
  }

  // ───────────────────────────────────────────── oynani kattalashtirish
  const hero = () => document.querySelector('.hero');
  const isOpen = () => hero().classList.contains('studio-on');
  function open() {
    if (!catalog) return;
    if (!isOpen()) { hero().classList.add('studio-on'); render(); }
  }

  function section(title, hint, body, id) {
    return `<section class="st-sec"${id ? ` id="${id}"` : ''}><div class="st-lab">${title}${hint ? ` <span class="hint-i">${hint}</span>` : ''}</div>${body}</section>`;
  }
  const chipRow = (id, items, on) => `<div class="st-chips" id="${id}">${items.map((x) =>
    `<button type="button" class="chip${x.key === on ? ' on' : ''}" data-v="${E.esc(x.key)}">${E.esc(x.label)}${x.small ? ` <small>${E.esc(x.small)}</small>` : ''}</button>`).join('')}</div>`;

  function render() {
    const o = opt();
    let html = '';
    if (premium()) {
      const range = catalog.premium_range || {min: 5, max: 30, popular: [10, 15, 20]};
      if (canTrial()) {
        html += trialOn()
          ? `<div class="trial on" id="trial"><div class="tx"><b>🎁 Imtiyoz yoqildi</b><span>${trialSlides()} slaydli taqdimot bepul. Rasmlar qo‘yilmaydi, slaydlar sonini o‘zgartirib bo‘lmaydi. Keyin slaydni AI ga qayta yozdirish alohida pullik.</span></div><button type="button" class="link" id="trial-off">Bekor qilish</button></div>`
          : `<div class="trial" id="trial"><div class="tx"><b>🎁 Bepul sinov taqdimoti</b><span>Har bir foydalanuvchiga bir marta: ${trialSlides()} slaydli taqdimot bepul (rasmsiz).</span></div><button type="button" class="btn sm" id="trial-on">Imtiyozdan foydalanish</button></div>`;
      }
      html += section('Taqdimot tili', '', chipRow('st-lang', [{key: '', label: 'Avto'}].concat(catalog.languages), S.lang) + '<div class="hint" id="auto-note"></div>');
      html += section('Manba', 'AI nimaga tayanadi', `<div class="srcs" id="srcs">${SOURCES.map((x) =>
        `<button type="button" class="src${x.key === S.src.kind ? ' on' : ''}" data-k="${x.key}"><b>${x.label}</b><small>${x.note}</small></button>`).join('')}</div><div id="src-panel"></div>`);
      html += section('Ko‘rinish uslubi', '', `<div class="st-styles" id="styles">${catalog.styles.map((st) =>
        `<button type="button" class="st-sty${st.key === S.style ? ' on' : ''}" data-k="${E.esc(st.key)}"><img src="/static/home-style-${E.esc(st.key)}.jpg" alt="" loading="lazy" width="960" height="540"><b>${E.esc(st.label)}</b></button>`).join('')}</div>`);
      if (!trialOn()) html += section('Matn hajmi', '(rang mavzuga qarab avtomatik tanlanadi)', `<div class="srcs" id="volumes">${VOLUMES.map((x) =>
        `<button type="button" class="src${x.key === S.volume ? ' on' : ''}" data-k="${x.key}"><b>${x.label}</b><small>${x.note}</small></button>`).join('')}</div>`);
      html += trialOn() ? section('Slaydlar soni', '', `<div class="st-count locked"><div class="cval"><b id="c-num">${trialSlides()}</b><span>slayd</span></div></div>
        <div class="hint">Bepul sinovda slaydlar soni o‘zgarmaydi. Boshqa son kerak bo‘lsa, imtiyozni bekor qiling.</div>`) : section('Slaydlar soni', '', `<div class="st-count"><button type="button" class="cbtn" id="c-minus" aria-label="Kamaytirish">−</button>
          <div class="cval"><b id="c-num">${S.count}</b><span>slayd</span></div><button type="button" class="cbtn" id="c-plus" aria-label="Ko‘paytirish">+</button>
          <input type="range" id="c-range" min="${range.min}" max="${range.max}" value="${S.count}"></div>
        <div class="st-chips" id="c-pop">${(range.popular || []).map((n) => `<button type="button" class="chip sm${n === S.count ? ' on' : ''}" data-n="${n}">${n}</button>`).join('')}</div>
        <div class="hint">${range.min} dan ${range.max} gacha istalgan son. Muqova va reja slaydi bu songa kirmaydi (kirish va xulosa kiradi).</div>`);
      html += section('Ism-familiya', '(taqdimotning muqovasiga yoziladi)', `<input class="fld" id="author" maxlength="80" placeholder="Ism Familiya" value="${E.esc(S.author)}">`);
      html += section('AI ga taqdimot qanday bo‘lishini tushuntiring', '(ixtiyoriy)', `<textarea class="fld" id="prefs" rows="2" maxlength="1000" placeholder="Auditoriya, maqsad, ohang, misollar yoki alohida talablarni erkin yozing.">${E.esc(S.prefs)}</textarea>
        <div class="st-chips" id="pref-ex">${PREF_EXAMPLES.map((t) => `<button type="button" class="chip sm" data-t="${E.esc(t)}">+ ${E.esc(t)}</button>`).join('')}</div>`);
    } else {
      const langs = (o.languages || ['uz', 'ru', 'en']).map((l) => ({key: l.key || l, label: l.label || DOC_LANG[l] || l}));
      if (!S.lang || !langs.some((l) => l.key === S.lang)) S.lang = langs[0].key;
      html += section('Til', '', chipRow('st-lang', langs, S.lang));
      if (o.form === 'thesis') {
        html += section('Muallif ismi', '', `<input class="fld" id="author" maxlength="80" placeholder="Ism Familiya" value="${E.esc(S.author)}">`);
        html += section('Universitet', '', `<input class="fld" id="univ" maxlength="120" value="${E.esc(S.univ)}">`);
        html += `<div class="st-two">${section('Fakultet', '(ixtiyoriy)', `<input class="fld" id="fac" maxlength="120" value="${E.esc(S.fac)}">`)}${section('Guruh', '(ixtiyoriy)', `<input class="fld" id="grp" maxlength="40" value="${E.esc(S.grp)}">`)}</div>`;
      } else {
        html += section('Hajmi', '', chipRow('st-size', o.sizes.map((z) => ({key: z.key, label: z.label, small: E.fmt(z.price)})), S.size));
        if (o.plan_styles) html += section('Reja usuli', '', chipRow('st-pstyle', o.plan_styles, S.pstyle));
        if (o.extras && o.extras.length) {
          html += section("Qo'shimchalar", '', `<div class="st-chips" id="extras">${o.extras.map((x) =>
            `<button type="button" class="chip${S.extras.includes(x.key) ? ' on' : ''}" data-x="${E.esc(x.key)}">${E.esc(x.label)}${x.price ? ` <small>+${E.fmt(x.price)}</small>` : ''}</button>`).join('')}</div>`);
        }
        html += section('Muallif ismi', '(muqovaga yoziladi)', `<input class="fld" id="author" maxlength="80" placeholder="Ism Familiya" value="${E.esc(S.author)}">`);
      }
    }
    const k = kindOf(S.kind);
    $('studio').innerHTML = `<div class="st-main">${html}</div>
      <aside class="st-side">
        ${premium() ? '<div class="pv" id="pv"></div><div class="hint" id="pv-note"></div>' : ''}
        <div class="st-sum" id="sum"></div>
        <div class="st-go"><div class="st-total"><span>Narx</span><b id="s-price"></b></div>
          <button class="btn block" id="go" type="submit">${trialOn() ? 'Bepul yaratish' : 'Yaratish'}</button></div>
        <div id="s-note"></div>
        <p class="hint st-eta">${(o.eta_minutes && k && k.heavy) ? `Taxminan ${o.eta_minutes} daqiqa (katta hujjatlar navbat bilan tayyorlanadi). Tayyor fayl Telegramga ham yuboriladi.` : `Taxminan ${o.eta_minutes || 3} daqiqa. Tayyor fayl Telegramga ham yuboriladi.`}</p>
      </aside>`;
    bind();
    if (premium()) { srcPanel(); autoNotes(); preview(); }
    summary();
  }

  // ───────────────────────────────────────────── hodisalar
  function oneOf(id, set) {
    const box = $(id); if (!box) return;
    box.onclick = (e) => {
      const b = e.target.closest('[data-v]'); if (!b) return;
      box.querySelectorAll('[data-v]').forEach((x) => x.classList.toggle('on', x === b));
      set(b.dataset.v); summary();
    };
  }
  function bind() {
    const inp = (id, key, after) => { if ($(id)) $(id).oninput = (e) => { S[key] = e.target.value; if (after) after(); save(); }; };
    inp('author', 'author', () => { if (premium()) preview(); summary(); });
    inp('prefs', 'prefs'); inp('univ', 'univ'); inp('fac', 'fac'); inp('grp', 'grp');
    if ($('trial-on')) $('trial-on').onclick = () => { S.trial = true; render(); save(); };
    if ($('trial-off')) $('trial-off').onclick = () => { S.trial = false; render(); save(); };
    oneOf('st-lang', (v) => { S.lang = v; autoNotes(); save(); });
    oneOf('st-size', (v) => { S.size = v; save(); });
    oneOf('st-pstyle', (v) => { S.pstyle = v; save(); });
    if ($('extras')) $('extras').onclick = (e) => {
      const b = e.target.closest('[data-x]'); if (!b) return;
      const k = b.dataset.x;
      S.extras = S.extras.includes(k) ? S.extras.filter((x) => x !== k) : S.extras.concat(k);
      b.classList.toggle('on', S.extras.includes(k)); summary(); save();
    };
    if ($('srcs')) $('srcs').onclick = (e) => {
      const b = e.target.closest('.src'); if (!b || b.dataset.k === S.src.kind) return;
      S.src = {kind: b.dataset.k, text: '', label: '', words: 0};
      document.querySelectorAll('#srcs .src').forEach((x) => x.classList.toggle('on', x === b));
      srcPanel(); summary();
    };
    if ($('styles')) $('styles').onclick = (e) => {
      const b = e.target.closest('.st-sty'); if (!b) return; S.style = b.dataset.k;
      document.querySelectorAll('#styles .st-sty').forEach((x) => x.classList.toggle('on', x === b)); preview(); summary(); save();
    };
    if ($('volumes')) $('volumes').onclick = (e) => {
      const b = e.target.closest('.src'); if (!b) return; S.volume = b.dataset.k;
      document.querySelectorAll('#volumes .src').forEach((x) => x.classList.toggle('on', x === b)); preview(); summary(); save();
    };
    if ($('c-minus')) {
      $('c-minus').onclick = () => setCount(S.count - 1);
      $('c-plus').onclick = () => setCount(S.count + 1);
      $('c-range').oninput = (e) => setCount(parseInt(e.target.value, 10));
      $('c-pop').onclick = (e) => { const b = e.target.closest('[data-n]'); if (b) setCount(parseInt(b.dataset.n, 10)); };
    }
    if ($('pref-ex')) $('pref-ex').onclick = (e) => {
      const b = e.target.closest('[data-t]'); if (!b) return;
      const area = $('prefs');
      area.value = (area.value.trim() ? area.value.trim().replace(/[.;,]?$/, '; ') : '') + E.tr(b.dataset.t);
      S.prefs = area.value; save();
    };
  }
  function setCount(n) {
    const range = catalog.premium_range || {min: 5, max: 30};
    S.count = Math.max(range.min, Math.min(range.max, n || range.min));
    $('c-num').textContent = S.count; $('c-range').value = S.count;
    document.querySelectorAll('#c-pop .chip').forEach((c) => c.classList.toggle('on', parseInt(c.dataset.n, 10) === S.count));
    summary(); save();
  }

  // ───────────────────────────────────────────── taqdimot: tavsiya, ko'rinish, manba
  const langLabel = (k) => ((catalog.languages.find((l) => l.key === k)) || {}).label || k;
  const themeOf = (k) => catalog.themes.find((t) => t.key === k);
  const activeTheme = () => themeOf((S.suggest.theme || {}).key) || catalog.themes[0];
  const volumeOf = (k) => VOLUMES.find((x) => x.key === k) || VOLUMES[0];

  function suggest() {
    clearTimeout(timer);
    const topic = S.topic.trim();
    if (topic.length < 3) { S.suggest = {language: '', theme: null}; autoNotes(); return; }
    timer = setTimeout(async () => {
      const my = ++seq;
      try {
        const r = await E.api('/suggest', {json: {topic}});
        if (my !== seq) return;
        S.suggest = {language: r.language, theme: r.theme};
      } catch (e) { return; }
      autoNotes(); preview(); summary();
    }, 450);
  }
  function autoNotes() {
    const n = $('auto-note'); if (!n) return;
    n.textContent = !S.lang && S.suggest.language ? `Mavzuga qarab aniqlandi: ${langLabel(S.suggest.language)}. Kerak bo‘lsa, yuqoridan o‘zgartiring.` : '';
  }
  function preview() {
    const pv = $('pv'); if (!pv) return;
    const title = trunc(S.topic.trim() || 'Taqdimot mavzusi shu yerda', 70), by = S.author.trim();
    const th = activeTheme() || {background: '#fff', accent: '#2457FF', heading: '#0C1226', label: ''};
    let bg = th.background, ink = th.heading, extra = '', font = '';
    if (S.style === 'qorongu') { bg = '#111827'; ink = '#fff'; }
    if (S.style === 'jurnal') font = "font-family:Georgia,'Times New Roman',serif;";
    if (S.style === 'blok') extra = `<div class="pvblock" style="background:${th.accent}"></div>`;
    if (S.style === 'kontur') extra = `<div class="pvframe" style="border-color:${th.heading}"></div>`;
    pv.style.cssText = `background:${bg};${font}`;
    const white = S.style === 'blok';
    pv.innerHTML = `${extra}<div class="pvbar" style="background:${th.accent}"></div>
      <div class="pvt" style="color:${white ? '#fff' : ink}">${E.esc(title)}${by ? `<small style="color:${white ? '#fff' : th.accent}">${E.esc(by)}</small>` : ''}</div>`;
    const st = catalog.styles.find((x) => x.key === S.style);
    $('pv-note').textContent = `${st ? st.label : ''} uslubi · ${volumeOf(S.volume).short}`;
    autoNotes();
  }

  function srcPanel() {
    const box = $('src-panel'), k = S.src.kind;
    if (!box) return;
    if (k === 'ai') { box.innerHTML = '<div class="hint">Manba bersangiz, taqdimot aynan shu matnga tayanadi. Bermasangiz, AI mavzu bo‘yicha o‘zi yozadi.</div>'; return; }
    if (k === 'text') {
      box.innerHTML = `<textarea class="fld" id="src-text" rows="5" maxlength="60000" placeholder="O‘z matningizni yoki fikrlaringizni shu yerga yozing yoki joylang…">${E.esc(S.src.text)}</textarea><div class="hint" id="src-count"></div>`;
      const area = $('src-text'), count = () => { S.src.words = area.value.trim() ? area.value.trim().split(/\s+/).length : 0; $('src-count').textContent = S.src.words + ' so‘z'; };
      count();
      area.oninput = () => { S.src.text = area.value; S.src.label = ''; count(); summary(); };
      return;
    }
    if (S.src.text) {
      box.innerHTML = `<div class="note ok">✓ ${E.esc(S.src.label)} · ${E.fmt(S.src.words)} so‘z <button type="button" class="link" id="src-clear" style="margin-left:8px">Olib tashlash</button></div>`;
      $('src-clear').onclick = () => { S.src = {kind: k, text: '', label: '', words: 0}; srcPanel(); summary(); };
      return;
    }
    if (k === 'file') {
      box.innerHTML = `<label class="drop" id="src-drop"><b>Faylni shu yerga tashlang yoki tanlang</b>
        <span class="hint">PDF, DOCX yoki PPTX · 10 MB gacha</span><input type="file" id="src-file" accept=".pdf,.docx,.pptx"></label><div id="src-out"></div>`;
      const send = (f) => upload(() => { const form = new FormData(); form.append('file', f, f.name); return {form}; });
      $('src-file').onchange = (e) => { if (e.target.files[0]) send(e.target.files[0]); };
      const drop = $('src-drop');
      ['dragenter', 'dragover'].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.add('over'); }));
      ['dragleave', 'drop'].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.remove('over'); }));
      drop.addEventListener('drop', (e) => { const f = e.dataTransfer.files[0]; if (f) send(f); });
      return;
    }
    box.innerHTML = `<div class="st-url"><input class="fld" id="src-url" placeholder="https://..."><button type="button" class="btn out sm" id="src-get">Matnni olish</button></div>
      <div class="hint">Bir nechta havolani bo‘sh joy bilan ajratib yozish mumkin (5 tagacha).</div><div id="src-out"></div>`;
    $('src-get').onclick = () => upload(() => ({json: {urls: $('src-url').value}}));
  }
  async function upload(make) {
    const out = $('src-out'), kindNow = S.src.kind;
    if (!me) { save(); E.login(); return; }        // fayl o'qish kirgan foydalanuvchiga ochiq
    out.innerHTML = '<span class="spin"></span> &nbsp;Matn o‘qilmoqda…';
    try {
      const r = await E.api('/source', make());
      if (S.src.kind !== kindNow) return;
      S.src = {kind: kindNow, text: r.text, label: r.label || (kindNow === 'url' ? 'Sayt' : 'Fayl'), words: r.words};
      srcPanel(); summary();
    } catch (e) {
      out.innerHTML = `<div class="note bad">${E.esc(e.message)}</div>`;
      if (e.code === 'auth') { save(); E.login(); }
    }
  }

  // ───────────────────────────────────────────── narx va xulosa
  function price() {
    const o = opt();
    if (trialOn()) return 0;
    if (premium()) return (catalog.premium_prices.find((p) => p.slides === S.count) || {}).price || 0;
    if (o.form === 'thesis') return o.price || 0;
    const z = (o.sizes || []).find((x) => x.key === S.size) || (o.sizes || [])[0] || {price: 0};
    return z.price + (o.extras || []).filter((x) => S.extras.includes(x.key)).reduce((a, x) => a + x.price, 0);
  }
  function summary() {
    if (!$('s-price')) return;
    const p = price(), o = opt();
    let rows = [];
    if (premium()) {
      rows = [['Til', S.lang ? langLabel(S.lang) : (S.suggest.language ? langLabel(S.suggest.language) + ' (avto)' : 'Avto')],
        ['Manba', S.src.kind === 'ai' ? 'AI o‘zi yozadi' : (S.src.label || (S.src.text ? 'Sizning matningiz' : '—'))],
        ['Uslub', ((catalog.styles.find((x) => x.key === S.style) || {}).label) || ''],
        ['Matn hajmi', trialOn() ? volumeOf('kop').short : volumeOf(S.volume).short],
        ['Slaydlar', (trialOn() ? trialSlides() : S.count) + ' ta']];
      if (trialOn()) rows.push(['Rasmlar', 'Yo‘q (bepul sinov)']);
    } else if (o.form !== 'thesis') {
      rows = [['Hajmi', ((o.sizes || []).find((x) => x.key === S.size) || {}).label || '']];
    }
    $('sum').innerHTML = rows.map((r) => `<div class="sum"><span>${r[0]}</span><b>${E.esc(r[1])}</b></div>`).join('') +
      (me ? `<div class="sum"><span>Balansingiz</span><b>${E.fmt(me.balance)} so‘m</b></div>` : '');
    $('s-price').textContent = trialOn() ? 'Bepul' : E.fmt(p) + ' so‘m';
    $('s-note').innerHTML = !me ? '<div class="note">Yaratish uchun kiring: hisob birinchi kirishda o‘zi ochiladi. Tanlovlaringiz saqlanib qoladi.</div>'
      : me.balance >= p ? '' : `<div class="note wait">Yetmaydi: yana <b>${E.fmt(p - me.balance)} so‘m</b> kerak. <a class="link" href="/app#/wallet">Hamyonni to‘ldirish</a></div>`;
  }

  // ───────────────────────────────────────────── qoralama (kirishdan keyin tanlovlar qaytadi)
  function save() {
    try { sessionStorage.setItem(DRAFT, JSON.stringify({...S, src: {...S.src}, suggest: undefined, t: Date.now()})); } catch (e) { /* maxfiy rejim */ }
  }
  function restore() {
    let d = null;
    try { d = JSON.parse(sessionStorage.getItem(DRAFT) || 'null'); } catch (e) { d = null; }
    if (!d || Date.now() - (d.t || 0) > 6 * 3600 * 1000) return false;
    Object.keys(S).forEach((k) => { if (k !== 'suggest' && d[k] !== undefined) S[k] = d[k]; });
    if (!VOLUMES.some((x) => x.key === S.volume)) S.volume = 'kop';
    return !!S.topic;
  }

  // ───────────────────────────────────────────── buyurtma
  function params() {
    const o = opt();
    const p = {topic: S.topic.trim(), language: S.lang, author: S.author.trim()};
    if (premium()) {
      Object.assign(p, {preferences: S.prefs.trim(), slide_count: trialOn() ? trialSlides() : S.count, style: S.style, volume: trialOn() ? 'kop' : S.volume,
        source_text: S.src.kind === 'ai' ? '' : S.src.text, source_label: S.src.kind === 'ai' ? '' : S.src.label});
      if (trialOn()) p.trial = true;
    } else if (o.form === 'thesis') {
      Object.assign(p, {university: S.univ.trim(), faculty: S.fac.trim(), group: S.grp.trim()});
    } else {
      Object.assign(p, {size: S.size, extras: S.extras, plan_style: o.plan_styles ? S.pstyle : ''});
    }
    return p;
  }

  async function submit(ev) {
    ev.preventDefault();
    if (!catalog) return;
    S.topic = $('topic').value;
    if (S.topic.trim().length < 3) { E.toast('Mavzu kamida 3 ta belgidan iborat bo‘lsin'); $('topic').focus(); return; }
    if (!isOpen()) { open(); return; }
    let note = $('s-note'), btn = $('go');
    const fail = (msg) => { note.innerHTML = `<div class="note bad">${E.esc(msg)}</div>`; };
    if (premium()) {
      if (S.src.kind === 'text' && S.src.text.trim().length < 20) return fail('Matn juda qisqa. Ko‘proq yozing yoki «AI o‘zi yozadi» ni tanlang.');
      if ((S.src.kind === 'file' || S.src.kind === 'url') && !S.src.text) return fail(S.src.kind === 'file' ? 'Avval faylni yuklang yoki «AI o‘zi yozadi» ni tanlang.' : 'Avval havoladan matnni oling yoki «AI o‘zi yozadi» ni tanlang.');
    }
    if (opt().form === 'thesis' && !S.univ.trim()) return fail('Universitet nomini kiriting.');
    save();
    if (!me) { E.login(); return; }
    btn.disabled = true; btn.innerHTML = spin + '&nbsp; Yuborilmoqda…';
    try {
      const sent = params();
      const res = await E.api('/jobs', {json: {kind: S.kind, params: sent}});
      me.balance = res.balance;
      if (sent.trial) { me.free_trial = false; S.trial = false; }
      const count = sent.slide_count || S.count;
      E.header('home');
      try { sessionStorage.removeItem(DRAFT); sessionStorage.setItem(LIVE, JSON.stringify({id: res.job.id, kind: S.kind, count})); } catch (e) { /* ixtiyoriy */ }
      watch(res.job, S.kind, count);
    } catch (e) {
      btn.disabled = false; btn.textContent = trialOn() ? 'Bepul yaratish' : 'Yaratish';
      if (e.code === 'trial_used') { me.free_trial = false; S.trial = false; render(); }
      note = $('s-note');
      note.innerHTML = `<div class="note bad">${E.esc(e.message)}${e.code === 'no_balance' ? ' <a class="link" href="/app#/wallet">Hamyonni to‘ldirish</a>' : ''}</div>`;
      if (e.code === 'auth') E.login();
    }
  }

  // ───────────────────────────────────────────── tayyorlanish: animatsiya va natija
  function watch(job, kind, count) {
    const isDeck = kind === 'premium_presentation' || kind === 'simple_presentation';
    hero().classList.add('studio-on', 'forging');
    const box = $('forge-box');
    box.hidden = false;
    $('prompt-form').hidden = true;
    box.innerHTML = '<div id="forge-anim"></div><div id="forge-out" class="forge-out"></div>';
    box.scrollIntoView({behavior: 'smooth', block: 'start'});
    forge = E.forge($('forge-anim'), {topic: job.title, mode: isDeck ? 'slides' : 'pages', count, kind,
      label: (kindOf(kind) || {}).label || '', startedAt: job.created_at});
    forge.update(job);
    $('forge-out').innerHTML = '<p class="hint" style="text-align:center">Bu sahifani yopib ketishingiz mumkin: tayyor bo‘lgach «Hujjatlarim» da ko‘rinadi va Telegramga ham keladi.</p>';
    const poll = async () => {
      let d;
      try { d = await E.api('/jobs/' + encodeURIComponent(job.id)); } catch (e) { pollTimer = setTimeout(poll, 4000); return; }
      const j = d.job;
      forge.update(j);
      if (j.status === 'queued' || j.status === 'running') { pollTimer = setTimeout(poll, 2500); return; }
      try { sessionStorage.removeItem(LIVE); } catch (e) { /* ixtiyoriy */ }
      E.me(true).then(() => E.header('home'));
      if (j.status === 'failed') {
        forge.fail();
        $('forge-out').innerHTML = `<div class="note bad">${E.esc(j.error || 'Xatolik yuz berdi')}</div>
          <div class="forge-act"><button type="button" class="btn" id="f-again">Qayta urinish</button></div>`;
        $('f-again').onclick = reset;
        return;
      }
      await forge.finish(isDeck ? 'PPTX' : 'DOCX');
      $('forge-out').innerHTML = `<div class="forge-act">
          ${isDeck ? `<a class="btn" href="/app#/job/${E.esc(j.id)}">Ko‘rish va tahrirlash</a>` : ''}
          <a class="btn ${isDeck ? 'out' : ''}" href="/api/v1/jobs/${E.esc(j.id)}/file">Yuklab olish</a>
          <button type="button" class="btn ghost" id="f-new">Yangi mavzu</button></div>
        <p class="hint" style="text-align:center">Fayl Telegramga ham yuborilgan.</p>`;
      $('f-new').onclick = () => { S.topic = ''; $('topic').value = ''; reset(); };
    };
    pollTimer = setTimeout(poll, 1500);
  }
  function reset() {
    clearTimeout(pollTimer);
    if (forge) { forge.stop(); forge = null; }
    $('forge-box').hidden = true; $('forge-box').innerHTML = '';
    $('prompt-form').hidden = false;
    hero().classList.remove('forging');
    if (S.topic.trim()) render(); else hero().classList.remove('studio-on');
    $('topic').focus();
  }

  // ───────────────────────────────────────────── ishga tushirish
  async function init() {
    const form = $('prompt-form'), topic = $('topic');
    form.addEventListener('submit', submit);
    topic.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit ? form.requestSubmit() : submit(e); } });
    topic.addEventListener('input', () => {
      S.topic = topic.value;
      if (S.topic.trim().length >= 3) open();
      if (isOpen()) { if (premium()) { preview(); suggest(); } summary(); }
      save();
    });
    $('kind-chips').addEventListener('click', (e) => { const b = e.target.closest('[data-kind]'); if (b) { pickKind(b.dataset.kind); save(); } });
    try { catalog = await E.api('/catalog'); } catch (e) { return; }
    me = await E.me();
    if (!S.author && me && me.name) S.author = me.name;
    // Eski havolalar: /#yaratish?kind=course_work yoki /app#/create?kind=...
    const want = (location.hash.split('kind=')[1] || '').split('&')[0];
    const restored = restore();
    if (want && kindOf(want)) S.kind = want;
    if (!kindOf(S.kind)) S.kind = 'premium_presentation';
    chips();
    pickKind(S.kind, true);
    if (restored) { topic.value = S.topic; open(); if (premium()) suggest(); if (me) E.toast('Tanlovlaringiz saqlangan. «Yaratish» ni bosing.'); }
    let live = null;
    try { live = JSON.parse(sessionStorage.getItem(LIVE) || 'null'); } catch (e) { live = null; }
    if (live && me) {
      try {
        const d = await E.api('/jobs/' + encodeURIComponent(live.id));
        if (d.job.status === 'queued' || d.job.status === 'running') watch(d.job, live.kind, live.count);
        else sessionStorage.removeItem(LIVE);
      } catch (e) { try { sessionStorage.removeItem(LIVE); } catch (x) { /* ixtiyoriy */ } }
    }
    if (want || restored) document.getElementById('yaratish').scrollIntoView({block: 'start'});
    // Sahifadagi xizmat kartochkalari (#yaratish?kind=...): sahifa qayta yuklanmaydi, oyna o'sha xizmat bilan ochiladi.
    window.addEventListener('hashchange', () => {
      const k = (location.hash.split('kind=')[1] || '').split('&')[0];
      if (!k || !kindOf(k) || !$('forge-box').hidden) return;
      pickKind(k); save();
      try { history.replaceState(null, '', '#yaratish'); } catch (e) { /* ixtiyoriy */ }   // keyingi bosishda ham ishlasin
      document.getElementById('yaratish').scrollIntoView({behavior: 'smooth', block: 'start'});
      setTimeout(() => topic.focus({preventScroll: true}), 350);
    });
  }
  E.studio = {init};
})();
