/* Botdan saytga bir bosishda kirish (/go?t=<token>&to=<joy>).
 *
 * Token faqat shu skript POST qilganda sessiyaga almashadi (havolani oldindan ochib ko'radigan robotlar uni
 * ishlatib qo'ymasin). Kirgach, avval shu brauzerda Google akkaunti bilan kirilgan bo'lsa, birlashtirish
 * so'raladi; so'ng mijoz botda bosgan xizmat sahifasiga o'tadi. Havola eskirgan bo'lsa-yu sessiya hali
 * tirik bo'lsa — baribir o'sha sahifaga; sessiya ham bo'lmasa — «botga qaytib qayta bosing».
 */
(function () {
  'use strict';
  const E = window.Edu;
  const box = document.getElementById('go');
  const q = new URLSearchParams(location.search);
  const to = (q.get('to') || '').replace(/[^a-zA-Z0-9_]/g, '');
  const PLACES = {home: '/', docs: '/app#/docs', profile: '/app#/profile'};
  let bot = 'Edufayl_bot';

  async function target() {
    if (PLACES[to]) return PLACES[to];
    if (/^buy_[A-Z0-9]{8}$/.test(to)) return '/app#/buy/' + to.slice(4);
    try {
      const c = await E.api('/catalog');
      bot = c.bot || bot;
      if (to && to !== 'slide_rewrite' && (c.kinds || []).some((k) => k.key === to)) return '/#yaratish?kind=' + to;
    } catch (e) { /* katalogsiz ham bosh sahifa ochiladi */ }
    return '/';
  }

  function show(title, text, buttons) {
    box.innerHTML = '<img src="/static/logo-sm.webp" alt="Edufayl" width="54" height="54"><h2>' + E.esc(title) + '</h2>' +
      '<p>' + text + '</p>' + buttons;
  }

  async function mergeThenGo() {
    let offer = null;
    try { offer = (await E.api('/auth/merge')).offer; } catch (e) { offer = null; }
    if (!offer) { location.replace(await target()); return; }
    show('Akkauntlarni birlashtiramizmi?',
      '<span>Bu brauzerda avval Google akkaunti bilan kirgansiz:</span><br><b>' + E.esc(offer.email || '—') + '</b></p><p>' +
      'Uni Telegram akkauntingizga qo‘shsak, balans (' + E.fmt(offer.balance) + ' so‘m) va hujjatlar bitta joyda bo‘ladi.',
      '<button type="button" class="btn block" id="m-yes">Ha, birlashtirish</button>' +
      '<button type="button" class="btn out block" id="m-no">Yo‘q, kerak emas</button>');
    const answer = async (accept) => {
      box.querySelectorAll('button').forEach((b) => { b.disabled = true; });
      try { await E.api('/auth/merge', {json: {accept}}); }
      catch (e) { E.toast(e.message); }
      location.replace(await target());
    };
    document.getElementById('m-yes').onclick = () => answer(true);
    document.getElementById('m-no').onclick = () => answer(false);
  }

  async function expired() {
    const me = await E.me(true);
    if (me) { await mergeThenGo(); return; }
    await target();
    show('Havola eskirgan',
      'Xavfsizlik uchun bu havola faqat bir marta va qisqa vaqt ishlaydi. Botga qaytib, tugmani qayta bosing — sayt sizni o‘zi taniydi.',
      '<a class="btn block" href="https://t.me/' + E.esc(bot) + '">' + E.TG + '&nbsp; Botga qaytish</a>' +
      '<button type="button" class="btn out block" id="g-login">Saytga boshqacha kirish</button>');
    document.getElementById('g-login').onclick = () => E.login('/');
  }

  (async function init() {
    const token = q.get('t') || '';
    try { history.replaceState(null, '', '/go' + (to ? '?to=' + to : '')); } catch (e) { /* token manzil satrida qolmasin */ }
    if (q.get('done')) { await mergeThenGo(); return; }
    if (window.__go) {                 // go.html dagi tezkor yo'l tokenni allaqachon yuborgan
      const x = await window.__go;
      if (x.leaving) return;           // kerakli sahifa ochilmoqda
      if (x.network) { show('Internet yo‘q', 'Aloqa uzildi. Internetni tekshirib, sahifani yangilang.', ''); return; }
      if (x.d && x.d.ok) { await mergeThenGo(); return; }
      await expired();
      return;
    }
    if (!token || q.get('bad')) { await expired(); return; }
    try {
      await E.api('/auth/go', {json: {token, to}});
    } catch (e) {
      if (e.code === 'network') {
        show('Internet yo‘q', 'Aloqa uzildi. Internetni tekshirib, sahifani yangilang.', '');
        return;
      }
      await expired();
      return;
    }
    await mergeThenGo();
  })();
})();
