"""Slayddagi fotosurat o'rinlarini Together bilan to'ldiradi.

AI slaydni HTML qilib chizadi va rasm kerak joyga shunchaki belgi
qo'yadi:

    <img data-prompt="wide documentary photograph of ..." class="photo">

Bu modul o'sha belgilarni topadi, har biri uchun rasm yaratadi va uni
HTML ichiga to'g'ridan-to'g'ri joylaydi (data URI). Brauzer rasmni
o'zining CSS qoidalari bilan (object-fit, border-radius) joylashtiradi,
chizuvchi esa uni shundayligicha PowerPointga o'tkazadi.

Ikonkalar boshqacha ishlaydi: ular `assets/icons/` da tayyor turadi,
faqat slayd rangiga bo'yaladi. Shuning uchun ular tekin, tez va har
safar bir xil sifatda chiqadi.

Rasm yoki ikonka chiqmasa, `<img>` o'rniga o'sha o'lchamdagi rangli
blok qoladi — slaydda teshik ochilmaydi va joylashuv buzilmaydi.
"""

import asyncio
import base64
import logging
import mimetypes
import os
import re
from typing import Callable, List, Optional, Tuple

log = logging.getLogger("html_images")

# Taqdimotda nechta fotosurat bo'lishi. Pastki chegara mijoz so'ragani —
# rasmsiz taqdimot quruq ko'rinadi; yuqorisi narx va vaqt uchun.
MIN_PHOTOS = 3
MAX_PHOTOS = 6

_IMG_TAG = re.compile(r"<img\b[^>]*\bdata-prompt\s*=\s*([\"'])(.*?)\1[^>]*>",
                      re.IGNORECASE | re.DOTALL)
_ICON_TAG = re.compile(r"<img\b[^>]*\bdata-icon\s*=\s*([\"'])(.*?)\1[^>]*>",
                       re.IGNORECASE | re.DOTALL)
_ICON_COLOUR = re.compile(r"\bdata-icon-color\s*=\s*([\"'])(.*?)\1",
                          re.IGNORECASE)
_CLASS = re.compile(r"\bclass\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)
_STYLE = re.compile(r"\bstyle\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)


def requests_in(html: str) -> List[str]:
    """Shu slaydda so'ralgan rasm tavsiflari."""
    return [match.group(2).strip() for match in _IMG_TAG.finditer(html)
            if match.group(2).strip()]


def count_requests(pages: List[str]) -> int:
    return sum(len(requests_in(page)) for page in pages)


def _data_uri(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        log.warning("Rasm o'qilmadi (%s): %s", path, exc)
        return None
    kind = mimetypes.guess_type(path)[0] or "image/png"
    return f"data:{kind};base64," + base64.b64encode(raw).decode("ascii")


def _placeholder(tag: str, fill: str) -> str:
    """Rasm chiqmasa — o'sha o'lchamdagi rangli blok.

    `<img>` ni shunchaki o'chirib tashlasak, slaydning joylashuvi
    buziladi: yonidagi bloklar surilib ketadi.
    """
    classes = _CLASS.search(tag)
    style = _STYLE.search(tag)
    parts = []
    if classes:
        parts.append(f'class="{classes.group(2)}"')
    extra = style.group(2).rstrip("; ") + "; " if style else ""
    parts.append(f'style="{extra}background:#{fill}"')
    return "<div " + " ".join(parts) + "></div>"


def apply_icons(pages: List[str], theme) -> Tuple[List[str], int]:
    """Ikonka belgilarini tayyor ikonkalarga almashtiradi.

    `assets/icons/` da 142 ta bir rangli siluet turadi. Ular mavzuga
    qarab tanlanadi va slaydning rangiga bo'yaladi — rasm chizdirish
    shart emas, ya'ni pul ham, kutish ham yo'q. Eski taqdimot tizimida
    aynan shular ishlatilardi va chiroyli chiqardi.
    """
    try:
        from . import icon_render
    except Exception as exc:
        log.warning("Ikonka moduli mavjud emas: %s", exc)
        return pages, 0

    used = set()
    placed = 0
    result = []

    for page in pages:
        def swap(match):
            nonlocal placed
            tag, name = match.group(0), match.group(2).strip()
            colour = _ICON_COLOUR.search(tag)
            tint = (colour.group(2) if colour else theme.accent).lstrip("#")

            path = icon_render.resolve(name, used=used)
            if not path:
                return _placeholder(tag, theme.accent_soft)
            painted = icon_render.tinted(path, tint) or path
            uri = _data_uri(painted)
            if not uri:
                return _placeholder(tag, theme.accent_soft)
            placed += 1
            return tag.replace("<img", f'<img src="{uri}"', 1)

        result.append(_ICON_TAG.sub(swap, page))

    log.info("Ikonkalar qo'yildi: %d ta", placed)
    return result, placed


async def illustrate(pages: List[str], theme, topic: str = "",
                     limit: int = MAX_PHOTOS,
                     progress_cb: Optional[Callable] = None) -> Tuple[List[str], int]:
    """Rasm o'rinlarini to'ldiradi. (slaydlar, chiqqan rasmlar soni)."""
    wanted: List[Tuple[int, str]] = []
    for index, page in enumerate(pages):
        for prompt in requests_in(page):
            wanted.append((index, prompt))

    if not wanted:
        log.info("Slaydlarda rasm so'ralmagan")
        return pages, 0

    # Chegaradan oshgani oddiy blok bo'lib qoladi: birinchi so'ralganlari
    # muhimroq (muqova va boshlang'ich slaydlar).
    wanted = wanted[:max(1, int(limit))]

    try:
        from services.together_service import get_together_service

        together = get_together_service()
    except Exception as exc:
        log.error("Together xizmati mavjud emas: %s", exc)
        together = None

    made = {}
    for number, (index, prompt) in enumerate(wanted, 1):
        if progress_cb:
            try:
                progress_cb(number - 1, len(wanted))
            except Exception:
                pass
        if together is None:
            continue
        try:
            path = await together.generate_image(prompt, aspect_ratio="16:9")
        except Exception as exc:
            log.warning("Rasm chizilmadi (%s): %s", prompt[:50], exc)
            path = None
        if not path or not os.path.exists(path):
            continue
        uri = _data_uri(path)
        try:
            os.remove(path)
        except OSError:
            pass
        if uri:
            made[(index, prompt)] = uri

    filled = 0
    result = []
    for index, page in enumerate(pages):
        def swap(match):
            nonlocal filled
            tag, prompt = match.group(0), match.group(2).strip()
            uri = made.get((index, prompt))
            if not uri:
                return _placeholder(tag, theme.accent_soft)
            filled += 1
            return tag.replace("<img", f'<img src="{uri}"', 1)

        result.append(_IMG_TAG.sub(swap, page))

    log.info("Fotosuratlar: %d ta so'ralgan, %d tasi chiqdi",
             len(wanted), filled)
    return result, filled
