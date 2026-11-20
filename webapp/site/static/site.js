/* Edufayl sayti: umumiy yordamchilar (API, kirish oynasi, sarlavha) */
(function () {
  'use strict';
  const Edu = (window.Edu = window.Edu || {});

  Edu.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  // Saytda varaqlanadigan taqdimotlar (Zamonaviy, Klassik). 3D — faqat yuklab olinadi (PowerPoint'da ochiladi).
  Edu.isDeck = (k) => k === 'premium_presentation' || k === 'simple_presentation';
  Edu.NOTE3D = '🧊 3D taqdimotni kompyuterdagi Microsoft PowerPoint (2019, 2021, 365) da «Slayd-shou» (F5) rejimida oching — telefonda 3D ko‘rinmaydi. Saytda varaqlash va tahrirlash bu xizmat uchun hozircha ishlamaydi.';
  Edu.fmt = (n) => Number(n || 0).toLocaleString('ru-RU').replace(/ /g, ' ');
  Edu.$ = (sel, root) => (root || document).querySelector(sel);

  Edu.api = async function (path, opts) {
    opts = opts || {};
    const init = {method: opts.method || 'GET', credentials: 'same-origin', headers: {}};
    if (opts.json !== undefined) {
      init.method = opts.method || 'POST';
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.json);
    }
    if (opts.form) { init.method = 'POST'; init.body = opts.form; }
    let res, data;
    try {
      res = await fetch('/api/v1' + path, init);
    } catch (e) {
      throw Object.assign(new Error('Aloqa yo‘q. Internetni tekshirib, qayta urining.'), {code: 'network'});
    }
    try {
      data = await res.json();
    } catch (e) {
      // Javob keldi, lekin JSON emas: sayt oldidagi Cloudflare'ning xato sahifasi (502/504/524) — internet emas, server.
      throw Object.assign(new Error('Server hozir javob bermadi. Birozdan keyin qayta urining.'),
        {code: 'bad_reply', status: res.status});
    }
    if (!res.ok || data.ok === false) {
      throw Object.assign(new Error(data.error || 'Xatolik yuz berdi'), {code: data.code || String(res.status), status: res.status, data});
    }
    return data;
  };

  Edu.toast = function (text) {
    const el = document.createElement('div');
    el.className = 'toast';
    el.textContent = text;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3600);
  };

  let meCache, cfgCache, chosenLang = '';
  Edu.me = async function (force) {
    if (meCache === undefined || force) {
      try { meCache = (await Edu.api('/me')).user || null; } catch (e) { meCache = null; }
      // Kirgan odamning tili akkauntida saqlangan (bot bilan bir xil): sayt ham shunda ochiladi. Mijoz shu sahifada
      // tilni o'zi tanlagan bo'lsa (javob kelguncha) — uning tanlovi qoladi va akkauntga yoziladi.
      if (meCache && meCache.language && meCache.language !== Edu.lang()) {
        if (chosenLang) {
          meCache.language = chosenLang;
          Edu.api('/profile', {json: {language: chosenLang}}).catch(() => {});
        } else Edu.setLang(meCache.language);
      }
    }
    return meCache;
  };

  Edu.authConfig = async function () {
    if (!cfgCache) { try { cfgCache = await Edu.api('/auth/config'); } catch (e) { cfgCache = {google: false, bot: ''}; } }
    return cfgCache;
  };

  // Tilni almashtiradi; kirgan bo'lsa profilga ham yozadi (bot tili ham shu bo'ladi).
  Edu.chooseLang = async function (lang) {
    chosenLang = lang;
    Edu.setLang(lang);
    if (meCache) {
      meCache.language = lang;
      try { await Edu.api('/profile', {json: {language: lang}}); } catch (e) { /* til baribir almashdi */ }
    }
  };

  const GOOGLE_G = '<svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>';
  const TG = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M21.5 4.3 2.9 11.5c-1.3.5-1.3 1.2-.2 1.5l4.7 1.5 1.8 5.6c.2.6.1.8.7.8.5 0 .7-.2 1-.5l2.3-2.3 4.7 3.5c.9.5 1.5.2 1.7-.8l3.1-14.6c.3-1.2-.5-1.8-1.2-1.4zM8.2 13.7l9.4-5.9c.4-.3.8-.1.5.2l-7.8 7z"/></svg>';
  Edu.GOOGLE_G = GOOGLE_G; Edu.TG = TG;

  function langChips(cls) {
    return Edu.langs().map((l) => '<button type="button" class="chip sm ' + (cls || '') + (l.key === Edu.lang() ? ' on' : '') + '" data-lang="' + l.key + '">' + l.name + '</button>').join('');
  }
  Edu.langChips = langChips;

  // Kirish va ro'yxatdan o'tish: Google yoki Telegram. Hisob birinchi kirishda o'zi ochiladi.
  Edu.login = function (next) {
    return new Promise((resolve) => {
      const modal = document.createElement('div');
      modal.className = 'modal';
      modal.innerHTML = '<div class="box login"><div class="lg-langs" id="lg-langs">' + langChips() + '</div>' +
        '<h3 style="margin:14px 0 6px;font-size:22px">Kirish yoki ro‘yxatdan o‘tish</h3>' +
        '<p style="margin:0 0 16px;color:#4A5272;font-size:14px">Hisobingiz bo‘lmasa, birinchi kirishda o‘zi ochiladi. Parol kerak emas.</p>' +
        '<div id="lg-google"></div>' +
        '<div class="or" id="lg-or" hidden><span>yoki</span></div>' +
        '<button type="button" class="btn out block" id="lg-tg">' + TG + '&nbsp; Telegram orqali kirish</button>' +
        '<div id="lg-body" style="margin-top:14px"></div>' +
        '<button class="link" id="lg-x" style="margin-top:14px">Yopish</button></div>';
      document.body.appendChild(modal);
      let stop = false;
      const close = (ok) => { stop = true; document.removeEventListener('edu:lang', relink); modal.remove(); resolve(ok); };
      modal.querySelector('#lg-x').onclick = () => close(false);
      modal.addEventListener('click', (e) => { if (e.target === modal) close(false); });
      modal.querySelector('#lg-langs').onclick = (e) => {
        const b = e.target.closest('[data-lang]'); if (!b) return;
        Edu.chooseLang(b.dataset.lang);
        modal.querySelectorAll('#lg-langs [data-lang]').forEach((x) => x.classList.toggle('on', x === b));
      };
      const relink = () => { const g = modal.querySelector('#lg-gbtn'); if (g) g.href = '/api/v1/auth/google/start?lang=' + Edu.lang(); };
      document.addEventListener('edu:lang', relink);

      Edu.authConfig().then((cfg) => {
        if (!cfg.google) return;
        modal.querySelector('#lg-google').innerHTML = '<a class="btn gbtn block" id="lg-gbtn" href="/api/v1/auth/google/start?lang=' + Edu.lang() + '">' + GOOGLE_G + '&nbsp; Google bilan davom etish</a>';
        modal.querySelector('#lg-or').hidden = false;
      });

      modal.querySelector('#lg-tg').onclick = async () => {
        const body = modal.querySelector('#lg-body');
        body.innerHTML = '<span class="spin"></span>';
        let start;
        try { start = await Edu.api('/auth/start', {method: 'POST'}); }
        catch (e) { body.innerHTML = '<div class="note bad">' + Edu.esc(e.message) + '</div>'; return; }
        body.innerHTML = '<p class="hint" style="margin:0 0 10px;text-align:left">Botda bir marta <b>Start</b> bosing, shundan keyin sayt sizni taniydi. Balans va fayllar bot bilan umumiy.</p>' +
          '<a class="btn block" target="_blank" rel="noopener" href="' + Edu.esc(start.url) + '">Telegramda ochish</a>' +
          '<p class="hint" style="margin-top:14px"><span class="spin" style="width:16px;height:16px;border-width:2px"></span> &nbsp;Tasdiqlashni kutyapman…</p>';
        const until = Date.now() + start.expires_in * 1000;
        while (!stop && Date.now() < until) {
          await new Promise((r) => setTimeout(r, 2000));
          if (stop) return;
          try {
            const p = await Edu.api('/auth/poll?token=' + encodeURIComponent(start.token));
            if (p.status === 'ok') {
              meCache = undefined;
              const me = await Edu.me(true);
              close(true);
              if (next) location.href = next; else if (me) location.reload();
              return;
            }
          } catch (e) { /* tarmoq vaqtincha uzilsa, urinish davom etadi */ }
        }
        if (!stop) body.innerHTML = '<div class="note wait">Havola eskirdi. Oynani yopib, qaytadan urinib ko‘ring.</div>';
      };
    });
  };

  Edu.logout = async function () {
    try { await Edu.api('/auth/logout', {method: 'POST'}); } catch (e) { /* baribir chiqamiz */ }
    location.href = '/';
  };

  // Kirmagan odamga bosh sahifada kirish/ro'yxatdan o'tish oynasi o'zi ochiladi — har tashrifda bir marta
  // (yopsa, shu tashrif davomida qayta chiqmaydi). Qidiruv botlariga ko'rsatilmaydi: Google sahifani
  // oyna bilan yopilgan holda ko'rmasin.
  const BOT_UA = /bot|crawl|spider|slurp|lighthouse|headless|bingpreview|yandex|google-|facebookexternalhit/i;
  function offerLogin() {
    if (Edu._loginOffered) return;
    Edu._loginOffered = true;
    if (navigator.webdriver || BOT_UA.test(navigator.userAgent || '')) return;
    if (document.querySelector('.modal')) return;
    try {
      if (sessionStorage.getItem('edu_login_offered')) return;
      sessionStorage.setItem('edu_login_offered', '1');
    } catch (e) { /* maxfiy rejim: baribir bir marta ko'rsatiladi */ }
    Edu.login(null);
  }
  Edu.offerLogin = offerLogin;

  // «Botga qaytish»: har sahifada pastki burchakda (botdan kelgan mijoz chatga bir bosishda qaytsin).
  Edu.botButton = async function () {
    if (document.getElementById('tg-back')) return;
    const cfg = await Edu.authConfig();
    const bot = (cfg && cfg.bot) || 'Edufayl_bot';
    const a = document.createElement('a');
    a.id = 'tg-back'; a.className = 'tg-back'; a.href = 'https://t.me/' + encodeURIComponent(bot);
    a.setAttribute('aria-label', 'Botga qaytish');
    a.innerHTML = TG + '<span>Botga qaytish</span>';
    document.body.appendChild(a);
  };

  // Sarlavhadagi tugmalar: til tanlagich, kirgan bo'lsa balans va kabinet, aks holda "Kirish".
  // Balans o'zi yangilanadi: admin chekni tasdiqlasa yoki Click/Payme/Uzum to'lovi tushsa — sahifani yangilash shart
  // emas. Sahifa ochiq (ko'rinib) turganda har BAL_EVERY ms da va sahifaga qaytilganda balans so'raladi; o'zgarsa
  // sarlavhadagi summa yangilanadi, ko'paygan bo'lsa xabar chiqadi va `edu:balance` hodisasi yuboriladi.
  const BAL_EVERY = 12000;
  let balTimer = null, balBusy = false;
  Edu.checkBalance = async function () {
    if (balBusy || !meCache || document.hidden) return;
    balBusy = true;
    try {
      const old = Number(meCache.balance || 0);
      const fresh = (await Edu.api('/me')).user;
      if (!fresh) return;
      const now = Number(fresh.balance || 0);
      meCache = Object.assign(meCache, fresh);
      if (now === old) return;
      const pb = document.querySelector('#hd-pay .pb');
      if (pb) pb.textContent = Edu.fmt(now) + ' so‘m';
      if (now > old) Edu.toast('✅ Balans to‘ldirildi');
      document.dispatchEvent(new CustomEvent('edu:balance', {detail: {old, balance: now}}));
    } catch (e) { /* keyingi safar */ } finally { balBusy = false; }
  };
  function watchBalance() {
    if (balTimer) return;
    balTimer = setInterval(Edu.checkBalance, BAL_EVERY);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) Edu.checkBalance(); });
    window.addEventListener('focus', () => Edu.checkBalance());
  }

  Edu.header = async function (active) {
    const box = document.getElementById('actions');
    if (!box) return;
    const me = await Edu.me();
    if (me) watchBalance();
    box.classList.toggle('in', !!me);
    box.innerHTML = '<div class="langsw" id="langsw"><button type="button" class="chip sm" id="langbtn" aria-haspopup="true">' +
      '<span class="gl">🌐</span> ' + Edu.langs().find((l) => l.key === Edu.lang()).short + '</button>' +
      '<div class="langmenu" id="langmenu" hidden>' + langChips('menu') + '</div></div>' +
      '<a class="btn sm out" href="/shop">Tayyor mavzular</a>' +
      // «To'lov» — har sahifada, kirgan-kirmaganidan qat'i nazar (sarlavha yuqorida yopishib turadi).
      '<a class="btn sm pay" id="hd-pay" href="/app#/wallet"><span class="pl">💳 To‘lov</span>' +
        (me ? '<span class="pb">' + Edu.fmt(me.balance) + ' so‘m</span>' : '') + '</a>' + (me
        ? '<a class="btn sm" href="/app#/profile">Kabinet</a>'
        : '<button class="btn sm" id="hd-login"><span class="full">Kirish / Ro‘yxatdan o‘tish</span><span class="short">Kirish</span></button>');
    Edu.botButton();
    const b = document.getElementById('hd-login');
    if (b) b.onclick = () => Edu.login(active === 'home' ? '/app' : null);
    if (!me) document.getElementById('hd-pay').onclick = (e) => { e.preventDefault(); Edu.login('/app#/wallet'); };
    if (!me && active === 'home') offerLogin();
    const menu = document.getElementById('langmenu');
    document.getElementById('langbtn').onclick = (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; };
    menu.onclick = (e) => {
      const c = e.target.closest('[data-lang]'); if (!c) return;
      menu.hidden = true; Edu.chooseLang(c.dataset.lang);
    };
    if (!Edu._menuClose) {
      Edu._menuClose = true;
      document.addEventListener('click', () => { const m = document.getElementById('langmenu'); if (m) m.hidden = true; });
      document.addEventListener('edu:lang', () => { const l = document.getElementById('langbtn'); if (l) l.innerHTML = '<span class="gl">🌐</span> ' + Edu.langs().find((x) => x.key === Edu.lang()).short; document.querySelectorAll('#langmenu [data-lang]').forEach((x) => x.classList.toggle('on', x.dataset.lang === Edu.lang())); });
    }
  };

  // Tayyor fayl Telegramga yetdimi (job.telegram: 1 — fayl, 2 — havola, -1 — yetmadi, 0 — hali yoki kerak emas).
  Edu.tgNote = function (job, bot) {
    const t = Number(job && job.telegram || 0);
    if (t === 1) return '<span>📩 Fayl Telegramga ham yuborilgan.</span>';
    if (t === 2) return '<span>📩 Fayl Telegram uchun katta: botga havola yuborildi, faylni shu yerdan yuklab oling.</span>';
    if (t === -1) return '<span>⚠️ Telegramga yuborib bo‘lmadi — botni ochib, Start bosing.</span> <a class="link" target="_blank" rel="noopener" href="https://t.me/' +
      Edu.esc(bot || 'Edufayl_bot') + '">Botni ochish</a>';
    return '<span>📩 Fayl Telegramga ham yuboriladi.</span>';
  };
  // «📩 Telegramga yuborish» tugmasi: fayl botga yetmagan bo'lsa (yoki mijoz yana olmoqchi bo'lsa) qayta yuboradi.
  Edu.tgBox = function (job, el, bot) {
    el.innerHTML = Edu.tgNote(job, bot) + ' <button type="button" class="link tg-send">📩 Telegramga yuborish</button>';
    el.querySelector('.tg-send').onclick = async (e) => {
      const btn = e.currentTarget; btn.disabled = true; btn.textContent = 'Yuborilmoqda…';
      try {
        const d = await Edu.api('/jobs/' + encodeURIComponent(job.id) + '/telegram', {method: 'POST'});
        Object.assign(job, d.job); Edu.tgBox(job, el, bot); Edu.toast('Fayl Telegramga yuborildi');
      } catch (err) { Edu.tgBox(job, el, bot); Edu.toast(err.message); }
    };
  };
  // Fayl tayyor bo'lgach Telegramga yuborish bir necha soniya oladi: belgini shu vaqt ichida yangilab turadi.
  Edu.watchTg = function (job, el, bot) {
    if (!el) return;
    el.innerHTML = Edu.tgNote(job, bot);
    let left = 6;
    const tick = async () => {
      if (!document.body.contains(el)) return;
      if (Number(job.telegram || 0) !== 0 || left-- <= 0) { Edu.tgBox(job, el, bot); return; }
      try { job = (await Edu.api('/jobs/' + encodeURIComponent(job.id))).job; el.innerHTML = Edu.tgNote(job, bot); } catch (e) { /* keyingi urinish */ }
      setTimeout(tick, 3000);
    };
    setTimeout(tick, 2500);
  };

  // iPhone/iPad: Telegram (va boshqa ilovalar) ichidagi brauzer faylni telefonga saqlay olmaydi — faqat ko'rsatadi.
  // Shuning uchun u yerda «Yuklab olish» faylni Telegram chatiga yuboradi va buni aniq aytadi (bot chatidan fayl
  // saqlanadi yoki ulashiladi). Android va kompyuterda — odatdagidek yuklab olish (server baribir botga ham yuboradi).
  Edu.isIOS = () => /iP(hone|ad|od)/.test(navigator.userAgent || '') ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  function dlSheet(html) {
    let m = document.getElementById('dl-sheet');
    if (!m) {
      m = document.createElement('div'); m.className = 'modal'; m.id = 'dl-sheet';
      m.addEventListener('click', (e) => { if (e.target === m || e.target.closest('[data-x]')) m.remove(); });
      document.body.appendChild(m);
    }
    m.innerHTML = '<div class="box">' + html + '</div>';
  }
  document.addEventListener('click', async (e) => {
    const a = e.target.closest && e.target.closest('a[href^="/api/v1/jobs/"]');
    if (!a || e.defaultPrevented || a.hasAttribute('data-plain') || !/\/file$/.test(a.getAttribute('href') || '')) return;
    if (!Edu.isIOS() || !(meCache && meCache.telegram)) return;
    e.preventDefault();
    const href = a.getAttribute('href'), id = href.split('/')[4];
    const view = '<a class="link" data-plain href="' + Edu.esc(href) + '">Faylni shu yerda ko‘rish</a>';
    dlSheet('<p style="margin:0"><span class="spin"></span></p><p>Yuborilmoqda…</p>');
    const bot = ((await Edu.authConfig()) || {}).bot || 'Edufayl_bot';
    try {
      await Edu.api('/jobs/' + encodeURIComponent(id) + '/telegram', {method: 'POST'});
      dlSheet('<h3 style="margin:0 0 8px">✅ Fayl Telegramga yuborildi</h3>' +
        '<p style="color:#4A5272;margin:0 0 16px">Bot chatida faylni oching — u yerdan telefonga saqlash yoki ulashish mumkin.</p>' +
        '<a class="btn" style="width:100%" href="https://t.me/' + Edu.esc(bot) + '">Botni ochish</a>' +
        '<p style="margin:14px 0 0">' + view + ' · <button type="button" class="link" data-x>Yopish</button></p>');
    } catch (err) {
      dlSheet('<p class="note bad" style="text-align:left">' + Edu.esc(err.message) + '</p>' +
        '<p style="margin:14px 0 0">' + view + ' · <button type="button" class="link" data-x>Yopish</button></p>');
    }
  });

  // Saqlash muddati: 2 kundan ko'p bo'lsa — kunda («29 kun qoldi»), aks holda soatda.
  Edu.leftText = function (expiresAt) {
    const hours = Math.max(0, Math.round((expiresAt * 1000 - Date.now()) / 3600000));
    return hours >= 48 ? Math.floor(hours / 24) + ' kun qoldi' : hours + ' soat qoldi';
  };

  Edu.copy = async function (text) {
    try { await navigator.clipboard.writeText(text); Edu.toast('Nusxalandi'); }
    catch (e) { Edu.toast(text); }
  };
})();
