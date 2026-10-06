"""Vikipediya va Wikimedia Commons dan HAQIQIY fotosurat.

Model rasm blokiga `data-wiki="Registan"` yozsa (haqiqiy, aniq ob'ekt: tarixiy
bino, shahar, mashhur joy, vafot etgan tarixiy shaxs), avval shu maqolaning
bosh rasmi qidiriladi, topilmasa Commons'da qidiriladi. Topilmasa yoki
litsenziya mos kelmasa — hech narsa qaytmaydi va chaqiruvchi AI rasmga o'tadi.

API kaliti kerak emas; Wikimedia faqat aniq `User-Agent` talab qiladi.

Litsenziya: faqat Public Domain, CC0 va CC BY olinadi. CC BY-SA (ulashishda
bir xil litsenziya sharti), NC/ND, "fair use" va cheklovli (shaxs huquqi,
tovar belgisi) rasmlar o'tkazib yuboriladi. CC BY da muallif yozuvi
`credit` da qaytadi — chaqiruvchi uni slaydga qo'yadi.
"""

import asyncio
import base64
import html
import io
import logging
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

TIMEOUT = 8
MAX_BYTES = 4_000_000
THUMB_WIDTH = 1280
MIN_WIDTH = 900

_CACHE: Dict[str, Optional["WikiPhoto"]] = {}


@dataclass
class WikiPhoto:
    uri: str                # data:image/jpeg;base64,...
    title: str              # fayl nomi
    license: str            # "CC BY 4.0", "Public domain"
    author: str
    credit: str             # slaydga yoziladigan qator ("" — yozuv shart emas)
    page: str               # fayl sahifasi


def enabled() -> bool:
    """`WIKI_PHOTOS=0` bilan o'chiriladi (tarmoq bo'lmasa yoki muammo chiqsa)."""
    return os.getenv("WIKI_PHOTOS", "").strip().lower() not in ("0", "false", "no", "off")


def user_agent() -> str:
    contact = os.getenv("WIKI_CONTACT", "https://t.me/Edufayl_bot")
    return f"EdufaylBot/1.0 ({contact}) python-aiohttp"


# ───────────────────────────────────────────────────────── litsenziya

_TAG = re.compile(r"<[^>]+>")
_PUBLIC = re.compile(r"^(?:public domain|pd\b|pd-|cc0|cc-zero)", re.IGNORECASE)
_CC_BY = re.compile(r"^cc[- ]by[- ]?\d", re.IGNORECASE)          # "CC BY 4.0", "CC-BY-3.0"
_BAD_TERMS = re.compile(r"\b(?:sa|nc|nd)\b|share\s?alike|non-?commercial|no-?deriv|fair use",
                        re.IGNORECASE)


def _meta(info: dict, key: str) -> str:
    value = (info.get("extmetadata") or {}).get(key) or {}
    return str(value.get("value", "") if isinstance(value, dict) else value or "").strip()


def plain(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", text or ""))).strip()


def judge(info: dict) -> Optional[dict]:
    """Rasm ishlatilsa bo'ladimi: {"license", "author", "credit_required"} yoki None."""
    if _meta(info, "NonFree").lower() in ("true", "1", "yes"):
        return None
    if _meta(info, "Restrictions"):                      # shaxs huquqi, tovar belgisi...
        return None
    short = plain(_meta(info, "LicenseShortName")) or plain(_meta(info, "UsageTerms"))
    if not short or _BAD_TERMS.search(short):
        return None
    author = plain(_meta(info, "Artist"))
    if _PUBLIC.match(short):
        return {"license": short, "author": author, "credit_required": False}
    if _CC_BY.match(short):
        return {"license": short, "author": author, "credit_required": True}
    return None


def credit_line(license_name: str, author: str) -> str:
    author = (author or "").strip()
    if len(author) > 60:
        author = author[:57].rstrip() + "…"
    who = f"{author}, " if author else ""
    return f"Foto: {who}{license_name}, Wikimedia Commons"


# ───────────────────────────────────────────────────────── tarmoq

async def _get_json(url: str, params: dict) -> dict:
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": user_agent()}) as session:
        async with session.get(url, params=params) as response:
            response.raise_for_status()
            return await response.json(content_type=None)


async def _get_bytes(url: str) -> bytes:
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=TIMEOUT * 2)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": user_agent()}) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.content.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError("rasm juda katta")
            return data


_IMAGEINFO = {
    "prop": "imageinfo",
    "iiprop": "url|size|mime|extmetadata",
    "iiurlwidth": THUMB_WIDTH,
    "iiextmetadatafilter": "LicenseShortName|UsageTerms|Artist|NonFree|Restrictions|Copyrighted",
    "format": "json",
    "formatversion": 2,
}


def _usable(info: dict) -> bool:
    if (info.get("mime") or "") not in ("image/jpeg", "image/png"):
        return False
    width, height = int(info.get("width") or 0), int(info.get("height") or 0)
    if width < MIN_WIDTH or not height:
        return False
    return 0.7 <= width / height <= 2.4          # juda uzun yoki tor rasm slaydga mos emas


def _pick(pages: List[dict]) -> Optional[tuple]:
    """Sahifalar ichidan birinchi yaroqli va litsenziyasi mos rasm: (page, info, verdict)."""
    for page in pages:
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        if not _usable(info):
            continue
        verdict = judge(info)
        if verdict:
            return page, info, verdict
    return None


async def _from_article(title: str) -> Optional[tuple]:
    """Maqolaning bosh rasmi (agar litsenziyasi mos bo'lsa)."""
    data = await _get_json(WIKIPEDIA_API, {
        "action": "query", "titles": title, "prop": "pageimages", "piprop": "name",
        "redirects": 1, "format": "json", "formatversion": 2})
    for page in (data.get("query") or {}).get("pages") or []:
        name = page.get("pageimage")
        if not name:
            continue
        files = await _get_json(COMMONS_API, {
            "action": "query", "titles": "File:" + name, **_IMAGEINFO})
        picked = _pick((files.get("query") or {}).get("pages") or [])
        if picked:
            return picked
    return None


async def _from_search(query: str) -> Optional[tuple]:
    """Commons'da qidiruv: birinchi litsenziyasi mos, yetarli o'lchamli fotosurat."""
    data = await _get_json(COMMONS_API, {
        "action": "query", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": 12, **_IMAGEINFO})
    pages = sorted((data.get("query") or {}).get("pages") or [], key=lambda p: p.get("index", 99))
    return _pick(pages)


def _to_data_uri(raw: bytes) -> str:
    from PIL import Image

    image = Image.open(io.BytesIO(raw))
    image.load()
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    if image.width > THUMB_WIDTH:
        image = image.resize((THUMB_WIDTH, round(image.height * THUMB_WIDTH / image.width)))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=85, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


async def find(query: str) -> Optional[WikiPhoto]:
    """`query` (inglizcha maqola nomi yoki qisqa so'rov) bo'yicha mos rasm; yo'q bo'lsa None.

    Hech qachon xato ko'tarmaydi: tarmoq yoki litsenziya muammosi — shunchaki None.
    """
    query = re.sub(r"\s+", " ", (query or "").strip())[:120]
    if not query or not enabled():
        return None
    if query.lower() in _CACHE:
        return _CACHE[query.lower()]
    photo = None
    failed = False
    try:
        picked = None
        try:
            picked = await _from_article(query)
        except Exception as exc:
            log.info("Vikipediya maqolasi olinmadi (%s): %s", query, exc)
            failed = True
        if not picked:
            picked = await _from_search(query)
        if picked:
            page, info, verdict = picked
            url = info.get("thumburl") or info.get("url")
            uri = _to_data_uri(await _get_bytes(url))
            photo = WikiPhoto(
                uri=uri, title=str(page.get("title", "")),
                license=verdict["license"], author=verdict["author"],
                credit=credit_line(verdict["license"], verdict["author"]) if verdict["credit_required"] else "",
                page=str(info.get("descriptionurl", "")))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.info("Wikimedia rasmi topilmadi (%s): %s", query, exc)
        failed = True
    if not failed:                       # tarmoq xatosi eslab qolinmaydi: keyingi safar qayta uriniladi
        if len(_CACHE) > 200:
            _CACHE.clear()
        _CACHE[query.lower()] = photo
    return photo
