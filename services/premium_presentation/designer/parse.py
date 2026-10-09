"""Kam matnli sahifa (HTML kompozitsiya) → vektor dizayner uchun mazmun (spec).

AI matnni avvalgidek kompozitsiya qolipiga yozadi: rejaning tekshiruvlari, so'z chegarasi, rasm
generatsiyasi va saytdagi ko'rinish o'zgarmaydi. PPTX chizilayotganda esa sahifaning MAZMUNI olinadi
(sarlavha, bosh gap, punktlar, rasm) va slayd vektor dizayn bilan qaytadan chiziladi.

Diagramma, formula va misol sahifalari bu yerda o'qilmaydi (`None`) — ular avvalgidek HTML dan chiziladi.
"""
import base64
import re
from typing import Dict, List, Optional

from lxml import html as lxml_html

from .. import deck_compose


def _classes(el) -> List[str]:
    return (el.get("class") or "").split()


def _find(root, cls: str):
    return root.xpath(f".//*[contains(concat(' ', normalize-space(@class), ' '), ' {cls} ')]")


def _first(root, cls: str) -> str:
    found = _find(root, cls)
    return _clean(found[0].text_content()) if found else ""


def _all(root, cls: str) -> List:
    return _find(root, cls)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().strip("…").strip()


def _photo(root) -> Optional[bytes]:
    for img in root.xpath(".//img[contains(concat(' ', normalize-space(@class), ' '), ' photo ')]"):
        src = img.get("src") or ""
        match = re.match(r"data:image/[\w.+-]+;base64,(.+)", src, re.DOTALL)
        if match:
            try:
                return base64.b64decode(match.group(1))
            except Exception:
                return None
    return None


def _section(page: str):
    try:
        doc = lxml_html.fromstring(page)
    except Exception:
        return None
    found = doc.xpath("//section[contains(concat(' ', normalize-space(@class), ' '), ' slide ')]")
    return found[0] if found else None


def spec_of(page: str, index: int, total: int) -> Optional[Dict]:
    """Sahifa mazmuni. Vektor dizaynga mos kelmasa — None (sahifa HTML dan chiziladi)."""
    section = _section(page)
    if section is None:
        return None
    cls = _classes(section)
    title = _first(section, "title")

    if index == 0 and "dark" in cls:
        return {"kind": "cover", "title": title, "lead": _first(section, "lead"),
                "credit": " · ".join(_clean(e.text_content()) for e in _find(section, "note") + _find(section, "sub")
                                     if _clean(e.text_content())),
                "photo": _photo(section)}

    if "reja" in cls:
        items = [{"title": _clean(e.text_content())} for e in _find(section, "card-title")]
        return {"kind": "plan", "title": title, "items": [i for i in items if i["title"]]}

    layout = deck_compose.layout_of(page)
    lead = _first(section, "lead")
    para = " ".join(_clean(e.text_content()) for e in _find(section, "k-p"))
    photo = _photo(section)

    if layout in deck_compose.PHOTO_LAYOUTS or layout == "rasm_fon":
        return {"kind": "photo", "layout": layout, "title": title, "lead": lead, "text": para, "photo": photo}
    if layout == "iqtibos":
        return {"kind": "photo", "title": title, "quote": _first(section, "quote"),
                "by": _first(section, "quote-by").lstrip("—– ").strip(), "text": para, "photo": photo}
    if layout == "kartalar":
        items = [{"title": _first(c, "k-h"), "note": _first(c, "k-d")} for c in _all(section, "k-card")]
        return _items("group", title, lead, items)
    if layout == "bosqichlar":
        items = [{"title": _first(c, "k-h"), "note": _first(c, "k-d")} for c in _all(section, "k-step")]
        return _items("sequence", title, lead, items)
    if layout == "vaqt":
        items = [{"title": _first(c, "k-y"), "note": _first(c, "k-yd")} for c in _all(section, "k-stop")]
        return _items("sequence", title, lead, items)
    if layout == "raqamlar":
        items = []
        for c in _all(section, "k-kpi"):
            value = " ".join(x for x in (_first(c, "k-v"), _first(c, "k-u")) if x)
            items.append({"title": _first(c, "k-l"), "note": _first(c, "k-d"), "value": value})
        spec = _items("numbers", title, lead, items)
        if spec:
            spec["source"] = _first(section, "k-src")
        return spec
    if layout == "qiyos":
        sides = []
        for half in _all(section, "k-half"):
            sides.append({"name": _first(half, "k-h2"), "question": _first(half, "k-q"),
                          "items": [_clean(e.text_content()) for e in _find(half, "k-li") if _clean(e.text_content())]})
        if len(sides) == 2 and all(s["items"] for s in sides):
            return {"kind": "compare", "title": title, "sides": sides}
        return None
    if layout == "yakun" or (index == total - 1 and layout == ""):
        points = [_clean(e.text_content()) for e in _find(section, "k-ln") if _clean(e.text_content())]
        if not lead and not points:
            return None
        return {"kind": "finale", "title": title, "lead": lead, "points": points}
    return None


def _items(kind: str, title: str, lead: str, items: List[Dict]) -> Optional[Dict]:
    items = [i for i in items if i.get("title") or i.get("note")]
    if len(items) < 2:
        return None
    return {"kind": kind, "title": title, "lead": lead, "items": items[:8]}
