"""Slayd rasmlarini internetdan (Brave Image Search) topadi.

Qoida: bitta mavzu uchun Brave'ga faqat BITTA so'rov yuboriladi (200 ta
natija). Shu natijalardan har sarlavhaga mos rasmni AI tanlaydi:

    1. Mavzu inglizcha qidiruv so'ziga aylantiriladi (AI, bitta qisqa so'rov).
    2. Brave bitta so'rov bilan 200 tagacha rasm beradi; stok saytlar
       (suv belgili), do'konlar va kichik rasmlar olib tashlanadi.
    3. AI sarlavhalar va rasm nomlarini ko'rib, har slaydga mos rasmlarni
       tanlaydi (bir rasm — bitta slaydga).
    4. Tanlangan rasm yuklab olinadi va tekshiriladi.

Topilmagan slaydga hech narsa qaytarilmaydi — uni chaqiruvchi AI bilan
chizdiradi. Mavzu natijalari xotirada saqlanadi: o'sha mavzuga keyingi
murojaat (muqova, slaydni qayta yaratish, boshqa mijoz) Brave'ga yangi
so'rov yubormaydi va oldin ishlatilgan rasmlarni qayta bermaydi.
"""
import asyncio
import io
import logging
import os
import re
import time
import uuid
from collections import OrderedDict
from typing import Dict, List, Optional, Sequence
from urllib.parse import urlparse

import aiohttp

from services import ai_usage

log = logging.getLogger("photo_search")

BRAVE_URL = "https://api.search.brave.com/res/v1/images/search"
RESULTS = 200                 # Brave bir so'rovda beradigan eng ko'p natija
MIN_WIDTH = 600               # bundan kichik rasm slaydda xira ko'rinadi
MAX_SIDE = 1600               # PPTX og'irlashmasin
MAX_BYTES = 15 * 1024 * 1024
MAX_CANDIDATES = 120          # AI ga ko'rsatiladigan nomzodlar
CACHE_TOPICS = 300            # xotirada saqlanadigan mavzular soni

# Suv belgili stok saytlar, do'konlar va sifatsiz manbalar.
_BLOCKED = (
    "gettyimages", "istockphoto", "shutterstock", "alamy", "dreamstime", "123rf",
    "depositphotos", "stock.adobe", "adobestock", "vecteezy", "freepik", "canstockphoto",
    "bigstockphoto", "agefotostock", "superstock", "pond5", "colourbox", "stockfresh",
    "shootplanet", "amazon.", "ebay.", "aliexpress", "etsy.", "walmart.", "temu.",
    "pinimg.com", "pinterest.", "lookaside.fbsbx", "fbcdn", "instagram",
)
_BAD_EXT = (".svg", ".gif", ".ico")


def api_key() -> str:
    return (os.getenv("BRAVE_API_KEY") or os.getenv("BRAVE_SEARCH_API_KEY") or "").strip()


def enabled() -> bool:
    """Brave qidiruvi yoqilganmi. `PHOTO_SEARCH=0` — o'chirish (faqat AI chizadi)."""
    flag = os.getenv("PHOTO_SEARCH", "").strip().lower()
    if flag in ("0", "false", "no", "off", "yo'q"):
        return False
    return bool(api_key())


# ───────────────────────────────────────────── mavzu natijalari (xotira)

class _Pool:
    __slots__ = ("candidates", "used", "created")

    def __init__(self, candidates: List[dict]):
        self.candidates = candidates
        self.used: set = set()
        self.created = time.time()


_pools: "OrderedDict[str, _Pool]" = OrderedDict()
_locks: Dict[str, asyncio.Lock] = {}


def _topic_key(topic: str) -> str:
    return re.sub(r"\s+", " ", (topic or "").strip().lower())


def reset() -> None:
    """Xotirani tozalaydi (testlar uchun)."""
    _pools.clear()
    _locks.clear()


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _slug(page_url: str) -> str:
    """Sahifa manzilidan so'zlar: nomi bo'sh natija uchun AI ga ishora (".../gur-e-amir-mausoleum")."""
    try:
        path = urlparse(page_url).path
    except ValueError:
        return ""
    words = re.sub(r"[^A-Za-z]+", " ", path.rsplit(".", 1)[0] if "." in path[-6:] else path)
    return re.sub(r"\s+", " ", words).strip()[-90:]


def usable(results: Sequence[dict]) -> List[dict]:
    """Brave natijalaridan yaroqlilarini ajratadi: {url, title, source, width, height}."""
    seen, out = set(), []
    for item in results or []:
        props = item.get("properties") or {}
        url = str(props.get("url") or "").strip()
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        where = f"{item.get('source') or ''} {_host(url)} {item.get('url') or ''}".lower()
        if any(mark in where for mark in _BLOCKED):
            continue
        if urlparse(url).path.lower().endswith(_BAD_EXT):
            continue
        width, height = int(props.get("width") or 0), int(props.get("height") or 0)
        if width and width < MIN_WIDTH:
            continue
        if width and height and not 0.5 <= width / height <= 2.6:
            continue
        seen.add(url)
        out.append({"url": url, "title": str(item.get("title") or "").strip()[:140],
                    "hint": _slug(str(item.get("url") or "")),
                    "source": str(item.get("source") or _host(url))[:60],
                    "width": width, "height": height})
    return out


async def _brave(query: str) -> List[dict]:
    params = {"q": query, "count": str(RESULTS), "safesearch": "strict"}
    headers = {"Accept": "application/json", "X-Subscription-Token": api_key()}
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        async with session.get(BRAVE_URL, params=params, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Brave HTTP {resp.status}: {(await resp.text())[:200]}")
            data = await resp.json(content_type=None)
    return list((data or {}).get("results") or [])


# ─────────────────────────────────────────────────────── AI so'rovlari

def _ask_json(system: str, user: str, max_tokens: int) -> dict:
    from services.premium_presentation import llm_client

    return llm_client._call_openrouter(system, user, temperature=0.2,
                                       max_tokens=max_tokens, kind="photo")


_QUERY_SYSTEM = (
    "You turn a presentation topic (any language) into ONE short English image-search "
    "query (2-6 words) that finds real photographs of its main subject. Keep proper "
    "names of places and people (transliterated to English). No quotes, no words like "
    "'presentation' or 'slide'. Answer JSON: {\"query\": \"...\"}"
)


async def search_query(topic: str) -> str:
    """Mavzudan inglizcha qidiruv so'zi. AI ishlamasa — mavzuning o'zi."""
    try:
        data = await asyncio.to_thread(_ask_json, _QUERY_SYSTEM, f"Topic: {topic}", 200)
        query = re.sub(r"\s+", " ", str((data or {}).get("query") or "")).strip(" \"'.")
        if 2 <= len(query) <= 80:
            return query
    except Exception as exc:
        log.warning("Qidiruv so'zi tuzilmadi: %s", exc)
    return topic.strip()[:80]


_PICK_SYSTEM = (
    "You fill presentation slides with photos from a numbered list of image-search "
    "results (each has a title or page words, and a source site). Goal: fill AS MANY "
    "slots as possible — ideally every slot.\n"
    "- An image fits a slot when it is about the presentation topic and relates to the "
    "slot (same person, place, building, object, era, activity or idea). An exact match "
    "is not required: a relevant photo of the topic is much better than no photo.\n"
    "- For every slot give up to 3 ids, best first.\n"
    "- Also give \"spare\": up to 15 other ids that are good general photos of the topic "
    "(used when a slot's photo fails to download).\n"
    "- Skip results that look like: posters, book covers, products for sale, logos, "
    "screenshots, video games, memes, or a different topic. Maps and diagrams only when "
    "the slot is about geography, territory or structure.\n"
    "- Every id may be used only once in the whole answer.\n"
    "- Leave a slot empty only when no remaining result is about the topic at all.\n"
    "Answer JSON: {\"picks\": [{\"slot\": 1, \"ids\": [12, 40]}, ...], \"spare\": [3, 7]}"
)


def _pick_prompt(topic: str, slots: Sequence[str], candidates: Sequence[dict]) -> str:
    lines = [f"Presentation topic: {topic}", "", "Slots:"]
    lines += [f"{n}. {text}" for n, text in enumerate(slots, 1)]
    lines += ["", "Search results:"]
    lines += [f"{i}. {c['title'] or c.get('hint') or '(no title)'} [{c['source']}]"
              for i, c in enumerate(candidates)]
    return "\n".join(lines)


def parse_picks(data: dict, slots: int, candidates: int) -> List[List[int]]:
    """AI javobi → har slot uchun nomzod raqamlari (takrorsiz, chegaradagi)."""
    picks: List[List[int]] = [[] for _ in range(slots)]
    taken = set()
    for item in (data or {}).get("picks") or []:
        try:
            slot = int(item.get("slot")) - 1
        except (TypeError, ValueError, AttributeError):
            continue
        if not 0 <= slot < slots:
            continue
        for raw in item.get("ids") or []:
            try:
                ident = int(raw)
            except (TypeError, ValueError):
                continue
            if 0 <= ident < candidates and ident not in taken and len(picks[slot]) < 3:
                taken.add(ident)
                picks[slot].append(ident)
    return picks


def parse_spare(data: dict, picks: List[List[int]], candidates: int) -> List[int]:
    """Zaxira rasmlar: slotlarga tanlanmaganlari, takrorsiz."""
    taken = {ident for slot in picks for ident in slot}
    spare: List[int] = []
    for raw in (data or {}).get("spare") or []:
        try:
            ident = int(raw)
        except (TypeError, ValueError):
            continue
        if 0 <= ident < candidates and ident not in taken:
            taken.add(ident)
            spare.append(ident)
    return spare


# ─────────────────────────────────────────────────────────── yuklab olish

def _save_image(raw: bytes) -> Optional[str]:
    from PIL import Image

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception:
        return None
    if image.width < MIN_WIDTH or not 0.5 <= image.width / max(1, image.height) <= 2.6:
        return None
    if image.mode != "RGB":
        background = Image.new("RGB", image.size, "white")
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        image = background
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    os.makedirs("temp", exist_ok=True)
    path = os.path.join("temp", f"brave_{uuid.uuid4().hex[:12]}.jpg")
    image.save(path, "JPEG", quality=86, optimize=True)
    return path


# Ko'p saytlar (Wikimedia, WordPress hostinglari) bot ko'rinishidagi so'rovni rad etadi.
_DOWNLOAD_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8,*/*;q=0.5",
}


async def _download(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    try:
        async with session.get(url, allow_redirects=True) as resp:
            if resp.status != 200:
                return None
            if "image" not in (resp.headers.get("Content-Type") or "image").lower():
                return None
            # `read(n)` faqat kelib ulgurgan qismni beradi — rasm oxirigacha o'qiladi.
            raw = bytearray()
            async for chunk in resp.content.iter_chunked(64 * 1024):
                raw += chunk
                if len(raw) > MAX_BYTES:
                    return None
    except Exception as exc:
        log.debug("Rasm yuklanmadi (%s): %s", url[:80], exc)
        return None
    return await asyncio.to_thread(_save_image, bytes(raw))


# ─────────────────────────────────────────────────────────── asosiy kirish

async def _pool(topic: str, search=None) -> _Pool:
    """Mavzu natijalari: birinchi murojaatda Brave'ga BITTA so'rov, keyin xotiradan."""
    key = _topic_key(topic)
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        pool = _pools.get(key)
        if pool is not None:
            _pools.move_to_end(key)
            return pool
        try:
            query = await search_query(topic)
            results = await (search or _brave)(query)
            candidates = usable(results)
            log.info("Brave: «%s» → %d natija, %d tasi yaroqli", query, len(results), len(candidates))
        except Exception as exc:
            # Xato ham eslab qolinadi: mavzuga ikkinchi so'rov yuborilmaydi.
            log.warning("Brave qidiruvi ishlamadi (%s): %s", topic[:60], exc)
            candidates = []
        pool = _Pool(candidates)
        _pools[key] = pool
        while len(_pools) > CACHE_TOPICS:
            old, _ = _pools.popitem(last=False)
            _locks.pop(old, None)
        return pool


async def find_photos(topic: str, slots: Sequence[str], *, search=None,
                      choose=None) -> List[Optional[str]]:
    """Har slot (sarlavha/rasm tavsifi) uchun yuklangan rasm yo'li yoki None.

    `search(query)` va `choose(system, user)` — testlarda almashtiriladi.
    """
    result: List[Optional[str]] = [None] * len(slots)
    if not slots or not (topic or "").strip() or (search is None and not enabled()):
        return result
    pool = await _pool(topic, search)
    candidates = [c for c in pool.candidates if c["url"] not in pool.used][:MAX_CANDIDATES]
    if not candidates:
        return result

    try:
        if choose is not None:
            data = await choose(_PICK_SYSTEM, _pick_prompt(topic, slots, candidates))
        else:
            data = await asyncio.to_thread(_ask_json, _PICK_SYSTEM,
                                           _pick_prompt(topic, slots, candidates), 1500)
    except Exception as exc:
        log.warning("AI rasm tanlamadi: %s", exc)
        return result
    picks = parse_picks(data, len(slots), len(candidates))

    timeout = aiohttp.ClientTimeout(total=20, connect=8)
    headers = _DOWNLOAD_HEADERS
    gate = asyncio.Semaphore(4)

    async with aiohttp.ClientSession(timeout=timeout, headers=headers, trust_env=True) as session:
        async def one(slot: int) -> None:
            async with gate:
                for ident in picks[slot]:
                    url = candidates[ident]["url"]
                    if url in pool.used:
                        continue
                    path = await _download(session, url)
                    if path:
                        pool.used.add(url)
                        result[slot] = path
                        return

        await asyncio.gather(*(one(slot) for slot in range(len(slots)) if picks[slot]))

        # Tanlangani yuklanmagan yoki AI bo'sh qoldirgan slotlarga zaxira rasmlar.
        spare = iter(parse_spare(data, picks, len(candidates)))
        for slot in range(len(slots)):
            while result[slot] is None:
                ident = next(spare, None)
                if ident is None:
                    break
                url = candidates[ident]["url"]
                if url in pool.used:
                    continue
                path = await _download(session, url)
                if path:
                    pool.used.add(url)
                    result[slot] = path

    found = sum(1 for path in result if path)
    if found:
        ai_usage.record("photo", ai_usage.PHOTO_SITE, found)
    log.info("Brave rasmlari: %d slotdan %d tasiga topildi", len(slots), found)
    return result
