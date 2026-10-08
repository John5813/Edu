"""Taqdimotni QO'LDA tahrirlash (saytda bepul): matn, diagramma raqamlari, slaydlar tartibi.

AI ishlatilmaydi — o'zgarish aniq, mijozning o'zi yozgan narsa. Sahifa faqat brauzerda qayta
sig'diriladi va suratga olinadi (`html_render.render`, tuzatuvchi AI siz).

- Matn: sahifadagi matnli bloklar (`EDITABLE`) brauzer DOM ida tartib raqami bo'yicha almashtiriladi —
  mijoz ko'rgan sahifa bilan server qayta chizadigan sahifa aynan bir xil element ro'yxatiga ega.
  Sahifa ichida saqlangan asl slayd (`<!--manba:...-->`) ham shu o'zgarish bilan yangilanadi: keyin AI ga
  qayta yozdirilsa, mijozning tuzatishi yo'qolmaydi.
- Diagramma: raqamlar asl slayddagi `.chart` blokidan o'qiladi, mijoz o'zgartirgach diagramma kod bilan
  qayta chiziladi va sahifadagi o'sha diagramma o'rniga qo'yiladi.
- Tartib: sahifalar o'rni almashadi, nusxalanadi yoki o'chiriladi; reja sahifasi (2-sahifa) yangi
  sarlavhalardan qayta yig'iladi.
"""
import base64
import html as html_lib
import logging
import os
import re
import shutil
import tempfile
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

from . import deck_calc, deck_charts, deck_logic, html_render, html_slides, themes

log = logging.getLogger(__name__)

# Mijoz bosib o'zgartira oladigan matnli bloklar (sayt ham aynan shu ro'yxatni ishlatadi).
EDITABLE = (".title, .lead, .par, .item-text, .card-title, .card-note, .kpi-value, .kpi-label, .kpi-note, "
            ".when, .what, .quote, .quote-by, .note, .misol-task, .misol-text, .misol-answer, .rasm-matn, "
            ".formula-note, th, td")
PLAN_INDEX = 1
MAX_TEXT = 700                 # bitta blok uchun
MAX_EDITS = 80
MAX_PAGES = 40
_ALLOWED = {"b", "strong", "i", "em", "br", "sup", "sub"}

# Brauzerda: tahrirlanadigan elementlar ro'yxati (ichma-ich bo'lsa — faqat tashqisi, diagramma ichidagisi yo'q).
_LIST_JS = """(sel) => [...document.querySelectorAll(sel)].filter((el) =>
  !el.closest('svg') && !(el.parentElement && el.parentElement.closest(sel)) && el.textContent.trim())"""

_APPLY_JS = """({sel, edits}) => {
  const list = (%s)(sel);
  const pairs = [];
  for (const e of edits) {
    const el = list[e.k];
    if (!el) continue;
    const old = el.textContent;
    el.innerHTML = e.html;
    pairs.push({old, html: e.html, title: el.classList.contains('title')});
  }
  return {count: list.length, pairs, html: '<!doctype html>' + document.documentElement.outerHTML};
}""" % _LIST_JS

# Asl slaydda o'sha bloklar matni bo'yicha topiladi (tartibi bezaklar sababli farq qilishi mumkin).
_SOURCE_JS = """({sel, pairs}) => {
  const norm = (t) => String(t || '').replace(/\\s+/g, ' ').trim();
  const list = (%s)(sel);
  const used = new Set();
  let hit = 0;
  for (const p of pairs) {
    const el = list.find((x) => !used.has(x) && norm(x.textContent) === norm(p.old));
    if (!el) continue;
    used.add(el); el.innerHTML = p.html; hit++;
  }
  const s = document.querySelector('section.slide');
  return {hit, html: s ? s.outerHTML : document.body.innerHTML};
}""" % _LIST_JS

_CHART_JS = """({k, html}) => {
  const charts = [...document.querySelectorAll('.chart')].filter((el) => !el.parentElement.closest('.chart'));
  if (!charts[k]) return null;
  charts[k].outerHTML = html;
  return '<!doctype html>' + document.documentElement.outerHTML;
}"""


class ManualEditError(RuntimeError):
    """Mijozga ko'rsatiladigan xato."""


# ─────────────────────────────────────────────────────────────── yordamchilar

class _Clean(HTMLParser):
    """Faqat qalin/kursiv/qator uzilishi qoladi; boshqa teglar va atributlar olib tashlanadi."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: List[str] = []
        self.open: List[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "br":
            self.out.append("<br>")
        elif tag in ("div", "p") and self.out:
            self.out.append("<br>")
        elif tag in _ALLOWED:
            self.out.append(f"<{tag}>")
            self.open.append(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in _ALLOWED and tag != "br" and tag in self.open:
            while self.open:
                last = self.open.pop()
                self.out.append(f"</{last}>")
                if last == tag:
                    break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html_lib.escape(data, quote=False))


def clean_html(text: str) -> str:
    parser = _Clean()
    parser.feed(str(text or "")[:MAX_TEXT * 4])
    parser.close()
    out = "".join(parser.out) + "".join(f"</{t}>" for t in reversed(parser.open))
    out = re.sub(r"(<br>\s*){3,}", "<br><br>", out).strip()
    out = re.sub(r"^(<br>)+|(<br>)+$", "", out)
    return out


def _plain_len(fragment: str) -> int:
    return len(html_lib.unescape(re.sub(r"<[^>]+>", "", fragment)).strip())


def with_source(page: str, body: str) -> str:
    token = base64.b64encode(body.encode("utf-8")).decode("ascii")
    if html_slides._SOURCE.search(page):
        return html_slides._SOURCE.sub(lambda _m: f"<!--manba:{token}-->", page, count=1)
    return page.replace("</head>", f"<!--manba:{token}--></head>", 1)


def theme_of(deck: dict):
    return themes.for_deck(deck.get("topic", ""), deck.get("style", ""), deck.get("volume", ""),
                           deck.get("theme_key", ""))


def _browser_eval(steps: List[Tuple[str, str, object]]) -> List[object]:
    """[(html, js, arg)] — har birini brauzerda ochib, JS natijasini qaytaradi."""
    from playwright.sync_api import sync_playwright

    out = []
    with sync_playwright() as playwright:
        browser = html_render._launch(playwright)
        try:
            page = browser.new_page(viewport={"width": html_slides.SLIDE_W_PX, "height": html_slides.SLIDE_H_PX})
            for markup, script, arg in steps:
                page.set_content(markup, wait_until="domcontentloaded", timeout=30000)
                out.append(page.evaluate(script, arg))
        finally:
            browser.close()
    return out


def render(pages: List[str]) -> Tuple[List[str], Dict[int, str], str]:
    """Sahifalarni sig'dirib suratga oladi (AI tuzatishisiz). (yakuniy sahifalar, {o'rni: png}, papka)."""
    work = tempfile.mkdtemp(prefix="manual_")
    shots_dir = os.path.join(work, "shots")
    os.makedirs(shots_dir, exist_ok=True)
    final: List[str] = []
    path = html_render.render(pages, out_dir=work, name="sahifa", collect=final, shots_dir=shots_dir)
    try:
        os.remove(path)
    except OSError:
        pass
    if len(final) != len(pages):
        shutil.rmtree(work, ignore_errors=True)
        raise ManualEditError("Sahifa chizilmadi. Qayta urinib ko'ring.")
    shots = {}
    for position in range(len(pages)):
        shot = os.path.join(shots_dir, f"shot_{position + 1:02d}.png")
        if os.path.exists(shot):
            shots[position] = shot
    return final, shots, work


def titles(deck: dict) -> List[str]:
    return [deck_logic.title_of(html_slides.source_of(page) or page) for page in deck["pages"]]


def plan_page(deck: dict, pages: List[str]) -> Optional[str]:
    """Reja sahifasi (2-sahifa) — qolgan sahifalarning sarlavhalaridan (oxirgi — xulosa — kirmaydi)."""
    total = len(pages)
    if total <= 3:
        return None
    outline = list(deck.get("outline") or [])
    items = []
    for index in range(2, total - 1):
        title = deck_logic.title_of(html_slides.source_of(pages[index]) or pages[index])
        brief = outline[index].get("brief", "") if index < len(outline) and isinstance(outline[index], dict) else ""
        if title:
            items.append((title, brief))
    if not items:
        return None
    body = deck_logic.plan_slide(items, deck.get("language", "uz"))
    return html_slides.build_pages([body], theme_of(deck), deck.get("language", "uz"))[0]


def has_plan(deck: dict) -> bool:
    return bool(deck.get("has_plan", len(deck.get("pages") or []) > 3))


# ─────────────────────────────────────────────────────────────── 1. matn

def text_info(deck: dict, index: int) -> Dict:
    """Sahifa HTML i va tahrirlash qoidasi (brauzer o'zi ro'yxatni tuzadi)."""
    return {"html": deck["pages"][index], "selector": EDITABLE,
            "locked": index == PLAN_INDEX and has_plan(deck)}


def apply_text(deck: dict, index: int, edits: List[Dict], expect: int) -> Dict:
    """Matn o'zgarishlarini qo'llaydi. Qaytaradi: {pages: {i: html}, shots: {i: png}, work, title_changed}."""
    pages = list(deck["pages"])
    if not 0 <= index < len(pages):
        raise ManualEditError("Bunday sahifa yo'q.")
    if index == PLAN_INDEX and has_plan(deck):
        raise ManualEditError("Reja sahifasi boshqa sahifalar sarlavhalaridan o'zi yig'iladi.")
    clean = []
    for edit in (edits or [])[:MAX_EDITS]:
        try:
            k = int(edit.get("k"))
        except (TypeError, ValueError, AttributeError):
            continue
        fragment = clean_html(edit.get("html", ""))
        if _plain_len(fragment) > MAX_TEXT:
            raise ManualEditError(f"Matn juda uzun: bitta blokda ko'pi bilan {MAX_TEXT} ta belgi.")
        if k >= 0:
            clean.append({"k": k, "html": fragment})
    if not clean:
        raise ManualEditError("O'zgarish yo'q.")

    page = pages[index]
    source = html_slides.source_of(page)
    first = _browser_eval([(page, _APPLY_JS, {"sel": EDITABLE, "edits": clean})])[0]
    if int(first["count"]) != int(expect):
        raise ManualEditError("Sahifa boshqa joyda o'zgargan. Sahifani yangilab, qaytadan urinib ko'ring.")
    new_page = first["html"]
    old_title = deck_logic.title_of(source or page)
    if source:
        wrapped = f"<!doctype html><html><head><meta charset='utf-8'></head><body>{source}</body></html>"
        second = _browser_eval([(wrapped, _SOURCE_JS, {"sel": EDITABLE, "pairs": first["pairs"]})])[0]
        new_page = with_source(new_page, second["html"])
    targets = {index: new_page}
    new_title = deck_logic.title_of(html_slides.source_of(new_page) or new_page)
    title_changed = new_title != old_title
    if title_changed and has_plan(deck) and index != PLAN_INDEX:
        pages[index] = new_page
        plan = plan_page(deck, pages)
        if plan:
            targets[PLAN_INDEX] = plan
    order = sorted(targets)
    final, shots, work = render([targets[i] for i in order])
    return {"pages": {i: final[pos] for pos, i in enumerate(order)},
            "shots": {order[pos]: path for pos, path in shots.items()}, "work": work,
            "title_changed": title_changed, "title": new_title}


# ─────────────────────────────────────────────────────────────── 2. diagramma

_KIND = {"bar": "bar", "ustun": "bar", "column": "bar", "line": "line", "chiziq": "line",
         "donut": "donut", "pie": "donut", "halqa": "donut"}


def _attrs(tag: str) -> Dict[str, str]:
    return {key.lower(): html_lib.unescape(value) for key, _, value in deck_charts._ATTR.findall(tag)}


def _spec(tag: str) -> Dict:
    data = _attrs(tag)
    raw = data.get("series") or data.get("values") or ""
    pair_labels, pair_values = deck_charts._pairs(raw)
    rows = [("", pair_values)] if pair_values else deck_charts._series(raw)
    labels = deck_charts._labels(data.get("labels", ""))
    if pair_values and len(labels) != len(pair_values):
        labels = pair_labels
    if len(rows) >= 2 and all(len(values) == 1 for _, values in rows):
        names = [name for name, _ in rows]
        rows = [("", [values[0] for _, values in rows])]
        if len(labels) != len(names) and all(names):
            labels = names
    width = max([len(values) for _, values in rows] or [0])
    labels = (labels + [""] * width)[:width]
    return {"kind": _KIND.get((data.get("kind") or "bar").strip().lower(), "bar"), "labels": labels,
            "series": [{"name": name, "values": list(values)} for name, values in rows],
            "unit": data.get("unit") or data.get("ylabel") or "", "source": data.get("source") or "",
            "xlabel": data.get("xlabel") or ""}


def _chart_source(deck: dict, index: int) -> str:
    page = deck["pages"][index]
    return deck_calc.apply(html_slides.source_of(page) or "")


def charts(deck: dict, index: int) -> List[Dict]:
    """Sahifadagi diagrammalar (faqat chizilganlari): mijozga tahrirlash uchun."""
    body = _chart_source(deck, index)
    out = []
    theme = None
    for tag in deck_charts._TAG.finditer(body):
        theme = theme or theme_of(deck)
        drawn = deck_charts.draw(tag.group(0), theme)
        if drawn.startswith('<div class="chart"'):
            out.append(_spec(tag.group(0)))
    return out


def count_charts(deck: dict, index: int) -> int:
    try:
        return deck_charts.count(_chart_source(deck, index))
    except Exception:
        return 0


def _tag_of(spec: Dict, old: Dict[str, str]) -> str:
    def clean(text, limit=60, bad=",|:"):
        text = re.sub(r"\s+", " ", str(text or "")).strip()[:limit]
        return "".join(" " if ch in bad else ch for ch in text).strip()

    kind = _KIND.get(str(spec.get("kind") or "bar"), "bar")
    labels = [clean(x, 40) or str(i + 1) for i, x in enumerate(spec.get("labels") or [])][:24]
    series = []
    for row in (spec.get("series") or [])[:6]:
        values = []
        for value in (row.get("values") or [])[:len(labels)]:
            try:
                number = float(str(value).replace(",", ".").replace(" ", ""))
            except (TypeError, ValueError):
                raise ManualEditError("Qiymatlar faqat raqam bo'lsin.")
            if abs(number) > 1e12:
                raise ManualEditError("Raqam juda katta.")
            values.append(number)
        if len(values) != len(labels):
            raise ManualEditError("Har bir qatorga qiymat yozing.")
        series.append((clean(row.get("name"), 40), values))
    if kind == "donut":
        series = series[:1]
    if not labels or len(labels) < 2 or not series:
        raise ManualEditError("Diagrammada kamida 2 ta qiymat bo'lsin.")
    if kind == "donut" and any(v < 0 for v in series[0][1]):
        raise ManualEditError("Halqa diagrammada manfiy qiymat bo'lmaydi.")

    def fmt(value: float) -> str:
        return str(int(value)) if float(value).is_integer() else f"{value:.6g}"

    attrs = dict(old)
    attrs.update({"kind": kind, "labels": ",".join(labels),
                  "series": "|".join(f"{name}: {','.join(fmt(v) for v in values)}" if name else ",".join(fmt(v) for v in values)
                                     for name, values in series),
                  "unit": clean(spec.get("unit"), 30, "|"), "source": clean(spec.get("source"), 120, "|"),
                  "xlabel": clean(spec.get("xlabel"), 40, "|")})
    attrs.pop("values", None)
    attrs.pop("ylabel", None)
    attrs.pop("size", None)
    parts = " ".join(f'data-{key}="{html_lib.escape(value, quote=True)}"' for key, value in attrs.items() if value != "")
    return f'<div class="chart" {parts}></div>'


def apply_chart(deck: dict, index: int, k: int, spec: Dict) -> Dict:
    pages = list(deck["pages"])
    if not 0 <= index < len(pages):
        raise ManualEditError("Bunday sahifa yo'q.")
    page = pages[index]
    body = _chart_source(deck, index)
    tags = list(deck_charts._TAG.finditer(body))
    sized = list(deck_charts._TAG.finditer(html_slides._half_charts(body)))
    theme = theme_of(deck)
    drawn_index, target = -1, None
    for position, tag in enumerate(tags):
        if deck_charts.draw(tag.group(0), theme).startswith('<div class="chart"'):
            drawn_index += 1
            if drawn_index == k:
                target = position
                break
    if target is None:
        raise ManualEditError("Diagramma topilmadi. Sahifani yangilab, qaytadan urinib ko'ring.")
    new_tag = _tag_of(spec, _attrs(tags[target].group(0)))
    half = "half" in (_attrs(sized[target].group(0)).get("size") or "") if target < len(sized) else False
    drawn = deck_charts.draw(new_tag.replace('class="chart"', 'class="chart"' + (' data-size="half"' if half else ""), 1), theme)
    if not drawn.startswith('<div class="chart"'):
        raise ManualEditError("Bu qiymatlardan diagramma chizib bo'lmadi: kamida 2 ta qiymat kiriting.")
    new_page = _browser_eval([(page, _CHART_JS, {"k": k, "html": drawn})])[0]
    if not new_page:
        raise ManualEditError("Diagramma topilmadi. Sahifani yangilab, qaytadan urinib ko'ring.")
    old = tags[target]
    new_page = with_source(new_page, body[:old.start()] + new_tag + body[old.end():])
    final, shots, work = render([new_page])
    return {"pages": {index: final[0]}, "shots": {index: shots[0]} if 0 in shots else {}, "work": work}


# ─────────────────────────────────────────────────────────────── 3. tartib

def apply_order(deck: dict, order: List[int]) -> Dict:
    """`order` — asosiy sahifalarning (muqova va rejadan keyingi) yangi tartibi, asl 0-indekslarda.

    Takrorlansa — nusxa, tushib qolsa — o'chirildi. Muqova va reja o'z joyida qoladi.
    Qaytaradi: {pages, mapping (yangi o'rin → asl indeks yoki None), plan (yangi reja sahifasi yoki None), shots, work}.
    """
    pages = list(deck["pages"])
    fixed = 2 if has_plan(deck) else 1
    try:
        order = [int(x) for x in order]
    except (TypeError, ValueError):
        raise ManualEditError("Tartib noto'g'ri.")
    if len(order) < (2 if fixed == 2 else 1):
        raise ManualEditError("Kamida 2 ta sahifa qolsin." if fixed == 2 else "Kamida bitta sahifa qolsin.")
    if any(not fixed <= x < len(pages) for x in order):
        raise ManualEditError("Tartib noto'g'ri.")
    if fixed + len(order) > MAX_PAGES:
        raise ManualEditError(f"Ko'pi bilan {MAX_PAGES} ta sahifa.")
    if order == list(range(fixed, len(pages))):
        raise ManualEditError("O'zgarish yo'q.")
    mapping: List[Optional[int]] = list(range(fixed)) + order
    new_pages = [pages[i] for i in mapping]
    shots, work, plan = {}, "", None
    if fixed == 2:
        plan_html = plan_page(deck, new_pages)
        if plan_html:
            final, shots, work = render([plan_html])
            new_pages[PLAN_INDEX] = plan = final[0]
            shots = {PLAN_INDEX: shots[0]} if 0 in shots else {}
            mapping[PLAN_INDEX] = None
    return {"pages": new_pages, "mapping": mapping, "plan": plan, "shots": shots, "work": work}
