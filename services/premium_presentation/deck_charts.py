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

import colorsys
import html
import logging
import re
from typing import Dict, List, Tuple

log = logging.getLogger("deck_charts")

_TAG = re.compile(r'<div\b[^>]*\bclass\s*=\s*(["\'])[^"\']*\bchart\b[^"\']*\1'
                  r'[^>]*>\s*</div>', re.IGNORECASE | re.DOTALL)
_ATTR = re.compile(r'\bdata-([a-z]+)\s*=\s*(["\'])(.*?)\2',
                   re.IGNORECASE | re.DOTALL)

# Qatorlarni bir-biridan ajratish uchun turli RANGLAR. Sxemaning o'z
# `chart` ro'yxati bitta rangning tuslari — ustunlar/chiziqlar/bo'laklar
# bir-biriga o'xshab, ajratib bo'lmasdi. Birinchisi sxemaning asosiy
# rangi, qolganlari undan uzoq (tus burchagi bo'yicha) rang-barang.
_DISTINCT = ("F59E0B", "10B981", "E11D48", "8B5CF6", "06B6D4", "EAB308",
             "EC4899", "64748B")
_MIN_HUE_GAP = 0.07   # ~25 daraja


def _colour(theme, index: int) -> str:
    colours = palette(theme)
    return colours[index % len(colours)]


def _hue(colour: str) -> float:
    r, g, b = (int(colour[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hsv(r, g, b)[0]


def _hue_gap(a: str, b: str) -> float:
    gap = abs(_hue(a) - _hue(b))
    return min(gap, 1 - gap)


def _lift(colour: str, share: float) -> str:
    parts = (int(colour[i:i + 2], 16) for i in (0, 2, 4))
    return "".join(f"{round(c + (255 - c) * share):02X}" for c in parts)


def palette(theme) -> Tuple[str, ...]:
    """Diagramma ranglari: asosiy rang + bir-biridan aniq farq qiladigan ranglar."""
    base = (theme.chart or (theme.accent,))[0]
    dark = bool(getattr(theme, "style", "") == "qorongu")
    picked = [base]
    for colour in _DISTINCT:
        if dark:
            colour = _lift(colour, 0.25)
        if all(_hue_gap(colour, other) >= _MIN_HUE_GAP for other in picked):
            picked.append(colour)
    return tuple(picked)


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


# "2022: 0.29, 2023: 0.28" — yorliq va qiymat juftlari bitta qatorda.
_PAIR = re.compile(r"\s*([^:=,;|\n]+?)\s*[:=]\s*(-?\d[\d\s]*(?:\.\d+)?)\s*%?\s*")


def _pairs(text: str) -> Tuple[List[str], List[float]]:
    """Yorliq:qiymat juftlari. Matn to'liq juftlardan iborat bo'lmasa — bo'sh.

    Model ma'lumotni ko'pincha shunday yozadi. Ilgari bu bitta
    qiymatli qator deb o'qilib, diagramma tashlab yuborilardi.
    """
    text = str(text or "").strip()
    if "|" in text:
        return [], []
    pieces = [piece for piece in re.split(r"[,;\n]", text) if piece.strip()]
    labels, values = [], []
    for piece in pieces:
        match = _PAIR.fullmatch(piece)
        if not match:
            return [], []
        labels.append(match.group(1).strip())
        values.append(float(match.group(2).replace(" ", "")))
    if len(values) < 2:
        return [], []
    return labels, values


def _series(text: str) -> List[Tuple[str, List[float]]]:
    """`Nomi: 1,2,3|Boshqasi: 4,5,6` → [(nom, [qiymat])].

    Qatorlar `|` bilan ajratiladi. Model ba'zan `;` yoki yangi qator
    bilan ajratadi — bir nechta nomli qator bo'lsa, ular ham ajratuvchi
    deb olinadi (aks holda ikki qator bittaga qo'shilib ketardi).
    """
    text = str(text or "")
    if "|" not in text:
        for mark in ("\n", ";"):
            parts = [part for part in text.split(mark) if part.strip()]
            if len(parts) >= 2 and all(":" in part for part in parts):
                text = "|".join(parts)
                break
    rows = []
    for part in text.split("|"):
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
    # Kichik qiymatlar (Gini 0.29, stavka 2.75) ikki xonagacha
    # yoziladi — aks holda 0.29 va 0.28 ikkalasi "0,3" bo'lib qolardi.
    # 1 dan kichik qiymatlar (chastota 0.004) esa nolga yaxlitlanmaydi:
    # ilgari 0.004 va 0.002 ikkalasi "0" bo'lib, grafik ma'nosiz qolardi.
    if value == 0:
        return "0"
    magnitude = abs(value)
    if magnitude >= 1 and abs(value - round(value)) < 0.005:
        return str(int(round(value)))
    if magnitude >= 10:
        return f"{value:.1f}".replace(".", ",")
    if magnitude >= 0.1:
        return f"{value:.2f}".rstrip("0").replace(".", ",").rstrip(",")
    for digits in (3, 4, 5, 6):
        text = f"{value:.{digits}f}".rstrip("0")
        if float(text) != 0:
            return text.replace(".", ",").rstrip(",")
    return "0"


def _text(x, y, value, size, colour, anchor="middle", weight="400"):
    return (f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" '
            f'fill="#{colour}" text-anchor="{anchor}" '
            f'font-weight="{weight}" font-family="Arial, sans-serif">'
            f'{html.escape(str(value))}</text>')


# ────────────────────────────────────────────────────────── turlari

def _nice_ticks(lo: float, hi: float, target: int = 5) -> List[float]:
    """[lo, hi] ni qoplaydigan "chiroyli" qadamli bo'linmalar (1, 2, 2.5, 5, 10 x 10^n)."""
    import math

    span = hi - lo
    if span <= 0:
        span = abs(hi) or 1.0
    raw = span / max(target, 1)
    magnitude = 10 ** math.floor(math.log10(raw))
    step = magnitude * 10
    for factor in (1, 2, 2.5, 5, 10):
        if factor * magnitude >= raw:
            step = factor * magnitude
            break
    start = math.floor(lo / step + 1e-9) * step
    ticks, value = [], start
    while value < hi + step * 0.999 and len(ticks) < 12:
        ticks.append(round(value, 10))
        value += step
        if ticks[-1] >= hi - 1e-9:
            break
    return ticks


def _tick_text(value: float) -> str:
    text = _fmt(value)
    # Minglik bo'shliq: 12000 → "12 000" (o'qish osonroq).
    head, sep, tail = text.partition(",")
    if len(head.lstrip("-")) > 4:
        head = f"{int(head):,}".replace(",", "\u00a0")
    return head + sep + tail


def _y_scale(rows, zero_based: bool):
    """(ticks, lo, hi): Y o'qi. Ustunlar har doim noldan; chiziq — qiymatlar
    tor oraliqda bo'lsa (7,9 → 8,3) noldan emas, aks holda tekis chiziq chiqadi."""
    values = [v for _, vals in rows for v in vals]
    low, high = min(values), max(values)
    if zero_based or low <= 0 or (high - low) > 0.6 * high:
        low = min(low, 0.0)
        ticks = _nice_ticks(low, high)
    else:
        pad = (high - low) * 0.15 or high * 0.05
        ticks = _nice_ticks(low - pad, high + pad)
    return ticks, ticks[0], ticks[-1] if ticks[-1] > ticks[0] else ticks[0] + 1


def _axes(parts, theme, ticks, lo, hi, left, top, plot_w, plot_h, xlabel, H):
    """Gorizontal to'r, Y o'qi imzolari, X o'qi sarlavhasi."""
    for tick in ticks:
        y = top + plot_h - plot_h * (tick - lo) / ((hi - lo) or 1.0)
        parts.append(f'<line x1="{left}" y1="{y:.0f}" x2="{left + plot_w}" '
                     f'y2="{y:.0f}" stroke="#{theme.muted}" stroke-opacity="0.28" '
                     f'stroke-width="1.5"/>')
        parts.append(_text(left - 14, y + 8, _tick_text(tick), 24, theme.muted,
                           anchor="end"))
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" '
                 f'stroke="#{theme.muted}" stroke-width="2"/>')
    parts.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" '
                 f'y2="{top + plot_h}" stroke="#{theme.muted}" stroke-width="2"/>')
    if xlabel:
        parts.append(_text(left + plot_w / 2, H - 10, xlabel, 24, theme.muted))


def _thin(count: int, limit: int = 8) -> set:
    """Ko'p nuqtada yorliqning har k-sini qoldiradi (oxirgisi doim)."""
    if count <= limit:
        return set(range(count))
    k = -(-count // limit)
    keep = set(range(0, count, k))
    keep.add(count - 1)
    return keep


def _left_margin(ticks) -> int:
    width = max(len(_tick_text(t)) for t in ticks) * 14 + 30
    return max(96, min(width, 190))


def _bar(rows, labels, theme, unit, W, H, xlabel="") -> str:
    """Ustunli diagramma: Y o'qi shkalasi bilan, noldan boshlanadi."""
    ticks, lo, hi = _y_scale(rows, zero_based=True)
    left = _left_margin(ticks)
    top, right = 48, 24
    bottom = 64 + (34 if xlabel else 0) + _legend_height(rows, W)
    plot_h = H - top - bottom
    plot_w = W - left - right
    count = max(len(labels), max(len(values) for _, values in rows))
    group = plot_w / count
    pad = group * 0.22
    bar_w = (group - pad) / len(rows)
    show = _thin(count)
    parts = []
    _axes(parts, theme, ticks, lo, hi, left, top, plot_w, plot_h, xlabel, H)

    for index in range(count):
        base = left + group * index + pad / 2
        for order, (_, values) in enumerate(rows):
            if index >= len(values):
                continue
            value = values[index]
            height = max(plot_h * (value - lo) / ((hi - lo) or 1.0), 3)
            x = base + bar_w * order
            y = top + plot_h - height
            colour = _colour(theme, order)
            parts.append(
                f'<rect x="{x:.0f}" y="{y:.0f}" width="{max(bar_w - 6, 4):.0f}" '
                f'height="{height:.0f}" rx="6" fill="#{colour}"/>')
            if count <= 10 or index in (0, count - 1):
                parts.append(_text(x + (bar_w - 6) / 2, y - 12, _fmt(value),
                                   25 if count <= 8 else 21, theme.heading,
                                   weight="700"))
        if index < len(labels) and index in show:
            parts.append(_text(left + group * index + group / 2,
                               top + plot_h + 36, labels[index], 25 if count <= 8 else 22,
                               theme.body, weight="700"))

    parts.append(_legend(rows, theme, H - 12 - (34 if xlabel else 0), W))
    return _svg(parts, unit, theme, W, H)


def _line(rows, labels, theme, unit, W, H, xlabel="") -> str:
    """Chiziqli diagramma: X va Y o'qlari, shkala, nuqtalarda qiymat."""
    ticks, lo, hi = _y_scale(rows, zero_based=False)
    left = _left_margin(ticks) + 12
    top, right = 56, 48
    bottom = 64 + (34 if xlabel else 0) + _legend_height(rows, W)
    plot_h = H - top - bottom
    plot_w = W - left - right
    count = max(len(labels), max(len(values) for _, values in rows))
    step = (plot_w - 40) / max(count - 1, 1)
    x0 = left + 20
    show = _thin(count)
    parts = []
    _axes(parts, theme, ticks, lo, hi, left, top, plot_w, plot_h, xlabel, H)
    radius = 9 if count <= 12 else 6

    for order, (_, values) in enumerate(rows):
        colour = _colour(theme, order)
        points = []
        for index, value in enumerate(values[:count]):
            x = x0 + step * index
            y = top + plot_h - plot_h * (value - lo) / ((hi - lo) or 1.0)
            points.append((x, y))
        path = " ".join(f"{'M' if i == 0 else 'L'}{x:.0f},{y:.0f}"
                        for i, (x, y) in enumerate(points))
        parts.append(f'<path d="{path}" fill="none" stroke="#{colour}" '
                     f'stroke-width="5" stroke-linejoin="round"/>')
        labelled = {0, len(points) - 1}
        if values:
            labelled.update({values.index(max(values)), values.index(min(values))})
        for index, (x, y) in enumerate(points):
            parts.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{radius}" '
                         f'fill="#{colour}"/>')
            if not (count <= 8 or index in labelled):
                continue
            # Bir necha qatorda yozuvlar to'qnashmasin: shu nuqtada eng
            # yuqori qiymat tepada, eng pasti ostida; o'rtadagilar yozilmaydi.
            column = [vals[index] for _, vals in rows if index < len(vals)]
            value = values[index]
            if len(column) > 1 and max(column) != min(column):
                if value == max(column):
                    above = True
                elif value == min(column):
                    above = False
                else:
                    continue
            else:
                above = order % 2 == 0
            parts.append(_text(x, y - 22 if above else y + 40, _fmt(value),
                               25 if count <= 8 else 22, theme.heading,
                               weight="700"))

    for index, label in enumerate(labels[:count]):
        if index in show:
            parts.append(_text(x0 + step * index, top + plot_h + 36, label,
                               25 if count <= 8 else 22, theme.body, weight="700"))

    parts.append(_legend(rows, theme, H - 12 - (34 if xlabel else 0), W))
    return _svg(parts, unit, theme, W, H)


def _wrap_label(text: str, size: int, room: float) -> List[str]:
    """Imzoni `room` pikselga sig'dirib bir yoki ikki qatorga bo'ladi (qalin harf ~0.6 em)."""
    limit = max(8, int(room / (size * 0.6)))
    if len(text) <= limit:
        return [text]
    cut = text.rfind(" ", 0, limit + 1)
    if cut < limit * 0.4:
        cut = limit
    first, rest = text[:cut].rstrip(), text[cut:].strip()
    if len(rest) > limit:
        rest = rest[:max(limit - 1, 1)].rstrip() + "…"
    return [first, rest] if rest else [first]


def _donut(rows, labels, theme, unit, W, H, xlabel="") -> str:
    """Halqa diagramma — ulushlar.

    Imzolar halqaning yonida, diagramma kengligiga SIG'ISHI shart: uzun
    nomlar (qozoqcha, ruscha) ilgari o'ng chetda kesilib qolardi. Shuning
    uchun shrift kichraytiriladi, kerak bo'lsa halqa ixchamlashadi va imzo
    ikki qatorga bo'linadi.
    """
    values = rows[0][1]
    total = sum(values) or 1.0
    texts = []
    for index, value in enumerate(values):
        label = labels[index] if index < len(labels) else ""
        texts.append(f"{label} — {_fmt(100.0 * value / total)}%")
    longest = max((len(t) for t in texts), default=0)

    radius = min(H * 0.42, W * 0.22)
    size = 30
    for shrink in (1.0, 0.88, 0.76):
        radius = min(H * 0.42, W * 0.22) * shrink
        room = W - (radius * 2 + 40 + 56 + 38) - 24         # imzo uchun qolgan eni
        size = 30
        while size > 22 and longest * size * 0.6 > room:
            size -= 2
        if longest * size * 0.6 <= room:
            break
    room = W - (radius * 2 + 40 + 56 + 38) - 24
    cx, cy, thickness = radius + 40, H / 2, radius * 0.33

    parts = []
    angle = -90.0
    for index, value in enumerate(values):
        span = 360.0 * value / total
        colour = _colour(theme, index)
        parts.append(_arc(cx, cy, radius, thickness, angle, angle + span,
                          colour))
        angle += span

    # Yonida imzolar: halqaning ichiga yozuv sig'maydi.
    wrapped = [_wrap_label(t, size, room) for t in texts]
    step = size * 1.8
    heights = [step + (len(w) - 1) * size * 1.15 for w in wrapped]
    line_y = cy - sum(heights) / 2 + size
    for index, lines in enumerate(wrapped):
        colour = _colour(theme, index)
        left = cx + radius + 56
        parts.append(f'<rect x="{left:.0f}" y="{line_y - 18:.0f}" width="22" '
                     f'height="22" rx="5" fill="#{colour}"/>')
        for number, line in enumerate(lines):
            parts.append(_text(left + 38, line_y + number * size * 1.15, line, size,
                               theme.body, anchor="start", weight="700"))
        line_y += heights[index]

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


_LEGEND_ROW = 36


def _legend_lines(rows, width) -> List[List[Tuple[int, str, int]]]:
    """Izoh qatorlari: har yozuvning haqiqiy kengligiga qarab, sig'masa keyingi qatorga."""
    lines: List[List[Tuple[int, str, int]]] = [[]]
    x = 24
    for order, (name, _) in enumerate(rows):
        if not name:
            continue
        size = 30 + len(name) * 16 + 34          # kvadrat + matn (27px) + oraliq
        if lines[-1] and x + size > width - 24:
            lines.append([])
            x = 24
        lines[-1].append((order, name, x))
        x += size
    return lines if lines[0] else []


def _legend_height(rows, width) -> int:
    """Izoh egallaydigan balandlik (nomi bor qator 2 tadan kam bo'lsa — izoh yo'q)."""
    if len([name for name, _ in rows if name]) < 2:
        return 0
    return 22 + _LEGEND_ROW * max(len(_legend_lines(rows, width)) - 1, 0)


def _legend(rows, theme, y, width=W) -> str:
    if len([name for name, _ in rows if name]) < 2:
        return ""
    lines = _legend_lines(rows, width)
    parts = []
    for number, line in enumerate(lines):
        row_y = y - _LEGEND_ROW * (len(lines) - 1 - number)
        for order, name, x in line:
            parts.append(f'<rect x="{x}" y="{row_y - 16:.0f}" width="20" height="20" '
                         f'rx="5" fill="#{_colour(theme, order)}"/>')
            parts.append(_text(x + 30, row_y, name, 27, theme.body, anchor="start"))
    return "".join(parts)


def _svg(parts, unit, theme, W, H) -> str:
    head = ""
    if unit:
        head = _text(24, 24, unit, 27, theme.muted, anchor="start")
    return (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'xmlns="http://www.w3.org/2000/svg">{head}'
            + "".join(parts) + "</svg>")


_UNIT_IN_NAME = re.compile(r"\(([^)]{1,24})\)")


def _scale_groups(rows, ratio: float = 6.0, hard_ratio: float = 40.0):
    """Qatorlar kattaligi keskin farq qilsa (milliard va foiz) bitta o'qqa
    sig'maydi: ular ikkita alohida diagrammaga ajratiladi. Bir birlik —
    bir diagramma.

    "Aholi (mlrd)" va "Urbanizatsiya (%)" kabi turli birlik qavsda yozilgan bo'lsa,
    kattaligi 6 baravardan farq qiluvchi qatorlar ajratiladi. Birlik ko'rsatilmagan yoki
    bir xil bo'lsa (masalan, uchta ham foiz: 85, 15 va 10) — bitta diagramma:
    kichik qator ayrim diagrammaga tushib, nomi va izohisiz qolmasin. Faqat o'lchamlar
    benihoya farq qilsa (40 baravardan ko'p) ajratiladi.
    """
    if len(rows) < 2:
        return [rows]
    peaks = [max(values) if values else 0.0 for _, values in rows]
    big = max(peaks)
    if big <= 0:
        return [rows]
    units = {found.group(1).strip().lower()
             for name, _ in rows if name for found in [_UNIT_IN_NAME.search(name)] if found}
    limit = ratio if len(units) >= 2 else hard_ratio
    large = [row for row, peak in zip(rows, peaks) if peak * limit >= big]
    small = [row for row, peak in zip(rows, peaks) if peak * limit < big]
    return [large, small] if large and small else [rows]


def _stack(kind, groups, labels, theme, unit, width, height, xlabel) -> str:
    """Har guruh o'z o'qi va birligi bilan, bir-birining ostida."""
    panels = []
    each = max(height // len(groups), 240)
    for number, group in enumerate(groups):
        names = [name for name, _ in group if name]
        found = re.search(r"\(([^)]{1,24})\)", names[0]) if names else None
        label = found.group(1) if found else (unit if number == 0 else "")
        if not label and len(names) == 1:
            label = names[0]               # yolg'iz qator nomsiz qolmasin
        last = number == len(groups) - 1
        body = kind(group, labels, theme, label, width, each + (40 if last and xlabel else 0),
                    xlabel=xlabel if last else "")
        panels.append(f'<div class="chart">{body}</div>')
    return '<div class="chart-stack">' + "".join(panels) + "</div>"


_KINDS = {"bar": _bar, "ustun": _bar, "column": _bar,
          "line": _line, "chiziq": _line,
          "donut": _donut, "pie": _donut, "halqa": _donut}


# ────────────────────────────────────────────────────────── kirish

def draw(html_body: str, theme) -> str:
    """Slayddagi har bir `.chart` blokini tayyor SVG bilan almashtiradi."""

    def swap(match):
        tag = match.group(0)
        data: Dict[str, str] = {key.lower(): html.unescape(value)
                                for key, _, value in _ATTR.findall(tag)}
        raw = data.get("series") or data.get("values") or ""
        pair_labels, pair_values = _pairs(raw)
        rows = [("", pair_values)] if pair_values else _series(raw)
        if not rows:
            log.warning("Diagrammada ma'lumot yo'q: %s", tag[:120])
            return ""
        labels = _labels(data.get("labels", ""))
        if pair_values and len(labels) != len(pair_values):
            labels = pair_labels
        # Model ulushlarni ko'pincha har birini alohida qator qilib
        # yozadi: "AQSh: 45|Yevropa: 30|Osiyo: 25". Bu uchta bitta
        # qiymatli qator emas — bitta qatorning uchta qiymati. Ilgari
        # halqa faqat birinchisini chizib "— 100%" derdi, keyin esa
        # bunday halqa butunlay tashlab yuborilardi.
        if len(rows) >= 2 and all(len(values) == 1 for _, values in rows):
            names = [row_name for row_name, _ in rows]
            rows = [("", [values[0] for _, values in rows])]
            if len(labels) != len(names) and all(names):
                labels = names
        name = (data.get("kind") or "bar").strip().lower()
        kind = _KINDS.get(name, _bar)
        # Bitta qiymatli halqa "100%" deydi, xolos — hech narsani
        # ko'rsatmaydi, halqaning o'zi esa chizilmay (boshi va oxiri
        # bir nuqta) faqat imzo qolardi. Bunday diagramma tashlanadi.
        # Yagona qiymatdan diagramma chiqmaydi ("— 100%" halqa yoki
        # bitta ustun). Lekin raqam tashlab yuborilmaydi: u yirik
        # ko'rsatkich bo'lib turadi, slaydda bo'sh joy qolmaydi.
        if sum(len(values) for _, values in rows) == 1:
            row_name, values = rows[0]
            unit = (data.get("unit") or "").strip()
            label = row_name or (labels[0] if labels else "")
            log.info("Bitta qiymatli diagramma ko'rsatkichga aylantirildi")
            return ('<div class="kpi"><div class="kpi-value">'
                    f'{html.escape(_fmt(values[0]))}</div>'
                    f'<div class="kpi-label">{html.escape(" ".join((label, unit)).strip())}'
                    '</div></div>')
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
        unit = (data.get("ylabel") or data.get("unit") or "").strip()
        xlabel = (data.get("xlabel") or "").strip()
        groups = [] if kind is _donut else _scale_groups(rows)
        try:
            if len(groups) > 1:
                return _stack(kind, groups, labels, theme, unit, width, height, xlabel)
            body = kind(rows, labels, theme, unit, width, height, xlabel=xlabel)
        except Exception as exc:
            log.warning("Diagramma chizilmadi (%s): %s", data.get("kind"), exc)
            return ""
        return f'<div class="chart">{body}</div>'

    return _TAG.sub(swap, html_body)


def count(html_body: str) -> int:
    return len(_TAG.findall(html_body))
