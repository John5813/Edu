import logging
import os
import uuid

from pptx import Presentation

from . import config
from .image_client import generate_image
from .layouts import SLIDE_H, SLIDE_W, render_canvas
from .models import Brief

log = logging.getLogger("renderer")


def _replace_with_panel(element, brief: Brief) -> None:
    """Rasm o'rnini rangli panel bilan to'ldiradi — kompozitsiya buzilmasin."""
    element.type = "rect"
    element.radius = True
    element.fill = element.fill or (brief.theme.accent if brief.theme else "E8A020")
    element.prompt = None


def build_presentation(brief: Brief) -> str:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank_layout = prs.slide_layouts[6]  # to'liq bo'sh layout

    # Butun taqdimot bo'ylab bitta ikonka ikki marta ishlatilmasin.
    used_icons: set[str] = set()

    for s in brief.slides:
        slide = prs.slides.add_slide(blank_layout)

        # image elementlari uchun rasm generatsiyasi
        image_paths: dict[int, str] = {}
        for el in s.canvas.elements:
            if el.type == "image" and el.prompt:
                path = generate_image(el.prompt)
                if path:
                    image_paths[id(el)] = path
                else:
                    # Rasmni jimgina tashlab ketish slaydni yarim bo'sh qoldiradi
                    # va aynan shu sababdan taqdimotlar rasmsiz chiqib ketgan edi.
                    log.error(
                        "Slayd %s: rasm yaratilmadi (TOGETHER_API_KEY bormi?) — "
                        "o'rniga rangli panel qo'yiladi", s.index
                    )
                    _replace_with_panel(el, brief)

        render_canvas(slide, s, image_paths, used_icons)

    os.makedirs(config.WORK_DIR, exist_ok=True)
    out_path = os.path.join(config.WORK_DIR, f"ppt_{uuid.uuid4().hex[:10]}.pptx")
    prs.save(out_path)
    log.info("PPTX saqlandi: %s", out_path)
    return out_path
