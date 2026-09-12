"""Tuzilma sxemalari — bir nechta shakl, mavzuga qarab tanlanadi.

Ilgari sxema bitta shaklda edi: ildiz bloki, ostida to'rtta ustun, har
ustunda uchtadan katak. Mavzu o'zgarsa faqat yozuvlar o'zgarardi, rasm esa
har hujjatda aynan bir xil ko'rinardi.

Endi ikki narsa o'zgaradi:

  • **Tuzilma turi** — modelning o'zi aytadi. Tarkibiy qismlarga bo'linadigan
    mavzu ierarxiya, bosqichma-bosqich boradigani jarayon, qaytariladigani
    sikl, bir-birining ustiga quriladigani esa darajalar bo'ladi.
  • **Shakl** — har tur uchun bir nechta to'g'ri chizma bor. Qaysi biri
    ishlatilishi mavzudan olingan urug' bilan tanlanadi, ya'ni ikki xil
    mavzu ikki xil ko'rinadi, bir mavzu esa qayta yaratilganda o'zgarmaydi.

Chizmalar `charts.py` dagi ranglar va yordamchi funksiyalardan foydalanadi.
`charts` bu modulni faqat chaqiruv paytida import qiladi, shuning uchun
aylanma bog'liqlik yo'q.
"""

import hashlib
import logging
import math

import matplotlib
import matplotlib.patheffects as path_effects
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon

from . import palettes
from .palettes import GRID, INK, INK_SOFT, SURFACE

logger = logging.getLogger(__name__)

_WIDTH = 7.6
_DPI = 150

# Tuzilma turi → shu turga mos chizmalar. Ro'yxatdagi har bir shakl o'sha
# ma'lumot uchun TO'G'RI bo'lishi shart: jarayonni doiraviy sxema bilan
# ko'rsatish mumkin emas, agar u qaytarilmasa.
FORMS_BY_KIND = {
    "hierarchy": ("tree", "radial", "mindmap"),
    "components": ("radial", "tree", "mindmap"),
    "process": ("flow", "chevron", "mindmap"),
    "cycle": ("cycle", "flow"),
    "levels": ("levels", "pyramid", "tree"),
}
DEFAULT_KIND = "hierarchy"
ALL_FORMS = tuple(sorted({form for forms in FORMS_BY_KIND.values() for form in forms}))


def forms_for(kind: str) -> tuple:
    return FORMS_BY_KIND.get(str(kind or "").strip().lower(),
                             FORMS_BY_KIND[DEFAULT_KIND])


def pick_form(kind: str, seed: str, preferred: str = "") -> str:
    """Mavzuga bog'langan, lekin takrorlanmaydigan shakl tanlaydi.

    `preferred` — tashqaridan (loyiha ishidagi `variety`) kelgan tanlov.
    U shu turga to'g'ri kelsa ishlatiladi; kelmasa mavzu urug'idan
    tanlanadi, ya'ni har mavzu o'z shakliga ega bo'ladi.
    """
    options = forms_for(kind)
    if preferred in options:
        return preferred
    digest = hashlib.sha256(str(seed).encode("utf-8")).hexdigest()
    return options[int(digest[:8], 16) % len(options)]


# ─────────────────────────────────────────────────────────────── yordamchilar

def _shorten(text, limit: int = 34) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _wrap(text: str, width: int) -> str:
    """Matnni so'z chegarasida bo'ladi — katak ichiga sig'sin."""
    words = str(text or "").split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return "\n".join(lines[:3])


def _tint(hex_str: str, amount: float) -> str:
    """Rangni oqqa yaqinlashtiradi — ichki kataklar uchun ochroq tus."""
    value = (hex_str or "").lstrip("#")
    if len(value) != 6:
        return hex_str
    channels = [int(value[i:i + 2], 16) for i in (0, 2, 4)]
    mixed = [round(c + (255 - c) * amount) for c in channels]
    return "#" + "".join(f"{c:02x}" for c in mixed)


def _box(axes, x, y, w, h, fill, text, size, *, bold=False, edge=None,
         text_colour=None, rounding=0.35, wrap=None):
    axes.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={rounding}",
        facecolor=fill, edgecolor=edge or fill, linewidth=1.4, zorder=2))
    if not text:
        return
    axes.text(x + w / 2, y + h / 2,
              _wrap(text, wrap) if wrap else text,
              ha="center", va="center", fontsize=size, zorder=3,
              color=text_colour or palettes.on_fill(fill),
              fontweight="bold" if bold else "normal", linespacing=1.15)


def _arrow(axes, start, end, colour=GRID, width=1.8, style="-|>"):
    axes.add_patch(FancyArrowPatch(
        start, end, arrowstyle=style, mutation_scale=11,
        color=colour, linewidth=width, zorder=1,
        shrinkA=0, shrinkB=0))


def _line(axes, xs, ys, colour=GRID, width=1.6):
    axes.plot(xs, ys, color=colour, linewidth=width, zorder=1,
              solid_capstyle="round")


def _canvas(height: float):
    figure, axes = plt.subplots(figsize=(_WIDTH, height), dpi=_DPI)
    figure.patch.set_facecolor(SURFACE)
    axes.set_facecolor(SURFACE)
    axes.set_xlim(0, 100)
    axes.set_ylim(0, 100)
    axes.axis("off")
    return figure, axes


def _title(axes, title: str):
    if title:
        axes.set_title(title, fontsize=11, color=INK, loc="left", pad=10)


def _parts(data: dict, limit: int = 6) -> list:
    """Tarmoqlarni (nom, elementlar) juftliklariga keltiradi."""
    out = []
    for branch in (data.get("branches") or []):
        if not isinstance(branch, dict):
            continue
        name = " ".join(str(branch.get("name") or "").split())
        if not name:
            continue
        items = [" ".join(str(i).split()) for i in (branch.get("items") or [])]
        out.append((name, [i for i in items if i][:3]))
    return out[:limit]


# ══════════════════════════════════════════════════════════════════ daraxt

def _tree(axes, root: str, parts: list, palette) -> float:
    """Yuqorida ildiz, ostida ustunlar — klassik tashkiliy sxema."""
    columns = len(parts)
    depth = max((len(items) for _n, items in parts), default=0)

    root_w, root_h = 46, 13
    root_y = 86
    _box(axes, 50 - root_w / 2, root_y, root_w, root_h, palette.ramp[3],
         _shorten(root, 46), 11, bold=True, wrap=30)

    branch_h, item_h, gap = 11.0, 9.0, 3.2
    branch_y = root_y - 14 - depth * 0  # tarmoq qatori ildizdan pastda
    branch_y = 60
    column_gap = 2.8
    col_w = (100 - column_gap * (columns - 1)) / columns

    for index, (name, items) in enumerate(parts):
        hue = palette.categorical[index % len(palette.categorical)]
        col_x = index * (col_w + column_gap)
        centre = col_x + col_w / 2

        _line(axes, [50, 50], [root_y, root_y - 7])
        _line(axes, [50, centre], [root_y - 7, root_y - 7])
        _line(axes, [centre, centre], [root_y - 7, branch_y + branch_h])

        _box(axes, col_x, branch_y, col_w, branch_h, hue,
             _shorten(name, 30), 9.5, bold=True, wrap=max(12, int(col_w / 1.6)))

        for level, item in enumerate(items):
            item_y = branch_y - (level + 1) * (item_h + gap)
            _line(axes, [centre, centre], [item_y + item_h, item_y + item_h + gap],
                  width=1.2)
            _box(axes, col_x + col_w * 0.05, item_y, col_w * 0.9, item_h,
                 _tint(hue, 0.86), _shorten(item, 34), 8.5, edge=hue,
                 text_colour=INK, wrap=max(12, int(col_w / 1.5)))

    floor = branch_y - depth * (item_h + gap) - 3
    return floor


# ══════════════════════════════════════════════════════════════════ radial

def _radial(axes, root: str, parts: list, palette) -> float:
    """Markazda butun, atrofida qismlar — ulushlarga bo'linadigan mavzuga."""
    count = len(parts)
    # Markaz biroz pastda: eng yuqoridagi qismning yozuvi tepada turadi.
    centre_x, centre_y, radius = 50.0, 46.0, 30.0

    axes.add_patch(Circle((centre_x, centre_y), 15.5, facecolor=palette.ramp[3],
                          edgecolor=SURFACE, linewidth=2.5, zorder=3))
    axes.text(centre_x, centre_y, _wrap(_shorten(root, 40), 14), ha="center",
              va="center", fontsize=10, fontweight="bold", zorder=4,
              color=palettes.on_fill(palette.ramp[3]), linespacing=1.15)

    for index, (name, items) in enumerate(parts):
        angle = math.pi / 2 - index * 2 * math.pi / count
        x = centre_x + radius * math.cos(angle)
        y = centre_y + radius * math.sin(angle) * 0.92
        hue = palette.categorical[index % len(palette.categorical)]

        _line(axes, [centre_x + 15.5 * math.cos(angle), x],
              [centre_y + 15.5 * math.sin(angle) * 0.92, y], width=1.8)

        width, height = 27.0, 11.0
        _box(axes, x - width / 2, y - height / 2, width, height, hue,
             _shorten(name, 28), 9.2, bold=True, wrap=16)

        # Elementlar katakdan markazga QARAMA-QARSHI tomonda yoziladi:
        # yuqoridagi qism uchun tepada, pastdagisi uchun ostida. Ilgari
        # ular yon tomonga yozilardi va chapdagisi rasm chetidan chiqib
        # ketardi; hammasini ostiga qo'yganda esa yuqoridagi yozuv markaz
        # bloki ustiga tushib qolardi.
        if items:
            upward = math.sin(angle) > 0.3
            axes.text(x, y + (height / 2 + 1.5 if upward else -height / 2 - 1.5),
                      "\n".join(_shorten(item, 24) for item in items),
                      ha="center", va="bottom" if upward else "top",
                      fontsize=7.6, color=INK_SOFT, linespacing=1.5, zorder=3)
    return -6.0


# ═════════════════════════════════════════════════════════════════ mindmap

def _mindmap(axes, root: str, parts: list, palette) -> float:
    """Chapda ildiz, o'ngda tarmoqlar — uzun nomlar sig'adigan shakl."""
    count = len(parts)
    root_w, root_h = 30.0, 16.0
    root_x, root_y = 2.0, 50 - root_h / 2
    _box(axes, root_x, root_y, root_w, root_h, palette.ramp[3],
         _shorten(root, 48), 10.5, bold=True, wrap=18)

    span = 92.0
    branch_h = min(15.0, span / count - 3.0)
    step = span / count
    left = root_x + root_w

    for index, (name, items) in enumerate(parts):
        hue = palette.categorical[index % len(palette.categorical)]
        centre_y = 96 - step * (index + 0.5)
        y = centre_y - branch_h / 2

        # Ildizdan tarmoqqa egri chiziq.
        mid = left + 6
        axes.plot([left, mid, mid, mid + 4],
                  [50, 50, centre_y, centre_y],
                  color=GRID, linewidth=1.6, zorder=1,
                  solid_capstyle="round")

        width = 30.0
        _box(axes, mid + 4, y, width, branch_h, hue, _shorten(name, 30), 9.4,
             bold=True, wrap=18)

        if items:
            axes.text(mid + 4 + width + 2, centre_y,
                      "\n".join(f"— {_shorten(item, 26)}" for item in items),
                      ha="left", va="center", fontsize=8, color=INK_SOFT,
                      linespacing=1.5, zorder=3)
    return 0.0


# ════════════════════════════════════════════════════════════════════ oqim

def _flow(axes, root: str, parts: list, palette, chevron: bool = False) -> float:
    """Chapdan o'ngga bosqichlar — ketma-ket boradigan jarayon uchun."""
    count = len(parts)
    _box(axes, 2, 86, 96, 12, palette.ramp[3], _shorten(root, 60), 10.5,
         bold=True, wrap=60)

    gap = 2.5 if chevron else 4.0
    width = (100 - gap * (count - 1)) / count
    y, height = 58.0, 16.0

    for index, (name, items) in enumerate(parts):
        hue = palette.categorical[index % len(palette.categorical)]
        x = index * (width + gap)

        if chevron:
            tip = min(4.0, width * 0.18)
            points = [(x, y), (x + width - tip, y), (x + width, y + height / 2),
                      (x + width - tip, y + height), (x, y + height)]
            if index:
                points.append((x + tip, y + height / 2))
            axes.add_patch(Polygon(points, closed=True, facecolor=hue,
                                   edgecolor=SURFACE, linewidth=2, zorder=2))
            axes.text(x + width / 2, y + height / 2,
                      _wrap(_shorten(name, 30), max(10, int(width / 1.7))),
                      ha="center", va="center", fontsize=9.2, zorder=3,
                      fontweight="bold", color=palettes.on_fill(hue),
                      linespacing=1.15)
        else:
            _box(axes, x, y, width, height, hue, _shorten(name, 30), 9.2,
                 bold=True, wrap=max(10, int(width / 1.7)))
            if index:
                _arrow(axes, (x - gap + 0.4, y + height / 2), (x - 0.4, y + height / 2))

        # Bosqich raqami — ketma-ketlik ko'rinib tursin.
        axes.text(x + width / 2, y + height + 2.5, str(index + 1),
                  ha="center", va="bottom", fontsize=9, color=INK_SOFT,
                  fontweight="bold", zorder=3)

        if items:
            axes.text(x + width / 2, y - 3,
                      "\n".join(f"• {_shorten(item, 20)}" for item in items),
                      ha="center", va="top", fontsize=7.8, color=INK_SOFT,
                      linespacing=1.5, zorder=3)

    deepest = max((len(items) for _n, items in parts), default=0)
    return y - 6 - deepest * 4.5


# ═══════════════════════════════════════════════════════════════════ sikl

def _cycle(axes, root: str, parts: list, palette) -> float:
    """Doira bo'ylab bosqichlar — takrorlanadigan jarayon uchun."""
    count = len(parts)
    centre_x, centre_y, radius = 50.0, 48.0, 31.0

    axes.text(centre_x, centre_y, _wrap(_shorten(root, 40), 16), ha="center",
              va="center", fontsize=10.5, fontweight="bold", color=INK,
              zorder=4, linespacing=1.2)

    positions = []
    for index in range(count):
        angle = math.pi / 2 - index * 2 * math.pi / count
        positions.append((centre_x + radius * math.cos(angle),
                          centre_y + radius * math.sin(angle) * 0.95))

    # Avval yoylar, keyin kataklar — o'q katak ostida qolsin.
    for index in range(count):
        start = np.array(positions[index])
        end = np.array(positions[(index + 1) % count])
        axes.add_patch(FancyArrowPatch(
            tuple(start), tuple(end), connectionstyle="arc3,rad=-0.22",
            arrowstyle="-|>", mutation_scale=15, color=palette.ramp[1],
            linewidth=2.2, zorder=1, shrinkA=17, shrinkB=17))

    for index, ((name, items), (x, y)) in enumerate(zip(parts, positions)):
        hue = palette.categorical[index % len(palette.categorical)]
        width, height = 26.0, 12.0
        _box(axes, x - width / 2, y - height / 2, width, height, hue,
             _shorten(name, 26), 9.2, bold=True, wrap=15)
        if items:
            # Yozuv yoy ustiga tushishi mumkin — ochiq hoshiya uni har
            # qanday fonda o'qiladigan qiladi.
            axes.text(x, y - height / 2 - 1.5,
                      "\n".join(_shorten(item, 20) for item in items[:2]),
                      ha="center", va="top", fontsize=7.4, color=INK_SOFT,
                      linespacing=1.5, zorder=4,
                      path_effects=[path_effects.withStroke(
                          linewidth=3, foreground=SURFACE)])
    return -8.0


# ═════════════════════════════════════════════════════════════════ darajalar

def _levels(axes, root: str, parts: list, palette, pyramid: bool = False) -> float:
    """Ustma-ust qatlamlar — biri ikkinchisiga asos bo'ladigan tuzilma."""
    count = len(parts)
    _box(axes, 2, 88, 96, 11, palette.ramp[3], _shorten(root, 60), 10.5,
         bold=True, wrap=60)

    top, bottom = 84.0, 4.0
    gap = 2.6
    height = (top - bottom - gap * (count - 1)) / count

    for index, (name, items) in enumerate(parts):
        hue = palette.categorical[index % len(palette.categorical)]
        y = top - (index + 1) * height - index * gap

        if pyramid:
            # Yuqorigi qatlam tor, pastkisi keng — asos pastda.
            narrow = 44 + index * (52 / max(count - 1, 1))
            x = 50 - narrow / 2
            width = narrow
        else:
            x, width = 4.0, 92.0

        _box(axes, x, y, width, height, hue, "", 9)
        label = _shorten(name, 40)
        detail = " · ".join(_shorten(item, 20) for item in items[:2])
        axes.text(x + width / 2, y + height / 2 + (1.6 if detail else 0),
                  _wrap(label, 46), ha="center", va="center", fontsize=9.6,
                  fontweight="bold", color=palettes.on_fill(hue), zorder=3)
        if detail:
            axes.text(x + width / 2, y + height / 2 - 2.6, detail, ha="center",
                      va="center", fontsize=7.6, zorder=3,
                      color=palettes.on_fill(hue), alpha=0.85)
    return 0.0


# ═══════════════════════════════════════════════════════════════ tanlash

_HEIGHTS = {
    "tree": 4.6,
    "radial": 4.9,
    "mindmap": 4.4,
    "flow": 3.8,
    "chevron": 3.8,
    "cycle": 4.9,
    "levels": 4.4,
    "pyramid": 4.6,
}


def draw(data: dict, title: str, work_dir: str, palette=None,
         language: str = "uz", form: str = "") -> str:
    """Tuzilma sxemasini chizadi.

    Shakl ma'lumotdagi `kind` va mavzu urug'idan tanlanadi, shuning uchun
    har hujjat boshqacha ko'rinadi. `form` berilsa va u shu turga to'g'ri
    kelsa, o'sha ishlatiladi.
    """
    from .charts import _figure_guard, _palette, _save

    palette = _palette(palette)
    root = str(data.get("root") or title or "").strip()
    parts = _parts(data)
    if len(parts) < 2:
        raise ValueError("sxema uchun kamida ikkita qism kerak")

    kind = str(data.get("kind") or DEFAULT_KIND).strip().lower()
    shape = pick_form(kind, f"{root}|{title}|{len(parts)}", form)
    height = _HEIGHTS.get(shape, 4.6)
    # Tarmoq ko'p bo'lsa mindmap va daraxt cho'ziladi.
    if shape == "mindmap":
        height = max(height, 1.05 * len(parts) + 1.2)
    elif shape == "tree":
        depth = max((len(items) for _n, items in parts), default=0)
        height = max(3.2, 2.6 + 0.62 * depth)

    with _figure_guard():
        figure, axes = _canvas(height)
        if shape == "radial":
            floor = _radial(axes, root, parts, palette)
        elif shape == "mindmap":
            floor = _mindmap(axes, root, parts, palette)
        elif shape == "flow":
            floor = _flow(axes, root, parts, palette)
        elif shape == "chevron":
            floor = _flow(axes, root, parts, palette, chevron=True)
        elif shape == "cycle":
            floor = _cycle(axes, root, parts, palette)
        elif shape == "levels":
            floor = _levels(axes, root, parts, palette)
        elif shape == "pyramid":
            floor = _levels(axes, root, parts, palette, pyramid=True)
        else:
            floor = _tree(axes, root, parts, palette)

        # Har chizma o'zining pastki chegarasini qaytaradi: aks holda
        # rasmning yarmi bo'sh qolardi.
        axes.set_ylim(min(floor, 98.0), 100)
        _title(axes, title)
        return _save(figure, work_dir, language)
