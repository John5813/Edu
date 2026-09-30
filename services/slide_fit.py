"""Oddiy taqdimot matnini slaydga sig'diradi — qirqmasdan.

Muammo: model ba'zan bitta slaydga 300 so'zgacha matn yozadi. Eski hisob
(`_calculate_auto_font_size`) shriftni taxminan tanlardi, matn qutidan
chiqib ketar, ko'rish dasturi uni 9-10 pt gacha kichraytirar yoki oxiri
qirqilardi. Matnni qisqartirish esa ma'noni buzadi.

Bu modul matnni HAQIQIY shrift o'lchamlari bilan o'lchaydi (Times New
Roman bilan bir xil enli Liberation Serif) va qaror qiladi:

  * sig'sa (18 pt dan kichik bo'lmagan shriftda) — bitta blok, avvalgidek;
  * sig'masa, lekin ikki ustunda 16 pt da sig'sa — yonma-yon ikki ustun;
  * yana ham uzun bo'lsa — gap chegarasida bo'linib, keyingi slaydda
    "(davomi)" bilan davom etadi. Hech narsa tashlab yuborilmaydi.

Rasmli va ustunli slaydlarda matn o'z joyiga sig'masa, ular oddiy matn
slaydiga o'tkaziladi (rasm o'rniga o'qiladigan matn muhimroq).
"""

import functools
import logging
import os
import re
from typing import Dict, List

logger = logging.getLogger(__name__)

# Slayd matn qutilarining o'lchamlari (dyuym) — document_service dagi bilan bir xil.
BODY_W, BODY_H = 11.0, 5.0          # to'liq kenglikdagi matn: (1, 2, 11 x 5)
COLUMN_W = 5.4                      # yonma-yon ikki ustunning har biri
SIDE_IMAGE_W, SIDE_IMAGE_H = 5.8, 4.5     # rasmli slayd yonidagi matn
HORIZONTAL_W, HORIZONTAL_H = 12.0, 2.0    # gorizontal rasm ustidagi matn
TWO_COL_W, TWO_COL_H = 5.6, 3.9     # ikki ustunli slayd ustuni
THREE_COL_W, THREE_COL_H = 3.7, 3.3     # kalit so'z uchun joy ajratilgan

# PowerPoint matn qutisining ichki bo'sh joyi (yon 0.1", yuqori-past 0.05").
INSET_X, INSET_Y = 0.2, 0.1
LINE_HEIGHT = 1.2                   # shrift o'lchamiga nisbatan
COMFORT_PT = 18                     # bitta blokda shundan kichik bo'lmasin
MIN_PT = 16                         # ikki ustunda shundan kichik bo'lmasin
SIDE_MIN_PT = 16
COLUMN_MIN_PT = 14

_FONT_PATHS = (
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
)
_SENTENCE = re.compile(r"(?<=[.!?…])\s+")
_MEASURE_PT = 100          # o'lchash shrifti (aniqlik uchun katta, keyin masshtablanadi)

_CONTINUED = {"uz": "(davomi)", "ru": "(продолжение)", "en": "(continued)"}
TEXT_LAYOUTS = {"intro", "conclusion", "text_with_numbers", "default", "text", "text_only", ""}


@functools.lru_cache(maxsize=1)
def _font():
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    for path in _FONT_PATHS:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, _MEASURE_PT)
            except OSError:
                continue
    return None


@functools.lru_cache(maxsize=4096)
def _word_width(word: str) -> float:
    """So'z kengligi — 1 pt shrift uchun, pt birligida."""
    font = _font()
    if font is None:
        return len(word) * 0.5          # shrift topilmasa: konservativ o'rtacha
    return font.getlength(word) / _MEASURE_PT


def count_lines(text: str, pt: float, width_in: float) -> int:
    """Berilgan shriftda matn necha qatorga sig'adi (so'z bo'yicha o'rash)."""
    usable = max((width_in - INSET_X) * 72.0, 1.0)
    space = _word_width(" ") * pt
    lines = 0
    for paragraph in (text or "").replace("\r", "").split("\n"):
        words = paragraph.split()
        if not words:
            lines += 1
            continue
        lines += 1
        used = 0.0
        for word in words:
            width = _word_width(word) * pt
            if used == 0.0:
                used = width
            elif used + space + width <= usable:
                used += space + width
            else:
                lines += 1
                used = width
            while used > usable:            # juda uzun so'z bir necha qator oladi
                lines += 1
                used -= usable
    return lines


def fits(text: str, width_in: float, height_in: float, pt: float) -> bool:
    need = count_lines(text, pt, width_in) * pt * LINE_HEIGHT / 72.0
    return need <= height_in - INSET_Y


def words(text: str) -> int:
    return len((text or "").split())


def sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE.split((text or "").strip()) if s.strip()]


def split_into_columns(text: str, parts: int) -> List[str]:
    """Matnni gap chegarasida `parts` ta teng uzunlikdagi bo'lakka bo'ladi.

    Gap yetmasa, kamroq bo'lak qaytadi (bo'sh ustun hosil qilinmaydi).
    """
    text = (text or "").strip()
    if not text:
        return []
    items = sentences(text)
    if parts <= 1 or len(items) < 2:
        return [text]
    parts = min(parts, len(items))
    total = sum(len(x) for x in items)
    columns, current, size = [], [], 0
    for index, sentence in enumerate(items):
        current.append(sentence)
        size += len(sentence)
        left_sentences = len(items) - index - 1
        left_columns = parts - len(columns) - 1
        due = size >= total * (len(columns) + 1) / parts
        if left_columns > 0 and left_sentences >= left_columns and (due or left_sentences == left_columns):
            columns.append(" ".join(current))
            current = []
    if current:
        columns.append(" ".join(current))
    return columns


def _as_text(value) -> str:
    if isinstance(value, dict):
        value = value.get("text", value.get("content", ""))
    if isinstance(value, list):
        value = " ".join(str(x) for x in value)
    return str(value or "").strip()


def _two_columns_fit(text: str, pt: float) -> List[str] | None:
    parts = split_into_columns(text, 2)
    if len(parts) == 2 and all(fits(p, COLUMN_W, BODY_H, pt) for p in parts):
        return parts
    return None


def plan_text(text: str) -> List[Dict]:
    """Uzun matn uchun reja: [{'text': ..., 'columns': [..] | None}, ...].

    Har element bitta slayd. Birinchisi asosiy, qolganlari davomi.
    """
    text = (text or "").strip()
    if fits(text, BODY_W, BODY_H, COMFORT_PT):
        return [{"text": text, "columns": None}]
    cols = _two_columns_fit(text, MIN_PT)
    if cols:
        return [{"text": text, "columns": cols}]

    # Sig'maydi — gap chegarasida bo'laklarga ajratamiz. Har bo'lak 18 pt da
    # bitta blokka yoki 16 pt da ikki ustunga sig'ishi kerak: 16 pt dagi
    # bitta uzun blok o'qishga noqulay (qator 120 belgi), shuning uchun
    # bunday matn erta ikkiga bo'linadi.
    def comfortable(candidate: str) -> bool:
        return fits(candidate, BODY_W, BODY_H, COMFORT_PT) or bool(_two_columns_fit(candidate, MIN_PT))

    chunks, current = [], []
    for sentence in sentences(text) or [text]:
        candidate = " ".join(current + [sentence])
        if current and not comfortable(candidate):
            chunks.append(" ".join(current))
            current = [sentence]
        else:
            current.append(sentence)
    if current:
        chunks.append(" ".join(current))

    # Oxirgi bo'lak juda qisqa qolmasin (bitta jumla — yomon ko'rinadi):
    # oldingi bilan birlashtirib, teng bo'linadi.
    if len(chunks) >= 2 and words(chunks[-1]) < 25:
        half = split_into_columns(" ".join(chunks[-2:]), 2)
        if len(half) == 2:
            chunks[-2:] = half

    plan = []
    for chunk in chunks:
        if fits(chunk, BODY_W, BODY_H, COMFORT_PT):
            plan.append({"text": chunk, "columns": None})
        else:
            plan.append({"text": chunk, "columns": _two_columns_fit(chunk, MIN_PT)})
    return plan


def _text_slides(slide: Dict, text: str, language: str, layout: str) -> List[Dict]:
    plan = plan_text(text)
    out = []
    for index, item in enumerate(plan):
        new = dict(slide)
        new["layout"] = layout
        new["content"] = item["text"]
        if item["columns"]:
            new["_columns_text"] = item["columns"]
        else:
            new.pop("_columns_text", None)
        if index:
            suffix = _CONTINUED.get(language, _CONTINUED["uz"])
            new["title"] = f"{(slide.get('title') or '').strip()} {suffix}".strip()
        out.append(new)
    if len(out) > 1:
        logger.info("Uzun slayd %d ta slaydga bo'ldi: %r", len(out), (slide.get("title") or "")[:50])
    return out


def _column_texts(slide: Dict) -> List[str]:
    texts = []
    for col in slide.get("columns") or []:
        if isinstance(col, dict):
            texts.append(_as_text(col.get("column_content", col.get("text", col.get("content", "")))))
        else:
            texts.append(_as_text(col))
    return [t for t in texts if t]


def prepare(slides: List[Dict], language: str = "uz") -> List[Dict]:
    """Slaydlar ro'yxatini matn sig'adigan qilib tayyorlaydi (yangi ro'yxat)."""
    result: List[Dict] = []
    for slide in slides:
        layout = slide.get("layout") or ""
        content = _as_text(slide.get("content"))

        if layout in TEXT_LAYOUTS:
            if content:
                result.extend(_text_slides(slide, content, language, layout or "default"))
            else:
                result.append(slide)

        elif layout in ("right_image", "left_image"):
            if not content or fits(content, SIDE_IMAGE_W, SIDE_IMAGE_H, SIDE_MIN_PT):
                result.append(slide)
            else:
                result.extend(_text_slides(slide, content, language, "text_with_numbers"))

        elif layout == "horizontal_image":
            if not content or fits(content, HORIZONTAL_W, HORIZONTAL_H, SIDE_MIN_PT):
                result.append(slide)
            else:
                result.extend(_text_slides(slide, content, language, "text_with_numbers"))

        elif layout in ("two_column", "three_column"):
            texts = _column_texts(slide)
            if not texts and content:
                texts = [content]
            if layout == "two_column":
                width, height = TWO_COL_W, TWO_COL_H
            else:
                width, height = THREE_COL_W, THREE_COL_H
            per_column = split_into_columns(" ".join(texts), 2 if layout == "two_column" else 3) \
                if len(texts) < (2 if layout == "two_column" else 3) else texts
            if all(fits(t, width, height, COLUMN_MIN_PT) for t in per_column):
                result.append(slide)
            else:
                joined = " ".join(texts)
                merged = dict(slide)
                merged.pop("columns", None)
                result.extend(_text_slides(merged, joined, language, "text_with_numbers"))

        else:
            result.append(slide)
    return result
