"""Loyiha ishining vizual instrumentlari.

Beshta bir xil jadval o'rniga har ma'lumot turi o'z shaklini oladi:
xarajat — ustunli diagramma, prognoz — chiziq, bosqichlar — Gantt lentasi,
risklar — matritsa. Hammasi PNG qilib chiziladi va hujjatga rasm sifatida
qo'yiladi.

Ranglar tasodifiy tanlanmagan: rang ko'rlik uchun tekshirilgan palitradan
olingan va har rang bajaradigan ishiga qarab beriladi — kattalik uchun
bitta rangning to'qlashuvi, holat uchun alohida status ranglari.
"""

import logging
import os
import re
import uuid

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

logger = logging.getLogger(__name__)

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e3e2df"

# Kattalik uchun bitta hue: ko'proq = to'qroq. Beshta qadam — validator
# to'liq rampni rad etdi, chunki qo'shni qadamlar yorug'ligi bo'yicha juda
# yaqin bo'lib, ustunlar bir-biridan ajralmay qolardi. Eng ochig'i sirtga
# singib ketmasligi uchun 250-qadamdan pastga tushmaydi.
BLUE_RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"]

# Holat ranglari — faqat holat uchun, seriya rangi sifatida ishlatilmaydi.
STATUS = {1: "#0ca30c", 2: "#fab219", 3: "#ec835a", 4: "#d03b3b"}

_FIGSIZE = (7.6, 4.2)
_DPI = 150


def _number(value) -> float:
    """AI qaytargan "12 500 000 so'm" kabi qiymatdan sonni ajratadi."""
    if isinstance(value, (int, float)):
        return float(value)
    digits = re.sub(r"[^\d.,-]", "", str(value or "")).replace(" ", "")
    digits = digits.replace(",", "." if digits.count(",") == 1 and "." not in digits else "")
    try:
        return float(digits)
    except ValueError:
        return 0.0


def _format(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} mln".replace(".0 ", " ")
    if value >= 1_000:
        return f"{value / 1_000:.0f} ming"
    return f"{value:.0f}"


def _on_fill(fill: str) -> str:
    """To'ldirish rangi ustidagi matn rangi — oq matn och fonda o'qilmaydi."""
    red, green, blue = (int(fill[i:i + 2], 16) / 255 for i in (1, 3, 5))
    channels = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in (red, green, blue)
    ]
    luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    return "#ffffff" if luminance < 0.42 else INK


def _shorten(text: str, limit: int = 34) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _new_figure(height: float = _FIGSIZE[1]):
    figure, axes = plt.subplots(figsize=(_FIGSIZE[0], height), dpi=_DPI)
    figure.patch.set_facecolor(SURFACE)
    axes.set_facecolor(SURFACE)
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axes.spines[side].set_color(GRID)
    axes.tick_params(colors=INK_SOFT, labelsize=9, length=0)
    return figure, axes


def _save(figure, work_dir: str) -> str:
    os.makedirs(work_dir, exist_ok=True)
    path = os.path.join(work_dir, f"pwchart_{uuid.uuid4().hex[:10]}.png")
    figure.savefig(path, facecolor=SURFACE, bbox_inches="tight", pad_inches=0.18)
    plt.close(figure)
    return path


# ────────────────────────────────────────────────────────────── byudjet

def budget_bar(rows: list, title: str, work_dir: str) -> str:
    """Xarajat moddalari — gorizontal ustunlar, kattaligi bo'yicha tartiblangan.

    Doiraviy diagramma emas: o'quvchining vazifasi "qaysi modda qimmat"
    degan taqqoslash, va uzun o'zbekcha nomlar doira atrofiga sig'maydi.
    """
    items = [(str(r.get("name", "")), _number(r.get("amount"))) for r in rows]
    items = [(name, amount) for name, amount in items if amount > 0]
    if not items:
        raise ValueError("byudjetda son yo'q")

    items.sort(key=lambda pair: pair[1])
    names = [_shorten(name) for name, _ in items]
    values = [amount for _, amount in items]

    height = max(2.6, 0.46 * len(items) + 1.2)
    figure, axes = _new_figure(height)

    # Kattalik bo'yicha to'qlashuv: eng kattasi eng to'q.
    order = sorted(range(len(values)), key=lambda i: values[i])
    shades = [BLUE_RAMP[0]] * len(values)
    for rank, index in enumerate(order):
        step = int(rank / max(len(values) - 1, 1) * (len(BLUE_RAMP) - 1))
        shades[index] = BLUE_RAMP[step]

    bars = axes.barh(names, values, color=shades, height=0.62,
                     edgecolor=SURFACE, linewidth=2)
    axes.set_xlim(0, max(values) * 1.18)
    axes.xaxis.set_visible(False)
    axes.spines["bottom"].set_visible(False)
    axes.spines["left"].set_visible(False)

    for bar, value in zip(bars, values):
        axes.text(bar.get_width() + max(values) * 0.02, bar.get_y() + bar.get_height() / 2,
                  _format(value), va="center", ha="left", fontsize=9, color=INK)

    axes.set_title(title, fontsize=11, color=INK, loc="left", pad=12)
    return _save(figure, work_dir)


# ───────────────────────────────────────────────────────────── prognoz

def forecast_line(points: list, title: str, unit: str, work_dir: str) -> str:
    """Prognoz — bitta chiziq va ishonch oralig'i. Bitta seriya, legend kerak emas."""
    periods = [str(p.get("period", "")) for p in points]
    values = [_number(p.get("value")) for p in points]
    if len(values) < 3:
        raise ValueError("prognoz uchun kamida uchta nuqta kerak")

    lows = [_number(p.get("low")) or value * 0.9 for p, value in zip(points, values)]
    highs = [_number(p.get("high")) or value * 1.1 for p, value in zip(points, values)]

    figure, axes = _new_figure()
    axes.fill_between(periods, lows, highs, color=BLUE_RAMP[0], alpha=0.35, linewidth=0)
    axes.plot(periods, values, color=BLUE_RAMP[2], linewidth=2,
              marker="o", markersize=7, markerfacecolor=BLUE_RAMP[2],
              markeredgecolor=SURFACE, markeredgewidth=2)

    axes.grid(axis="y", color=GRID, linewidth=1)
    axes.set_axisbelow(True)
    axes.spines["left"].set_visible(False)

    # Faqat oxirgi nuqta belgilanadi — har nuqtaga raqam qo'yish shovqin.
    # Qiymat allaqachon o'z birligida (o'q nomida aytilgan), qayta o'lchanmaydi.
    axes.annotate(f"{values[-1]:,.0f}".replace(",", " "),
                  (len(values) - 1, values[-1]),
                  textcoords="offset points", xytext=(-6, 14),
                  ha="right", fontsize=10, color=INK, fontweight="bold")
    axes.margins(x=0.06)

    axes.set_title(title, fontsize=11, color=INK, loc="left", pad=12)
    if unit:
        axes.set_ylabel(unit, fontsize=9, color=INK_SOFT)
    return _save(figure, work_dir)


# ─────────────────────────────────────────────────────────────── Gantt

def gantt(stages: list, title: str, work_dir: str) -> str:
    """Bosqichlar vaqt o'qida — jadval emas, lenta."""
    rows = []
    cursor = 0.0
    for stage in stages:
        name = _shorten(str(stage.get("name", "")))
        start = _number(stage.get("start"))
        length = max(_number(stage.get("duration")), 0.5)
        if not start:
            start = cursor
        cursor = start + length
        rows.append((name, start, length))
    if not rows:
        raise ValueError("bosqich yo'q")

    height = max(2.6, 0.46 * len(rows) + 1.2)
    figure, axes = _new_figure(height)

    labels = [name for name, _, _ in rows]
    positions = range(len(rows))
    for index, (_, start, length) in enumerate(rows):
        step = int(index / max(len(rows) - 1, 1) * (len(BLUE_RAMP) - 1))
        fill = BLUE_RAMP[step]
        axes.barh(index, length, left=start, height=0.55,
                  color=fill, edgecolor=SURFACE, linewidth=2)
        axes.text(start + length / 2, index, f"{length:g} oy",
                  va="center", ha="center", fontsize=8.5, color=_on_fill(fill))

    axes.set_yticks(list(positions))
    axes.set_yticklabels(labels, fontsize=9)
    axes.invert_yaxis()
    axes.grid(axis="x", color=GRID, linewidth=1)
    axes.set_axisbelow(True)
    axes.spines["left"].set_visible(False)
    axes.set_xlabel("oy", fontsize=9, color=INK_SOFT)
    axes.set_title(title, fontsize=11, color=INK, loc="left", pad=12)
    return _save(figure, work_dir)


# ────────────────────────────────────────────────────────────── risklar

_LEVEL_WORDS = {"past": 1, "o'rta": 2, "orta": 2, "yuqori": 3,
                "низкая": 1, "низкий": 1, "средняя": 2, "средний": 2,
                "высокая": 3, "высокий": 3, "low": 1, "medium": 2, "high": 3}


def _level(value) -> int:
    text = str(value or "").strip().lower().replace("ʻ", "'").replace("‘", "'")
    for word, level in _LEVEL_WORDS.items():
        if text.startswith(word):
            return level
    number = int(_number(value))
    return min(max(number, 1), 3) if number else 2


def risk_matrix(risks: list, title: str, work_dir: str) -> str:
    """Ehtimollik × ta'sir matritsasi.

    Rang xavf darajasini bildiradi, lekin uni yolg'iz tashlab qo'ymaydi:
    har katakda risk raqami turadi va ro'yxat pastda beriladi.
    """
    placed = []
    for number, risk in enumerate(risks[:9], start=1):
        placed.append((number, _level(risk.get("likelihood")), _level(risk.get("impact"))))
    if not placed:
        raise ValueError("risk yo'q")

    figure, axes = _new_figure(4.0)
    axis_labels = ["Past", "O'rta", "Yuqori"]

    fills = {}
    for x in range(3):
        for y in range(3):
            severity = (x + 1) * (y + 1)
            tier = 1 if severity <= 2 else 2 if severity <= 4 else 3 if severity <= 6 else 4
            fills[(x, y)] = STATUS[tier]
            axes.add_patch(Rectangle((x, y), 1, 1, facecolor=STATUS[tier],
                                     edgecolor=SURFACE, linewidth=3))

    for number, likelihood, impact in placed:
        fill = fills[(likelihood - 1, impact - 1)]
        axes.text(likelihood - 0.5, impact - 0.5, str(number),
                  ha="center", va="center", fontsize=13,
                  color=_on_fill(fill), fontweight="bold")

    axes.set_xlim(0, 3)
    axes.set_ylim(0, 3)
    axes.set_xticks([0.5, 1.5, 2.5])
    axes.set_yticks([0.5, 1.5, 2.5])
    axes.set_xticklabels(axis_labels, fontsize=9)
    axes.set_yticklabels(axis_labels, fontsize=9)
    axes.set_xlabel("Ehtimolligi", fontsize=9, color=INK_SOFT)
    axes.set_ylabel("Ta'siri", fontsize=9, color=INK_SOFT)
    for side in ("left", "bottom"):
        axes.spines[side].set_visible(False)
    axes.set_title(title, fontsize=11, color=INK, loc="left", pad=12)
    return _save(figure, work_dir)


def render_formula(latex: str, work_dir: str) -> str:
    """Formulani matematik yozuv sifatida chizadi."""
    figure = plt.figure(figsize=(6.4, 0.9), dpi=_DPI)
    figure.patch.set_facecolor(SURFACE)
    figure.text(0.02, 0.45, f"${latex}$", fontsize=17, color=INK, va="center")
    return _save(figure, work_dir)
