"""Loyiha ishining vizual instrumentlari.

Har ma'lumot turi bitta emas, bir nechta to'g'ri shaklga ega: xarajatni
gorizontal ustun ham, lollipop ham, donut ham, sharshara ham ko'rsata oladi.
Qaysi biri ishlatilishini `variety.py` hal qiladi — shu sababli ketma-ket
ikki loyiha ishi bir xil ko'rinmaydi.

Ranglar ham qat'iy emas: `palettes.py` dagi oltita sxemadan biri tanlanadi.
Lekin rang bajaradigan ishi o'zgarmaydi — kattalik uchun bitta rangning
to'qlashuvi, holat uchun alohida status ranglari.
"""

import contextlib
import logging
import os
import re
import uuid

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

from . import palettes
from .palettes import GRID, INK, INK_SOFT, STATUS, SURFACE, Palette

logger = logging.getLogger(__name__)

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
    return palettes.on_fill(fill)


def _palette(palette) -> Palette:
    return palette or palettes.DEFAULT_PALETTE


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


@contextlib.contextmanager
def _figure_guard():
    """Chizish davomida ochilgan figuralar har qanday holatda yopilishini kafolatlaydi.

    matplotlib figuralarni global ro'yxatda ushlab turadi. `_save` ga
    yetib bormasdan xato yuz bersa (masalan ma'lumot kutilmagan shaklda
    bo'lsa), figura o'z buferi bilan xotirada qolib ketardi — bot uzoq
    ishlagani sari xotira shu tarzda to'lardi.
    """
    before = set(plt.get_fignums())
    try:
        yield
    finally:
        for number in set(plt.get_fignums()) - before:
            try:
                plt.close(number)
            except Exception:
                pass


def _save(figure, work_dir: str) -> str:
    os.makedirs(work_dir, exist_ok=True)
    path = os.path.join(work_dir, f"pwchart_{uuid.uuid4().hex[:10]}.png")
    figure.savefig(path, facecolor=SURFACE, bbox_inches="tight", pad_inches=0.18)
    plt.close(figure)
    return path


# ══════════════════════════════════════════════════════════════ byudjet
#
# To'rtta shakl ham bitta savolga javob beradi: qaysi modda qimmat.
# Doiraviy diagramma faqat beshtagacha moddada ishlatiladi — undan
# ko'pida bo'laklar ajralmay qoladi.

def _budget_rows(rows: list) -> list:
    items = [(_shorten(str(r.get("name", ""))), _number(r.get("amount"))) for r in rows]
    items = [(name, amount) for name, amount in items if amount > 0]
    if not items:
        raise ValueError("byudjetda son yo'q")
    return items


def budget_bar(rows: list, title: str, work_dir: str, palette=None) -> str:
    """Gorizontal ustunlar, kattaligi bo'yicha tartiblangan."""
    palette = _palette(palette)
    items = sorted(_budget_rows(rows), key=lambda pair: pair[1])
    names = [name for name, _ in items]
    values = [amount for _, amount in items]

    figure, axes = _new_figure(max(2.6, 0.46 * len(items) + 1.2))
    bars = axes.barh(names, values, color=palettes.shades(palette, values),
                     height=0.62, edgecolor=SURFACE, linewidth=2)
    axes.set_xlim(0, max(values) * 1.18)
    axes.xaxis.set_visible(False)
    for side in ("bottom", "left"):
        axes.spines[side].set_visible(False)
    for bar, value in zip(bars, values):
        axes.text(bar.get_width() + max(values) * 0.02,
                  bar.get_y() + bar.get_height() / 2, _format(value),
                  va="center", ha="left", fontsize=9, color=INK)
    _title(axes, title)
    return _save(figure, work_dir)


def budget_lollipop(rows: list, title: str, work_dir: str, palette=None) -> str:
    """Nuqta va ingichka chiziq — ustunga qaraganda yengilroq ko'rinadi."""
    palette = _palette(palette)
    items = sorted(_budget_rows(rows), key=lambda pair: pair[1])
    names = [name for name, _ in items]
    values = [amount for _, amount in items]
    positions = range(len(items))

    figure, axes = _new_figure(max(2.6, 0.46 * len(items) + 1.2))
    axes.hlines(list(positions), 0, values, color=palette.ramp[1], linewidth=2.4)
    axes.scatter(values, list(positions), s=130, color=palette.ramp[3],
                 zorder=3, edgecolor=SURFACE, linewidth=1.5)
    axes.set_yticks(list(positions))
    axes.set_yticklabels(names, fontsize=9)
    axes.set_xlim(0, max(values) * 1.22)
    axes.xaxis.set_visible(False)
    for side in ("bottom", "left"):
        axes.spines[side].set_visible(False)
    for index, value in enumerate(values):
        axes.text(value + max(values) * 0.025, index, _format(value),
                  va="center", ha="left", fontsize=9, color=INK)
    _title(axes, title)
    return _save(figure, work_dir)


def budget_donut(rows: list, title: str, work_dir: str, palette=None) -> str:
    """Ulushlar halqasi — markazda jami summa."""
    palette = _palette(palette)
    items = sorted(_budget_rows(rows), key=lambda pair: pair[1], reverse=True)
    if len(items) > 5:
        # Oltinchi va undan keyingilari bir bo'lakka yig'iladi: ingichka
        # bo'laklarni ko'z ajratmaydi va yozuvlari ustma-ust tushadi.
        head_items, tail_items = items[:4], items[4:]
        items = head_items + [("Qolgan moddalar", sum(v for _, v in tail_items))]

    values = [amount for _, amount in items]
    figure, axes = plt.subplots(figsize=(_FIGSIZE[0], 4.4), dpi=_DPI)
    figure.patch.set_facecolor(SURFACE)
    axes.set_facecolor(SURFACE)

    axes.pie(values, labels=[name for name, _ in items],
             colors=palette.categorical[:len(items)],
             startangle=90, counterclock=False,
             wedgeprops=dict(width=0.42, edgecolor=SURFACE, linewidth=2),
             textprops=dict(fontsize=9, color=INK))
    axes.text(0, 0, _format(sum(values)), ha="center", va="center",
              fontsize=13, color=INK, fontweight="bold")
    axes.set_title(title, fontsize=11, color=INK, loc="left", pad=12)
    return _save(figure, work_dir)


def budget_waterfall(rows: list, title: str, work_dir: str, palette=None) -> str:
    """Sharshara — moddalar birin-ketin qo'shilib jamini hosil qiladi."""
    palette = _palette(palette)
    items = sorted(_budget_rows(rows), key=lambda pair: pair[1], reverse=True)[:7]
    total = sum(amount for _, amount in items)

    figure, axes = _new_figure(4.2)
    bottom = 0.0
    for index, (name, amount) in enumerate(items):
        fill = palette.ramp[min(index, len(palette.ramp) - 1)]
        axes.bar(index, amount, bottom=bottom, width=0.62,
                 color=fill, edgecolor=SURFACE, linewidth=2)
        # Ulanish chizig'i — keyingi ustun qayerdan boshlanishini ko'rsatadi.
        axes.text(index, bottom + amount, _format(amount), ha="center",
                  va="bottom", fontsize=8, color=INK_SOFT)
        if index < len(items) - 1:
            axes.plot([index + 0.31, index + 0.69], [bottom + amount] * 2,
                      color=INK_SOFT, linewidth=0.9, linestyle=(0, (3, 3)), zorder=1)
        bottom += amount

    axes.bar(len(items), total, width=0.62, color=palette.ramp[-1],
             edgecolor=SURFACE, linewidth=2)
    axes.text(len(items), total, _format(total), ha="center", va="bottom",
              fontsize=9.5, color=INK, fontweight="bold")

    axes.set_xticks(range(len(items) + 1))
    axes.set_xticklabels([_shorten(name, 16) for name, _ in items] + ["Jami"],
                         fontsize=8.5, rotation=28, ha="right")
    # Y o'qi 1e9 kabi ilmiy yozuvni ko'rsatardi — qiymatlar ustunlarda yoziladi.
    axes.yaxis.set_visible(False)
    axes.set_ylim(0, total * 1.14)
    for side in ("left", "bottom"):
        axes.spines[side].set_visible(False)
    _title(axes, title)
    return _save(figure, work_dir)


# ══════════════════════════════════════════════════════════════ prognoz

def _forecast_series(points: list):
    periods = [str(p.get("period", "")) for p in points]
    values = [_number(p.get("value")) for p in points]
    if len(values) < 3:
        raise ValueError("prognoz uchun kamida uchta nuqta kerak")
    return periods, values


def _last_label(axes, values):
    """Faqat oxirgi nuqta belgilanadi — har nuqtaga raqam qo'yish shovqin."""
    axes.annotate(f"{values[-1]:,.0f}".replace(",", " "),
                  (len(values) - 1, values[-1]),
                  textcoords="offset points", xytext=(-6, 14),
                  ha="right", fontsize=10, color=INK, fontweight="bold")


def forecast_line(points: list, title: str, unit: str, work_dir: str, palette=None) -> str:
    """Chiziq va ishonch oralig'i. Bitta seriya, legend kerak emas."""
    palette = _palette(palette)
    periods, values = _forecast_series(points)
    lows = [_number(p.get("low")) or value * 0.9 for p, value in zip(points, values)]
    highs = [_number(p.get("high")) or value * 1.1 for p, value in zip(points, values)]

    figure, axes = _new_figure()
    axes.fill_between(periods, lows, highs, color=palette.ramp[0], alpha=0.35, linewidth=0)
    axes.plot(periods, values, color=palette.ramp[2], linewidth=2,
              marker="o", markersize=7, markerfacecolor=palette.ramp[2],
              markeredgecolor=SURFACE, markeredgewidth=2)
    _time_axis(axes, unit)
    _last_label(axes, values)
    _title(axes, title)
    return _save(figure, work_dir)


def forecast_area(points: list, title: str, unit: str, work_dir: str, palette=None) -> str:
    """To'ldirilgan maydon — o'sishning to'planishini ko'rsatadi."""
    palette = _palette(palette)
    periods, values = _forecast_series(points)

    figure, axes = _new_figure()
    axes.fill_between(periods, values, color=palette.ramp[1], alpha=0.55, linewidth=0)
    axes.plot(periods, values, color=palette.ramp[3], linewidth=2.2,
              marker="o", markersize=6, markerfacecolor=palette.ramp[3],
              markeredgecolor=SURFACE, markeredgewidth=2)
    axes.set_ylim(0, max(values) * 1.16)
    _time_axis(axes, unit)
    _last_label(axes, values)
    _title(axes, title)
    return _save(figure, work_dir)


def forecast_column(points: list, title: str, unit: str, work_dir: str, palette=None) -> str:
    """Ustunlar — davrlar aniq ajralib turadi, oxirgisi prognoz sifatida ochroq."""
    palette = _palette(palette)
    periods, values = _forecast_series(points)

    figure, axes = _new_figure()
    fills = [palette.ramp[2]] * len(values)
    fills[-1] = palette.ramp[0]     # oxirgi davr — prognoz, shuning uchun ochroq
    axes.bar(periods, values, width=0.6, color=fills, edgecolor=SURFACE, linewidth=2)
    for index, value in enumerate(values):
        axes.text(index, value, _format(value), ha="center", va="bottom",
                  fontsize=8.5, color=INK)
    axes.set_ylim(0, max(values) * 1.18)
    _time_axis(axes, unit)
    _title(axes, title)
    return _save(figure, work_dir)


def _time_axis(axes, unit: str):
    axes.grid(axis="y", color=GRID, linewidth=1)
    axes.set_axisbelow(True)
    axes.spines["left"].set_visible(False)
    axes.margins(x=0.06)
    if unit:
        axes.set_ylabel(unit, fontsize=9, color=INK_SOFT)


# ══════════════════════════════════════════════════════════════ bosqichlar

def _stage_rows(stages: list) -> list:
    rows, cursor = [], 0.0
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
    return rows


def gantt(stages: list, title: str, work_dir: str, palette=None) -> str:
    """Bosqichlar vaqt o'qida — jadval emas, lenta."""
    palette = _palette(palette)
    rows = _stage_rows(stages)

    figure, axes = _new_figure(max(2.6, 0.46 * len(rows) + 1.2))
    for index, (_, start, length) in enumerate(rows):
        step = int(index / max(len(rows) - 1, 1) * (len(palette.ramp) - 1))
        fill = palette.ramp[step]
        axes.barh(index, length, left=start, height=0.55,
                  color=fill, edgecolor=SURFACE, linewidth=2)
        axes.text(start + length / 2, index, f"{length:g} oy",
                  va="center", ha="center", fontsize=8.5, color=_on_fill(fill))

    axes.set_yticks(list(range(len(rows))))
    axes.set_yticklabels([name for name, _, _ in rows], fontsize=9)
    axes.invert_yaxis()
    axes.grid(axis="x", color=GRID, linewidth=1)
    axes.set_axisbelow(True)
    axes.spines["left"].set_visible(False)
    axes.set_xlabel("oy", fontsize=9, color=INK_SOFT)
    _title(axes, title)
    return _save(figure, work_dir)


def timeline_milestones(stages: list, title: str, work_dir: str, palette=None) -> str:
    """Vaqt chizig'i — belgilar chiziqda, nomlar navbatma-navbat yuqori/quyi."""
    palette = _palette(palette)
    rows = _stage_rows(stages)

    figure, axes = _new_figure(3.8)
    span = max(start + length for _, start, length in rows)
    axes.hlines(0, 0, span, color=GRID, linewidth=3)

    for index, (name, start, length) in enumerate(rows):
        centre = start + length / 2
        fill = palette.categorical[index % len(palette.categorical)]
        above = index % 2 == 0
        offset = 0.34 if above else -0.34
        axes.plot([centre, centre], [0, offset * 0.6], color=GRID, linewidth=1.2)
        axes.scatter(centre, 0, s=190, color=fill, zorder=3,
                     edgecolor=SURFACE, linewidth=2.4)
        axes.text(centre, offset, f"{name}\n{length:g} oy",
                  ha="center", va="bottom" if above else "top",
                  fontsize=8.5, color=INK)

    axes.set_ylim(-0.95, 0.95)
    axes.set_xlim(-span * 0.05, span * 1.05)
    axes.yaxis.set_visible(False)
    for side in ("left", "bottom"):
        axes.spines[side].set_visible(False)
    axes.set_xlabel("oy", fontsize=9, color=INK_SOFT)
    _title(axes, title)
    return _save(figure, work_dir)


def timeline_steps(stages: list, title: str, work_dir: str, palette=None) -> str:
    """Zinapoya — har bosqich oldingisining ustiga qo'yiladi."""
    palette = _palette(palette)
    rows = _stage_rows(stages)

    figure, axes = _new_figure(max(3.0, 0.5 * len(rows) + 1.2))
    # Ustun uzunligi bosqich davomiyligini bildiradi: tartib raqamini
    # uzunlik bilan ko'rsatish o'quvchiga yolg'on ma'lumot berardi.
    longest = max(length for _, _, length in rows)
    for index, (name, _, length) in enumerate(rows):
        fill = palette.ramp[min(index, len(palette.ramp) - 1)]
        axes.barh(len(rows) - index - 1, length, height=0.62,
                  color=fill, edgecolor=SURFACE, linewidth=2)
        axes.text(length + longest * 0.03, len(rows) - index - 1,
                  f"{name} · {length:g} oy", va="center", ha="left",
                  fontsize=9, color=INK)

    axes.set_xlim(0, longest * 2.9)
    axes.xaxis.set_visible(False)
    axes.yaxis.set_visible(False)
    for side in ("left", "bottom"):
        axes.spines[side].set_visible(False)
    _title(axes, title)
    return _save(figure, work_dir)


# ══════════════════════════════════════════════════════════════ risklar

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


def _risk_rows(risks: list) -> list:
    rows = [
        (number, _shorten(str(risk.get("risk") or risk.get("name") or ""), 22),
         _level(risk.get("likelihood")), _level(risk.get("impact")))
        for number, risk in enumerate(risks[:9], start=1)
    ]
    if not rows:
        raise ValueError("risk yo'q")
    return rows


_RISK_AXIS = ["Past", "O'rta", "Yuqori"]


def risk_matrix(risks: list, title: str, work_dir: str, palette=None) -> str:
    """Ehtimollik × ta'sir matritsasi.

    Rang xavf darajasini bildiradi, lekin uni yolg'iz tashlab qo'ymaydi:
    har katakda risk raqami turadi va ro'yxat pastda beriladi. Status
    ranglari palitra bilan aylanmaydi — ular ma'no tashiydi.
    """
    rows = _risk_rows(risks)
    figure, axes = _new_figure(4.0)

    fills = {}
    for x in range(3):
        for y in range(3):
            severity = (x + 1) * (y + 1)
            tier = 1 if severity <= 2 else 2 if severity <= 4 else 3 if severity <= 6 else 4
            fills[(x, y)] = STATUS[tier]
            axes.add_patch(Rectangle((x, y), 1, 1, facecolor=STATUS[tier],
                                     edgecolor=SURFACE, linewidth=3))

    for number, _, likelihood, impact in rows:
        fill = fills[(likelihood - 1, impact - 1)]
        axes.text(likelihood - 0.5, impact - 0.5, str(number),
                  ha="center", va="center", fontsize=13,
                  color=_on_fill(fill), fontweight="bold")

    _risk_axes(axes, 0, 3, [0.5, 1.5, 2.5])
    for side in ("left", "bottom"):
        axes.spines[side].set_visible(False)
    _title(axes, title)
    return _save(figure, work_dir)


def risk_bubble(risks: list, title: str, work_dir: str, palette=None) -> str:
    """Pufakchali XY — har risk o'z rangida, raqami pufakcha ichida."""
    palette = _palette(palette)
    rows = _risk_rows(risks)

    figure, axes = _new_figure(4.2)
    for index, (number, _, likelihood, impact) in enumerate(rows):
        fill = palette.categorical[index % len(palette.categorical)]
        # Pufakcha kattaligi og'irlikni (ehtimollik × ta'sir) bildiradi.
        size = 260 + 150 * (likelihood * impact)
        axes.scatter(likelihood, impact, s=size, color=fill, alpha=0.8,
                     edgecolor=SURFACE, linewidth=2, zorder=3)
        axes.text(likelihood, impact, str(number), ha="center", va="center",
                  fontsize=10, color=_on_fill(fill), fontweight="bold", zorder=4)

    axes.grid(color=GRID, linewidth=0.9)
    axes.set_axisbelow(True)
    _risk_axes(axes, 0.4, 3.6, [1, 2, 3])
    _title(axes, title)
    return _save(figure, work_dir)


def risk_radar(risks: list, title: str, work_dir: str, palette=None) -> str:
    """Radar — risklar og'irligi bo'yicha profil."""
    palette = _palette(palette)
    rows = _risk_rows(risks)[:7]
    if len(rows) < 3:
        # Uch nuqtadan kam radar shakl hosil qilmaydi.
        return risk_bubble(risks, title, work_dir, palette)

    labels = [_shorten(name, 14) or str(number) for number, name, _, _ in rows]
    values = [likelihood * impact for _, _, likelihood, impact in rows]

    figure = plt.figure(figsize=(_FIGSIZE[0], 4.8), dpi=_DPI)
    figure.patch.set_facecolor(SURFACE)
    axes = figure.add_subplot(polar=True)
    figure.subplots_adjust(left=0.26, right=0.74, top=0.82, bottom=0.14)
    axes.set_facecolor(SURFACE)

    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    closed = angles + angles[:1]
    series = values + values[:1]

    axes.plot(closed, series, color=palette.ramp[3], linewidth=2)
    axes.fill(closed, series, color=palette.ramp[1], alpha=0.45)
    axes.set_xticks(angles)
    axes.set_xticklabels(labels, fontsize=8, color=INK_SOFT)
    # Yorliqlar chizma chetiga tegmasin — uzun o'zbekcha nomlar kesilardi.
    axes.tick_params(axis="x", pad=18)
    axes.set_yticks([3, 6, 9])
    axes.set_ylim(0, 10.5)   # tashqi halqa bilan yorliq orasida joy qolsin
    # Radial yorliqlarni ma'lumot ko'p bo'lgan tomondan uzoqlashtiramiz.
    axes.set_rlabel_position(180 / max(len(labels), 1))
    axes.tick_params(colors=INK_SOFT, labelsize=8)
    axes.grid(color=GRID)
    axes.spines["polar"].set_color(GRID)
    axes.set_title(title, fontsize=11, color=INK, loc="left", pad=18)
    return _save(figure, work_dir)


def _risk_axes(axes, low, high, ticks):
    axes.set_xlim(low, high)
    axes.set_ylim(low, high)
    axes.set_xticks(ticks)
    axes.set_yticks(ticks)
    axes.set_xticklabels(_RISK_AXIS, fontsize=9)
    axes.set_yticklabels(_RISK_AXIS, fontsize=9)
    axes.set_xlabel("Ehtimolligi", fontsize=9, color=INK_SOFT)
    axes.set_ylabel("Ta'siri", fontsize=9, color=INK_SOFT)


def _title(axes, title: str):
    axes.set_title(title, fontsize=11, color=INK, loc="left", pad=12)


def render_formula(latex: str, work_dir: str) -> str:
    """Formulani matematik yozuv sifatida chizadi."""
    with _figure_guard():
        figure = plt.figure(figsize=(6.4, 0.9), dpi=_DPI)
        figure.patch.set_facecolor(SURFACE)
        figure.text(0.02, 0.45, f"${latex}$", fontsize=17, color=INK, va="center")
        return _save(figure, work_dir)


# ══════════════════════════════════════════════════════════ shakl tanlash

_DRAWERS = {
    ("budget", "bar"): budget_bar,
    ("budget", "lollipop"): budget_lollipop,
    ("budget", "donut"): budget_donut,
    ("budget", "waterfall"): budget_waterfall,
    ("timeline", "gantt"): gantt,
    ("timeline", "milestones"): timeline_milestones,
    ("timeline", "steps"): timeline_steps,
    ("risks", "matrix"): risk_matrix,
    ("risks", "bubble"): risk_bubble,
    ("risks", "radar"): risk_radar,
    ("forecast", "line"): forecast_line,
    ("forecast", "area"): forecast_area,
    ("forecast", "column"): forecast_column,
}

_FALLBACK = {"budget": budget_bar, "timeline": gantt,
             "risks": risk_matrix, "forecast": forecast_line}


def draw(artifact: str, form: str, data: dict, title: str, work_dir: str,
         palette=None, unit: str = "") -> str:
    """Artefakt va tanlangan shakl bo'yicha chizmani chizadi."""
    drawer = _DRAWERS.get((artifact, form)) or _FALLBACK.get(artifact)
    if drawer is None:
        raise ValueError(f"chizma shakli yo'q: {artifact}/{form}")

    with _figure_guard():
        if artifact == "budget":
            return drawer(data.get("items") or [], title, work_dir, palette)
        if artifact == "timeline":
            return drawer(data.get("stages") or [], title, work_dir, palette)
        if artifact == "risks":
            return drawer(data.get("risks") or [], title, work_dir, palette)
        return drawer(data.get("points") or [], title, unit, work_dir, palette)
