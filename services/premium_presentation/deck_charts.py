"""Diagrammani KOD chizadi, AI emas.

Ilgari model diagrammani o'zi SVG qilib chizardi: ustunning
balandligini, o'qning o'rnini, yozuvning joyini o'zi hisoblardi.
Model arifmetikani ko'pincha xato qiladi — shuning uchun slaydda
balandligi nolga teng ustunlar, bir-birining ustiga tushgan yozuvlar
va bo'sh qolgan katta maydon chiqardi.

Endi model faqat MA'LUMOTNI aytadi:

    <div class="chart" data-kind="bar" data-labels="2016,2018,2020"
         data-series="Patentlar: 12,18,24|Nashrlar: 20,28,35"
         data-unit="ming"></div>

SVG ni esa shu modul chizadi. Hisob har safar to'g'ri bo'ladi:
ustunlar o'lchovli, yozuvlar ustma-ust tushmaydi, o'q imzolangan.
"""

import html
import logging
import re
from typing import Dict, List, Tuple

log = logging.getLogger("deck_charts")

_TAG = re.compile(r'<div\b[^>]*\bclass\s*=\s*(["\'])[^"\']*\bchart\b[^"\']*\1'
                  r'[^>]*>\s*</div>', re.IGNORECASE | re.DOTALL)
_ATTR = re.compile(r'\bdata-([a-z]+)\s*=\s*(["\'])(.*?)\2',
                   re.IGNORECASE | re.DOTALL)

# Chizma maydoni. Kengligi slaydning ichki eniga teng (1920 - 2*96),
# balandligi esa yarmidan sal kam — ostida izoh uchun joy qoladi.
W = 1728
H = 520
# Yarim ustunda (`.split` ichida) diagramma ikki baravar kichrayadi —
# shuning uchun uning o'z o'lchami ham kichik bo'lishi kerak, aks
# holda yozuvlari o'qib bo'lmas darajada mayda chiqadi.
HALF_W = 840
HALF_H = 520


def _numbers(text: str) -> List[float]:
    out = []
    for piece in str(text or "").replace(";", ",").split(","):
        piece = piece.strip().replace("%", "").replace(" ", "")
        if not piece:
            continue
        try:
            out.append(float(piece.replace(",", ".")))
        except ValueError:
            continue
    return out


def _series(text: str) -> List[Tuple[str, List[float]]]:
    """`Nomi: 1,2,3|Boshqasi: 4,5,6` → [(nom, [qiymat])]."""
    rows = []
    for part in str(text or "").split("|"):
        part = part.strip()
        if not part:
            continue
        name, _, values = part.partition(":")
        if not values.strip():
            name, values = "", part
        numbers = _numbers(values)
        if numbers:
            rows.append((name.strip(), numbers))
    return rows


def _labels(text: str) -> List[str]:
    return [piece.strip() for piece in str(text or "").split(",")
            if piece.strip()]


def _fmt(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}".replace(".", ",")


def _text(x, y, value, size, colour, anchor="middle", weight="400"):
    return (f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" '
            f'fill="#{colour}" text-anchor="{anchor}" '
            f'font-weight="{weight}" font-family="Arial, sans-serif">'
            f'{html.escape(str(value))}</text>')


# ────────────────────────────────────────────────────────── turlari

def _bar(rows, labels, theme, unit, W, H) -> str:
    """Ustunli diagramma. Bir nechta qator yonma-yon turadi."""
    top, bottom, left, right = 48, 64, 24, 24
    plot_h = H - top - bottom
    plot_w = W - left - right
    count = max(len(labels), max(len(values) for _, values in rows))
    peak = max(max(values) for _, values in rows) or 1.0

    group = plot_w / count
    pad = group * 0.22
    bar_w = (group - pad) / len(rows)

    parts = []
    # Asos chizig'i.
    parts.append(f'<line x1="{left}" y1="{top + plot_h}" '
                 f'x2="{left + plot_w}" y2="{top + plot_h}" '
                 f'stroke="#{theme.muted}" stroke-width="2"/>')

    for index in range(count):
        base = left + group * index + pad / 2
        for order, (_, values) in enumerate(rows):
            if index >= len(values):
                continue
            value = values[index]
            height = max(plot_h * value / peak, 3)
            x = base + bar_w * order
            y = top + plot_h - height
            colour = theme.chart[order % len(theme.chart)]
            parts.append(
                f'<rect x="{x:.0f}" y="{y:.0f}" width="{bar_w - 6:.0f}" '
                f'height="{height:.0f}" rx="6" fill="#{colour}"/>')
            parts.append(_text(x + (bar_w - 6) / 2, y - 12, _fmt(value),
                               27, theme.heading, weight="700"))
        if index < len(labels):
            parts.append(_text(left + group * index + group / 2,
                               top + plot_h + 38, labels[index], 27,
                               theme.body, weight="700"))

    parts.append(_legend(rows, theme, top + plot_h + 58))
    return _svg(parts, unit, theme, W, H)


def _line(rows, labels, theme, unit, W, H) -> str:
    """Chiziqli diagramma."""
    top, bottom, left, right = 48, 64, 48, 48
    plot_h = H - top - bottom
    plot_w = W - left - right
    count = max(len(labels), max(len(values) for _, values in rows))
    peak = max(max(values) for _, values in rows) or 1.0
    step = plot_w / max(count - 1, 1)

    parts = [f'<line x1="{left}" y1="{top + plot_h}" '
             f'x2="{left + plot_w}" y2="{top + plot_h}" '
             f'stroke="#{theme.muted}" stroke-width="2"/>']

    for order, (_, values) in enumerate(rows):
        colour = theme.chart[order % len(theme.chart)]
        points = []
        for index, value in enumerate(values[:count]):
            x = left + step * index
            y = top + plot_h - plot_h * value / peak
            points.append((x, y))
        path = " ".join(f"{'M' if i == 0 else 'L'}{x:.0f},{y:.0f}"
                        for i, (x, y) in enumerate(points))
        parts.append(f'<path d="{path}" fill="none" stroke="#{colour}" '
                     f'stroke-width="5" stroke-linejoin="round"/>')
        for index, (x, y) in enumerate(points):
            parts.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="9" '
                         f'fill="#{colour}"/>')
            parts.append(_text(x, y - 24, _fmt(values[index]), 27,
                               theme.heading, weight="700"))

    for index, label in enumerate(labels[:count]):
        parts.append(_text(left + step * index, top + plot_h + 38, label,
                           27, theme.body, weight="700"))

    parts.append(_legend(rows, theme, top + plot_h + 58))
    return _svg(parts, unit, theme, W, H)


def _donut(rows, labels, theme, unit, W, H) -> str:
    """Halqa diagramma — ulushlar."""
    values = rows[0][1]
    total = sum(values) or 1.0
    radius = min(H * 0.42, W * 0.22)
    cx, cy, thickness = radius + 40, H / 2, radius * 0.33

    parts = []
    angle = -90.0
    for index, value in enumerate(values):
        span = 360.0 * value / total
        colour = theme.chart[index % len(theme.chart)]
        parts.append(_arc(cx, cy, radius, thickness, angle, angle + span,
                          colour))
        angle += span

    # Yonida imzolar: halqaning ichiga yozuv sig'maydi.
    line_y = cy - len(values) * 27 + 27
    for index, value in enumerate(values):
        colour = theme.chart[index % len(theme.chart)]
        label = labels[index] if index < len(labels) else ""
        share = 100.0 * value / total
        left = cx + radius + 56
        parts.append(f'<rect x="{left:.0f}" y="{line_y - 18:.0f}" width="22" '
                     f'height="22" rx="5" fill="#{colour}"/>')
        parts.append(_text(left + 38, line_y, f"{label} — {_fmt(share)}%", 30,
                           theme.body, anchor="start", weight="700"))
        line_y += 54

    return _svg(parts, unit, theme, W, H)


def _arc(cx, cy, radius, thickness, start, end, colour) -> str:
    import math

    inner = radius - thickness
    big = 1 if end - start > 180 else 0

    def point(r, deg):
        rad = math.radians(deg)
        return cx + r * math.cos(rad), cy + r * math.sin(rad)

    x1, y1 = point(radius, start)
    x2, y2 = point(radius, end)
    x3, y3 = point(inner, end)
    x4, y4 = point(inner, start)
    return (f'<path d="M{x1:.1f},{y1:.1f} A{radius},{radius} 0 {big} 1 '
            f'{x2:.1f},{y2:.1f} L{x3:.1f},{y3:.1f} A{inner},{inner} 0 '
            f'{big} 0 {x4:.1f},{y4:.1f} Z" fill="#{colour}"/>')


def _legend(rows, theme, y) -> str:
    named = [name for name, _ in rows if name]
    if len(named) < 2:
        return ""
    parts = []
    x = 24
    for order, (name, _) in enumerate(rows):
        if not name:
            continue
        colour = theme.chart[order % len(theme.chart)]
        parts.append(f'<rect x="{x}" y="{y - 16:.0f}" width="20" height="20" '
                     f'rx="5" fill="#{colour}"/>')
        parts.append(_text(x + 30, y, name, 27, theme.body, anchor="start"))
        x += 44 + len(name) * 12
    return "".join(parts)


def _svg(parts, unit, theme, W, H) -> str:
    head = ""
    if unit:
        head = _text(24, 24, unit, 27, theme.muted, anchor="start")
    return (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'xmlns="http://www.w3.org/2000/svg">{head}'
            + "".join(parts) + "</svg>")


_KINDS = {"bar": _bar, "ustun": _bar, "column": _bar,
          "line": _line, "chiziq": _line,
          "donut": _donut, "pie": _donut, "halqa": _donut}


# ────────────────────────────────────────────────────────── kirish

def draw(html_body: str, theme) -> str:
    """Slayddagi har bir `.chart` blokini tayyor SVG bilan almashtiradi."""

    def swap(match):
        tag = match.group(0)
        data: Dict[str, str] = {key.lower(): value
                                for key, _, value in _ATTR.findall(tag)}
        rows = _series(data.get("series") or data.get("values") or "")
        if not rows:
            log.warning("Diagrammada ma'lumot yo'q: %s", tag[:120])
            return ""
        labels = _labels(data.get("labels", ""))
        name = (data.get("kind") or "bar").strip().lower()
        kind = _KINDS.get(name, _bar)
        # Bitta qiymatli halqa "100%" deydi, xolos — hech narsani
        # ko'rsatmaydi, halqaning o'zi esa chizilmay (boshi va oxiri
        # bir nuqta) faqat imzo qolardi. Bunday diagramma tashlanadi.
        if kind is _donut and len(rows[0][1]) < 2:
            log.warning("Bitta qiymatli halqa diagramma tashlandi")
            return ""
        if all(len(values) < 2 for _, values in rows) and kind is not _donut:
            log.warning("Bitta nuqtali diagramma tashlandi")
            return ""
        # Halqa tabiatan ixcham: u har doim yarim o'lchamda chiziladi.
        half = (data.get("size") or "").strip().lower() in ("half", "yarim")
        width, height = ((HALF_W, HALF_H) if half or kind is _donut
                         else (W, H))
        try:
            body = kind(rows, labels, theme, (data.get("unit") or "").strip(),
                        width, height)
        except Exception as exc:
            log.warning("Diagramma chizilmadi (%s): %s", data.get("kind"), exc)
            return ""
        return f'<div class="chart">{body}</div>'

    return _TAG.sub(swap, html_body)


def count(html_body: str) -> int:
    return len(_TAG.findall(html_body))
