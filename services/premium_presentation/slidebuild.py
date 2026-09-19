"""Qolip + mazmun + rang → tayyor slayd elementlari.

AI faqat "qaysi qolip" va "o'rinlarga nima yozilsin" deb beradi. Shu
modul o'sha mazmunni qolipdagi belgilangan o'rinlarga qo'yadi va
chizuvchi tushunadigan elementlar ro'yxatini yasaydi.

Ikki kafolat shu yerda:

1. Joylashuv qolipdan olinadi, AI dan emas — ustma-ust tushish
   bo'lmaydi.
2. Matn o'rin sig'imidan oshsa, oxirgi tugagan gapigacha qirqiladi —
   qutidan toshib chiqmaydi.
"""

import logging
import re
from typing import Dict, List, Optional

from .models import InfographicItem, VisualElement
from .templates import SLIDE_H, SLIDE_W, Slot, Template
from .themes import Theme

log = logging.getLogger("slidebuild")

_SENTENCE_END = re.compile(r"[.!?…](?=\s|$)")

# Bezak o'lchovlari.
_BAR_H = 0.085
_SIDE_W = 0.42


def fit_text(text: str, limit: int) -> str:
    """Matnni sig'imga keltiradi — gap o'rtasidan kesmasdan.

    Chegaradan oshgan matn avval oxirgi tugagan gapigacha, u ham
    topilmasa oxirgi butun so'zigacha qirqiladi. Shunda slaydda hech
    qachon yarim so'z turmaydi.
    """
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if limit <= 0 or len(value) <= limit:
        return value

    window = value[:limit]
    ends = list(_SENTENCE_END.finditer(window))
    if ends and ends[-1].end() >= limit * 0.55:
        return window[:ends[-1].end()].strip()

    cut = window.rsplit(" ", 1)[0].strip(" ,;:—–-")
    return (cut or window).rstrip() + "…"


def _colour(tone: str, theme: Theme) -> str:
    return {
        "heading": theme.heading,
        "body": theme.body,
        "muted": theme.muted,
        "accent": theme.accent,
        "invert": theme.invert,
    }.get(tone, theme.body)


def _text_element(slot: Slot, text: str, theme: Theme) -> Optional[VisualElement]:
    value = fit_text(text, slot.max_chars)
    if not value:
        return None
    return VisualElement(
        type="text", x=slot.x, y=slot.y, w=slot.w, h=slot.h,
        text=value, size=slot.size, bold=slot.bold, italic=slot.italic,
        align=slot.align, color=_colour(slot.tone, theme), locked=True,
    )


def _bullet_element(slot: Slot, values, theme: Theme) -> Optional[VisualElement]:
    """Bandlarni bitta matn qutisiga yig'adi.

    Har band alohida quti bo'lsa, biri uzun kelganda pastdagisiga minib
    qolardi. Bitta qutida ular bir-birini suradi, sig'masa esa chizuvchi
    shriftni kichraytiradi.
    """
    lines = []
    for item in (values or [])[:slot.max_items or 5]:
        line = fit_text(item, slot.max_chars)
        if line:
            lines.append(f"•  {line}")
    if not lines:
        return None
    return VisualElement(
        type="text", x=slot.x, y=slot.y, w=slot.w, h=slot.h,
        text="\n\n".join(lines), size=slot.size, align="left",
        color=_colour(slot.tone, theme), locked=True,
    )


def _infographic_element(slot: Slot, values, theme: Theme,
                         preset: str) -> Optional[VisualElement]:
    items = []
    for raw in (values or [])[:slot.max_items or 4]:
        if isinstance(raw, dict):
            title = fit_text(raw.get("title", ""), 42)
            text = fit_text(raw.get("text", ""), slot.max_chars)
            icon = (raw.get("icon") or "").strip() or None
            value = (raw.get("value") or "").strip() or None
        else:
            title, text, icon, value = fit_text(raw, 42), "", None, None
        if title or text:
            items.append(InfographicItem(title=title, text=text,
                                         icon=icon, value=value))
    if not items:
        return None
    return VisualElement(
        type="infographic", x=slot.x, y=slot.y, w=slot.w, h=slot.h,
        preset=preset, items=items, locked=True,
    )


def _scheme_element(slot: Slot, content: dict, theme: Theme) -> Optional[VisualElement]:
    raw = content.get("scheme")
    if isinstance(raw, dict):
        root = fit_text(raw.get("root", ""), 40)
        kind = (raw.get("kind") or "components").strip()
        branches = raw.get("items") or []
    else:
        root, kind, branches = "", "components", raw or []

    items = []
    for branch in list(branches)[:slot.max_items or 5]:
        if isinstance(branch, dict):
            title = fit_text(branch.get("title", ""), 38)
            text = fit_text(branch.get("text", ""), slot.max_chars)
        else:
            title, text = fit_text(branch, 38), ""
        if title:
            items.append(InfographicItem(title=title, text=text))
    if not items:
        return None

    allowed = {"hierarchy", "components", "process", "cycle", "levels"}
    return VisualElement(
        type="scheme", x=slot.x, y=slot.y, w=slot.w, h=slot.h,
        scheme_kind=kind if kind in allowed else "components",
        scheme_root=root or None, items=items, locked=True,
    )


def _chart_element(slot: Slot, content: dict, theme: Theme) -> Optional[VisualElement]:
    data = content.get("chart")
    if not isinstance(data, dict):
        return None
    categories = [str(c) for c in (data.get("categories") or []) if str(c).strip()]
    series = data.get("series") or []
    if not categories or not series:
        return None

    allowed = {"bar", "column", "line", "area", "pie", "donut", "radar", "scatter"}
    chart_type = (data.get("chart_type") or "column").strip().lower()
    return VisualElement(
        type="chart", x=slot.x, y=slot.y, w=slot.w, h=slot.h,
        chart_type=chart_type if chart_type in allowed else "column",
        chart_title=fit_text(data.get("chart_title", ""), 70) or None,
        caption=fit_text(data.get("caption", ""), 150) or None,
        categories=categories, series=series, locked=True,
    )


def _kpi_elements(slot: Slot, values, theme: Theme) -> List[VisualElement]:
    """Ko'rsatkich kartochkalarini o'rin ichida teng bo'lib joylaydi."""
    tiles = []
    for raw in (values or [])[:slot.max_items or 3]:
        if isinstance(raw, dict):
            value = fit_text(raw.get("value", ""), 12)
            label = fit_text(raw.get("label", ""), slot.max_chars)
        else:
            value, label = fit_text(raw, 12), ""
        if value:
            tiles.append((value, label))
    if not tiles:
        return []

    gap = 0.4
    width = (slot.w - gap * (len(tiles) - 1)) / len(tiles)
    elements = []
    for index, (value, label) in enumerate(tiles):
        elements.append(VisualElement(
            type="kpi", x=slot.x + index * (width + gap), y=slot.y,
            w=width, h=slot.h, value=value, label=label,
            # Raqam kattaligi ataylab beriladi: berilmasa chizuvchi
            # umumiy matn o'lchamini olib, ko'rsatkich mayda chiqardi.
            size=40, fill=theme.accent_soft, color=theme.accent, locked=True,
        ))
    return elements


# ───────────────────────────────────────────────────────── bezak

def _decor(template: Template, theme: Theme) -> List[VisualElement]:
    """Qolipning fon bezagi — matndan oldin chiziladi."""
    style = template.decor
    if style == "bar":
        title = template.slot("title")
        if not title:
            return []
        return [VisualElement(
            type="rect", x=title.x, y=title.y + title.h - 0.02,
            w=2.1, h=_BAR_H, fill=theme.accent, locked=True)]

    if style == "side":
        return [
            VisualElement(type="rect", x=0.0, y=0.0, w=_SIDE_W, h=SLIDE_H,
                          fill=theme.accent, locked=True),
            VisualElement(type="rect", x=0.9, y=4.15, w=2.6, h=_BAR_H,
                          fill=theme.accent, locked=True),
        ]

    if style == "band":
        return [VisualElement(type="rect", x=0.0, y=0.0, w=SLIDE_W, h=SLIDE_H,
                              fill=theme.band, locked=True)]

    if style == "full":
        # Rasm ustidagi matn o'qilishi uchun pastdan to'q parda.
        return [VisualElement(type="rect", x=0.0, y=3.9, w=SLIDE_W,
                              h=SLIDE_H - 3.9, fill=theme.band, locked=True)]

    if style == "compare":
        left = template.slot("left_title")
        right = template.slot("right_title")
        if not left or not right:
            return []
        height = SLIDE_H - left.y - 0.85
        return [
            VisualElement(type="rect", x=left.x - 0.3, y=left.y - 0.25,
                          w=left.w + 0.6, h=height, fill=theme.accent_soft,
                          radius=True, locked=True),
            VisualElement(type="rect", x=right.x - 0.3, y=right.y - 0.25,
                          w=right.w + 0.6, h=height, fill="F4F5F7",
                          radius=True, locked=True),
        ]

    return []


def _tone_for_band(template: Template, slot: Slot) -> str:
    """To'q fonli qolipda matn oq bo'lishi kerak."""
    if template.decor in ("band", "full") and slot.tone != "accent":
        return "invert"
    return slot.tone


# ─────────────────────────────────────────────────────────── asosiy

_PRESET_KINDS = {
    "cards": "cards", "steps": "steps", "timeline": "timeline",
    "cycle": "cycle", "pyramid": "pyramid",
}


def build_elements(template: Template, content: Dict, theme: Theme) -> List[VisualElement]:
    """Qolipni mazmun bilan to'ldirib, element ro'yxatini qaytaradi.

    Bo'sh qolgan ixtiyoriy o'rin shunchaki chizilmaydi — joyini qo'shni
    element egallamaydi, chunki joylashuv qat'iy.
    """
    elements: List[VisualElement] = list(_decor(template, theme))

    for slot in template.slots:
        value = content.get(slot.name)
        tone = _tone_for_band(template, slot)
        shaped = Slot(**{**slot.__dict__, "tone": tone})

        if slot.kind in ("title", "text", "quote", "caption", "number"):
            element = _text_element(shaped, value, theme)
            if element:
                elements.append(element)
        elif slot.kind == "bullets":
            element = _bullet_element(shaped, value, theme)
            if element:
                elements.append(element)
        elif slot.kind == "image":
            prompt = str(value or "").strip()
            if prompt:
                elements.append(VisualElement(
                    type="image", x=slot.x, y=slot.y, w=slot.w, h=slot.h,
                    prompt=prompt, locked=True))
        elif slot.kind == "chart":
            element = _chart_element(slot, content, theme)
            if element:
                elements.append(element)
        elif slot.kind in _PRESET_KINDS:
            element = _infographic_element(slot, value, theme,
                                           _PRESET_KINDS[slot.kind])
            if element:
                elements.append(element)
        elif slot.kind == "scheme":
            element = _scheme_element(slot, content, theme)
            if element:
                elements.append(element)
        elif slot.kind == "kpi":
            elements.extend(_kpi_elements(slot, value, theme))

    # Bezak har doim pastda qolsin: matn undan keyin chizilgani uchun
    # ustida turadi. To'liq rasm esa hammasidan oldin.
    elements.sort(key=lambda el: 0 if el.type == "image" and el.w >= SLIDE_W - 0.01
                  else (1 if el.type == "rect" else 2))
    return elements


def background_of(template: Template, theme: Theme) -> str:
    """Slayd foni — to'q qoliplarda bezak o'zi to'ldiradi."""
    return theme.background
