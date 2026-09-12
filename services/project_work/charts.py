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
import matplotlib.patheffects as path_effects
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter, ScalarFormatter

from . import palettes
from .palettes import GRID, INK, INK_SOFT, SURFACE, Palette

logger = logging.getLogger(__name__)

_FIGSIZE = (7.6, 4.2)
_DPI = 150

# Chizma ichidagi yozuvlar. Hujjat rus yoki ingliz tilida bo'lsa, diagramma
# ham o'sha tilda bo'lishi kerak — ilgari bu so'zlar kodda o'zbekcha qotib
# qolgan edi va ruscha loyiha ishida "Kirim / Chiqim" deb chiqardi.
_WORDS = {
    "month":      {"uz": "oy", "ru": "мес.", "en": "month"},
    "total":      {"uz": "jami", "ru": "всего", "en": "total"},
    "low":        {"uz": "Past", "ru": "Низкая", "en": "Low"},
    "medium":     {"uz": "O'rta", "ru": "Средняя", "en": "Medium"},
    "high":       {"uz": "Yuqori", "ru": "Высокая", "en": "High"},
    "likelihood": {"uz": "Ehtimolligi", "ru": "Вероятность", "en": "Likelihood"},
    "impact":     {"uz": "Ta'siri", "ru": "Влияние", "en": "Impact"},
    "revenue":    {"uz": "Tushum", "ru": "Выручка", "en": "Revenue"},
    "total_cost": {"uz": "Umumiy xarajat", "ru": "Общие затраты", "en": "Total cost"},
    "fixed_cost": {"uz": "Doimiy xarajat", "ru": "Постоянные затраты", "en": "Fixed cost"},
    "fixed":      {"uz": "Doimiy", "ru": "Постоянные", "en": "Fixed"},
    "variable":   {"uz": "O'zgaruvchi", "ru": "Переменные", "en": "Variable"},
    "plan":       {"uz": "reja", "ru": "план", "en": "plan"},
    "breakeven":  {"uz": "zararsizlik", "ru": "безубыточность", "en": "break-even"},
    "profit":     {"uz": "foyda", "ru": "прибыль", "en": "profit"},
    "inflow":     {"uz": "Kirim", "ru": "Поступления", "en": "Inflow"},
    "outflow":    {"uz": "Chiqim", "ru": "Расходы", "en": "Outflow"},
    "cumulative": {"uz": "To'plangan oqim", "ru": "Накопленный поток",
                   "en": "Cumulative flow"},
    "payback":    {"uz": "qoplanish", "ru": "окупаемость", "en": "payback"},
    "cum_share":  {"uz": "to'plangan, %", "ru": "накоплено, %", "en": "cumulative, %"},
    "volume":     {"uz": "hajm", "ru": "объём", "en": "volume"},
    "customer":   {"uz": "mijoz", "ru": "клиент", "en": "customer"},
}


def _w(language: str, key: str) -> str:
    words = _WORDS[key]
    return words.get(language, words["uz"])



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


_MILLION_WORD = {"uz": "mln", "ru": "млн", "en": "m"}


def _format(value: float, language: str = "uz") -> str:
    """Sonni yorliqqa tayyorlaydi: 240 000 000 → "240 mln", 1800 → "1 800".

    Faqat milliondan katta sonlar qisqartiriladi. Minglar qisqartilmaydi:
    1800 mijozni "2 ming" deb yozish raqamni buzadi — mijoz jadvalda 1 800
    ni ko'radi-yu, diagrammada boshqa sonni ko'radi.

    Ishora alohida ajratiladi, aks holda manfiy millionlar qisqarmay
    "-190000000" bo'lib chiqardi. Qisqartma so'zi hujjat tilida bo'ladi.
    """
    sign = "−" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000:
        word = _MILLION_WORD.get(language, "mln")
        return sign + f"{value / 1_000_000:.1f} {word}".replace(".0 ", " ")
    return sign + f"{round(value):,}".replace(",", " ")


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


def _compact_ticks(figure, language: str) -> None:
    """Raqamli o'qlardagi yorliqlarni qisqartiradi.

    matplotlib katta sonlarni burchakdagi "1e8" ko'paytuvchisi bilan
    ko'rsatadi — ilmiy yozuv loyiha ishida g'alati ko'rinadi va o'quvchi
    ustun qiymatini o'qiy olmaydi.

    Faqat sonli o'qlar tegiladi: kategoriya yorliqlari (bosqich nomlari,
    davrlar) boshqa formatlagichda turadi va ularga tegilmaydi.
    """
    for axes in figure.axes:
        for axis in (axes.xaxis, axes.yaxis):
            if not isinstance(axis.get_major_formatter(), ScalarFormatter):
                continue
            # Faqat million va undan yuqori qiymatlarda: "2 ming" degan
            # yorliq 2000 dan yomonroq o'qiladi, "250 mln" esa 2.5e8 dan
            # ancha yaxshi.
            span = max((abs(tick) for tick in axis.get_ticklocs()), default=0)
            if span >= 1_000_000:
                axis.set_major_formatter(
                    FuncFormatter(lambda value, _pos: _format(value, language)))


def _save(figure, work_dir: str, language: str = "uz") -> str:
    _compact_ticks(figure, language)
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


def budget_bar(rows: list, title: str, work_dir: str,
               palette=None, language: str = "uz") -> str:
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
                  bar.get_y() + bar.get_height() / 2, _format(value, language),
                  va="center", ha="left", fontsize=9, color=INK)
    _title(axes, title)
    return _save(figure, work_dir, language)


def budget_lollipop(rows: list, title: str, work_dir: str,
                    palette=None, language: str = "uz") -> str:
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
        axes.text(value + max(values) * 0.025, index, _format(value, language),
                  va="center", ha="left", fontsize=9, color=INK)
    _title(axes, title)
    return _save(figure, work_dir, language)


def budget_donut(rows: list, title: str, work_dir: str,
                 palette=None, language: str = "uz") -> str:
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
    axes.text(0, 0, _format(sum(values), language), ha="center", va="center",
              fontsize=13, color=INK, fontweight="bold")
    axes.set_title(title, fontsize=11, color=INK, loc="left", pad=12)
    return _save(figure, work_dir, language)


def budget_waterfall(rows: list, title: str, work_dir: str,
                     palette=None, language: str = "uz") -> str:
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
        axes.text(index, bottom + amount, _format(amount, language), ha="center",
                  va="bottom", fontsize=8, color=INK_SOFT)
        if index < len(items) - 1:
            axes.plot([index + 0.31, index + 0.69], [bottom + amount] * 2,
                      color=INK_SOFT, linewidth=0.9, linestyle=(0, (3, 3)), zorder=1)
        bottom += amount

    axes.bar(len(items), total, width=0.62, color=palette.ramp[-1],
             edgecolor=SURFACE, linewidth=2)
    axes.text(len(items), total, _format(total, language), ha="center", va="bottom",
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
    return _save(figure, work_dir, language)


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


def forecast_line(points: list, title: str, unit: str, work_dir: str,
                  palette=None, language: str = "uz") -> str:
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
    return _save(figure, work_dir, language)


def forecast_area(points: list, title: str, unit: str, work_dir: str,
                  palette=None, language: str = "uz") -> str:
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
    return _save(figure, work_dir, language)


def forecast_column(points: list, title: str, unit: str, work_dir: str,
                    palette=None, language: str = "uz") -> str:
    """Ustunlar — davrlar aniq ajralib turadi, oxirgisi prognoz sifatida ochroq."""
    palette = _palette(palette)
    periods, values = _forecast_series(points)

    figure, axes = _new_figure()
    fills = [palette.ramp[2]] * len(values)
    fills[-1] = palette.ramp[0]     # oxirgi davr — prognoz, shuning uchun ochroq
    axes.bar(periods, values, width=0.6, color=fills, edgecolor=SURFACE, linewidth=2)
    for index, value in enumerate(values):
        axes.text(index, value, _format(value, language), ha="center", va="bottom",
                  fontsize=8.5, color=INK)
    axes.set_ylim(0, max(values) * 1.18)
    _time_axis(axes, unit)
    _title(axes, title)
    return _save(figure, work_dir, language)


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


def gantt(stages: list, title: str, work_dir: str,
          palette=None, language: str = "uz") -> str:
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
    axes.set_xlabel(_w(language, "month"), fontsize=9, color=INK_SOFT)
    _title(axes, title)
    return _save(figure, work_dir, language)


def timeline_milestones(stages: list, title: str, work_dir: str,
                        palette=None, language: str = "uz") -> str:
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
    axes.set_xlabel(_w(language, "month"), fontsize=9, color=INK_SOFT)
    _title(axes, title)
    return _save(figure, work_dir, language)


def timeline_steps(stages: list, title: str, work_dir: str,
                   palette=None, language: str = "uz") -> str:
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
    return _save(figure, work_dir, language)


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


def _risk_levels(language: str) -> list:
    return [_w(language, "low"), _w(language, "medium"), _w(language, "high")]


def risk_bubble(risks: list, title: str, work_dir: str,
                palette=None, language: str = "uz") -> str:
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
    _risk_axes(axes, 0.4, 3.6, [1, 2, 3], language)
    _title(axes, title)
    return _save(figure, work_dir, language)


def risk_radar(risks: list, title: str, work_dir: str,
               palette=None, language: str = "uz") -> str:
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
    return _save(figure, work_dir, language)


def _risk_axes(axes, low, high, ticks, language: str = "uz"):
    axes.set_xlim(low, high)
    axes.set_ylim(low, high)
    axes.set_xticks(ticks)
    axes.set_yticks(ticks)
    levels = _risk_levels(language)
    axes.set_xticklabels(levels, fontsize=9)
    axes.set_yticklabels(levels, fontsize=9)
    axes.set_xlabel(_w(language, "likelihood"), fontsize=9, color=INK_SOFT)
    axes.set_ylabel(_w(language, "impact"), fontsize=9, color=INK_SOFT)


def _title(axes, title: str):
    axes.set_title(title, fontsize=11, color=INK, loc="left", pad=12)


def render_formula(latex: str, work_dir: str) -> str:
    """Formulani matematik yozuv sifatida chizadi."""
    with _figure_guard():
        figure = plt.figure(figsize=(6.4, 0.9), dpi=_DPI)
        figure.patch.set_facecolor(SURFACE)
        figure.text(0.02, 0.45, f"${latex}$", fontsize=17, color=INK, va="center")
        return _save(figure, work_dir)


# ══════════════════════════════════════════════════════ marketing prognozi
#
# Sotuv prognozi ikki o'lchovli: nechta sotiladi va qancha pul keladi.
# Ikkisi turli birlikda, shuning uchun ustun va chiziq ikkita o'qda turadi —
# bitta o'qqa siqilsa, kichik son ko'rinmay ketardi.

def _periods(data: dict):
    rows = [p for p in (data.get("periods") or []) if str(p.get("period", "")).strip()]
    if len(rows) < 2:
        raise ValueError("prognoz uchun kamida ikkita davr kerak")
    labels = [_shorten(str(p.get("period")), 14) for p in rows]
    units = [_number(p.get("units")) for p in rows]
    revenue = [_number(p.get("revenue")) for p in rows]
    return labels, units, revenue


def _second_axis(axes, label: str):
    """O'ng o'q — birinchisining to'rini takrorlamasin, faqat o'z yorliqlari."""
    twin = axes.twinx()
    twin.set_facecolor("none")
    for side in ("top", "left"):
        twin.spines[side].set_visible(False)
    twin.spines["right"].set_color(GRID)
    twin.tick_params(colors=INK_SOFT, labelsize=9, length=0)
    if label:
        twin.set_ylabel(label, fontsize=9, color=INK_SOFT)
    return twin


def marketing_sales_columns(data: dict, title: str, work_dir: str,
                            palette=None, language: str = "uz") -> str:
    """Sotuv hajmi ustunlarda, tushum chiziqda — klassik sotuv prognozi."""
    palette = _palette(palette)
    labels, units, revenue = _periods(data)

    figure, axes = _new_figure()
    axes.bar(labels, units, width=0.58, color=palette.ramp[1],
             edgecolor=SURFACE, linewidth=2,
             label=_sales_label(data.get("unit"), language, "volume"))
    axes.grid(axis="y", color=GRID, linewidth=1)
    axes.set_axisbelow(True)
    axes.spines["left"].set_visible(False)
    axes.set_ylim(0, max(units + [1]) * 1.22)
    if data.get("unit"):
        axes.set_ylabel(str(data["unit"]), fontsize=9, color=INK_SOFT)

    twin = _second_axis(axes, str(data.get("money_unit") or ""))
    twin.plot(labels, revenue, color=palette.ramp[4], linewidth=2.4,
              marker="o", markersize=7, markerfacecolor=palette.ramp[4],
              markeredgecolor=SURFACE, markeredgewidth=2,
              label=_sales_label(data.get("money_unit"), language, "revenue"))
    twin.set_ylim(0, max(revenue + [1]) * 1.3)
    twin.annotate(_format(revenue[-1], language), (len(revenue) - 1, revenue[-1]),
                  textcoords="offset points", xytext=(-6, 12), ha="right",
                  fontsize=10, color=INK, fontweight="bold")

    _merged_legend(axes, twin)
    _title(axes, title)
    return _save(figure, work_dir, language)


def marketing_sales_area(data: dict, title: str, work_dir: str,
                         palette=None, language: str = "uz") -> str:
    """Tushum maydoni — o'sishning to'planishi ko'zga tashlanadi."""
    palette = _palette(palette)
    labels, units, revenue = _periods(data)

    figure, axes = _new_figure()
    axes.fill_between(labels, revenue, color=palette.ramp[1], alpha=0.5, linewidth=0)
    axes.plot(labels, revenue, color=palette.ramp[3], linewidth=2.4,
              marker="o", markersize=6, markerfacecolor=palette.ramp[3],
              markeredgecolor=SURFACE, markeredgewidth=2,
              label=_sales_label(data.get("money_unit"), language, "revenue"))
    axes.grid(axis="y", color=GRID, linewidth=1)
    axes.set_axisbelow(True)
    axes.spines["left"].set_visible(False)
    axes.set_ylim(0, max(revenue + [1]) * 1.22)
    if data.get("money_unit"):
        axes.set_ylabel(str(data["money_unit"]), fontsize=9, color=INK_SOFT)

    twin = _second_axis(axes, str(data.get("unit") or ""))
    twin.plot(labels, units, color=INK_SOFT, linewidth=1.8, linestyle="--",
              marker="s", markersize=5, markerfacecolor=SURFACE,
              label=_sales_label(data.get("unit"), language, "volume"))
    twin.set_ylim(0, max(units + [1]) * 1.32)

    _merged_legend(axes, twin)
    _title(axes, title)
    return _save(figure, work_dir, language)


def marketing_channels(data: dict, title: str, work_dir: str,
                       palette=None, language: str = "uz") -> str:
    """Kanallar: nechta mijoz keltirdi va bir mijoz qanchaga tushdi."""
    palette = _palette(palette)
    rows = [c for c in (data.get("channels") or []) if str(c.get("name", "")).strip()]
    pairs = [(_shorten(str(c.get("name")), 26), _number(c.get("customers")),
              _number(c.get("cost_per_customer")) or
              (_number(c.get("budget")) / _number(c.get("customers"))
               if _number(c.get("customers")) else 0.0))
             for c in rows]
    pairs = [p for p in pairs if p[1] > 0]
    if not pairs:
        # Kanal ma'lumoti bo'sh bo'lsa sotuv prognoziga qaytamiz — bo'lim
        # diagrammasiz qolmasin.
        return marketing_sales_columns(data, title, work_dir, palette, language)

    pairs.sort(key=lambda p: p[1])
    names = [p[0] for p in pairs]
    customers = [p[1] for p in pairs]
    per_customer = [p[2] for p in pairs]

    figure, axes = _new_figure(height=max(3.0, 0.62 * len(pairs) + 1.3))
    positions = np.arange(len(pairs))
    fills = palettes.shades(palette, customers)
    axes.barh(positions, customers, height=0.62, color=fills,
              edgecolor=SURFACE, linewidth=1.5)
    axes.set_yticks(positions)
    axes.set_yticklabels(names, fontsize=9.5)
    axes.set_xlim(0, max(customers) * 1.3)
    axes.grid(axis="x", color=GRID, linewidth=1)
    axes.set_axisbelow(True)
    axes.spines["bottom"].set_visible(False)

    for position, count, cost in zip(positions, customers, per_customer):
        label = _format(count, language)
        if cost:
            label += f"  ({_format(cost, language)}/{_w(language, 'customer')})"
        axes.text(count + max(customers) * 0.02, position, label,
                  va="center", fontsize=9, color=INK_SOFT)

    _title(axes, title)
    return _save(figure, work_dir, language)


def _sales_label(unit, language: str, key: str) -> str:
    """Legenda yorlig'i: ma'no so'zi va qavs ichida birlik.

    Faqat birlikni yozish yetmaydi — "tonna" degan legenda nimaning
    tonnasi ekanini aytmaydi.
    """
    word = _w(language, key)
    unit = " ".join(str(unit or "").split())
    return f"{word} ({_shorten(unit, 14)})" if unit else word


def _merged_legend(axes, twin) -> None:
    """Ikki o'qdagi belgilarni bitta legendaga yig'adi."""
    handles, labels = axes.get_legend_handles_labels()
    extra_handles, extra_labels = twin.get_legend_handles_labels()
    if not handles and not extra_handles:
        return
    axes.legend(handles + extra_handles, labels + extra_labels,
                fontsize=9, frameon=False, loc="upper left",
                bbox_to_anchor=(0, 1.02), ncols=2)


# ══════════════════════════════════════════════════════ chiqimlar tarkibi

def _cost_rows(data: dict):
    rows = [(
        _shorten(str(item.get("name", "")), 28),
        _number(item.get("amount")),
        bool(item.get("fixed")),
    ) for item in (data.get("items") or [])]
    rows = [row for row in rows if row[1] > 0]
    if not rows:
        raise ValueError("chiqim moddalari bo'sh")
    return sorted(rows, key=lambda row: row[1], reverse=True)


def costs_donut(data: dict, title: str, work_dir: str,
                palette=None, language: str = "uz") -> str:
    """Ulushlar halqasi — qaysi modda pulni yeyayotgani darhol ko'rinadi."""
    palette = _palette(palette)
    rows = _cost_rows(data)[:7]
    amounts = [amount for _n, amount, _f in rows]
    total = sum(amounts)

    figure, axes = plt.subplots(figsize=(_FIGSIZE[0], 4.4), dpi=_DPI)
    figure.patch.set_facecolor(SURFACE)
    axes.set_facecolor(SURFACE)
    wedges, _texts = axes.pie(
        amounts,
        colors=[palette.categorical[i % len(palette.categorical)] for i in range(len(rows))],
        startangle=90, counterclock=False,
        wedgeprops=dict(width=0.42, edgecolor=SURFACE, linewidth=2),
    )
    axes.axis("equal")
    # Markazda yig'indi: halqa ulushni ko'rsatadi, umumiy son esa shu yerda.
    axes.text(0, 0.08, _format(total, language), ha="center", va="center",
              fontsize=16, fontweight="bold", color=INK)
    axes.text(0, -0.16, _w(language, "total"), ha="center", va="center",
              fontsize=9.5, color=INK_SOFT)

    axes.legend(
        wedges,
        [f"{name} — {amount / total * 100:.0f}%" for name, amount, _f in rows],
        fontsize=9, frameon=False, loc="center left", bbox_to_anchor=(1.0, 0.5),
    )
    axes.set_title(title, fontsize=11, color=INK, loc="left", pad=10)
    return _save(figure, work_dir, language)


def costs_pareto(data: dict, title: str, work_dir: str,
                 palette=None, language: str = "uz") -> str:
    """Pareto: ustunlar kamayish tartibida, chiziq to'plangan ulush.

    Chiqim tahlilida asosiy savol "qaysi ikki-uch modda xarajatning yarmini
    tashkil qiladi" — to'plangan chiziq shuni bir qarashda ko'rsatadi.
    """
    palette = _palette(palette)
    rows = _cost_rows(data)[:7]
    names = [name for name, _a, _f in rows]
    amounts = [amount for _n, amount, _f in rows]
    total = sum(amounts)

    figure, axes = _new_figure(height=4.4)
    positions = np.arange(len(rows))
    axes.bar(positions, amounts, width=0.6, color=palette.ramp[2],
             edgecolor=SURFACE, linewidth=2)
    axes.set_xticks(positions)
    axes.set_xticklabels([_wrap_label(name, 16) for name in names], fontsize=8.5)
    axes.grid(axis="y", color=GRID, linewidth=1)
    axes.set_axisbelow(True)
    axes.spines["left"].set_visible(False)
    axes.set_ylim(0, max(amounts) * 1.2)
    for position, amount in zip(positions, amounts):
        axes.text(position, amount, _format(amount, language), ha="center", va="bottom",
                  fontsize=8.5, color=INK)

    cumulative, running = [], 0.0
    for amount in amounts:
        running += amount
        cumulative.append(running / total * 100)
    twin = _second_axis(axes, _w(language, "cum_share"))
    twin.plot(positions, cumulative, color=palettes.STATUS[4], linewidth=2,
              marker="o", markersize=5, markerfacecolor=SURFACE, markeredgewidth=1.8)
    twin.set_ylim(0, 112)
    twin.axhline(80, color=INK_SOFT, linewidth=1, linestyle=":")

    _title(axes, title)
    return _save(figure, work_dir, language)


def costs_fixed_variable(data: dict, title: str, work_dir: str,
                         palette=None, language: str = "uz") -> str:
    """Doimiy va o'zgaruvchi chiqim — ikkita yig'ma ustun.

    Bu ajratish bo'limning mag'zi: o'zgaruvchi ulush katta bo'lsa hajm
    tushganda xarajat ham tushadi, doimiy ulush katta bo'lsa tushmaydi.
    """
    palette = _palette(palette)
    rows = _cost_rows(data)
    groups = [
        (_w(language, "fixed"), [row for row in rows if row[2]], palette.ramp[3]),
        (_w(language, "variable"), [row for row in rows if not row[2]],
         palette.ramp[1]),
    ]
    groups = [group for group in groups if group[1]]
    if len(groups) < 2:
        # Model hammasini bir turga qo'ygan — ajratishning ma'nosi qolmaydi.
        return costs_donut(data, title, work_dir, palette, language)

    figure, axes = _new_figure(height=4.2)
    for index, (label, members, base) in enumerate(groups):
        bottom = 0.0
        for order, (name, amount, _fixed) in enumerate(members):
            shade = palette.ramp[min(len(palette.ramp) - 1, 1 + order % 4)] \
                if base == palette.ramp[1] else palette.ramp[max(0, 4 - order % 4)]
            axes.bar(index, amount, bottom=bottom, width=0.5, color=shade,
                     edgecolor=SURFACE, linewidth=2)
            if amount > sum(a for _n, a, _f in rows) * 0.05:
                axes.text(index, bottom + amount / 2, _shorten(name, 20),
                          ha="center", va="center", fontsize=8,
                          color=_on_fill(shade))
            bottom += amount
        axes.text(index, bottom, _format(bottom, language), ha="center", va="bottom",
                  fontsize=10, fontweight="bold", color=INK)

    axes.set_xticks(range(len(groups)))
    axes.set_xticklabels([group[0] for group in groups], fontsize=10)
    axes.set_xlim(-0.6, len(groups) - 0.4)
    axes.grid(axis="y", color=GRID, linewidth=1)
    axes.set_axisbelow(True)
    axes.spines["left"].set_visible(False)
    _title(axes, title)
    return _save(figure, work_dir, language)


# ══════════════════════════════════════════════════════ zararsizlik nuqtasi

def _breakeven_figures(data: dict):
    fixed = _number(data.get("fixed"))
    price = _number(data.get("price"))
    variable = _number(data.get("variable"))
    if fixed <= 0 or price <= variable:
        raise ValueError("zararsizlik nuqtasi hisoblanmaydi")
    point = fixed / (price - variable)
    planned = _number(data.get("planned")) or point * 1.3
    return fixed, price, variable, point, planned


def breakeven_lines(data: dict, title: str, work_dir: str,
                    palette=None, language: str = "uz") -> str:
    """Tushum va xarajat chiziqlari kesishgan joy — zararsizlik nuqtasi."""
    palette = _palette(palette)
    fixed, price, variable, point, planned = _breakeven_figures(data)

    top = max(point, planned) * 1.35
    volumes = np.linspace(0, top, 120)
    revenue = price * volumes
    cost = fixed + variable * volumes

    figure, axes = _new_figure(height=4.3)
    axes.fill_between(volumes, revenue, cost, where=(cost >= revenue),
                      color=palettes.STATUS[4], alpha=0.13, linewidth=0)
    axes.fill_between(volumes, revenue, cost, where=(revenue > cost),
                      color=palettes.STATUS[1], alpha=0.13, linewidth=0)
    axes.plot(volumes, revenue, color=palette.ramp[3], linewidth=2.4, label=_w(language, "revenue"))
    axes.plot(volumes, cost, color=palettes.STATUS[3], linewidth=2.4,
              label=_w(language, "total_cost"))
    axes.axhline(fixed, color=INK_SOFT, linewidth=1.4, linestyle="--",
                 label=_w(language, "fixed_cost"))

    axes.scatter([point], [price * point], s=110, color=INK, zorder=5,
                 edgecolor=SURFACE, linewidth=2)
    axes.annotate(f"{_format(point, language)} {data.get('unit', '')}".strip(),
                  (point, price * point), textcoords="offset points",
                  xytext=(10, -16), fontsize=10, fontweight="bold", color=INK)
    if planned and abs(planned - point) > top * 0.04:
        axes.axvline(planned, color=palette.ramp[2], linewidth=1.2, linestyle=":")
        axes.annotate(_w(language, "plan"), (planned, price * top * 0.02),
                      textcoords="offset points", xytext=(5, 6),
                      fontsize=9, color=palette.ramp[3])

    axes.set_xlim(0, top)
    axes.set_ylim(0, max(revenue[-1], cost[-1]) * 1.08)
    axes.grid(color=GRID, linewidth=1)
    axes.set_axisbelow(True)
    axes.set_xlabel(str(data.get("unit") or _w(language, "volume")),
                    fontsize=9, color=INK_SOFT)
    axes.set_ylabel(str(data.get("money_unit") or ""), fontsize=9, color=INK_SOFT)
    axes.legend(fontsize=9, frameon=False, loc="upper left")
    _title(axes, title)
    return _save(figure, work_dir, language)


def breakeven_profit(data: dict, title: str, work_dir: str,
                     palette=None, language: str = "uz") -> str:
    """Foyda chizig'i nolni kesib o'tadi — xuddi shu nuqta, boshqa ko'rinishda."""
    palette = _palette(palette)
    fixed, price, variable, point, planned = _breakeven_figures(data)

    top = max(point, planned) * 1.35
    volumes = np.linspace(0, top, 120)
    profit = (price - variable) * volumes - fixed

    figure, axes = _new_figure(height=4.3)
    axes.fill_between(volumes, profit, 0, where=(profit < 0),
                      color=palettes.STATUS[4], alpha=0.16, linewidth=0)
    axes.fill_between(volumes, profit, 0, where=(profit >= 0),
                      color=palettes.STATUS[1], alpha=0.16, linewidth=0)
    axes.plot(volumes, profit, color=palette.ramp[3], linewidth=2.6)
    axes.axhline(0, color=INK_SOFT, linewidth=1.2)

    axes.scatter([point], [0], s=110, color=INK, zorder=5,
                 edgecolor=SURFACE, linewidth=2)
    axes.annotate(f"{_w(language, 'breakeven')}: {_format(point, language)} "
                  f"{data.get('unit', '')}".strip(),
                  (point, 0), textcoords="offset points", xytext=(10, 12),
                  fontsize=10, fontweight="bold", color=INK)
    if planned:
        planned_profit = (price - variable) * planned - fixed
        axes.scatter([planned], [planned_profit], s=90, color=palette.ramp[1],
                     zorder=5, edgecolor=SURFACE, linewidth=2)
        axes.annotate(f"{_w(language, 'plan')}: {_format(planned_profit, language)}",
                      (planned, planned_profit),
                      textcoords="offset points", xytext=(-8, 12), ha="right",
                      fontsize=9.5, color=palette.ramp[4])

    axes.set_xlim(0, top)
    axes.grid(color=GRID, linewidth=1)
    axes.set_axisbelow(True)
    axes.set_xlabel(str(data.get("unit") or _w(language, "volume")),
                    fontsize=9, color=INK_SOFT)
    axes.set_ylabel(f"{_w(language, 'profit')}, {data.get('money_unit', '')}".strip(", "),
                    fontsize=9, color=INK_SOFT)
    _title(axes, title)
    return _save(figure, work_dir, language)


# ══════════════════════════════════════════════════════════════ pul oqimi

def _cashflow_rows(data: dict):
    rows = [p for p in (data.get("periods") or []) if str(p.get("period", "")).strip()]
    if len(rows) < 2:
        raise ValueError("pul oqimi uchun kamida ikkita davr kerak")
    labels = [_shorten(str(p.get("period")), 12) for p in rows]
    income = [_number(p.get("income")) for p in rows]
    expense = [_number(p.get("expense")) for p in rows]
    cumulative, running = [], 0.0
    for money_in, money_out in zip(income, expense):
        running += money_in - money_out
        cumulative.append(running)
    return labels, income, expense, cumulative


def cashflow_bars(data: dict, title: str, work_dir: str,
                  palette=None, language: str = "uz") -> str:
    """Kirim yuqoriga, chiqim pastga, to'plangan oqim chiziqda."""
    palette = _palette(palette)
    labels, income, expense, cumulative = _cashflow_rows(data)

    figure, axes = _new_figure(height=4.3)
    positions = np.arange(len(labels))
    axes.bar(positions, income, width=0.56, color=palette.ramp[1],
             edgecolor=SURFACE, linewidth=2, label=_w(language, "inflow"))
    axes.bar(positions, [-value for value in expense], width=0.56,
             color=palettes.STATUS[3], edgecolor=SURFACE, linewidth=2,
             label=_w(language, "outflow"))
    axes.axhline(0, color=INK_SOFT, linewidth=1.2)
    axes.plot(positions, cumulative, color=INK, linewidth=2.2, marker="o",
              markersize=6, markerfacecolor=SURFACE, markeredgewidth=2,
              label=_w(language, "cumulative"))

    axes.set_xticks(positions)
    axes.set_xticklabels(labels, fontsize=9.5)
    axes.grid(axis="y", color=GRID, linewidth=1)
    axes.set_axisbelow(True)
    axes.spines["left"].set_visible(False)
    axes.set_ylabel(str(data.get("money_unit") or data.get("unit") or ""),
                    fontsize=9, color=INK_SOFT)
    _pad_limits(axes, income + [-value for value in expense] + cumulative)
    _breakeven_marker(axes, positions, cumulative, language)
    axes.legend(fontsize=9, frameon=False, loc="upper left", ncols=3,
                bbox_to_anchor=(0, 1.02))
    _title(axes, title)
    return _save(figure, work_dir, language)


def cashflow_waterfall(data: dict, title: str, work_dir: str,
                       palette=None, language: str = "uz") -> str:
    """Sharshara: har davr sof oqimi to'plangan qoldiqni qanday o'zgartiradi."""
    palette = _palette(palette)
    labels, income, expense, cumulative = _cashflow_rows(data)
    nets = [money_in - money_out for money_in, money_out in zip(income, expense)]

    figure, axes = _new_figure(height=4.3)
    positions = np.arange(len(labels))
    bottom = 0.0
    for position, net in zip(positions, nets):
        colour = palette.ramp[2] if net >= 0 else palettes.STATUS[3]
        axes.bar(position, net, bottom=bottom, width=0.56, color=colour,
                 edgecolor=SURFACE, linewidth=2)
        tip = bottom + net
        axes.text(position, tip,
                  _format(net, language) if net >= 0
                  else f"−{_format(-net, language)}",
                  ha="center", va="bottom" if net >= 0 else "top",
                  fontsize=9, color=INK)
        if position < len(positions) - 1:
            axes.plot([position + 0.28, position + 0.72], [tip, tip],
                      color=GRID, linewidth=1.2, linestyle="--")
        bottom = tip

    axes.axhline(0, color=INK_SOFT, linewidth=1.2)
    axes.set_xticks(positions)
    axes.set_xticklabels(labels, fontsize=9.5)
    axes.grid(axis="y", color=GRID, linewidth=1)
    axes.set_axisbelow(True)
    axes.spines["left"].set_visible(False)
    axes.set_ylabel(str(data.get("money_unit") or data.get("unit") or ""),
                    fontsize=9, color=INK_SOFT)
    # Yorliqlar ustun uchidan tashqarida turadi, shuning uchun o'qqa joy
    # qoldiriladi — aks holda birinchi ustunning raqami davr nomiga
    # yopishib qolardi.
    _pad_limits(axes, cumulative + [0])
    _breakeven_marker(axes, positions, cumulative, language)
    _title(axes, title)
    return _save(figure, work_dir, language)


def _pad_limits(axes, values) -> None:
    """Qiymatlar atrofida yorliqlar sig'adigan bo'sh joy qoldiradi."""
    if not values:
        return
    low, high = min(values), max(values)
    span = (high - low) or abs(high) or 1.0
    axes.set_ylim(low - span * 0.16, high + span * 0.16)


def _breakeven_marker(axes, positions, cumulative, language: str) -> None:
    """To'plangan oqim musbatga o'tgan davrni belgilaydi — qoplanish muddati."""
    for position, value in zip(positions, cumulative):
        if value < 0:
            continue
        # Nuqta o'qning yuqori chekkasiga yaqin bo'lsa yozuv sarlavhaga
        # chiqib ketardi — bunday holda u nuqtaning ostiga qo'yiladi.
        low, high = axes.get_ylim()
        near_top = value > low + (high - low) * 0.78
        axes.annotate(_w(language, "payback"), (position, value),
                      textcoords="offset points",
                      xytext=(0, -20) if near_top else (0, 18),
                      ha="center", fontsize=9, color=palettes.STATUS[1],
                      fontweight="bold",
                      # Yozuv ustun ustiga tushishi mumkin — ochiq hoshiya
                      # uni har qanday fonda o'qiladigan qiladi.
                      path_effects=[path_effects.withStroke(
                          linewidth=3, foreground=SURFACE)])
        return


# ══════════════════════════════════════════════════════════════ sxema

def structure_scheme(data: dict, title: str, work_dir: str,
                     palette=None, language: str = "uz") -> str:
    """Loyiha tuzilmasi sxemasi — bloklar va ularni bog'lovchi chiziqlar.

    Ilgari bu AI chizgan rasm edi: arzon modellar sxemadagi yozuvlarni
    buzib chizardi va natija o'qilmasdi. Endi sxema shu yerda chiziladi,
    ya'ni yozuvlar har doim to'g'ri va uslub hujjatning qolganiga mos.
    """
    palette = _palette(palette)
    root = _shorten(str(data.get("root") or title), 40)
    branches = [b for b in (data.get("branches") or []) if isinstance(b, dict)][:5]
    if len(branches) < 2:
        raise ValueError("sxema uchun kamida ikkita tarmoq kerak")

    columns = len(branches)

    # Balandlik eng chuqur tarmoqqa qarab olinadi: aks holda tarmoqlarda
    # bittadan element bo'lsa, rasm pastida katta bo'sh maydon qolardi.
    branch_y, branch_h, item_h, item_gap = 58.0, 12.0, 10.0, 3.5
    depth = max((len([i for i in (b.get("items") or [])][:3]) for b in branches),
                default=0)
    floor = branch_y - depth * (item_h + item_gap) - 4
    span = 100 - floor
    figure, axes = plt.subplots(
        figsize=(_FIGSIZE[0], max(2.9, 4.6 * span / 86.5)), dpi=_DPI)
    figure.patch.set_facecolor(SURFACE)
    axes.set_facecolor(SURFACE)
    axes.set_xlim(0, 100)
    axes.set_ylim(floor, 100)
    axes.axis("off")

    # Ildiz bloki
    root_w, root_h = 46, 13
    root_x, root_y = 50 - root_w / 2, 84
    _scheme_box(axes, root_x, root_y, root_w, root_h, palette.ramp[3], root, 11, bold=True)

    gap = 3.0
    col_w = (100 - gap * (columns - 1)) / columns

    for index, branch in enumerate(branches):
        hue = palette.categorical[index % len(palette.categorical)]
        col_x = index * (col_w + gap)
        centre = col_x + col_w / 2

        # Ildizdan tarmoqqa: vertikal + gorizontal ulanish
        axes.plot([50, 50], [root_y, root_y - 6], color=GRID, linewidth=1.6, zorder=1)
        axes.plot([50, centre], [root_y - 6, root_y - 6], color=GRID, linewidth=1.6, zorder=1)
        axes.plot([centre, centre], [root_y - 6, branch_y + branch_h],
                  color=GRID, linewidth=1.6, zorder=1)

        _scheme_box(axes, col_x, branch_y, col_w, branch_h, hue,
                    _shorten(str(branch.get("name", "")), 26), 9.5, bold=True)

        items = [str(i) for i in (branch.get("items") or [])][:3]
        for level, item in enumerate(items):
            item_y = branch_y - (level + 1) * (item_h + item_gap)
            axes.plot([centre, centre], [item_y + item_h, item_y + item_h + item_gap],
                      color=GRID, linewidth=1.2, zorder=1)
            _scheme_box(axes, col_x + col_w * 0.06, item_y, col_w * 0.88, item_h,
                        _tint(hue, 0.86), _shorten(item, 30), 8.5,
                        edge=hue, text_colour=INK)

    axes.set_title(title, fontsize=11, color=INK, loc="left", pad=12)
    return _save(figure, work_dir, language)


def _tint(hex_str: str, amount: float) -> str:
    """Rangni oqqa yaqinlashtiradi — ichki bloklar foni uchun."""
    h = (hex_str or "").lstrip("#")
    if len(h) != 6:
        return "#f2f2f2"
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    def mix(c):
        return int(round(c + (255 - c) * amount))
    return "#%02x%02x%02x" % (mix(r), mix(g), mix(b))


def _scheme_box(axes, x, y, w, h, fill, text, size, bold=False,
                edge=None, text_colour=None):
    """Yumaloq burchakli blok va uning ichidagi markazlashtirilgan matn."""
    axes.add_patch(FancyBboxPatch(
        (x + 1, y + 1), w - 2, h - 2,
        boxstyle="round,pad=0.6,rounding_size=2",
        facecolor=fill, edgecolor=edge or fill, linewidth=1.4, zorder=2,
    ))
    axes.text(x + w / 2, y + h / 2, _wrap_label(text, w),
              ha="center", va="center", fontsize=size,
              color=text_colour or _on_fill(fill),
              fontweight="bold" if bold else "normal", zorder=3)


def _wrap_label(text: str, width: float) -> str:
    """Blok eniga qarab matnni qatorlarga bo'ladi."""
    per_line = max(int(width * 0.42), 10)
    words, lines, current = str(text).split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if len(trial) <= per_line or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return "\n".join(lines[:3])


# ══════════════════════════════════════════════════════════ shakl tanlash

_DRAWERS = {
    ("budget", "bar"): budget_bar,
    ("budget", "lollipop"): budget_lollipop,
    ("budget", "donut"): budget_donut,
    ("budget", "waterfall"): budget_waterfall,
    ("timeline", "gantt"): gantt,
    ("timeline", "milestones"): timeline_milestones,
    ("timeline", "steps"): timeline_steps,
    ("risks", "bubble"): risk_bubble,
    ("scheme", "structure"): structure_scheme,
    ("risks", "radar"): risk_radar,
    ("forecast", "line"): forecast_line,
    ("forecast", "area"): forecast_area,
    ("forecast", "column"): forecast_column,
    ("marketing", "sales_columns"): marketing_sales_columns,
    ("marketing", "sales_area"): marketing_sales_area,
    ("marketing", "channels"): marketing_channels,
    ("costs", "donut"): costs_donut,
    ("costs", "pareto"): costs_pareto,
    ("costs", "fixed_variable"): costs_fixed_variable,
    ("breakeven", "lines"): breakeven_lines,
    ("breakeven", "profit"): breakeven_profit,
    ("cashflow", "bars"): cashflow_bars,
    ("cashflow", "waterfall"): cashflow_waterfall,
}

_FALLBACK = {"budget": budget_bar, "timeline": gantt, "scheme": structure_scheme,
             "risks": risk_bubble, "forecast": forecast_line,
             "marketing": marketing_sales_columns, "costs": costs_donut,
             "breakeven": breakeven_lines, "cashflow": cashflow_bars}

# Butun ma'lumot lug'atini oladigan artefaktlar: ularda bitta ro'yxat emas,
# bir nechta kalit ishlatiladi (davrlar, kanallar, narx, doimiy xarajat).
_WHOLE_DATA = {"scheme", "marketing", "costs", "breakeven", "cashflow"}


def draw(artifact: str, form: str, data: dict, title: str, work_dir: str,
         palette=None, unit: str = "", language: str = "uz") -> str:
    """Artefakt va tanlangan shakl bo'yicha chizmani chizadi."""
    drawer = _DRAWERS.get((artifact, form)) or _FALLBACK.get(artifact)
    if drawer is None:
        raise ValueError(f"chizma shakli yo'q: {artifact}/{form}")

    with _figure_guard():
        if artifact == "budget":
            return drawer(data.get("items") or [], title, work_dir, palette, language)
        if artifact == "timeline":
            return drawer(data.get("stages") or [], title, work_dir, palette, language)
        if artifact == "risks":
            return drawer(data.get("risks") or [], title, work_dir, palette, language)
        if artifact in _WHOLE_DATA:
            return drawer(data, title, work_dir, palette, language)
        return drawer(data.get("points") or [], title, unit, work_dir, palette, language)
