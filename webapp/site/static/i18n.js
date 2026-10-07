/* Edufayl sayti: interfeys tillari (uz, ru, en, kk).
 *
 * Sayt matnlari o'zbekcha yoziladi; boshqa tilda ular lug'at bo'yicha (o'zbekcha matn → tarjima) almashtiriladi.
 * Almashtirish avtomatik: sahifa va keyin paydo bo'lgan har bir matn (MutationObserver) tekshiriladi.
 *   - aniq moslik:   «Yaratish» → «Создать»
 *   - o'zgaruvchili: «{n} slayd» → «{n} слайдов»  ({n} — istalgan matn)
 *   - so'z/birlik:   « so‘m» → « сум» (lug'atda aniq mos kelmasa, matn ichidagi birliklar almashtiriladi)
 * Lug'at `i18n-dict.js` da (window.EDU_DICT).
 */
(function () {
  'use strict';
  const Edu = (window.Edu = window.Edu || {});
  const LANGS = ['uz', 'ru', 'en', 'kk'];
  const NAMES = {uz: 'O‘zbekcha', ru: 'Русский', en: 'English', kk: 'Қазақша'};
  const SHORT = {uz: 'UZ', ru: 'RU', en: 'EN', kk: 'KK'};
  const ATTRS = ['placeholder', 'title', 'aria-label', 'alt'];
  const SKIP = {SCRIPT: 1, STYLE: 1, TEXTAREA: 1, NOSCRIPT: 1};

  let lang = 'uz';
  const orig = new WeakMap();      // tugun → asl o'zbekcha matn
  const shown = new WeakMap();     // tugun → biz qo'ygan tarjima (kuzatuvchi o'zimizni ushlamasin)
  let exact = {}, patterns = [], words = [];
  // Apostrof turlari (o‘, o', oʻ ...) bir xil hisoblanadi: lug'at kalitida qaysi biri yozilgani muhim emas.
  const norm = (t) => String(t).replace(/[ʻʼ‘’`´]/g, "'");

  function detect() {
    let saved = '';
    try { saved = localStorage.getItem('edu_lang') || ''; } catch (e) { /* maxfiy rejim */ }
    if (LANGS.indexOf(saved) >= 0) return saved;
    const nav = String((navigator.languages && navigator.languages[0]) || navigator.language || '').slice(0, 2).toLowerCase();
    return nav === 'ru' ? 'ru' : nav === 'kk' ? 'kk' : nav === 'en' ? 'en' : 'uz';
  }

  function prepare() {
    const dict = (window.EDU_DICT || {})[lang] || {};
    exact = {}; patterns = []; words = [];
    Object.keys(dict).forEach((raw) => {
      if (raw === '$words') return;
      const key = norm(raw);
      if (/\{[a-z]+\}/.test(key)) {
        const names = [];
        const src = key.replace(/[.*+?^$()|[\]\\]/g, '\\$&').replace(/\{([a-z]+)\}/g, (m, n) => { names.push(n); return '([\\s\\S]+?)'; });
        patterns.push({re: new RegExp('^' + src + '$', 'd'), names, to: dict[raw]});
      } else exact[key] = dict[raw];
    });
    (dict.$words || []).forEach((pair) => words.push([new RegExp(pair[0], 'g'), pair[1]]));
  }

  function tr(text) {
    if (lang === 'uz' || !text) return text;
    const lead = text.match(/^\s*/)[0], tail = text.match(/\s*$/)[0];
    const core = text.trim();
    if (!core) return text;
    const key = norm(core);
    if (Object.prototype.hasOwnProperty.call(exact, key)) return lead + exact[key] + tail;
    for (let i = 0; i < patterns.length; i++) {
      const m = patterns[i].re.exec(key);
      if (m) {
        let out = patterns[i].to;
        patterns[i].names.forEach((n, k) => {
          const span = m.indices && m.indices[k + 1];
          const part = span ? core.slice(span[0], span[1]) : m[k + 1];    // asl matn (apostrofi o'zgarmagan)
          out = out.split('{' + n + '}').join(tr(part));
        });
        return lead + out + tail;
      }
    }
    let out = text;
    words.forEach((w) => { out = out.replace(w[0], w[1]); });
    return out;
  }
  Edu.tr = tr;

  function node(n) {
    if (n.nodeType === 3) {
      const parent = n.parentNode;
      if (!parent || SKIP[parent.nodeName]) return;
      if (shown.has(n) && shown.get(n) === n.data) return;          // o'zimiz qo'ygan matn
      orig.set(n, n.data);
      const out = tr(n.data);
      if (out !== n.data) { shown.set(n, out); n.data = out; } else shown.delete(n);
      return;
    }
    if (n.nodeType !== 1 || SKIP[n.nodeName]) return;
    attrs(n);
    for (let c = n.firstChild; c; c = c.nextSibling) node(c);
  }

  function attrs(el) {
    ATTRS.forEach((a) => {
      if (!el.hasAttribute(a)) return;
      const key = '_uz_' + a, cur = el.getAttribute(a);
      if (el[key + '_shown'] === cur) return;
      el[key] = cur;
      const out = tr(cur);
      if (out !== cur) { el[key + '_shown'] = out; el.setAttribute(a, out); } else el[key + '_shown'] = undefined;
    });
  }

  // Tilni almashtirganda tugunlar asl o'zbekcha matnidan qayta tarjima qilinadi.
  function restore(n) {
    if (n.nodeType === 3) { if (orig.has(n) && shown.has(n)) { n.data = orig.get(n); shown.delete(n); } return; }
    if (n.nodeType !== 1) return;
    ATTRS.forEach((a) => { const k = '_uz_' + a; if (n[k] !== undefined && n[k + '_shown'] !== undefined) { n.setAttribute(a, n[k]); n[k + '_shown'] = undefined; } });
    for (let c = n.firstChild; c; c = c.nextSibling) restore(c);
  }

  let observer = null;
  function observe() {
    if (observer) observer.disconnect();
    observer = new MutationObserver((list) => {
      observer.disconnect();
      try {
        list.forEach((m) => {
          if (m.type === 'childList') m.addedNodes.forEach(node);
          else if (m.type === 'characterData') node(m.target);
          else if (m.type === 'attributes') attrs(m.target);
        });
      } finally { start(); }
    });
    start();
  }
  function start() {
    if (observer && document.body) observer.observe(document.body, {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS});
  }

  Edu.lang = () => lang;
  Edu.langs = () => LANGS.map((k) => ({key: k, name: NAMES[k], short: SHORT[k]}));

  Edu.setLang = function (next, opts) {
    next = LANGS.indexOf(next) >= 0 ? next : 'uz';
    opts = opts || {};
    if (observer) observer.disconnect();
    if (document.body) restore(document.body);
    lang = next;
    if (opts.persist !== false) { try { localStorage.setItem('edu_lang', next); } catch (e) { /* ixtiyoriy */ } }
    document.documentElement.lang = next;
    prepare();
    if (document.body) { node(document.body); }
    if (!orig.has(document.head)) { /* sarlavha */ }
    const title = document.querySelector('title');
    if (title) {
      if (title._uz === undefined) title._uz = title.textContent;
      title.textContent = tr(title._uz);
    }
    observe();
    document.dispatchEvent(new CustomEvent('edu:lang', {detail: next}));
  };

  // Birinchi bo'yash oldidan: saqlangan (yoki brauzer) tilida boshlanadi.
  lang = detect();
  document.documentElement.lang = lang;
  prepare();
  if (document.body) { node(document.body); observe(); }
  else document.addEventListener('DOMContentLoaded', () => { node(document.body); observe(); const t = document.querySelector('title'); if (t) { t._uz = t.textContent; t.textContent = tr(t._uz); } });
})();
