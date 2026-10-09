"""Oddiy taqdimot uchun slayd chizish vositalari (python-pptx, tayyor shakllar).

`slide_layouts` dagi 25 ta shablon shu yerdagi sodda bo'laklardan yig'iladi:
matn qutisi, yumshoq karta, raqamli doira, ikonka, chiziq, rasm.

Matn hajmi haqiqiy o'lchov bilan tekshiriladi (`slide_fit`): sig'masa
`Ctx.overflow` belgilanadi, rejalovchi esa boshqa shablonga o'tadi.
Hech qachon matn qirqilmaydi.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from services import slide_fit

logger = logging.getLogger(__name__)

FONT = "Times New Roman"

# Mazmun maydoni (dyuym). Sarlavha 0.3–1.3 da turadi; Mandala fonlarning
# chet-hoshiyasiga tushmaslik uchun chetlardan 0.9" ichkarida.
AREA_L, AREA_T, AREA_R, AREA_B = 0.9, 1.65, 12.45, 7.0
AREA_W, AREA_H = AREA_R - AREA_L, AREA_B - AREA_T


@dataclass
class Palette:
    accent: str = "2563EB"          # shablonning sarlavha rangi (hex, #siz)
    text: str = "1A1A1A"
    dark: bool = False              # fon to'qmi
    card: str = "FFFFFF"            # karta foni
    card_alpha: int = 82            # foiz
    on_accent: str = "FFFFFF"       # rangli fon ustidagi matn

    @property
    def muted(self) -> str:
        return self.text


def _brightness(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b


def palette_for(template_service, template_id: Optional[str]) -> Palette:
    """Shablon ranglaridan palitra. Shablon yo'q bo'lsa — neytral ko'k."""
    pal = Palette()
    if not template_service or not template_id:
        return pal
    try:
        colors = template_service.get_readable_colors(template_id)
        pal.accent = str(colors["title"])
        pal.text = str(colors["text"])
        pal.dark = template_service.background_luminance(template_id) < 120
    except Exception as e:                      # rang topilmasa ham slayd chiqsin
        logger.warning("Palette fallback: %s", e)
        return pal
    if pal.dark:
        pal.card, pal.card_alpha = "14141E", 68
    pal.on_accent = "FFFFFF" if _brightness(pal.accent) < 150 else "1A1A1A"
    return pal


@dataclass
class Ctx:
    """Bitta slayd chizish holati."""
    slide: object
    pal: Palette
    language: str = "uz"
    used_icons: set = field(default_factory=set)
    use_icons: bool = True
    image: Optional[str] = None     # tayyor rasm yo'li (rasmli shablonlar)
    dry: bool = False               # faqat o'lchash: sig'adimi?
    overflow: bool = False          # matn eng kichik shriftda ham sig'madi
    icon_finder: object = None      # (head, text, used) -> path | None


# ── past darajali yordamchilar ──────────────────────────────────────────────

def _rgb(hex_colour: str) -> RGBColor:
    return RGBColor.from_string(hex_colour.upper())


def _set_alpha(element, percent: int) -> None:
    """solidFill ichidagi srgbClr ga shaffoflik qo'shadi."""
    clr = element.find(qn("a:solidFill")).find(qn("a:srgbClr"))
    for old in clr.findall(qn("a:alpha")):
        clr.remove(old)
    clr.append(clr.makeelement(qn("a:alpha"), {"val": str(int(percent * 1000))}))


def _no_shadow(shape) -> None:
    try:
        shape.shadow.inherit = False
    except Exception:
        pass


def _named(shape, name: str):
    # "fixed:" — `_apply_template_colors` bunday shakllar matnini qayta bo'yamaydi:
    # rang shu yerda, palitradan, karta fonini hisobga olib tanlangan.
    shape.name = f"fixed:{name}"
    return shape


def shape(ctx: Ctx, kind, left, top, width, height, fill: Optional[str] = None,
          alpha: int = 100, line: Optional[str] = None, line_alpha: int = 100,
          line_w: float = 1.0, name: str = "shape", radius: Optional[float] = None):
    """Shakl qo'shadi (dry rejimda ham — geometriya bir xil)."""
    s = ctx.slide.shapes.add_shape(kind, Inches(left), Inches(top), Inches(width), Inches(height))
    if fill:
        s.fill.solid()
        s.fill.fore_color.rgb = _rgb(fill)
        if alpha < 100:
            _set_alpha(s.fill._xPr, alpha)
    else:
        s.fill.background()
    if line:
        s.line.color.rgb = _rgb(line)
        s.line.width = Pt(line_w)
        if line_alpha < 100:
            _set_alpha(s.line._ln, line_alpha)
    else:
        s.line.fill.background()
    if radius is not None and kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        try:
            s.adjustments[0] = max(0.0, min(0.5, radius / max(min(width, height), 0.01)))
        except Exception:
            pass
    _no_shadow(s)
    return _named(s, name)


def card(ctx: Ctx, left, top, width, height, radius: float = 0.14, name: str = "card"):
    """Yumshoq yarim shaffof karta, shablon rangida ingichka chiziq bilan."""
    return shape(ctx, MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height,
                 fill=ctx.pal.card, alpha=ctx.pal.card_alpha,
                 line=ctx.pal.accent, line_alpha=45, line_w=1.0, name=name, radius=radius)


def panel(ctx: Ctx, left, top, width, height, radius: float = 0.14, alpha: int = 100,
          name: str = "panel"):
    """Shablon rangida to'liq to'ldirilgan panel."""
    return shape(ctx, MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height,
                 fill=ctx.pal.accent, alpha=alpha, name=name, radius=radius)


def line(ctx: Ctx, x1, y1, x2, y2, width: float = 2.0, alpha: int = 70, colour: Optional[str] = None):
    conn = ctx.slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1),
                                          Inches(x2), Inches(y2))
    conn.line.color.rgb = _rgb(colour or ctx.pal.accent)
    conn.line.width = Pt(width)
    if alpha < 100:
        _set_alpha(conn.line._ln, alpha)
    return _named(conn, "line")


def text(ctx: Ctx, left, top, width, height, paragraphs, pt: Optional[float] = None,
         bold: bool = False, colour: Optional[str] = None, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, min_pt: int = 14, max_pt: int = 22, italic: bool = False,
         space_after: float = 0, name: str = "text"):
    """Matn qutisi. `paragraphs` — satr yoki [(matn, {bold, pt, colour, italic})...].

    `pt` berilmasa, sig'adigan eng katta shrift (max_pt..min_pt) tanlanadi.
    Sig'masa — `ctx.overflow = True` va min_pt ishlatiladi.
    Qaytadi: tanlangan shrift.
    """
    if isinstance(paragraphs, str):
        paragraphs = [(paragraphs, {})]
    paragraphs = [(t, o) for t, o in paragraphs if t is not None]
    if not any(str(t).strip() for t, _ in paragraphs):
        # Bo'sh matn qutisi qo'yilmaydi: PowerPoint/WPS unda "Double-tap to add text" ko'rsatadi.
        return pt or min_pt

    if pt is None:
        pt = min_pt
        for cand in range(int(max_pt), int(min_pt) - 1, -1):
            if _paragraphs_fit(paragraphs, width, height, cand, bold, space_after):
                pt = cand
                break
        else:
            ctx.overflow = True
    elif not _paragraphs_fit(paragraphs, width, height, pt, bold, space_after):
        ctx.overflow = True

    box = ctx.slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    _named(box, name)
    tf = box.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.vertical_anchor = anchor
    for index, (value, opts) in enumerate(paragraphs):
        p = tf.paragraphs[0] if index == 0 else tf.add_paragraph()
        p.alignment = opts.get("align", align)
        if space_after and index < len(paragraphs) - 1:
            p.space_after = Pt(space_after)
        run = p.add_run()
        run.text = value
        font = run.font
        font.name = FONT
        font.size = Pt(opts.get("pt", pt))
        font.bold = opts.get("bold", bold)
        font.italic = opts.get("italic", italic)
        font.color.rgb = _rgb(opts.get("colour", colour or ctx.pal.text))
    return pt


def _paragraphs_fit(paragraphs, width, height, pt, bold, space_after) -> bool:
    """Har abzats o'z shriftida; umumiy balandlik qutiga sig'adimi."""
    need = 0.0
    for index, (value, opts) in enumerate(paragraphs):
        size = opts.get("pt", pt)
        lines = slide_fit.count_lines(value, size * (1.04 if opts.get("bold", bold) else 1.0), width)
        need += lines * size * slide_fit.LINE_HEIGHT / 72.0
        if space_after and index < len(paragraphs) - 1:
            need += space_after / 72.0
    return need <= height - slide_fit.INSET_Y


def number_badge(ctx: Ctx, left, top, size, label: str, filled: bool = True, pt: Optional[int] = None):
    """Raqamli doira (rangli, ichida oq raqam)."""
    if filled:
        shape(ctx, MSO_SHAPE.OVAL, left, top, size, size, fill=ctx.pal.accent, name="badge")
        colour = ctx.pal.on_accent
    else:
        shape(ctx, MSO_SHAPE.OVAL, left, top, size, size, fill=ctx.pal.card,
              alpha=ctx.pal.card_alpha, line=ctx.pal.accent, line_w=1.5, name="badge")
        colour = ctx.pal.accent
    size_pt = pt or max(12, int(size * 72 * 0.42))
    text(ctx, left, top, size, size, label, pt=size_pt, bold=True, colour=colour,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, name="badge_text")
    return size_pt


def icon_badge(ctx: Ctx, head: str, body: str, left, top, size) -> bool:
    """Ikonka (doira ichida). Ikonka topilmasa — False (chaqiruvchi raqam qo'yadi)."""
    if not ctx.use_icons or ctx.icon_finder is None:
        return False
    try:
        path = ctx.icon_finder(head, body, ctx.used_icons)
    except Exception as e:
        logger.warning("Icon lookup failed: %s", e)
        return False
    if not path or not os.path.isfile(path):
        return False
    if ctx.dry:
        return True
    from services.premium_presentation import icon_render
    shape(ctx, MSO_SHAPE.OVAL, left, top, size, size, fill="FFFFFF" if not ctx.pal.dark else "14141E",
                   alpha=78, line=ctx.pal.accent, line_alpha=45, line_w=1.25, name="icon")
    glyph = icon_render.tinted(path, ctx.pal.accent) or path
    inner = size * 0.56
    ctx.slide.shapes.add_picture(glyph, Inches(left + (size - inner) / 2),
                                 Inches(top + (size - inner) / 2), Inches(inner), Inches(inner))
    ctx.used_icons.add(os.path.basename(path))
    return True

def marker(ctx: Ctx, head: str, body: str, left, top, size, label: str = "") -> None:
    """Raqam o'rniga ikonka. Mavzuga mos ikonka band bo'lsa ham takrorlanishiga
    yo'l qo'yiladi; ikonka umuman topilmasa (fayllar yo'q) — oxirgi chora raqam."""
    if icon_badge(ctx, head, body, left, top, size):
        return
    used = ctx.used_icons
    ctx.used_icons = set()
    try:
        found = icon_badge(ctx, head, body, left, top, size)
    finally:
        ctx.used_icons = used | ctx.used_icons
    if not found:
        number_badge(ctx, left, top, size, label or "•")


def picture(ctx: Ctx, left, top, width, height, bias: float = 0.4, rounded: bool = True):
    """Rasmni nisbatini saqlab qo'yadi (ortiqchasi qirqiladi). Rasm bo'lmasa False."""
    if ctx.dry:
        return bool(ctx.image)
    if not ctx.image or not os.path.isfile(ctx.image):
        return False
    from PIL import Image
    with Image.open(ctx.image) as img:
        iw, ih = img.size
    pic = ctx.slide.shapes.add_picture(ctx.image, Inches(left), Inches(top), Inches(width), Inches(height))
    if iw and ih:
        target, actual = width / height, iw / ih
        if actual > target:
            extra = 1 - target / actual
            pic.crop_left = pic.crop_right = extra / 2
        elif actual < target:
            extra = 1 - actual / target
            pic.crop_top, pic.crop_bottom = extra * bias, extra * (1 - bias)
    if rounded:
        try:
            pic.auto_shape_type = MSO_SHAPE.ROUNDED_RECTANGLE
            geom = pic._element.spPr.find(qn("a:prstGeom"))
            av = geom.find(qn("a:avLst"))
            if av is None:
                av = geom.makeelement(qn("a:avLst"), {})
                geom.append(av)
            av.append(av.makeelement(qn("a:gd"), {"name": "adj", "fmla": "val 6000"}))
        except Exception:
            pass
    _named(pic, "image")
    return True


def split_sentences(value: str) -> List[str]:
    return slide_fit.sentences(value or "")
