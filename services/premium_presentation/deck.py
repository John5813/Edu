"""Qolipli slaydlardan PPTX yig'adi.

Bu modul eski `pipeline.py` ning o'rnini bosadi. U yerda AI bergan
koordinatalar tuzatilar, elementlar surilar, shrift kichraytirilar,
oxirida har slayd rasmga aylantirilib vision model bilan tekshirilardi.
Endi joylashuv qolipdan olinadi, shuning uchun tuzatadigan narsa yo'q:

    reja (qolip + mazmun)  →  elementlar  →  PPTX

Rasm faqat rasm o'rni bor qoliplarda so'raladi — taqdimotga ikki-uchta,
hammasiga emas.
"""

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

from pptx import Presentation
from pptx.util import Inches

from . import infographics
from .image_client import generate_image
from .layouts import render_canvas
from .models import SlideCanvas, VisualElement
from .slidebuild import build_elements
from .templates import SLIDE_H, SLIDE_W, Template, get as get_template
from .themes import Theme

log = logging.getLogger("deck")

# Oxirgi yig'ishda rasmlar bo'yicha natija — Telegram tomoni o'qiydi.
LAST_IMAGE_REPORT = {"wanted": 0, "failed": 0, "reason": ""}


@dataclass
class PlannedSlide:
    """Bitta slayd: qaysi qolip va unga nima yoziladi."""

    layout: str
    content: Dict

    @property
    def template(self) -> Template:
        return get_template(self.layout)


class _CanvasShim:
    """`render_canvas` kutadigan eng kichik slayd ko'rinishi."""

    def __init__(self, index: int, background: str, elements: List[VisualElement]):
        self.index = index
        self.canvas = SlideCanvas(background=background, elements=elements)


class _ThemeShim:
    """Infografika ranglarini mavzu sxemasidan oladi.

    `infographics` moduli `primary`/`accent` nomli maydonlarni kutadi —
    eski `Brief.theme` shunday edi. Shu ikki nomni sxemamizdan beramiz,
    shunda infografika ham tanlangan rangda chiqadi.
    """

    def __init__(self, theme: Theme):
        self.primary = theme.accent
        self.accent = theme.chart[1] if len(theme.chart) > 1 else theme.accent
        # To'liq qator: infografikaning har bandi shu sxemada qoladi.
        self.series = list(theme.chart) or [theme.accent]


class _ChartPalette:
    """Diagramma ranglari — `layouts._draw_chart` kutadigan ko'rinishda."""

    def __init__(self, theme: Theme):
        colours = ["#" + c for c in (theme.chart or (theme.accent,))]
        self.key = theme.key
        self.ramp = colours
        self.categorical = colours

    @property
    def lead(self) -> str:
        return self.ramp[0]


def expand(elements: List[VisualElement], theme: Theme) -> List[VisualElement]:
    """Infografikani ibtidoiy shakllarga yoyadi.

    Chizuvchi `infographic` turini tushunmaydi — uni kartochka, bosqich
    yoki halqa shakllariga aylantirish kerak. Yoyilmasa element
    tashlanmaydi: `infographics` o'zi oddiy ro'yxatga o'tkazadi.
    """
    shim = _ThemeShim(theme)
    out: List[VisualElement] = []
    for element in elements:
        if element.type != "infographic":
            out.append(element)
            continue
        parts = infographics.expand(element, shim)
        if parts:
            out.extend(_centre(parts, element))
        else:
            log.warning("Infografika yoyilmadi — element tashlandi")
    return out


def _centre(parts: List[VisualElement], slot: VisualElement) -> List[VisualElement]:
    """Yoyilgan blokni o'rni ichida vertikal markazga qo'yadi.

    Infografika o'z mazmuniga qarab balandlik oladi, ya'ni ajratilgan
    joydan past bo'lishi mumkin. Markazlanmasa blok yuqoriga yopishib,
    slaydning pastki uchdan biri bo'sh qolardi.
    """
    tops = [p.y for p in parts if p.y is not None]
    bottoms = [(p.y or 0) + (p.h or p.d or 0) for p in parts]
    if not tops or not bottoms:
        return parts

    height = max(bottoms) - min(tops)
    shift = (slot.h - height) / 2 - (min(tops) - slot.y)
    if shift <= 0.05:
        return parts
    for part in parts:
        part.y = (part.y or 0) + shift
    return parts


def slide_elements(planned: PlannedSlide, theme: Theme) -> List[VisualElement]:
    """Bitta slaydning tayyor elementlari."""
    return expand(build_elements(planned.template, planned.content, theme), theme)


def build(slides: List[PlannedSlide], theme: Theme,
          out_dir: str = "temp", with_images: bool = True) -> str:
    """Rejadagi slaydlardan PPTX yasaydi va fayl yo'lini qaytaradi."""
    presentation = Presentation()
    presentation.slide_width = Inches(SLIDE_W)
    presentation.slide_height = Inches(SLIDE_H)
    blank = presentation.slide_layouts[6]

    palette = _ChartPalette(theme)
    used_icons: set = set()
    wanted = failed = 0
    reason = ""

    for index, planned in enumerate(slides, 1):
        elements = slide_elements(planned, theme)

        image_paths: Dict[int, str] = {}
        for element in elements:
            if element.type != "image" or not element.prompt:
                continue
            wanted += 1
            if not with_images:
                failed += 1
                continue
            path = generate_image(element.prompt)
            if path:
                image_paths[id(element)] = path
            else:
                failed += 1
                reason = reason or "rasm modeli javob bermadi"
                log.error("Slayd %s: rasm yaratilmadi", index)

        # Rasm chiqmasa o'sha o'rin bo'sh qolmasin: rang bilan to'ldiriladi,
        # shunda slayd teshik ko'rinmaydi.
        drawable = []
        for element in elements:
            if element.type == "image" and id(element) not in image_paths:
                drawable.append(VisualElement(
                    type="rect", x=element.x, y=element.y,
                    w=element.w, h=element.h, fill=theme.accent_soft,
                    locked=True))
                continue
            drawable.append(element)

        canvas = _CanvasShim(index, theme.background, drawable)
        render_canvas(presentation.slides.add_slide(blank), canvas,
                      image_paths, used_icons, palette)

    LAST_IMAGE_REPORT.update({"wanted": wanted, "failed": failed, "reason": reason})

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"premium_{uuid.uuid4().hex[:10]}.pptx")
    presentation.save(path)
    log.info("Taqdimot yig'ildi: %s slayd, %s rasm (%s ta chiqmadi)",
             len(slides), wanted, failed)
    return path
