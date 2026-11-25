"""Tayyor PPTX ichidagi matnni saytda qo'lda tahrirlash (3D va Klassik taqdimotlar).

Zamonaviy taqdimot HTML sahifalardan qayta yig'iladi (`manual_edit`); 3D va Klassik taqdimotlarda esa manba —
PPTX faylning o'zi. Shu sababli matn to'g'ridan-to'g'ri PPTX dagi matn bloklarida almashtiriladi: shrift, rang,
o'lcham va joylashuv birinchi bo'lak (run) dan saqlanadi; 3D modellar, Morph o'tishlari va rasmlarga tegilmaydi
(python-pptx o'zi tanimagan qismlarni o'zgarishsiz saqlaydi).

Blok slayd ichidagi `shape_id` bilan topiladi (guruh ichidagilar ham) — u faylni saqlagandan keyin o'zgarmaydi.
"""
import copy
from typing import Dict, Iterator, List, Optional, Tuple

MAX_TEXT = 2000


class TextEditError(ValueError):
    pass


def _shapes(shapes) -> Iterator:
    for shape in shapes:
        if getattr(shape, "shape_type", None) == 6 and hasattr(shape, "shapes"):     # guruh
            yield from _shapes(shape.shapes)
        else:
            yield shape


def _kind(shape, index: int, slide) -> str:
    """Brauzerdagi yorliq uchun: sarlavha, matn yoki kichik yozuv."""
    try:
        if shape.is_placeholder and shape.placeholder_format.type in (1, 3):     # TITLE, CENTER_TITLE
            return "title"
    except Exception:
        pass
    name = (shape.name or "").lower()
    if "title" in name or "sarlavha" in name:
        return "title"
    size = 0
    for paragraph in shape.text_frame.paragraphs:
        for run in paragraph.runs:
            if run.font.size:
                size = max(size, run.font.size.pt)
    if size >= 26:
        return "title"
    return "text" if len(shape.text_frame.text) > 40 or size >= 14 else "label"


def _off_slide(shape, width: int, height: int) -> bool:
    """Blok butunlay slayd tashqarisida: 3D taqdimotda Morph uchun kutib turgan yorliqlar (keyingi slaydda uchib
    kiradi). Ular sahifada ko'rinmaydi — tahrirlash ro'yxatida turib mijozni chalg'itmasin."""
    try:
        left, top = int(shape.left or 0), int(shape.top or 0)
        right, bottom = left + int(shape.width or 0), top + int(shape.height or 0)
    except (TypeError, ValueError):
        return False
    return bool(width and height) and (right <= 0 or bottom <= 0 or left >= width or top >= height)


def _editable(slide) -> List:
    found = []
    prs = slide.part.package.presentation_part.presentation
    width, height = int(prs.slide_width or 0), int(prs.slide_height or 0)
    for shape in _shapes(slide.shapes):
        if not getattr(shape, "has_text_frame", False) or not shape.has_text_frame:
            continue
        top_level = shape._element.getparent().tag.endswith("}spTree")    # guruh ichidagilar guruhga nisbatan
        if top_level and _off_slide(shape, width, height):
            continue
        text = shape.text_frame.text.strip()
        if not text or text.isdigit() or len(text) <= 1:      # bo'sh bloklar va sahifa raqamlari
            continue
        found.append(shape)
    return found


def slide_texts(pptx_path: str, number: int) -> List[Dict]:
    """`number`-sahifadagi tahrirlanadigan matnlar: [{id, kind, text}] (yuqoridan pastga, chapdan o'ngga)."""
    from pptx import Presentation

    prs = Presentation(pptx_path)
    if not 1 <= number <= len(prs.slides):
        raise TextEditError("Bunday sahifa yo'q.")
    slide = prs.slides[number - 1]
    shapes = sorted(_editable(slide), key=lambda s: (int(s.top or 0), int(s.left or 0)))
    return [{"id": int(s.shape_id), "kind": _kind(s, i, slide), "text": s.text_frame.text}
            for i, s in enumerate(shapes)]


def _set_text(text_frame, value: str) -> None:
    """Matnni almashtiradi, birinchi bo'lak ko'rinishini saqlaydi. Qatorlar — alohida paragraflar."""
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    paragraphs = list(text_frame.paragraphs)
    # Yetmagan paragraflar oxirgisidan nusxa olinadi (marker va uslubi bilan).
    while len(paragraphs) < len(lines):
        last = paragraphs[-1]._p
        clone = copy.deepcopy(last)
        last.addnext(clone)
        paragraphs = list(text_frame.paragraphs)
    for paragraph in paragraphs[len(lines):]:            # ortiqchalari olib tashlanadi
        paragraph._p.getparent().remove(paragraph._p)
    for paragraph, line in zip(text_frame.paragraphs, lines):
        runs = list(paragraph.runs)
        if runs:
            runs[0].text = line
            for run in runs[1:]:
                run._r.getparent().remove(run._r)
        else:
            paragraph.add_run().text = line


def apply(pptx_path: str, number: int, edits: List[Dict]) -> Tuple[int, Optional[str]]:
    """Matnlarni PPTX ga yozadi (joyida). Qaytaradi: (o'zgargan bloklar soni, sahifaning yangi sarlavhasi)."""
    from pptx import Presentation

    prs = Presentation(pptx_path)
    if not 1 <= number <= len(prs.slides):
        raise TextEditError("Bunday sahifa yo'q.")
    slide = prs.slides[number - 1]
    by_id = {int(s.shape_id): s for s in _editable(slide)}
    changed = 0
    for edit in edits or []:
        try:
            shape = by_id.get(int(edit.get("id")))
        except (TypeError, ValueError, AttributeError):
            shape = None
        if shape is None:
            raise TextEditError("Matn bloki topilmadi. Sahifani yangilab, qaytadan urinib ko'ring.")
        value = str(edit.get("text") or "").strip()
        if not value:
            raise TextEditError("Matn bo'sh bo'lmasin.")
        if len(value) > MAX_TEXT:
            raise TextEditError(f"Matn juda uzun ({MAX_TEXT} belgidan oshmasin).")
        if value != shape.text_frame.text.strip():
            _set_text(shape.text_frame, value)
            changed += 1
    if changed:
        prs.save(pptx_path)
    texts = slide_texts(pptx_path, number) if changed else []
    title = next((t["text"] for t in texts if t["kind"] == "title"), None)
    return changed, title
