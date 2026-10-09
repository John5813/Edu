"""Oddiy taqdimot: 25 ta slayd shabloni va ularni mavzuga qarab tanlovchi reja.

Avval taqdimotda 6 ta shablon qat'iy tartibda takrorlanardi. Endi 25 ta
shablon bor; har taqdimotda ulardan boshqacha to'plam tanlanadi:

  * har shablon o'z ma'lumot shaklini talab qiladi (2 ustun, 4 karta,
    vaqt chizig'i, raqamli statistika, taqqoslash, rasmli shablonlar ...);
  * `assign` har asosiy slaydga mazmuniga eng mos, lekin oldingilardan
    farqli shablonni tanlaydi: model taklifi, matndagi belgilar (jarayon,
    raqamlar, yillar, taqqoslash) va mavzudan olingan tasodif hisobga olinadi;
  * tanlov haqiqiy o'lchov bilan tekshiriladi: matn shablonga sig'masa,
    keyingi mos shablon sinaladi. Matn hech qachon qirqilmaydi;
  * rasmli shablonlar soni cheklangan (Together AI narxi).

Premium taqdimot bu moduldan foydalanmaydi.
"""

import hashlib
import logging
import random
import re
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN

from services import slide_fit
from services import slide_kit as kit
from services.slide_kit import AREA_B as B, AREA_H as H, AREA_L as L, AREA_R as R, AREA_T as T, AREA_W as W

logger = logging.getLogger(__name__)

# Asosiy slayd emas: muqova, reja, kirish, xulosa, adabiyot, rahmat, jadval.
FIXED = {"cover", "plan", "intro", "conclusion", "references", "thanks", "table"}


# ── ma'lumotni bir shaklga keltirish ────────────────────────────────────────

_NUM_PREFIX = re.compile(r"^\s*\(?\d{1,2}[\.\)\-:]\s+")
_NUMBER = re.compile(
    r"(?<![\w.,])\d[\d  ]*(?:[.,]\d+)?\s?"
    r"(?:%|foiz|процент\w*|percent|mlrd|mln|млрд|млн|тыс\w*|ming|million|billion|thousand|marta|раз\w*|times)?",
    re.IGNORECASE)
_YEAR = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")


def _flatten(value) -> list:
    """Har qanday JSON qiymatidan matn bo'laklari (lug'at va ro'yxat ichidagilari ham)."""
    if value is None:
        return []
    if isinstance(value, dict):
        for key in ("text", "content"):
            if _s(value.get(key)):
                return [_s(value.get(key))]
        out = []
        for item in value.values():
            out.extend(_flatten(item))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_flatten(item))
        return out
    text = str(value).strip()
    return [text] if text else []


def _s(value) -> str:
    """Qiymat matni. Model ba'zan matnni lug'at ({"points": [...]}) yoki lug'atlar ro'yxati qilib
    qaytaradi — ilgari bunday slayd matnsiz qolib, PowerPoint'da "Double-tap to add text" chiqardi."""
    if isinstance(value, dict):
        if "text" in value or "content" in value:
            value = value.get("text", value.get("content", ""))
            if isinstance(value, (dict, list)):
                return " ".join(_flatten(value)).strip()
        else:
            return " ".join(_flatten(value)).strip()
    if isinstance(value, list):
        return " ".join(_flatten(value)).strip()
    return str(value or "").strip()


# Model matnni `content` o'rniga shu maydonlarga ham yozadi.
_ALT_TEXT_KEYS = ("bullets", "points", "key_points", "bullet_points", "paragraphs", "body", "text",
                  "description", "details", "list", "facts", "main_points")


def _clean(value: str) -> str:
    from services.ai_service import clean_text
    return clean_text(value).strip()


def _read_item(raw) -> Dict:
    if isinstance(raw, dict):
        head = raw.get("head") or raw.get("keyword") or raw.get("title") or raw.get("name") or ""
        body = raw.get("text") or raw.get("column_content") or raw.get("content") or raw.get("description") or ""
        value = raw.get("value") or raw.get("number") or ""
        if not _s(body):
            # Noma'lum kalit ({"point": "..."}): sarlavha va raqamdan boshqa hamma matn.
            body = " ".join(_flatten({k: v for k, v in raw.items()
                                      if k not in ("head", "keyword", "title", "name", "value", "number", "icon")}))
    else:
        head, body, value = "", raw, ""
    return {"head": _clean(_s(head)), "text": _clean(_s(body)), "value": _clean(_s(value))}


def items_of(slide: Dict) -> List[Dict]:
    """Slayd elementlari [{head, text, value}]: `items`, `columns`, raqamli
    satrlar yoki gaplardan (oxirgisi — eski shakldagi `content` uchun)."""
    raw = slide.get("items") or slide.get("columns") or []
    items = [i for i in (_read_item(r) for r in raw) if i["text"]]
    if items:
        return items
    content = _s(slide.get("content"))
    lines = [ln for ln in content.split("\n") if ln.strip()]
    if len(lines) >= 3 and all(_NUM_PREFIX.match(ln) for ln in lines):
        return [{"head": "", "text": _NUM_PREFIX.sub("", ln).strip(), "value": ""} for ln in lines]
    return [{"head": "", "text": s, "value": ""} for s in slide_fit.sentences(content)]


def text_of(slide: Dict) -> str:
    """Slayd matni bitta abzats sifatida."""
    content = _s(slide.get("content"))
    if content:
        return content
    return " ".join(i["text"] for i in items_of(slide))


def ensure_content(slide: Dict) -> Dict:
    """Slayd matnini `content` ga yig'adi (AI qatlami uchun): lug'at yoki ro'yxat bo'lib kelgan matn
    satrga aylanadi, `items` yoki boshqa maydonlardagi (`bullets`, `points` ...) matn ko'chiriladi."""
    content = slide.get("content")
    if isinstance(content, (dict, list)):
        parts = _flatten(content)
        slide["content"] = "\n".join(parts) if len(parts) > 1 else (parts[0] if parts else "")
    if not _s(slide.get("content")) and slide.get("items"):
        slide["content"] = " ".join(i["text"] for i in items_of(slide))
    if not _s(slide.get("content")):
        for key in _ALT_TEXT_KEYS:
            parts = _flatten(slide.get(key))
            if parts:
                slide["content"] = "\n".join(parts) if len(parts) > 1 else parts[0]
                break
    return slide


def find_number(text: str) -> str:
    """Matndagi eng yorqin raqam ("85%", "3,2 marta"); yil emas. Topilmasa ''."""
    best = ""
    for match in _NUMBER.finditer(text or ""):
        raw = match.group(0).strip()
        digits = re.sub(r"\D", "", raw)
        if not digits or (len(digits) == 4 and _YEAR.fullmatch(digits) and raw == digits):
            continue
        has_unit = bool(re.search(r"\D", raw.replace(" ", "").replace(",", "").replace(".", "")))
        if len(raw) > 12:
            continue
        if has_unit:
            return raw
        if not best and len(digits) >= 2:
            best = raw
    return best


def value_of(item: Dict) -> str:
    return item.get("value") or find_number(f"{item.get('head', '')} {item.get('text', '')}")


def stat_of(slide: Dict, text: str) -> Dict:
    stat = slide.get("stat")
    if isinstance(stat, dict) and _s(stat.get("value")):
        return {"value": _s(stat["value"]), "label": _s(stat.get("label"))}
    value = find_number(text)
    return {"value": value, "label": ""} if value else {}


def features(slide: Dict) -> Dict:
    items = items_of(slide)
    text = text_of(slide)
    return {
        "items": items,
        "text": text,
        "n": len(items),
        "heads": sum(1 for i in items if i["head"]),
        "sents": len(slide_fit.sentences(text)),
        "words": slide_fit.words(text),
        "stat": stat_of(slide, text),
        "values": sum(1 for i in items if value_of(i)),
        "years": len(set(_YEAR.findall(f"{slide.get('title', '')} {text}"))),
    }


def reshape(items: List[Dict], lo: int, hi: int) -> Optional[List[Dict]]:
    """Elementlar sonini [lo, hi] ga keltiradi — hech narsa tashlanmaydi:
    ortiqchasi oxirgisiga qo'shiladi, yetmasa uzun matn gap bo'yicha bo'linadi."""
    items = [dict(i) for i in items]
    if not items:
        return None
    if len(items) == hi + 1:
        a, b = items[-2], items[-1]
        tail = f"{b['head']}: {b['text']}" if b["head"] else b["text"]
        items[-2:] = [{"head": a["head"], "text": f"{a['text']} {tail}".strip(), "value": a["value"]}]
    while len(items) < lo:
        idx = max(range(len(items)), key=lambda k: len(slide_fit.sentences(items[k]["text"])))
        parts = slide_fit.sentences(items[idx]["text"])
        if len(parts) < 2:
            return None
        cut = max(1, len(parts) // 2)
        items[idx:idx + 1] = [
            {"head": items[idx]["head"], "text": " ".join(parts[:cut]), "value": items[idx]["value"]},
            {"head": "", "text": " ".join(parts[cut:]), "value": ""},
        ]
    return items if lo <= len(items) <= hi else None


# ── chizish: umumiy bo'laklar ───────────────────────────────────────────────

def _hb_paras(item: Dict, pt: int, pal) -> list:
    paras = []
    if item.get("head"):
        paras.append((item["head"], {"bold": True, "pt": pt + 2, "colour": pal.accent}))
    paras.append((item["text"], {"pt": pt}))
    return paras


def _hb_pt(ctx, boxes, max_pt: int = 20, min_pt: int = 14) -> int:
    """Hamma (element, kenglik, balandlik) qutilariga sig'adigan umumiy shrift."""
    for pt in range(max_pt, min_pt - 1, -1):
        if all(kit._paragraphs_fit(_hb_paras(i, pt, ctx.pal), w, h, pt, False, 4) for i, w, h in boxes):
            return pt
    ctx.overflow = True
    return min_pt


def _hb(ctx, item, left, top, width, height, pt, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    kit.text(ctx, left, top, width, height, _hb_paras(item, pt, ctx.pal), pt=pt,
             align=align, anchor=anchor, space_after=4, name="item")


def _uniform_pt(ctx, texts_boxes, max_pt: int = 20, min_pt: int = 14, bold: bool = False) -> int:
    for pt in range(max_pt, min_pt - 1, -1):
        if all(kit._paragraphs_fit([(t, {})], w, h, pt, bold, 0) for t, w, h in texts_boxes):
            return pt
    ctx.overflow = True
    return min_pt


def _one_line_pt(text: str, width: float, max_pt: int, min_pt: int) -> int:
    for pt in range(max_pt, min_pt - 1, -1):
        if slide_fit.count_lines(text, pt * 1.05, width) <= 1:
            return pt
    return min_pt


def _row_card(ctx, item, index, x, y, w, h, badge: float, pt: int, use_icon: bool = False):
    """Karta: chapda raqam (yoki ikonka), o'ngda sarlavha + matn."""
    kit.card(ctx, x, y, w, h)
    bx, by = x + 0.22, y + (h - badge) / 2 if h < 2.0 else y + 0.22
    kit.marker(ctx, item.get("head", ""), item["text"], bx, by, badge, str(index + 1))
    _hb(ctx, item, x + badge + 0.45, y + 0.08, w - badge - 0.65, h - 0.16, pt, anchor=MSO_ANCHOR.MIDDLE)


def _row_card_box(w, h, badge):
    return w - badge - 0.65, h - 0.16


# ── yangi shablonlar ────────────────────────────────────────────────────────

def r_four_cards(ctx, d):
    items, gap = d["items"], 0.3
    cw, ch = (W - gap) / 2, (H - gap - 0.15) / 2
    bw, bh = _row_card_box(cw, ch, 0.75)
    pt = _hb_pt(ctx, [(i, bw, bh) for i in items], 20, 14)
    for k, item in enumerate(items):
        x, y = L + (k % 2) * (cw + gap), T + 0.1 + (k // 2) * (ch + gap)
        _row_card(ctx, item, k, x, y, cw, ch, 0.75, pt)


def r_numbered_list(ctx, d):
    items = d["items"]
    n = len(items)
    rh = (H - 0.1) / n
    bw, bh = W - 1.7, rh - 0.08
    pt = _hb_pt(ctx, [(i, bw, bh) for i in items], 20, 14)
    for k, item in enumerate(items):
        y = T + 0.05 + k * rh
        size = min(0.9, rh - 0.2)
        kit.marker(ctx, item["head"], item["text"], L + (1.4 - size) / 2, y + (rh - size) / 2, size, f"{k + 1:02d}")
        _hb(ctx, item, L + 1.6, y + 0.04, bw, bh, pt, anchor=MSO_ANCHOR.MIDDLE)
        if k < n - 1:
            kit.line(ctx, L + 0.2, y + rh, R - 0.2, y + rh, width=1.0, alpha=45)


def r_bullets_icons(ctx, d):
    items = d["items"]
    n = len(items)
    rh = (H - 0.1) / n
    bw, bh = W - 1.75, rh - 0.2
    pt = _hb_pt(ctx, [(i, bw, bh) for i in items], 20, 14)
    badge = min(0.9, rh - 0.3)
    for k, item in enumerate(items):
        y = T + 0.05 + k * rh
        kit.card(ctx, L, y + 0.05, W, rh - 0.1)
        kit.marker(ctx, item["head"], item["text"], L + 0.25, y + (rh - badge) / 2, badge, str(k + 1))
        _hb(ctx, item, L + 1.4, y + 0.1, bw, bh, pt, anchor=MSO_ANCHOR.MIDDLE)


def r_timeline(ctx, d):
    items = d["items"]
    n = len(items)
    gap = 0.25
    cw = (W - (n - 1) * gap) / n
    line_y = T + 1.0
    bw, bh = cw - 0.3, H - 1.85
    pt = _hb_pt(ctx, [(i, bw, bh) for i in items], 18, 14)
    centers = [L + k * (cw + gap) + cw / 2 for k in range(n)]
    kit.line(ctx, centers[0], line_y, centers[-1], line_y, width=3.0, alpha=70)
    for k, item in enumerate(items):
        x = L + k * (cw + gap)
        value = item["value"] if item["value"] and item["value"] != item["head"] else ""
        if value:
            kit.text(ctx, x, T + 0.05, cw, 0.5, value, pt=_one_line_pt(value, cw, 22, 14), bold=True,
                     colour=ctx.pal.accent, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, name="year")
        kit.marker(ctx, item["head"], item["text"], centers[k] - 0.3, line_y - 0.3, 0.6, str(k + 1))
        kit.card(ctx, x, line_y + 0.55, cw, H - 1.6)
        _hb(ctx, item, x + 0.15, line_y + 0.65, bw, bh - 0.05, pt)


def r_staircase(ctx, d):
    items = d["items"]
    n = len(items)
    rh, shift = (H - 0.1) / n, 0.5
    badge = min(0.75, rh - 0.3)
    bw = W - 1.3 - (n - 1) * shift
    bh = rh - 0.26
    pt = _hb_pt(ctx, [(i, bw, bh) for i in items], 20, 14)
    for k, item in enumerate(items):
        x, y = L + k * shift, T + 0.05 + k * rh
        kit.card(ctx, x, y + 0.05, W - k * shift, rh - 0.1)
        kit.marker(ctx, item["head"], item["text"], x + 0.22, y + (rh - badge) / 2, badge, str(k + 1))
        _hb(ctx, item, x + badge + 0.5, y + 0.13, bw, bh, pt, anchor=MSO_ANCHOR.MIDDLE)


def r_chevron_process(ctx, d):
    items = d["items"]
    n = len(items)
    overlap = 0.25
    cw = (W + (n - 1) * overlap) / n
    colw = (W - (n - 1) * 0.25) / n
    heads = [i["head"] for i in items]
    head_pt = min(_uniform_pt(ctx, [(h, cw - 1.0, 1.0) for h in heads], 20, 13, bold=True), 20)
    for k, item in enumerate(items):
        x = L + k * (cw - overlap)
        kind = MSO_SHAPE.PENTAGON if k == 0 else MSO_SHAPE.CHEVRON
        kit.shape(ctx, kind, x, T + 0.1, cw, 1.1, fill=ctx.pal.accent, name="chevron")
        kit.text(ctx, x + (0.25 if k == 0 else 0.55), T + 0.1, cw - 1.0, 1.1, item["head"], pt=head_pt,
                 bold=True, colour=ctx.pal.on_accent, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
                 name="step")
    bw, bh = colw - 0.3, H - 1.75
    pt = _uniform_pt(ctx, [(i["text"], bw, bh) for i in items], 20, 14)
    for k, item in enumerate(items):
        x = L + k * (colw + 0.25)
        kit.card(ctx, x, T + 1.45, colw, H - 1.55)
        kit.text(ctx, x + 0.15, T + 1.6, bw, bh, item["text"], pt=pt, name="step_text")


def r_hub_spoke(ctx, d):
    items = d["items"]
    cx, cy, dia = L + W / 2, T + H / 2, 2.3
    cw, ch = 4.25, 2.3
    spots = [(L, T + 0.05), (L, B - ch - 0.05), (R - cw, T + 0.05), (R - cw, B - ch - 0.05)]
    bw, bh = cw - 0.4, ch - 0.2
    pt = _hb_pt(ctx, [(i, bw, bh) for i in items], 19, 14)
    for (x, y) in spots:          # chiziqlar ostida, doira va kartalar ustida
        edge_x = x + cw if x == L else x
        kit.line(ctx, cx, cy, edge_x, y + ch / 2, width=2.5, alpha=60)
    kit.shape(ctx, MSO_SHAPE.OVAL, cx - dia / 2, cy - dia / 2, dia, dia, fill=ctx.pal.accent, name="hub")
    if not _hub_icon(ctx, d, cx, cy, dia * 0.5):
        kit.text(ctx, cx - dia * 0.4, cy - dia * 0.3, dia * 0.8, dia * 0.6, d["title"], bold=True,
                 colour=ctx.pal.on_accent, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
                 min_pt=12, max_pt=22, name="hub_text")
    for (x, y), item in zip(spots, items):
        kit.card(ctx, x, y, cw, ch)
        _hb(ctx, item, x + 0.2, y + 0.1, bw, bh, pt, anchor=MSO_ANCHOR.MIDDLE)


def _hub_icon(ctx, d, cx, cy, size) -> bool:
    if not ctx.use_icons or ctx.icon_finder is None:
        return False
    try:
        path = ctx.icon_finder(d["title"], "", set())
    except Exception:
        return False
    import os
    if not path or not os.path.isfile(path):
        return False
    if ctx.dry:
        return True
    from pptx.util import Inches
    from services.premium_presentation import icon_render
    glyph = icon_render.tinted(path, ctx.pal.on_accent) or path
    ctx.slide.shapes.add_picture(glyph, Inches(cx - size / 2), Inches(cy - size / 2), Inches(size), Inches(size))
    return True


def r_pillars(ctx, d):
    items = d["items"]
    n = len(items)
    gap = 0.3
    cw = (W - (n - 1) * gap) / n
    head_pt = min(_uniform_pt(ctx, [(i["head"], cw - 0.3, 1.0) for i in items], 22, 14, bold=True), 22)
    bw, bh = cw - 0.4, H - 1.6
    pt = _uniform_pt(ctx, [(i["text"], bw, bh) for i in items], 20, 14)
    for k, item in enumerate(items):
        x = L + k * (cw + gap)
        kit.card(ctx, x, T + 0.1, cw, H - 0.2)
        kit.panel(ctx, x, T + 0.1, cw, 1.0)
        kit.text(ctx, x + 0.15, T + 0.1, cw - 0.3, 1.0, item["head"], pt=head_pt, bold=True,
                 colour=ctx.pal.on_accent, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, name="pillar")
        kit.text(ctx, x + 0.2, T + 1.3, bw, bh, item["text"], pt=pt, name="pillar_text")


def r_stat_hero(ctx, d):
    stat = d["stat"]
    value = stat["value"]
    kit.panel(ctx, L, T + 0.15, 4.2, H - 0.3, radius=0.25)
    vpt = _one_line_pt(value, 3.8, 80, 32)
    kit.text(ctx, L + 0.2, T + 0.6, 3.8, 2.2, value, pt=vpt, bold=True, colour=ctx.pal.on_accent,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, name="stat_value")
    if stat.get("label"):
        kit.text(ctx, L + 0.3, T + 2.95, 3.6, 1.6, stat["label"], colour=ctx.pal.on_accent,
                 align=PP_ALIGN.CENTER, min_pt=14, max_pt=20, name="stat_label")
    kit.text(ctx, L + 4.6, T + 0.15, W - 4.6, H - 0.3, d["text"], anchor=MSO_ANCHOR.MIDDLE,
             min_pt=16, max_pt=24, name="stat_text")


def r_stats_row(ctx, d):
    items = d["items"]
    n = len(items)
    gap = 0.3
    cw = (W - (n - 1) * gap) / n
    has_head = any(i["head"] for i in items)
    body_y = 2.55 if has_head else 1.7
    bw, bh = cw - 0.4, H - 0.4 - body_y - 0.1
    pt = _uniform_pt(ctx, [(i["text"], bw, bh) for i in items], 19, 14)
    for k, item in enumerate(items):
        x, y = L + k * (cw + gap), T + 0.2
        kit.card(ctx, x, y, cw, H - 0.4)
        value = value_of(item)
        kit.text(ctx, x + 0.1, y + 0.3, cw - 0.2, 1.2, value,
                 pt=_one_line_pt(value, cw - 0.2, 54, 26), bold=True, colour=ctx.pal.accent,
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, name="stat_value")
        if item["head"]:
            kit.text(ctx, x + 0.15, y + 1.55, cw - 0.3, 0.9, item["head"], bold=True,
                     colour=ctx.pal.accent, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
                     min_pt=14, max_pt=20, name="stat_head")
        kit.text(ctx, x + 0.2, y + body_y - 0.2, bw, bh, item["text"], pt=pt, align=PP_ALIGN.CENTER,
                 name="stat_text")


def r_quote_focus(ctx, d):
    sents = slide_fit.sentences(d["text"])
    quote, rest = sents[0], " ".join(sents[1:])
    kit.card(ctx, L, T + 0.15, W, 2.35, radius=0.2)
    kit.shape(ctx, MSO_SHAPE.RECTANGLE, L + 0.25, T + 0.45, 0.14, 1.75, fill=ctx.pal.accent, name="bar")
    kit.text(ctx, L + 0.55, T + 0.1, 1.3, 1.5, "“", pt=96, bold=True, colour=ctx.pal.accent,
             name="mark")
    kit.text(ctx, L + 1.7, T + 0.3, W - 2.1, 2.05, quote, italic=True, anchor=MSO_ANCHOR.MIDDLE,
             min_pt=18, max_pt=28, name="quote")
    kit.text(ctx, L + 0.2, T + 2.75, W - 0.4, H - 2.85, rest, min_pt=16, max_pt=22, name="quote_rest")


def r_split_panel(ctx, d):
    sents = slide_fit.sentences(d["text"])
    lead, rest = sents[0], sents[1:]
    kit.panel(ctx, L, T + 0.15, 4.3, H - 0.3, radius=0.25)
    kit.text(ctx, L + 0.3, T + 0.45, 3.7, H - 0.9, lead, colour=ctx.pal.on_accent,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE, min_pt=16, max_pt=26, bold=True, name="lead")
    kit.text(ctx, L + 4.7, T + 0.15, W - 4.7, H - 0.3, [("•  " + s, {}) for s in rest],
             anchor=MSO_ANCHOR.MIDDLE, min_pt=16, max_pt=22, space_after=10, name="points")


def r_icon_row(ctx, d):
    items = d["items"]
    n = len(items)
    gap = 0.3
    cw = (W - (n - 1) * gap) / n
    has_head = any(i["head"] for i in items)
    body_y = 3.05 if has_head else 1.95
    bw, bh = cw - 0.4, H - 0.2 - body_y - 0.1
    pt = _uniform_pt(ctx, [(i["text"], bw, bh) for i in items], 19, 14)
    for k, item in enumerate(items):
        x, y = L + k * (cw + gap), T + 0.1
        kit.card(ctx, x, y, cw, H - 0.2)
        size = 1.25
        bx = x + (cw - size) / 2
        kit.marker(ctx, item["head"], item["text"], bx, y + 0.3, size, str(k + 1))
        if item["head"]:
            kit.text(ctx, x + 0.15, y + 1.75, cw - 0.3, 1.0, item["head"], bold=True, colour=ctx.pal.accent,
                     align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, min_pt=15, max_pt=22, name="head")
        kit.text(ctx, x + 0.2, y + body_y - 0.1, bw, bh, item["text"], pt=pt, align=PP_ALIGN.CENTER,
                 name="body")


def r_comparison(ctx, d):
    items = d["items"]
    cw = (W - 0.6) / 2
    bw, bh = cw - 0.5, H - 1.45
    sides = [slide_fit.sentences(i["text"]) or [i["text"]] for i in items]
    head_pt = min(_uniform_pt(ctx, [(i["head"], cw - 0.4, 0.9) for i in items], 24, 15, bold=True), 24)
    paras = [[("•  " + s, {}) for s in side] for side in sides]
    pt = 14
    for cand in range(20, 13, -1):
        if all(kit._paragraphs_fit(p, bw, bh, cand, False, 8) for p in paras):
            pt = cand
            break
    else:
        ctx.overflow = True
    for k, item in enumerate(items):
        x = L if k == 0 else R - cw
        kit.card(ctx, x, T + 0.1, cw, H - 0.2)
        kit.panel(ctx, x, T + 0.1, cw, 0.95)
        kit.text(ctx, x + 0.2, T + 0.1, cw - 0.4, 0.95, item["head"], pt=head_pt, bold=True,
                 colour=ctx.pal.on_accent, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, name="side")
        kit.text(ctx, x + 0.25, T + 1.3, bw, bh, paras[k], pt=pt, space_after=8, name="side_text")
    kit.number_badge(ctx, L + W / 2 - 0.45, T + 0.12, 0.9, "VS", filled=True, pt=20)


def r_glossary_rows(ctx, d):
    items = d["items"]
    n = len(items)
    gap = 0.15
    rh = (H - 0.1 - (n - 1) * gap) / n
    lw = 3.0
    head_pt = min(_uniform_pt(ctx, [(i["head"], lw - 0.3, rh - 0.1) for i in items], 20, 13, bold=True), 20)
    bw, bh = W - lw - 0.5, rh - 0.1
    pt = _uniform_pt(ctx, [(i["text"], bw, bh) for i in items], 18, 14)
    for k, item in enumerate(items):
        y = T + 0.05 + k * (rh + gap)
        kit.panel(ctx, L, y, lw, rh, radius=0.12)
        kit.text(ctx, L + 0.15, y, lw - 0.3, rh, item["head"], pt=head_pt, bold=True,
                 colour=ctx.pal.on_accent, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, name="term")
        kit.card(ctx, L + lw + 0.15, y, W - lw - 0.15, rh, radius=0.12)
        kit.text(ctx, L + lw + 0.35, y + 0.05, bw, bh, item["text"], pt=pt, anchor=MSO_ANCHOR.MIDDLE,
                 name="definition")


def r_image_top_columns(ctx, d):
    items = d["items"]
    kit.picture(ctx, L, T + 0.05, W, 2.55, bias=0.5)
    cw, y, h = (W - 0.3) / 2, T + 2.8, H - 2.85
    bw, bh = cw - 0.4, h - 0.2
    pt = _hb_pt(ctx, [(i, bw, bh) for i in items], 18, 14)
    for k, item in enumerate(items):
        x = L + k * (cw + 0.3)
        kit.card(ctx, x, y, cw, h)
        _hb(ctx, item, x + 0.2, y + 0.1, bw, bh, pt, anchor=MSO_ANCHOR.MIDDLE)


def r_image_left_bullets(ctx, d):
    items = d["items"]
    n = len(items)
    kit.picture(ctx, L, T + 0.05, 4.7, H - 0.1)
    x0, w = L + 5.0, W - 5.0
    rh = (H - 0.1) / n
    bw, bh = w - 0.8, rh - 0.1
    pt = _hb_pt(ctx, [(i, bw, bh) for i in items], 19, 14)
    for k, item in enumerate(items):
        y = T + 0.05 + k * rh
        kit.marker(ctx, item["head"], item["text"], x0, y + (rh - 0.6) / 2, 0.6, str(k + 1))
        _hb(ctx, item, x0 + 0.8, y + 0.05, bw, bh, pt, anchor=MSO_ANCHOR.MIDDLE)


def r_image_right_cards(ctx, d):
    items = d["items"]
    gap = 0.2
    cw, ch = 6.75, (H - 0.1 - 2 * gap) / 3
    bw, bh = _row_card_box(cw, ch, 0.6)
    pt = _hb_pt(ctx, [(i, bw, bh) for i in items], 18, 14)
    for k, item in enumerate(items):
        _row_card(ctx, item, k, L, T + 0.05 + k * (ch + gap), cw, ch, 0.6, pt)
    kit.picture(ctx, L + 7.05, T + 0.05, W - 7.05, H - 0.1)


def r_image_overlay(ctx, d):
    kit.picture(ctx, 0, 0, 13.333, 7.5, bias=0.5, rounded=False)
    kit.shape(ctx, MSO_SHAPE.ROUNDED_RECTANGLE, 0.6, 4.5, 12.13, 2.55, fill="000000", alpha=62,
              name="veil", radius=0.2)
    kit.text(ctx, 0.9, 4.58, 11.5, 0.85, d["title"], bold=True, colour="FFFFFF", anchor=MSO_ANCHOR.MIDDLE,
             min_pt=20, max_pt=34, name="overlay_title")
    kit.text(ctx, 0.9, 5.45, 11.5, 1.5, d["text"], colour="FFFFFF", min_pt=15, max_pt=22,
             name="overlay_text")


# ── katalog ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Spec:
    name: str
    family: str                          # qo'shni slaydlarda bir xil ko'rinish bo'lmasin
    slots: Optional[tuple] = None        # elementlar soni [lo, hi]; None — matn shakli
    heads: bool = False                  # har elementda sarlavha kerak
    image: Optional[str] = None          # 'slide' | 'panorama'
    check: Optional[Callable[[Dict], bool]] = None
    render: Optional[Callable] = None    # None — eski (document_service) shablon
    own_title: bool = False              # sarlavhani shablonning o'zi chizadi
    fallback: bool = False               # rasm chiqmasa matnli ko'rinishga o'tadi
    desc_uz: str = ""
    desc_ru: str = ""
    desc_en: str = ""


def _short_heads(f: Dict, limit: int = 5) -> bool:
    return all(len(i["head"].split()) <= limit for i in f["items"] if i["head"])


SPECS: List[Spec] = [
    # eski 6 ta
    Spec("two_column", "cols", (2, 2), desc_uz="2 ustun, har birida ikonka va 2-3 gap",
         desc_ru="2 колонки с иконкой и 2-3 предложениями", desc_en="2 columns with icon and 2-3 sentences"),
    Spec("three_column", "cols", (3, 3), desc_uz="3 ustun: kalit so'z + 1 gap, ikonkali",
         desc_ru="3 колонки: ключевое слово + предложение, с иконками",
         desc_en="3 columns: keyword + one sentence, with icons"),
    Spec("right_image", "image", None, image="slide", fallback=True, check=lambda f: f["sents"] >= 2,
         desc_uz="o'ngda rasm, chapda matn", desc_ru="справа изображение, слева текст",
         desc_en="image on the right, text on the left"),
    Spec("left_image", "image", None, image="slide", fallback=True, check=lambda f: f["sents"] >= 2,
         desc_uz="chapda rasm, o'ngda matn", desc_ru="слева изображение, справа текст",
         desc_en="image on the left, text on the right"),
    Spec("horizontal_image", "image", None, image="panorama", fallback=True, check=lambda f: f["sents"] >= 2,
         desc_uz="pastda keng rasm, tepada matn", desc_ru="внизу широкое изображение, сверху текст",
         desc_en="wide image at the bottom, text above"),
    Spec("text_with_numbers", "text", None,
         desc_uz="raqamlab yozilgan faktlar (matn)", desc_ru="нумерованные факты (текст)",
         desc_en="numbered facts (text)"),
    # yangi 19 ta
    Spec("four_cards", "cards", (4, 4), render=r_four_cards,
         desc_uz="2x2 to'rtta karta", desc_ru="четыре карточки 2x2", desc_en="four cards in a 2x2 grid"),
    Spec("numbered_list", "list", (4, 5), render=r_numbered_list,
         desc_uz="katta raqamli ro'yxat (4-5 band)", desc_ru="список с крупными номерами (4-5 пунктов)",
         desc_en="list with big numbers (4-5 points)"),
    Spec("bullets_icons", "list", (3, 4), render=r_bullets_icons,
         desc_uz="ikonkali qatorlar", desc_ru="строки с иконками", desc_en="rows with icons"),
    Spec("timeline", "list", (3, 5), render=r_timeline,
         desc_uz="vaqt chizig'i (tarix, bosqichlar, yillar)", desc_ru="линия времени (история, этапы, годы)",
         desc_en="timeline (history, stages, years)"),
    Spec("staircase", "list", (3, 5), render=r_staircase,
         desc_uz="pog'onali o'sish/bosqichlar", desc_ru="ступени (рост, этапы)",
         desc_en="ascending steps (growth, stages)"),
    Spec("chevron_process", "list", (3, 4), heads=True, render=r_chevron_process,
         check=_short_heads, desc_uz="strelkali jarayon: qisqa sarlavha + izoh",
         desc_ru="процесс со стрелками: короткий заголовок + пояснение",
         desc_en="arrow process: short heading + explanation"),
    Spec("hub_spoke", "cards", (4, 4), render=r_hub_spoke,
         desc_uz="markaz va to'rt yo'nalish (tarkib, omillar)", desc_ru="центр и четыре направления (состав, факторы)",
         desc_en="hub with four spokes (components, factors)"),
    Spec("pillars", "cols", (3, 4), heads=True, render=r_pillars, check=_short_heads,
         desc_uz="ustunlar: rangli sarlavha + matn (turlari, guruhlari)",
         desc_ru="столбцы: цветной заголовок + текст (виды, группы)",
         desc_en="pillars: coloured heading + text (types, groups)"),
    Spec("stat_hero", "stat", None, render=r_stat_hero,
         check=lambda f: bool(f["stat"]) and f["sents"] >= 2,
         desc_uz="bitta katta raqam va izoh (matnda raqam bo'lsa)", desc_ru="одна крупная цифра и пояснение",
         desc_en="one big number with explanation"),
    Spec("stats_row", "stat", (3, 4), render=r_stats_row,
         check=lambda f: f["values"] >= 3,
         desc_uz="3-4 ta raqamli ko'rsatkich qatori", desc_ru="ряд из 3-4 числовых показателей",
         desc_en="row of 3-4 numeric indicators"),
    Spec("quote_focus", "text", None, render=r_quote_focus, check=lambda f: f["sents"] >= 3,
         desc_uz="asosiy fikr ajratib ko'rsatiladi, qolgani ostida",
         desc_ru="главная мысль выделена, остальное ниже", desc_en="key idea highlighted, rest below"),
    Spec("split_panel", "text", None, render=r_split_panel, check=lambda f: f["sents"] >= 3,
         desc_uz="chapda rangli panel (bosh gap), o'ngda bandlar", desc_ru="слева цветная панель, справа пункты",
         desc_en="coloured panel left, points right"),
    Spec("icon_row", "cols", (3, 4), render=r_icon_row,
         desc_uz="katta ikonkali 3-4 ustun (markazda)", desc_ru="3-4 колонки с крупными иконками",
         desc_en="3-4 centred columns with big icons"),
    Spec("comparison", "cards", (2, 2), heads=True, render=r_comparison, check=_short_heads,
         desc_uz="ikki tomonni taqqoslash (VS)", desc_ru="сравнение двух сторон (VS)",
         desc_en="two-sided comparison (VS)"),
    Spec("glossary_rows", "cards", (3, 5), heads=True, render=r_glossary_rows, check=_short_heads,
         desc_uz="atama va uning izohi qatorlari", desc_ru="термин и его пояснение по строкам",
         desc_en="term and explanation rows"),
    Spec("image_top_columns", "image", (2, 2), image="panorama", render=r_image_top_columns, fallback=True,
         desc_uz="tepada keng rasm, pastda ikki ustun", desc_ru="сверху широкое изображение, снизу две колонки",
         desc_en="wide image on top, two columns below"),
    Spec("image_left_bullets", "image", (3, 4), image="slide", render=r_image_left_bullets, fallback=True,
         desc_uz="chapda rasm, o'ngda raqamli bandlar", desc_ru="слева изображение, справа пункты",
         desc_en="image left, numbered points right"),
    Spec("image_right_cards", "image", (3, 3), image="slide", render=r_image_right_cards, fallback=True,
         desc_uz="chapda 3 karta, o'ngda rasm", desc_ru="слева 3 карточки, справа изображение",
         desc_en="3 cards left, image right"),
    Spec("image_overlay", "image", None, image="panorama", render=r_image_overlay, own_title=True,
         fallback=True, check=lambda f: 2 <= f["sents"] <= 4 and f["words"] <= 65,
         desc_uz="butun slaydga rasm, ustida qisqa matn (2-3 gap)", desc_ru="изображение на весь слайд и короткий текст",
         desc_en="full-slide image with short text overlay"),
]

CATALOG: Dict[str, Spec] = {s.name: s for s in SPECS}
NAMES = tuple(CATALOG)
KIT_LAYOUTS = {s.name for s in SPECS if s.render}          # yangi chizuvchilar
LEGACY_LAYOUTS = {s.name for s in SPECS if not s.render}


def image_kind(layout: str) -> Optional[str]:
    spec = CATALOG.get(layout)
    return spec.image if spec else None


def describe(language: str = "uz") -> str:
    """Prompt uchun katalog: nom, elementlar soni va qisqa tavsif."""
    attr = {"uz": "desc_uz", "ru": "desc_ru"}.get(language, "desc_en")
    word = {"uz": "element", "ru": "элементов", "en": "items"}.get(language, "items")
    rows = []
    for s in SPECS:
        lo, hi = s.slots or (3, 5)
        count = str(lo) if lo == hi else f"{lo}-{hi}"
        rows.append(f"- {s.name} ({count} {word}): {getattr(s, attr)}")
    return "\n".join(rows)


# ── tanlash ─────────────────────────────────────────────────────────────────

def _any(text: str, words) -> bool:
    return any(w in text for w in words)


_PROCESS = ("bosqich", "qadam", "avval", "keyin", "algoritm", "etap", "ketma-ket", "tartibda", "этап",
            "шаг", "стади", "сначала", "затем", "последовательн", "step", "stage", "phase", "workflow",
            "first,", "then ")
_COMPARE = ("farq", "taqqos", "solishtir", "afzallik", "kamchilik", "qarama", "сравн", "различ",
            "преимуществ", "недостат", "против", "compar", "differen", "versus", "advantage", "disadvantage")
_DEFINE = ("tushuncha", "ta'rif", "tarif", "atama", "deb ataladi", "определен", "понятие", "термин",
           "называется", "definition", "concept", "is defined", "refers to")
_TYPES = ("turlari", "tasnif", "guruh", "kategoriya", "виды", "классиф", "типы", "types", "classification",
          "categories", "kinds")
_PARTS = ("tarkib", "element", "omil", "komponent", "состав", "фактор", "компонент", "structure",
          "struktur", "factors", "components", "elements")
_HISTORY = ("tarix", "rivojlan", "истор", "развит", "history", "development", "evolution", "davr")


def _affinity(name: str, f: Dict, title: str) -> float:
    """Shablonning shu slayd mazmuniga mosligi (0..~3.5)."""
    hay = f"{title} {f['text']}".lower()
    score = 0.0
    process = sum(1 for w in _PROCESS if w in hay) >= 2
    if name in ("timeline", "staircase", "chevron_process") and process:
        score += 2.2
    if name == "timeline" and (f["years"] >= 3 or _any(hay, _HISTORY)):
        score += 2.8 if f["years"] >= 3 else 1.2
    if name == "comparison" and f["n"] == 2 and _any(hay, _COMPARE):
        score += 3.5
    if name in ("glossary_rows", "quote_focus", "split_panel") and _any(hay, _DEFINE):
        score += 1.5
    if name in ("pillars", "four_cards", "icon_row") and _any(hay, _TYPES):
        score += 1.6
    if name in ("hub_spoke", "four_cards", "pillars") and _any(hay, _PARTS):
        score += 1.4
    if name == "stats_row" and f["values"] >= 3:
        score += 3.0
    if name == "stat_hero" and f["stat"]:
        score += 2.2 if f["stat"].get("label") or re.search(r"%|foiz|процент|percent", f["text"], re.I) else 1.0
    if name == "text_with_numbers" and f["values"] >= 3:
        score += 0.8
    return score


def _shape_for(spec: Spec, slide: Dict, f: Dict) -> Optional[Dict]:
    """Slaydni shablon talab qilgan shaklga keltiradi; mos kelmasa None."""
    data = dict(slide)
    data["layout"] = spec.name
    data["stat"] = f["stat"]
    if spec.slots:
        items = reshape(f["items"], *spec.slots)
        if not items:
            return None
        if spec.heads and sum(1 for i in items if i["head"]) < len(items):
            return None
        data["items"] = items
        data["content"] = f["text"]
    else:
        data["items"] = f["items"]
        data["content"] = f["text"]
    if spec.check:
        probe = dict(f)
        probe["items"] = data["items"]
        probe["n"] = len(data["items"])
        probe["values"] = sum(1 for i in data["items"] if value_of(i))
        if not spec.check(probe):
            return None
    if spec.name == "text_with_numbers" and len(f["items"]) >= 3 and "\n" not in f["text"]:
        data["content"] = "\n".join(f"{k + 1}. {i['text']}" for k, i in enumerate(f["items"]))
    if spec.name in ("two_column", "three_column"):
        data["columns"] = [{"keyword": i["head"], "column_content": i["text"]} for i in data["items"]]
    return data


class _Scratch:
    """O'lchash uchun bo'sh taqdimot (rasmga tegmaydi, faylga yozilmaydi)."""

    def __init__(self):
        self.prs = Presentation()

    def slide(self):
        return self.prs.slides.add_slide(self.prs.slide_layouts[6])


def _fits(spec: Spec, data: Dict, scratch: _Scratch) -> bool:
    if spec.render is None:
        out = slide_fit.prepare([dict(data)], "uz")
        return len(out) == 1 and out[0].get("layout") == spec.name and not out[0].get("_columns_text")
    ctx = kit.Ctx(slide=scratch.slide(), pal=kit.Palette(), dry=True, image="dry" if spec.image else None,
                  use_icons=False)
    spec.render(ctx, render_data(data))
    return not ctx.overflow


def render_data(slide: Dict) -> Dict:
    f = features(slide)
    return {"title": _s(slide.get("title")), "items": f["items"], "text": f["text"], "stat": f["stat"]}


def _seed(topic: str, count: int) -> int:
    return int(hashlib.md5(f"{topic}|{count}".encode("utf-8")).hexdigest()[:8], 16)


def image_budget(main_count: int, allowed: bool = True) -> int:
    if not allowed or main_count <= 0:
        return 0
    return max(1, int(main_count * 0.35 + 0.5))


def assign(slides: List[Dict], topic: str = "", language: str = "uz", seed: Optional[int] = None,
           images: bool = True) -> List[Dict]:
    """Har asosiy slaydga shablon tanlaydi (yangi ro'yxat; kirish ro'yxati o'zgarmaydi).

    Model taklif qilgan `layout` hisobga olinadi, lekin takror, bir xil ko'rinish
    qatori va rasm ko'pligi cheklanadi. Mos shablon topilmasa — matnli slayd.
    """
    main_ids = [i for i, s in enumerate(slides) if (s.get("layout") or "") not in FIXED]
    n = len(main_ids)
    rng = random.Random(seed if seed is not None else _seed(topic, n))
    budget = image_budget(n, images)
    min_images = 1 if (n >= 4 and budget) else 0
    scratch = _Scratch()
    counts: Counter = Counter()
    prev: Optional[Spec] = None
    used_images = 0
    result = list(slides)

    for pos, idx in enumerate(main_ids):
        slide = slides[idx]
        f = features(slide)
        title = _s(slide.get("title"))
        suggested = slide.get("layout") if slide.get("layout") in CATALOG else None
        remaining = n - pos - 1
        ranked = []
        for spec in SPECS:
            if spec.image and (used_images >= budget or (prev and prev.image)):
                continue
            data = _shape_for(spec, slide, f)
            if data is None:
                continue
            score = rng.random() + _affinity(spec.name, f, title)
            if spec.name == suggested:
                score += 2.0
            score -= 2.5 * counts[spec.name]
            if prev:
                if spec.name == prev.name:
                    score -= 10
                elif spec.family == prev.family:
                    score -= 1.2
            if spec.image:
                score -= 0.3
                if used_images < min_images and pos >= n / 3:
                    score += 1.0 + (4.0 if remaining <= 1 else 0.0)
            ranked.append((score, spec, data))
        ranked.sort(key=lambda r: -r[0])

        chosen = None
        for _, spec, data in ranked:
            if _fits(spec, data, scratch):
                chosen = (spec, data)
                break
        if chosen is None:
            spec = CATALOG["text_with_numbers"]
            chosen = (spec, _shape_for(spec, slide, f) or {**slide, "layout": spec.name})

        spec, data = chosen
        counts[spec.name] += 1
        if spec.image:
            used_images += 1
        prev = spec
        result[idx] = data

    logger.info("Shablonlar: %s", ", ".join(result[i]["layout"] for i in main_ids))
    return result
