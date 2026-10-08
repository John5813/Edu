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
MAX_PHOTOS = 10


def photo_limit(slide_count: int, volume: str = "kop") -> int:
    """Bitta taqdimotda chizdiriladigan rasmlar chegarasi: kvota (`deck_logic.photo_quota`) va ozgina zaxira.

    `slide_count` — mijoz tanlagan son (muqova va reja bunga kirmaydi). Kam matnli taqdimotda rasm ko'p:
    30 slaydda 18 tagacha, shuning uchun eski qat'iy 10 ta chegarasi kvotaga qarab kengayadi.
    """
    from . import deck_logic

    return max(MAX_PHOTOS, deck_logic.photo_quota(int(slide_count or 0) + 2, volume) + 2)

_IMG_TAG = re.compile(r"<img\b[^>]*\bdata-prompt\s*=\s*([\"'])(.*?)\1[^>]*>",
                      re.IGNORECASE | re.DOTALL)
_ICON_TAG = re.compile(r"<img\b[^>]*\bdata-icon\s*=\s*([\"'])(.*?)\1[^>]*>",
                       re.IGNORECASE | re.DOTALL)
_ICON_COLOUR = re.compile(r"\bdata-icon-color\s*=\s*([\"'])(.*?)\1",
                          re.IGNORECASE)
# Har qanday <img>. Model ba'zan `data-prompt` o'rniga oddiy
# `<img src="..." alt="...">` yozadi; unday rasm hech qachon
# to'ldirilmaydi va brauzer uning o'rniga "buzuq rasm" belgisini
# alt matni bilan chizadi. Slaydda u ingichka chiziq bo'lib qoladi.
_ANY_IMG = re.compile(r"<img\b[^>]*>", re.IGNORECASE | re.DOTALL)
_HAS_DATA_SRC = re.compile(r"\bsrc\s*=\s*([\"'])\s*data:", re.IGNORECASE)
_ALT = re.compile(r"\balt\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)
_CLASS = re.compile(r"\bclass\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)
_STYLE = re.compile(r"\bstyle\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)


def normalize(pages: List[str]) -> List[str]:
    """Belgilanmagan `<img>` larni rasm so'roviga aylantiradi.

    Promptda `data-prompt` yozish aytilgan, lekin model uni ba'zan
    unutib, oddiy `<img src="..." alt="Laboratoriya">` yozadi. Bunday
    rasm to'ldirilmaydi va slaydda buzuq rasm belgisi bo'lib qoladi.
    Shunday `<img>` ning `alt` matni tavsif sifatida ishlatiladi.
    """
    result = []
    for page in pages:
        def fix(match):
            tag = match.group(0)
            if ("data-prompt" in tag.lower() or "data-icon" in tag.lower()
                    or _HAS_DATA_SRC.search(tag)):
                return tag
            alt = _ALT.search(tag)
            text = alt.group(2).strip() if alt else ""
            if not text:
                return tag
            # `src` ni olib tashlaymiz: u yaroqsiz, brauzer uni yuklay
            # olmaydi va rasm buzuq bo'lib chiqadi.
            cleaned = re.sub(r"\bsrc\s*=\s*([\"'])(.*?)\1", "", tag,
                             flags=re.IGNORECASE | re.DOTALL)
            return cleaned.replace("<img", f'<img data-prompt="{text}"', 1)

        result.append(_ANY_IMG.sub(fix, page))
    return result


def sweep(pages: List[str], theme) -> List[str]:
    """To'ldirilmay qolgan `<img>` larni rangli blokka almashtiradi.

    Chegaradan oshgan yoki xato tufayli chiqmagan rasm slaydda buzuq
    belgi bo'lib turmasin — uning o'rnida toza rangli maydon qolsin.
    """
    result = []
    for page in pages:
        def fix(match):
            tag = match.group(0)
            if _HAS_DATA_SRC.search(tag):
                return tag
            return _placeholder(tag, theme.accent_soft)

        result.append(_ANY_IMG.sub(fix, page))
    return result


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
            # Ikonkasi allaqachon qo'yilgan bo'lsa tegilmaydi: slayd
            # qayta chizilganda bu ikkinchi marta chaqiriladi.
            if _HAS_DATA_SRC.search(tag):
                return tag
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
            path = await together.generate_image(prompt, aspect_ratio="16:9",
                                                 target="premium")
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


# ─────────────────────────────────────────── matn va rasm bloki

# `<div class="rasm" data-prompt="...">` — model rasm so'ragan joy.
# Ichida rasm chiqmasa turadigan qo'shimcha matn bor, shuning uchun
# rasm chiqmasa hech narsa qilinmaydi: matn o'z joyida qoladi.
_RASM_OPEN = re.compile(
    r'<div\b[^>]*\bclass\s*=\s*(["\'])[^"\']*(?<![-\w])rasm(?![-\w])'
    r'[^"\']*\1[^>]*>', re.IGNORECASE)
_DIV = re.compile(r"<div\b[^>]*>|</div\s*>", re.IGNORECASE)
_PROMPT = re.compile(r"\bdata-prompt\s*=\s*([\"'])(.*?)\1",
                     re.IGNORECASE | re.DOTALL)


def photos_enabled() -> bool:
    """Rasm chizdirish yoqilganmi.

    Together kaliti bo'lsa — yoqilgan. Hisobda mablag' tugasa uni
    `PREMIUM_PHOTOS=0` bilan o'chirish mumkin: har so'rov bekorga vaqt
    olmasin. O'chiq bo'lsa rasm o'rnida qo'shimcha matn turadi.
    """
    flag = os.getenv("PREMIUM_PHOTOS", "").strip().lower()
    if flag in ("0", "false", "no", "off", "yo'q"):
        return False
    if flag in ("1", "true", "yes", "on", "ha"):
        return True
    return bool(os.getenv("TOGETHER_API_KEY"))


def photo_blocks(page: str) -> List[Tuple[int, int, str]]:
    """Sahifadagi rasm bloklari: (boshi, oxiri, inglizcha tavsif)."""
    found = []
    for opening in _RASM_OPEN.finditer(page):
        prompt = _PROMPT.search(opening.group(0))
        if not prompt or not prompt.group(2).strip():
            continue
        depth = 1
        for tag in _DIV.finditer(page, opening.end()):
            depth += -1 if tag.group(0).startswith("</") else 1
            if depth == 0:
                found.append((opening.start(), tag.end(),
                              prompt.group(2).strip()))
                break
    return found


# Rasm faqat oddiy realistik fotosurat bo'lsin: diagramma, sxema va
# infografika emas. Arzon model "diagram" so'zini ko'rsa yozuvli chizma
# chizadi, shuning uchun bunday so'zlar tavsifdan olib tashlanadi.
# Ro'yxat ataylab qisqa: "map", "table", "poster" kabi oddiy so'zlar
# real fotoda ham bo'ladi — ularni olib tashlash tavsifni buzadi.
#
# Yozuv taqiqini `TogetherService._render` o'zi qo'shadi; bu yerda
# qo'shilsa taqiq ikki marta, uzun va buzilgan holda chiqadi — rasm
# bo'sh yoki g'alati bo'lib qoladi.
_DIAGRAM_WORDS = re.compile(
    r"\b(?:diagrams?|infographics?|charts?|graphs?|schemes?|schematics?|"
    r"flow\s?charts?|mind\s?maps?|blueprints?|formulas?|equations?|"
    r"labell?ed|annotated)\b", re.IGNORECASE)

# Tavsif tozalangach deyarli hech narsa qolmasa — umumiy sahna.
_FALLBACK_SCENE = "people working together in a bright modern space"
_PHOTO_STYLE = "realistic natural photograph, natural light"


def photo_prompt(prompt: str) -> str:
    """Rasm tavsifini oddiy realistik fotosuratga yo'naltiradi (yumshoq)."""
    text = re.sub(r"\s{2,}", " ", prompt or "").strip(" ,;.")
    # Diagramma so'ralgan tavsifning bir qismini olib tashlash uni
    # buzadi ("an of a pyramid"); fotosi bo'lmaydigan narsa o'rniga
    # umumiy sahna chiziladi.
    if _DIAGRAM_WORDS.search(text) or len(re.findall(r"[A-Za-z]{3,}", text)) < 3:
        text = _FALLBACK_SCENE
    return f"{text}, {_PHOTO_STYLE}"


async def fill_photos(pages: List[str], limit: int = MAX_PHOTOS,
                      generate=None) -> Tuple[List[str], int]:
    """Rasm bloklariga rasm qo'yadi. (slaydlar, qo'yilgan rasmlar soni).

    Rasm chiqmagan blok tegilmaydi — unda qo'shimcha matn qoladi.
    """
    if generate is None:
        if not photos_enabled():
            return pages, 0
        try:
            from services.together_service import get_together_service

            together = get_together_service()
        except Exception as exc:
            log.error("Together xizmati mavjud emas: %s", exc)
            return pages, 0

        async def generate(prompt):
            return await together.generate_image(prompt, aspect_ratio="4:3",
                                                target="premium")

    # Rasmlar bir vaqtda chizdiriladi: ketma-ket bo'lsa har biri
    # bir daqiqagacha kutadi va taqdimot juda sekinlashadi.
    wanted = []
    for index, page in enumerate(pages):
        for start, end, prompt in photo_blocks(page):
            wanted.append((index, start, end, prompt))
    wanted = wanted[:max(0, int(limit))]
    gate = asyncio.Semaphore(3)

    async def one(prompt):
        async with gate:
            try:
                path = await generate(photo_prompt(prompt))
            except Exception as exc:
                log.warning("Rasm chizilmadi (%s): %s", prompt[:50], exc)
                return None
        uri = _data_uri(path) if path and os.path.exists(path) else None
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        return uri

    uris = await asyncio.gather(*(one(item[3]) for item in wanted))
    result, placed, tried = list(pages), 0, len(wanted)
    # Oxiridan boshlab almashtiriladi — oldingi o'rinlar siljimaydi.
    for (index, start, end, prompt), uri in sorted(
            zip(wanted, uris), key=lambda pair: (pair[0][0], -pair[0][1])):
        if not uri:
            continue
        page = result[index]
        result[index] = (page[:start] + '<div class="rasm photo-in"><img '
                         f'class="photo" src="{uri}" alt=""></div>'
                         + page[end:])
        placed += 1
    log.info("Rasm bloklari: %d tasi sinaldi, %d tasiga rasm qo'yildi",
             tried, placed)
    return result, placed


# ───────────────────────────────────────────────── muqova rasmi

_COVER_SECTION = re.compile(
    r'(<section\b[^>]*\bclass\s*=\s*")([^"]*\bslide\b[^"]*)(")', re.IGNORECASE)
_COVER_BODY = re.compile(r'<div\b([^>]*)\bclass\s*=\s*"([^"]*\bbody\b[^"]*)"([^>]*)>', re.IGNORECASE)
_COVER_END = re.compile(r"</div>\s*</section>\s*(?=<!--|</body>|$)", re.IGNORECASE)


_HAS_COVER_PHOTO = re.compile(r'<section\b[^>]*\bclass\s*=\s*"[^"]*\bcover-photo\b', re.IGNORECASE)


def with_cover_photo(page: str, uri: str) -> str:
    """Muqova sahifasini rasmli qiladi: chapda rasm, o'ngda sarlavha va izoh.

    Oddiy taqdimot muqovasi ham shunday (chap yarmi rasm). Rasm bo'lmasa bu
    funksiya chaqirilmaydi — muqova avvalgidek matnli qoladi.
    """
    opening = _COVER_SECTION.search(page)
    body = _COVER_BODY.search(page, opening.end() if opening else 0)
    end = None
    for end in _COVER_END.finditer(page):
        pass
    if not opening or not body or end is None or end.start() < body.end():
        return page
    photo = ('<div class="rasm photo-in cover-img"><img class="photo" '
             f'src="{uri}" alt=""></div><div class="cover-text">')
    result = (page[:opening.start()]
              + opening.group(1) + opening.group(2) + " cover-photo" + opening.group(3)
              + page[opening.end():body.start()]
              + f'<div{body.group(1)}class="{body.group(2)} cover-split"{body.group(3)}>' + photo
              + page[body.end():end.start()]
              + "</div></div></section>" + page[end.end():])
    return result


async def fill_cover(pages: List[str], topic: str, generate=None) -> Tuple[List[str], bool]:
    """Muqovaga mavzuga oid rasm qo'yadi (oddiy taqdimotdagi kabi).

    Rasm AI orqali mavzudan inglizcha sahnaga aylantirilib chizdiriladi. Rasm
    chiqmasa — muqova o'zgarishsiz qoladi (xato ko'tarilmaydi).
    """
    if not pages or _HAS_COVER_PHOTO.search(pages[0]) or not topic:
        return pages, False
    if generate is None:
        if not photos_enabled():
            return pages, False
        try:
            from services.together_service import get_together_service

            together = get_together_service()
        except Exception as exc:
            log.error("Together xizmati mavjud emas: %s", exc)
            return pages, False

        async def generate(subject):
            scene = await together._generate_image_prompt(subject, subject)
            return await together.generate_image(
                scene + ", wide cinematic composition, soft natural light, high quality photograph",
                aspect_ratio="4:3", target="premium")

    try:
        path = await generate(topic)
    except Exception as exc:
        log.warning("Muqova rasmi chizilmadi: %s", exc)
        return pages, False
    uri = _data_uri(path) if path and os.path.exists(path) else None
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    if not uri:
        return pages, False
    updated = with_cover_photo(pages[0], uri)
    if updated == pages[0]:
        return pages, False
    return [updated] + list(pages[1:]), True
