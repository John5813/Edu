"""Hujjatlarga qo'yiladigan diagrammalar — AI bergan ma'lumotdan chiziladi.

`services/project_work/charts.py` loyiha ishining aniq artefaktlariga
bog'langan (smeta satrlari, Gantt bosqichlari, risklar). Kurs ishida esa
mavzu har xil bo'ladi va AI o'zi "bu yerga chiziqli grafik kerak" deb
qaror qiladi, shuning uchun bu yerda umumiy chizuvchi turadi: kategoriyalar
va bir nechta qator — qolganini shakl turi hal qiladi.

Ranglar loyiha ishidagi palitradan olinadi, ya'ni bot chiqaradigan hamma
hujjat bir xil uslubda ko'rinadi.
"""

import contextlib
import logging
import os
import uuid

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from services.project_work import palettes

logger = logging.getLogger(__name__)

FIGSIZE = (7.2, 4.0)
DPI = 150

# AI shu turlardan birini so'raydi. Nomlar promptda ham shu ko'rinishda
# beriladi, shuning uchun ro'yxat bitta joyda turadi.
CHART_TYPES = ("line", "bar", "column", "pie", "scatter", "area")


@contextlib.contextmanager
def _figure_guard():
    """Xato bo'lsa ham ochilgan figura yopilishini kafolatlaydi.

    matplotlib figuralarni global ro'yxatda ushlaydi: saqlashgacha yetib
    bormasdan xato yuz bersa, figura buferi bilan xotirada qolib ketardi.
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


def _numbers(values) -> list:
    out = []
    for value in values or []:
        try:
            out.append(float(str(value).replace(",", ".").replace(" ", "")))
        except (TypeError, ValueError):
            out.append(0.0)
    return out


def _shorten(text, limit: int = 22) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _series(raw) -> list:
    """AI qaytargan qatorlarni (nom, qiymatlar) juftliklariga keltiradi."""
    out = []
    for item in raw or []:
        if isinstance(item, dict):
            name = item.get("name") or "Ko‘rsatkich"
            values = _numbers(item.get("values"))
        else:
            name, values = "Ko‘rsatkich", _numbers(item)
        if values:
            out.append((str(name), values))
    return out


def draw(spec: dict, work_dir: str, palette=None) -> str | None:
    """Diagrammani chizadi va PNG yo'lini qaytaradi; ma'lumot yaroqsiz bo'lsa None.

    `spec` — AI bergan lug'at: `chart_type`, `title`, `x_label`, `y_label`,
    `categories`, `series`.
    """
    palette = palette or palettes.DEFAULT_PALETTE
    kind = str(spec.get("chart_type") or "column").lower().strip()
    if kind not in CHART_TYPES:
        kind = "column"

    categories = [_shorten(c) for c in (spec.get("categories") or [])]
    series = _series(spec.get("series"))
    if not series:
        logger.warning("Diagramma ma'lumoti bo'sh: %s", spec.get("title"))
        return None

    # Kategoriya soni qiymat sonidan farq qilsa, ikkalasini qisqasiga tenglaymiz —
    # aks holda matplotlib xato beradi va diagramma umuman chiqmaydi.
    length = min([len(v) for _n, v in series] + ([len(categories)] if categories else []))
    if length < 2:
        logger.warning("Diagramma uchun kamida ikkita nuqta kerak: %s", spec.get("title"))
        return None
    series = [(name, values[:length]) for name, values in series]
    categories = categories[:length] if categories else [str(i + 1) for i in range(length)]

    with _figure_guard():
        figure, axes = plt.subplots(figsize=FIGSIZE, dpi=DPI)
        figure.patch.set_facecolor(palettes.SURFACE)
        axes.set_facecolor(palettes.SURFACE)

        colours = palette.categorical
        if kind == "pie":
            _draw_pie(axes, categories, series[0][1], palette)
        elif kind == "line":
            _draw_line(axes, categories, series, colours, fill=False)
        elif kind == "area":
            _draw_line(axes, categories, series, colours, fill=True)
        elif kind == "scatter":
            _draw_scatter(axes, categories, series, colours)
        elif kind == "bar":
            _draw_bars(axes, categories, series, colours, horizontal=True)
        else:
            _draw_bars(axes, categories, series, colours, horizontal=False)

        if kind != "pie":
            # Faqat berilgan bo'lsa yoziladi: XY diagramma o'z nomlarini
            # allaqachon qo'ygan va bo'sh qiymat ularni o'chirib yuborardi.
            if str(spec.get("x_label") or "").strip():
                axes.set_xlabel(str(spec["x_label"]).strip(), fontsize=10,
                                color=palettes.INK_SOFT)
            if str(spec.get("y_label") or "").strip():
                axes.set_ylabel(str(spec["y_label"]).strip(), fontsize=10,
                                color=palettes.INK_SOFT)
            for side in ("top", "right"):
                axes.spines[side].set_visible(False)
            for side in ("left", "bottom"):
                axes.spines[side].set_color(palettes.GRID)
            axes.tick_params(colors=palettes.INK_SOFT, labelsize=9, length=0)
            axes.grid(axis="y" if kind != "bar" else "x",
                      color=palettes.GRID, linewidth=0.8, alpha=0.6)
            axes.set_axisbelow(True)

        title = str(spec.get("title") or "").strip()
        if title:
            axes.set_title(title, fontsize=11, color=palettes.INK, loc="left", pad=12)

        # Legenda faqat bir nechta qator bo'lganda ma'noli: bitta qatorda u
        # shunchaki joy egallaydi. XY diagrammada esa qator nomlari o'qlarda
        # turadi, ya'ni legendaga qo'yiladigan belgi ham qolmaydi.
        scatter_xy = kind == "scatter" and len(series) >= 2
        if len(series) > 1 and kind != "pie" and not scatter_xy:
            axes.legend(fontsize=9, frameon=False, loc="best")

        os.makedirs(work_dir, exist_ok=True)
        path = os.path.join(work_dir, f"docchart_{uuid.uuid4().hex[:10]}.png")
        figure.savefig(path, facecolor=palettes.SURFACE, bbox_inches="tight",
                       pad_inches=0.2)
        plt.close(figure)
        return path


def _draw_line(axes, categories, series, colours, fill: bool) -> None:
    positions = range(len(categories))
    for index, (name, values) in enumerate(series):
        hue = colours[index % len(colours)]
        axes.plot(list(positions), values, marker="o", markersize=5,
                  linewidth=2.2, color=hue, label=name)
        if fill:
            axes.fill_between(list(positions), values, color=hue, alpha=0.18)
    axes.set_xticks(list(positions))
    axes.set_xticklabels(categories, rotation=0 if len(categories) <= 6 else 30,
                         ha="center" if len(categories) <= 6 else "right")


def _draw_scatter(axes, categories, series, colours) -> None:
    """XY o'qi: birinchi qator — x, ikkinchisi — y.

    Faqat bitta qator bo'lsa, kategoriyalar x sifatida ishlatiladi va
    diagramma chiziqsiz nuqtalar to'plamiga aylanadi.
    """
    if len(series) >= 2:
        x_name, x_values = series[0]
        y_name, y_values = series[1]
        axes.scatter(x_values, y_values, s=70, color=colours[0],
                     edgecolor=palettes.SURFACE, linewidth=1.2, zorder=3)
        axes.set_xlabel(x_name, fontsize=10, color=palettes.INK_SOFT)
        axes.set_ylabel(y_name, fontsize=10, color=palettes.INK_SOFT)
        return
    name, values = series[0]
    axes.scatter(range(len(values)), values, s=70, color=colours[0],
                 edgecolor=palettes.SURFACE, linewidth=1.2, zorder=3, label=name)
    axes.set_xticks(range(len(categories)))
    axes.set_xticklabels(categories, rotation=0 if len(categories) <= 6 else 30,
                         ha="center" if len(categories) <= 6 else "right")


def _draw_bars(axes, categories, series, colours, horizontal: bool) -> None:
    count = len(series)
    span = 0.8 / count
    positions = range(len(categories))
    for index, (name, values) in enumerate(series):
        hue = colours[index % len(colours)]
        offset = (index - (count - 1) / 2) * span
        shifted = [p + offset for p in positions]
        if horizontal:
            axes.barh(shifted, values, height=span * 0.92, color=hue, label=name)
        else:
            axes.bar(shifted, values, width=span * 0.92, color=hue, label=name)
    if horizontal:
        axes.set_yticks(list(positions))
        axes.set_yticklabels(categories)
    else:
        axes.set_xticks(list(positions))
        axes.set_xticklabels(categories, rotation=0 if len(categories) <= 6 else 30,
                             ha="center" if len(categories) <= 6 else "right")


def _draw_pie(axes, categories, values, palette) -> None:
    # Ulushlar halqasi: bo'lak nomi yonida, foizi ichida — mijoz nima
    # ko'rsatilayotganini diagrammaning o'zidan o'qiy olishi kerak.
    axes.pie(
        values,
        labels=categories,
        colors=palette.categorical[: len(values)],
        autopct="%1.0f%%",
        startangle=90,
        counterclock=False,
        wedgeprops=dict(width=0.45, edgecolor=palettes.SURFACE, linewidth=2),
        textprops=dict(fontsize=9, color=palettes.INK),
    )
    axes.axis("equal")
