/* Edufayl sayti: umumiy yordamchilar (API, kirish oynasi, sarlavha) */
(function () {
  'use strict';
  const Edu = (window.Edu = {});

  Edu.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
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
      data = await res.json();
    } catch (e) {
      throw Object.assign(new Error('Aloqa yo‘q. Internetni tekshirib, qayta urining.'), {code: 'network'});
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

  let meCache;
  Edu.me = async function (force) {
    if (meCache === undefined || force) {
      try { meCache = (await Edu.api('/me')).user || null; } catch (e) { meCache = null; }
    }
    return meCache;
  };

  // Telegram orqali kirish: brauzer token oladi, bot uni tasdiqlaydi, brauzer sessiya oladi.
  Edu.login = function (next) {
    return new Promise((resolve) => {
      const modal = document.createElement('div');
      modal.className = 'modal';
      modal.innerHTML = '<div class="box"><h3 style="margin:0 0 8px;font-size:22px">Telegram orqali kirish</h3>' +
        '<p style="margin:0 0 18px;color:#4A5272">Botda bir marta <b>Start</b> bosing, shundan keyin sayt sizni taniydi. Balans va fayllar bot bilan umumiy.</p>' +
        '<div id="lg-body"><span class="spin"></span></div>' +
        '<button class="link" id="lg-x" style="margin-top:16px">Yopish</button></div>';
      document.body.appendChild(modal);
      let stop = false;
      const close = (ok) => { stop = true; modal.remove(); resolve(ok); };
      modal.querySelector('#lg-x').onclick = () => close(false);
      modal.addEventListener('click', (e) => { if (e.target === modal) close(false); });
      (async () => {
        const body = modal.querySelector('#lg-body');
        let start;
        try { start = await Edu.api('/auth/start', {method: 'POST'}); }
        catch (e) { body.innerHTML = '<div class="note bad">' + Edu.esc(e.message) + '</div>'; return; }
        body.innerHTML = '<a class="btn block" target="_blank" rel="noopener" href="' + Edu.esc(start.url) + '">Telegramda ochish</a>' +
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
      })();
    });
  };

  Edu.logout = async function () {
    try { await Edu.api('/auth/logout', {method: 'POST'}); } catch (e) { /* baribir chiqamiz */ }
    location.href = '/';
  };

  // Sarlavhadagi tugmalar: kirgan bo'lsa balans, kirmagan bo'lsa "Telegram orqali kirish".
  Edu.header = async function (active) {
    const box = document.getElementById('actions');
    if (!box) return;
    const me = await Edu.me();
    box.classList.toggle('in', !!me);
    const tg = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M21.5 4.3 2.9 11.5c-1.3.5-1.3 1.2-.2 1.5l4.7 1.5 1.8 5.6c.2.6.1.8.7.8.5 0 .7-.2 1-.5l2.3-2.3 4.7 3.5c.9.5 1.5.2 1.7-.8l3.1-14.6c.3-1.2-.5-1.8-1.2-1.4zM8.2 13.7l9.4-5.9c.4-.3.8-.1.5.2l-7.8 7z"/></svg>';
    box.innerHTML = '<a class="btn sm out" href="/shop">Tayyor mavzular</a>' + (me
      ? '<a class="bal" href="/app#/wallet" title="Hamyon">' + Edu.fmt(me.balance) + ' so‘m</a><a class="btn sm" href="/app">Kabinet</a>'
      : '<button class="btn sm" id="hd-login">' + tg + '<span class="full">Telegram orqali kirish</span><span class="short">Kirish</span></button>');
    const b = document.getElementById('hd-login');
    if (b) b.onclick = () => Edu.login(active === 'home' ? '/app' : null);
  };

  Edu.copy = async function (text) {
    try { await navigator.clipboard.writeText(text); Edu.toast('Nusxalandi'); }
    catch (e) { Edu.toast(text); }
  };
})();
