"""Brauzerdan o'qilgan joylashuvni PowerPoint slaydiga qo'yadi.

Har element o'z turiga mos PowerPoint obyektiga aylanadi:

  matn   → tahrirlanadigan matn qutisi
  blok   → to'ldirilgan shakl (kerak bo'lsa burchaklari yumaloq)
  jadval → PowerPointning o'z jadvali
  SVG    → rasm (diagrammani shakl bilan qayta chizishning foydasi yo'q)

Joylashuv brauzer hisoblagan piksel o'rinlaridan olinadi, shuning uchun
elementlar ustma-ust tushmaydi.
"""

import logging
import os
from typing import Dict, List

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

from .html_extract import (PX_TO_EMU, PX_TO_PT, SLIDE_H_IN, SLIDE_H_PX,
                           SLIDE_W_IN, SLIDE_W_PX, font_name)

log = logging.getLogger("pptx_build")

_ALIGN = {
    "left": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
    "justify": PP_ALIGN.JUSTIFY,
}


def _emu(px: float) -> Emu:
    return Emu(int(round(float(px) * PX_TO_EMU)))


def _pt(px: float) -> float:
    return round(float(px) * PX_TO_PT, 1)


def _colour(value) -> RGBColor:
    try:
        return RGBColor.from_string(str(value).upper()[:6])
    except Exception:
        return RGBColor.from_string("000000")


def _clip(block: Dict) -> Dict:
    """Slayddan chiqib ketgan qismni kesadi."""
    x = max(0.0, float(block.get("x", 0)))
    y = max(0.0, float(block.get("y", 0)))
    w = min(float(block.get("w", 0)) + min(0.0, float(block.get("x", 0))),
            SLIDE_W_PX - x)
    h = min(float(block.get("h", 0)) + min(0.0, float(block.get("y", 0))),
            SLIDE_H_PX - y)
    return {"x": x, "y": y, "w": max(w, 1.0), "h": max(h, 1.0)}


# ────────────────────────────────────────────────────────── elementlar

def _add_rect(slide, block: Dict) -> None:
    area = _clip(block)
    radius = float(block.get("radius") or 0)
    if block.get("circle"):
        # border-radius: 50% — bu doira. Ilgari u burchagi yumaloq
        # kvadrat bo'lib chiqardi.
        shape_kind = MSO_SHAPE.OVAL
    elif radius >= 4:
        shape_kind = MSO_SHAPE.ROUNDED_RECTANGLE
    else:
        shape_kind = MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(
        shape_kind, _emu(area["x"]), _emu(area["y"]),
        _emu(area["w"]), _emu(area["h"]))

    if shape_kind is MSO_SHAPE.ROUNDED_RECTANGLE:
        # Burchak radiusi qisqa tomonning ulushi bilan beriladi.
        short = max(min(area["w"], area["h"]), 1.0)
        try:
            shape.adjustments[0] = max(0.0, min(0.5, radius / short))
        except (IndexError, ValueError):
            pass

    if block.get("fill"):
        shape.fill.solid()
        shape.fill.fore_color.rgb = _colour(block["fill"])
    else:
        shape.fill.background()

    if block.get("border"):
        shape.line.color.rgb = _colour(block["border"])
        shape.line.width = Pt(max(_pt(block.get("borderWidth") or 1), 0.5))
    else:
        shape.line.fill.background()

    # PowerPoint yangi shaklga mavzu uslubini beradi — soya bilan.
    # HTML dagi blokda soya yo'q, shuning uchun uslub butunlay olib
    # tashlanadi: rang va chegarani yuqorida o'zimiz berdik.
    shape.shadow.inherit = False
    style = shape._element.find(
        "{http://schemas.openxmlformats.org/presentationml/2006/main}style")
    if style is not None:
        shape._element.remove(style)

    # Shakl ichida matn bo'lmaydi: matn alohida quti bo'lib keladi.
    shape.text_frame.text = ""


def _add_text(slide, block: Dict) -> None:
    text = str(block.get("text") or "").strip()
    if not text:
        return
    if block.get("upper"):
        text = text.upper()

    area = _clip(block)
    # Bir qatorli matn qayta O'RALMASIN. Ilgari quti o'n piksel
    # kengaytirilardi va matn PowerPointda baribir qaytadan o'ralib,
    # oxirgi so'z pastga tushib qo'shnisining ustiga chiqardi. Endi
    # o'lcham brauzerdagining aynan o'zi, bir qatorlisida esa o'rash
    # butunlay o'chiriladi.
    # Bir qatorli matnga ozgina zaxira kenglik beriladi: PowerPointdagi
    # shrift brauzernikidan bir necha piksel keng chiqsa, oxirgi so'z
    # pastga ko'chib qo'shnisining ustiga tushardi. O'rashni butunlay
    # o'chirib bo'lmaydi — o'shanda PowerPoint qutini markazga qarab
    # kengaytiradi va chapga tekislangan matn o'rtaga siljib qoladi.
    single = int(block.get("lines") or 1) <= 1
    slack = max(area["w"] * 0.02, 6.0) if single else 2.0
    frame_box = slide.shapes.add_textbox(
        _emu(area["x"]), _emu(area["y"]),
        _emu(area["w"] + slack), _emu(area["h"]))
    frame = frame_box.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = 0
    frame.margin_top = frame.margin_bottom = 0
    frame.vertical_anchor = MSO_ANCHOR.TOP

    size = _pt(block.get("size") or 16)
    # Qator oralig'i AYNAN punktda beriladi. Nisbat bilan berilsa
    # ("1.15") PowerPoint uni o'zining bir qator balandligiga ko'paytiradi
    # va qatorlar brauzerdagidan baland chiqib, matn quyidagi bezakka
    # minib qolardi.
    line_height = float(block.get("lineHeight") or 0)
    spacing = Pt(_pt(line_height)) if line_height > 0 else None

    alignment = _ALIGN.get(block.get("align"), PP_ALIGN.LEFT)
    name = font_name(block.get("family"))
    bold = int(block.get("weight") or 400) >= 600
    italic = bool(block.get("italic"))
    colour = _colour(block.get("color") or "000000")

    # <br> bilan ajratilgan satrlar alohida abzats bo'ladi — ular
    # bir-biriga yopishib qolmasin.
    for index, line in enumerate(text.split("\n")):
        paragraph = (frame.paragraphs[0] if index == 0
                     else frame.add_paragraph())
        paragraph.alignment = alignment
        paragraph.space_before = Pt(0)
        paragraph.space_after = Pt(0)
        if spacing is not None:
            paragraph.line_spacing = spacing
        run = paragraph.add_run()
        run.text = line
        font = run.font
        font.size = Pt(max(size, 6))
        font.bold = bold
        font.italic = italic
        font.name = name
        font.color.rgb = colour


def _add_table(slide, block: Dict) -> None:
    rows = [row for row in (block.get("rows") or []) if row]
    if not rows:
        return
    columns = max(len(row) for row in rows)
    area = _clip(block)

    graphic = slide.shapes.add_table(
        len(rows), columns, _emu(area["x"]), _emu(area["y"]),
        _emu(area["w"]), _emu(area["h"]))
    table = graphic.table

    widths = [float(w) for w in (block.get("widths") or [])]
    if len(widths) == columns and sum(widths) > 0:
        scale = area["w"] / sum(widths)
        for index, width in enumerate(widths):
            table.columns[index].width = _emu(width * scale)

    heights = [float(h) for h in (block.get("heights") or [])]
    if len(heights) == len(rows):
        for index, height in enumerate(heights):
            table.rows[index].height = _emu(height)

    size = _pt(block.get("size") or 24)
    header_fill = block.get("headerFill")
    header_colour = block.get("headerColor")
    body_colour = block.get("bodyColor")

    for row_index, row in enumerate(rows):
        for column_index in range(columns):
            cell = table.cell(row_index, column_index)
            source = row[column_index] if column_index < len(row) else {}
            cell.text = str(source.get("text") or "")
            cell.margin_left = cell.margin_right = Emu(45720)
            cell.margin_top = cell.margin_bottom = Emu(18288)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE

            if row_index == 0 and header_fill:
                cell.fill.solid()
                cell.fill.fore_color.rgb = _colour(header_fill)
            else:
                cell.fill.background()

            for paragraph in cell.text_frame.paragraphs:
                paragraph.alignment = _ALIGN.get(source.get("align"),
                                                 PP_ALIGN.CENTER)
                for run in paragraph.runs:
                    run.font.size = Pt(max(size, 8))
                    run.font.bold = bool(source.get("bold")) or row_index == 0
                    run.font.name = "Arial"
                    colour = header_colour if row_index == 0 else body_colour
                    run.font.color.rgb = _colour(colour or "1A1A1A")


def _add_image(slide, block: Dict) -> None:
    path = block.get("path")
    if not path or not os.path.exists(path):
        return
    area = _clip(block)
    slide.shapes.add_picture(
        path, _emu(area["x"]), _emu(area["y"]),
        _emu(area["w"]), _emu(area["h"]))


# ──────────────────────────────────────────────────────────── slaydlar

def _background(slide, colour: str) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = _colour(colour or "FFFFFF")


def add_slide(presentation, layout: Dict) -> None:
    """Bitta slaydni tahrirlanadigan elementlardan yig'adi."""
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    _background(slide, layout.get("background"))

    # Tartib muhim: fon bloklari avval, matn keyin — shunda matn
    # ularning ustida turadi.
    order = {"rect": 0, "image": 1, "table": 2, "text": 3}
    blocks = sorted(layout.get("blocks") or [],
                    key=lambda item: order.get(item.get("kind"), 3))

    for block in blocks:
        kind = block.get("kind")
        try:
            if kind == "rect":
                _add_rect(slide, block)
            elif kind == "text":
                _add_text(slide, block)
            elif kind == "table":
                _add_table(slide, block)
            elif kind == "image":
                _add_image(slide, block)
        except Exception as exc:
            log.warning("Element qo'yilmadi (%s): %s", kind, exc)


def add_picture_slide(presentation, image_path: str) -> None:
    """Zaxira yo'l: butun slaydni rasm qilib qo'yadi.

    Joylashuvni o'qib bo'lmaganda ishlatiladi — mijoz bo'sh slayd
    o'rniga hech bo'lmasa ko'rinadigan slayd olsin.
    """
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.shapes.add_picture(
        image_path, 0, 0,
        presentation.slide_width, presentation.slide_height)


def new_presentation():
    from pptx import Presentation
    from pptx.util import Inches

    presentation = Presentation()
    presentation.slide_width = Inches(SLIDE_W_IN)
    presentation.slide_height = Inches(SLIDE_H_IN)
    return presentation
