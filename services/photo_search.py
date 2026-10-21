"""Slayd rasmlarini internetdan (Brave Image Search) topadi.

Qoida: bitta mavzu uchun Brave'ga faqat BITTA so'rov yuboriladi (200 ta
natija). Mavhum/futuristik mavzular AI bilan chizishga yo'naltiriladi;
haqiqiy foto kerak bo'lgan mavzularda qidiruv tili mavzuga qarab tanlanadi:

    1. Tarix va madaniyatda mahalliy til, global texnologiyada odatda inglizcha so'rov.
    2. Brave bitta so'rov bilan 200 tagacha rasm beradi; stok saytlar
       (suv belgili), do'konlar va kichik rasmlar olib tashlanadi.
    3. AI sarlavhalar va rasm nomlarini ko'rib, har slaydga mos rasmlarni
       tanlaydi (bir rasm — bitta slaydga).
    4. Tanlangan rasm yuklab olinadi, tekshiriladi va crop uchun fokus aniqlanadi.

Topilmagan slaydga hech narsa qaytarilmaydi — uni chaqiruvchi AI bilan
chizdiradi. Mavzu natijalari xotirada saqlanadi: o'sha mavzuga keyingi
murojaat (muqova, slaydni qayta yaratish, boshqa mijoz) Brave'ga yangi
so'rov yubormaydi va oldin ishlatilgan rasmlarni qayta bermaydi.
"""
import asyncio
import contextlib
import functools
import io
import json
import logging
import os
import re
import time
import uuid
from collections import OrderedDict
from typing import Dict, List, Optional, Sequence, Tuple
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
_BRAVE_SEARCH_LANGS = frozenset({
    "ar", "bg", "ca", "cs", "da", "de", "el", "en", "es", "et", "fi", "fr",
    "he", "hr", "hu", "id", "it", "ja", "ko", "lt", "lv", "nb", "nl", "pl",
    "pt-br", "pt-pt", "ro", "ru", "sk", "sl", "sr", "sv", "th", "tr", "uk",
    "vi", "zh-hans", "zh-hant",
})
_AI_FIRST_TOPIC = re.compile(
    r"\b(?:AI|artificial intelligence|machine learning|deep learning|neural network|"
    r"sun['’]?iy intellekt\w*|mashinaviy o['’]?rganish\w*|neyron tarmoq\w*|"
    r"искусственн\w+ интеллект\w*|нейросет\w*|машинн\w+ обучен\w*|"
    r"internet\w*|internet of things|cyber ?security|cyberspace|cloud computing|"
    r"virtual reality|augmented reality|metaverse|robotics|robototexnika|"
    r"kelajak texnolog\w*|future technolog\w*|digital transformation|"
    r"космос\w*|cosmos\w*|outer space|space exploration|space\w*|koinot\w*|kosmos\w*|"
    r"futuristic|kelajak shah\w*|future cit\w*)\b",
    re.IGNORECASE,
)

# Suv belgili stok saytlar, do'konlar va sifatsiz manbalar.
_BLOCKED = (
    "gettyimages", "istockphoto", "shutterstock", "alamy", "dreamstime", "123rf",
    "depositphotos", "stock.adobe", "adobestock", "vecteezy", "freepik", "canstockphoto",
    "bigstockphoto", "agefotostock", "superstock", "pond5", "colourbox", "stockfresh",
    "shootplanet", "amazon.", "ebay.", "aliexpress", "etsy.", "walmart.", "temu.",
    "pinimg.com", "pinterest.", "lookaside.fbsbx", "fbcdn", "instagram",
    # Slayd, hujjat va konspekt saytlari: rasmlari — birovning taqdimoti yoki matnli bet.
    "slideplayer", "slideshare", "slideserve", "slidetodoc", "slidesgo", "pdfslide", "scribd", "docplayer",
    "studfile", "studylib", "studopedia", "myshared", "present5", "ppt-online", "coursehero", "quizlet",
    "vdocuments", "fliphtml5", "issuu", "yumpu", "dokumen.pub", "prezi.", "academia.edu", "researchgate",
    "semanticscholar", "infourok", "multiurok", "nsportal", "znanio", "videouroki", "showme.", "brainly",
    # O'zbek taqdimot, referat va konspekt saytlari: o'zbekcha mavzuda Brave birinchi navbatda shularni
    # beradi — rasmlari tayyor slaydlar va hujjat betlari (soff.uz «OFF» suv belgisi bilan).
    "soff.uz", "arxiv.uz", "slaydchi", "slayd", "referat", "hozir.org", "fayllar.org", "kompy.info",
    "denemetr", "ziyonet", "ziyouz", "kitobxon", "mustaqil-ish", "mustaqilish", "kurs-ishi", "kursishi",
    # Ilmiy jurnallar: rasmlari — grafik, jadval va sxemalar ("Figure 2").
    "ncbi.nlm.nih.gov", "europepmc", "sciencedirect", "elsevier", "springer", "wiley.com", "tandfonline",
    "frontiersin", "mdpi.com", "jacc.org", "ahajournals", "bmj.com", "thelancet", "nejm.org", "plos",
    "revportcardiol", "cureus", "hindawi", "karger", "sagepub", "oup.com", "biomedcentral", "jamanetwork",
)
_BAD_EXT = (".svg", ".gif", ".ico")
# Sarlavhasi shunday so'zli natija — slayd, jadval, sxema yoki matnli bet bo'lishi ehtimoli katta.
_TEXTY = re.compile(
    r"(?<![a-z])(?:slides?|figs?|figures?|ppt|pptx|powerpoint|presentation|lecture|chart|diagram|infographic|table|"
    r"graph|flowchart|worksheet|poster|quote|screenshot|text|template|slayd|taqdimot|jadval|sxema|"
    r"слайд\w*|презентац\w*|лекци\w*|схем\w*|таблиц\w*|диаграмм\w*|инфографи\w*|"
    r"referat\w*|реферат\w*|konspekt\w*|конспект\w*|mustaqil ish\w*|kurs ishi|pdf|docx?|document\w*)(?![a-z])",
    re.IGNORECASE)
# Rasm manzilidagi sahifa belgisi: ".../file-46759_page-5_generate.jpg", ".../slide12.png" — hujjat yoki
# taqdimotning bitta beti.
_PAGE_URL = re.compile(r"(?:^|[/_.-])(?:page|slide|sahifa|list)[-_]?\d+(?![a-z])", re.IGNORECASE)


def api_key() -> str:
    """Hozirgi Brave kaliti: bir nechta kalit navbat bilan (`services/brave_keys.py`, admin panelda qo'shiladi)."""
    from services import brave_keys

    return brave_keys.current()


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


def prefer_ai(topic: str) -> bool:
    """Mavhum/futuristik mavzuda, odatiy mix rejimida, AI tasvirini ustun ko'radi."""
    return bool(_AI_FIRST_TOPIC.search(topic or ""))


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


# Aniq fanlar (formulalar ruxsat): faqat slayd, ma'ruza va shablon tashlanadi — formula, grafik, sxema qoladi.
_TEXTY_SLIDES = re.compile(
    r"(?<![a-z])(?:slides?|ppt|pptx|powerpoint|presentation|lecture|screenshot|template|worksheet|poster|"
    r"slayd|taqdimot|слайд\w*|презентац\w*|лекци\w*)(?![a-z])", re.IGNORECASE)


def usable(results: Sequence[dict], formulas: bool = False) -> List[dict]:
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
        if _PAGE_URL.search(url):
            continue
        if (_TEXTY_SLIDES if formulas else _TEXTY).search(f"{item.get('title') or ''} {_slug(str(item.get('url') or ''))}"):
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


async def _brave(query: str, search_lang: str = "") -> List[dict]:
    """Brave so'rovi. Kalit rad etilsa (401/403/429) — navbatdagi kalit bilan yana urinadi."""
    from services import brave_keys

    params = {"q": query, "count": str(RESULTS), "safesearch": "strict"}
    if search_lang in _BRAVE_SEARCH_LANGS:
        params["search_lang"] = search_lang
    timeout = aiohttp.ClientTimeout(total=20)
    tried = set()
    while True:
        key = brave_keys.take()
        if not key or key in tried:
            raise RuntimeError("Brave: ishlaydigan kalit qolmadi")
        tried.add(key)
        headers = {"Accept": "application/json", "X-Subscription-Token": key}
        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            async with session.get(BRAVE_URL, params=params, headers=headers) as resp:
                if resp.status in (401, 403, 429):
                    brave_keys.report_failure(key, resp.status)
                    log.warning("Brave kaliti %s rad etildi (HTTP %s) — keyingisi", brave_keys.mask(key), resp.status)
                    continue
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
    "Create ONE short image-search query (2-6 words) for REAL photographs relevant to a "
    "presentation topic. Choose the query language based on where the best photographs are "
    "likely to exist, not by blindly translating everything into English. For people, history, "
    "culture, places, and regional topics, search in the language/script of that culture when "
    "it is likely to find more authentic local photos (e.g. Amir Temur: Uzbek; Ottoman/Turkish "
    "history: Turkish; Chinese history: Chinese; Mongolian history: Mongolian). Keep names in "
    "their locally used form/script. For globally shared technology or science (AI, internet, "
    "space), use English unless the topic is explicitly regional. For Uzbek or Mongolian, use "
    "the actual local-language query even though Brave may not support a search_lang filter. "
    "Set search_lang only to one of: ar, bg, ca, cs, da, de, el, en, es, et, fi, fr, he, hr, "
    "hu, id, it, ja, ko, lt, lv, nb, nl, pl, pt-br, pt-pt, ro, ru, sk, sl, sr, sv, th, tr, "
    "uk, vi, zh-hans, zh-hant; otherwise use an empty string. Avoid words that return text "
    "artifacts: presentation, slide, map, diagram, chart, infographic, table, poster. "
    "Answer JSON: {\"query\": \"...\", \"search_lang\": \"...\"}"
)


async def search_plan(topic: str) -> Tuple[str, str]:
    """Mavzuga mos qidiruv iborasi va Brave qo'llaydigan til filtri."""
    try:
        data = await asyncio.to_thread(_ask_json, _QUERY_SYSTEM, f"Topic: {topic}", 200)
        query = re.sub(r"\s+", " ", str((data or {}).get("query") or "")).strip(" \"'.")
        search_lang = str((data or {}).get("search_lang") or "").strip().lower()
        if 2 <= len(query) <= 80:
            return query, search_lang if search_lang in _BRAVE_SEARCH_LANGS else ""
    except Exception as exc:
        log.warning("Rasm qidiruv rejasi tuzilmadi: %s", exc)
    return topic.strip()[:80], ""


async def search_query(topic: str) -> str:
    """Mavzu uchun qidiruv iborasi (eski chaqiruvchilar bilan moslik)."""
    query, _ = await search_plan(topic)
    return query


@functools.lru_cache(maxsize=512)
def _face_focus(path: str) -> Optional[Tuple[float, float]]:
    """Suratdagi yuz(lar) markazini qaytaradi; topilmasa None."""
    try:
        import cv2

        image = cv2.imread(path)
        if image is None:
            return None
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        scale = min(1.0, 1200 / max(image.shape[:2]))
        if scale < 1:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        detector = cv2.CascadeClassifier(cascade_path)
        if detector.empty():
            log.warning("Yuz aniqlash modeli yuklanmadi: %s", cascade_path)
            return None
        faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                          minSize=(max(24, gray.shape[1] // 40),) * 2)
        if len(faces):
            weighted_x = weighted_y = total = 0.0
            for x, y, width, height in faces:
                weight = float(width * height)
                weighted_x += (x + width / 2) * weight
                weighted_y += (y + height / 2) * weight
                total += weight
            return (min(1.0, max(0.0, weighted_x / total / gray.shape[1])),
                    min(1.0, max(0.0, weighted_y / total / gray.shape[0])))
    except Exception as exc:
        log.debug("Rasm fokusini aniqlab bo'lmadi (%s): %s", path, exc)
    return None


def focal_point(path: str, default_y: float = 0.4) -> Tuple[float, float]:
    """Rasmning kesishda saqlanishi kerak bo'lgan nuqtasi (x, y), 0..1 oralig'ida."""
    return _face_focus(os.path.abspath(path)) or (0.5, min(1.0, max(0.0, default_y)))


def crop_margins(image_width: int, image_height: int, box_width: float, box_height: float,
                 focus_x: float = 0.5, focus_y: float = 0.4) -> tuple:
    """Rasmni cho'zmasdan box nisbatiga kesish uchun (left, right, top, bottom) ulushlari."""
    if image_width <= 0 or image_height <= 0 or box_width <= 0 or box_height <= 0:
        return 0.0, 0.0, 0.0, 0.0
    focus_x = min(1.0, max(0.0, float(focus_x)))
    focus_y = min(1.0, max(0.0, float(focus_y)))
    image_ratio, box_ratio = image_width / image_height, box_width / box_height
    if image_ratio > box_ratio:
        keep = box_ratio / image_ratio
        left = min(1.0 - keep, max(0.0, focus_x - keep / 2))
        return left, 1.0 - keep - left, 0.0, 0.0
    if image_ratio < box_ratio:
        keep = image_ratio / box_ratio
        top = min(1.0 - keep, max(0.0, focus_y - keep / 2))
        return 0.0, 0.0, top, 1.0 - keep - top
    return 0.0, 0.0, 0.0, 0.0


def object_position(path: str, box_ratio: float) -> str:
    """CSS object-position: fokusni qirqish oynasiga markazlaydi."""
    from PIL import Image

    with Image.open(path) as image:
        width, height = image.size
    focus_x, focus_y = focal_point(path)
    margins = crop_margins(width, height, box_ratio, 1.0, focus_x, focus_y)
    left, _, top, _ = margins
    if width / height > box_ratio:
        keep = box_ratio / (width / height)
        x_pos = left / max(1e-9, 1.0 - keep)
        y_pos = 0.5
    elif width / height < box_ratio:
        keep = (width / height) / box_ratio
        x_pos = 0.5
        y_pos = top / max(1e-9, 1.0 - keep)
    else:
        x_pos = y_pos = 0.5
    return f"{x_pos * 100:.1f}% {y_pos * 100:.1f}%"


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
    "- NEVER pick anything that is likely to contain text: presentation slides or slide "
    "screenshots, document or book pages, tables, charts, diagrams, infographics, posters, "
    "book covers, screenshots, quotes. Also skip products for sale, logos, video games, "
    "memes and other topics. Pick real photographs only.\n"
    "- Every id may be used only once in the whole answer.\n"
    "- Leave a slot empty only when no remaining result is about the topic at all.\n"
    "Answer JSON: {\"picks\": [{\"slot\": 1, \"ids\": [12, 40]}, ...], \"spare\": [3, 7]}"
)


_PICK_FORMULAS = ("Exception for this exact-science presentation: images with formulas, equations, graphs, "
                  "geometric figures and scientific diagrams ARE allowed and welcome; still never pick slides, "
                  "document pages, screenshots or posters.")


def _pick_prompt(topic: str, slots: Sequence[str], candidates: Sequence[dict], formulas: bool = False) -> str:
    lines = [f"Presentation topic: {topic}"] + ([_PICK_FORMULAS] if formulas else []) + ["", "Slots:"]
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


# ───────────────────────────────────────────── matnli rasmni ko'z bilan tekshirish

_TEXT_CHECK = (
    "You screen web images before they are placed on presentation slides as PHOTOS. Judge EACH numbered image "
    "on its own. REJECT it if ANY of these is true: it is a presentation slide, a slide thumbnail or a grid of "
    "slides (even with a nice picture on it); it is a document, book, textbook or scanned page, or a photo or "
    "screenshot of one (even if only part of the page is visible); it has a heading, title, caption, label, "
    "bullet list or sentence written ON it that a viewer can read, in any language; it is a poster, banner, "
    "advert, product package, logo, certificate, infographic, chart, table, labelled map or diagram; it has a "
    "website watermark or a site name stamped on it. ACCEPT only real photographs (or plain illustrations) with "
    "no readable text, or where text is tiny and incidental (a distant street sign, a number plate). "
    "For every image first say in a few words what you see, then give the verdict. Answer JSON: "
    "{\"images\": [{\"n\": 1, \"see\": \"...\", \"verdict\": \"accept\" or \"reject\"}]}"
)


_TEXT_CHECK_FORMULAS = (
    "You check images for a math/physics/computer-science presentation. Formulas, equations, graphs, geometric "
    "figures and labelled scientific diagrams are WELCOME. Judge EACH numbered image on its own: REJECT it if it "
    "is a screenshot of a presentation slide, a document or book page, a website, a poster, a worksheet, or "
    "mostly paragraphs of prose text, or has a text watermark, OR is a video thumbnail / ad / banner with a big "
    "headline (e.g. \"How to Solve ...\"), a brand or school logo, or text cut off at the image edge. "
    "For every image first say in a few words what you see, then give the verdict. Answer JSON: "
    "{\"images\": [{\"n\": 1, \"see\": \"...\", \"verdict\": \"accept\" or \"reject\"}]}"
)

# Bitta so'rovdagi rasmlar soni: ko'p rasmni birga ko'rganda model raqamlarni adashtirib, matnli
# varaqni o'tkazib yuborardi.
CHECK_BATCH = 4


def _thumb_b64(path: str) -> str:
    import base64

    from PIL import Image

    with Image.open(path) as image:
        image = image.convert("RGB")
        # Hujjat betidagi mayda yozuv ham o'qilsin (640 da xira bo'lib, "foto" deb o'tib ketardi).
        image.thumbnail((896, 896))
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=82)
    return base64.b64encode(buffer.getvalue()).decode()


def parse_rejects(data: dict, count: int) -> set:
    """Model javobi → rad etilgan rasmlar (0 dan). `{"images": [{n, verdict}]}` va eski `{"reject": [...]}`.

    Hukmi yo'q rasm ham rad etiladi: model uni ko'rmay qolgan bo'lsa, matnli varaq o'tib ketmasin.
    """
    out, judged = set(), set()
    data = data or {}
    for item in data.get("images") or []:
        try:
            number = int(item.get("n"))
        except (TypeError, ValueError, AttributeError):
            continue
        if not 1 <= number <= count:
            continue
        judged.add(number - 1)
        if str(item.get("verdict") or "").strip().lower() != "accept":
            out.add(number - 1)
    if "images" in data:
        return out | (set(range(count)) - judged)
    for value in data.get("reject") or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= number <= count:
            out.add(number - 1)
    return out


def _ask_text_check(paths: Sequence[str], formulas: bool = False) -> set:
    from services.premium_presentation import llm_client

    out = set()
    for start in range(0, len(paths), CHECK_BATCH):
        batch = paths[start:start + CHECK_BATCH]
        content = [{"type": "text", "text": _TEXT_CHECK_FORMULAS if formulas else _TEXT_CHECK}]
        for number, path in enumerate(batch, 1):
            content.append({"type": "text", "text": f"Image {number}:"})
            content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + _thumb_b64(path)}})
        payload = {"temperature": 0.0, "max_tokens": 120 + 80 * len(batch),
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "user", "content": content}]}
        # "photocheck" — qat'iy model zanjiri (config.PHOTO_TEXT_CHECK_MODELS), admin tanlovi ta'sir qilmaydi.
        raw = llm_client._content(llm_client._request("photocheck", payload, timeout=90))
        data = json.loads(llm_client._clean_json(raw))
        out |= {start + index for index in parse_rejects(data, len(batch))}
    return out


# ───────────────────────────── matnli varaqni bepul, mahalliy aniqlash (AI so'rovidan oldin)

def text_lines(path: str) -> Tuple[int, float]:
    """Rasmdagi matn qatorlari: (soni, rasm yuzasidan ulushi). O'qib bo'lmasa — (0, 0).

    Harflar chegarasi (morfologik gradient) gorizontal yopishtiriladi: matn qatori uzun, past va
    "zich-siyrak" to'g'ri to'rtburchak bo'lib chiqadi. Fotoda bunday bir xil qatorlar deyarli bo'lmaydi.
    """
    try:
        import cv2
    except ImportError:
        return 0, 0.0
    image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if image is None:
        return 0, 0.0
    height, width = image.shape
    scale = 900 / max(height, width)
    image = cv2.resize(image, (max(1, int(width * scale)), max(1, int(height * scale))),
                       interpolation=cv2.INTER_AREA)
    height, width = image.shape
    grad = cv2.morphologyEx(image, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    _, edges = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    joined = cv2.morphologyEx(edges, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (max(9, width // 60), 1)))
    count, _, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    lines, area = 0, 0
    for x, y, w, h, _ in stats[1:count]:
        if not height * 0.008 <= h <= height * 0.06 or w < width * 0.06 or w < h * 3.5:
            continue
        fill = cv2.countNonZero(edges[y:y + h, x:x + w]) / float(w * h)
        if 0.2 <= fill <= 0.75:
            lines += 1
            area += w * h
    return lines, area / float(width * height)


def looks_like_text_page(path: str, formulas: bool = False) -> bool:
    """Slayd yoki hujjat beti: kamida 6 qator matn va u rasmning 5 % idan ko'pini egallaydi.

    Chegaralar soff.uz / arxiv.uz slaydlari, hujjat betlari va yangilik fotolari ustida tanlangan:
    fotolar (o'rmon, shahar, odamlar) chegaradan ancha past. Aniq fanlarda formulali rasm ruxsat —
    u yerda faqat zich matnli bet (hujjat, konspekt) tashlanadi.
    """
    lines, share = text_lines(path)
    if formulas:
        return lines >= 10 and share >= 0.15
    return lines >= 6 and share >= 0.05


async def text_heavy(paths: Sequence[str], check=None, formulas: bool = False) -> set:
    """Matnli (slayd, jadval, sxema, yozuvli) rasmlarning tartib raqamlari.

    Avval bepul mahalliy tekshiruv (`looks_like_text_page`): yaqqol slayd va hujjat betlari AI ga
    yuborilmay tashlanadi. Qolganini ko'rish modeli (qat'iy zanjir) ko'radi. Tekshiruv ishlamasa —
    HAMMASI rad etiladi (fail-closed): matnli skrinshot ko'z bilan tekshirilmay slaydga tushib qolmasin.
    Slotlar AI rasmi bilan to'ldiriladi.
    """
    if not paths:
        return set()
    paths = list(paths)
    local = await asyncio.to_thread(lambda: {i for i, p in enumerate(paths) if looks_like_text_page(p, formulas)})
    rest = [i for i in range(len(paths)) if i not in local]
    if local:
        log.info("Matnli varaq (mahalliy tekshiruv): %d ta", len(local))
    if not rest:
        return local
    try:
        if check is not None:
            bad = set(await check([paths[i] for i in rest]))
        else:
            bad = await asyncio.to_thread(_ask_text_check, [paths[i] for i in rest], formulas)
    except Exception as exc:
        log.warning("Rasmdagi matn tekshirilmadi — hammasi tashlandi: %s", exc)
        return set(range(len(paths)))
    return local | {rest[k] for k in bad if 0 <= k < len(rest)}


# ─────────────────────────────────────────────────────────── asosiy kirish

async def _pool(topic: str, search=None, formulas: bool = False) -> _Pool:
    """Mavzu natijalari: birinchi murojaatda Brave'ga BITTA so'rov, keyin xotiradan."""
    key = _topic_key(topic)
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        pool = _pools.get(key)
        if pool is not None:
            _pools.move_to_end(key)
            return pool
        try:
            query, search_lang = await search_plan(topic)
            results = (await search(query) if search is not None
                       else await _brave(query, search_lang))
            candidates = usable(results, formulas)
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
                      choose=None, check=None, formulas: bool = False) -> List[Optional[str]]:
    """Har slot (sarlavha/rasm tavsifi) uchun yuklangan rasm yo'li yoki None.

    `search(query)`, `choose(system, user)` va `check(paths)` (matnli rasmlar) — testlarda almashtiriladi.
    `formulas` — aniq fanlar: formulali, grafikli rasmlar ruxsat (slayd va hujjat skrinshotlari baribir yo'q).
    """
    result: List[Optional[str]] = [None] * len(slots)
    if not slots or not (topic or "").strip() or (search is None and not enabled()):
        return result
    pool = await _pool(topic, search, formulas)
    candidates = [c for c in pool.candidates if c["url"] not in pool.used][:MAX_CANDIDATES]
    if not candidates:
        return result

    try:
        if choose is not None:
            data = await choose(_PICK_SYSTEM, _pick_prompt(topic, slots, candidates, formulas))
        else:
            data = await asyncio.to_thread(_ask_json, _PICK_SYSTEM,
                                           _pick_prompt(topic, slots, candidates, formulas), 1500)
    except Exception as exc:
        log.warning("AI rasm tanlamadi: %s", exc)
        return result
    picks = parse_picks(data, len(slots), len(candidates))

    timeout = aiohttp.ClientTimeout(total=20, connect=8)
    gate = asyncio.Semaphore(4)
    queues = [list(picks[slot]) for slot in range(len(slots))]
    spare = parse_spare(data, picks, len(candidates))

    async def next_photo(session, slot: int) -> Optional[str]:
        """Slotning navbatdagi nomzodi (avval o'z tanlovi, keyin zaxira) — yuklangan fayl yoki None."""
        while queues[slot] or spare:
            ident = queues[slot].pop(0) if queues[slot] else spare.pop(0)
            url = candidates[ident]["url"]
            if url in pool.used:
                continue
            pool.used.add(url)
            async with gate:
                path = await _download(session, url)
            if path:
                return path
        return None

    # Yuklangan rasmlar ko'z bilan tekshiriladi: ichida matn, jadval, sxema yoki slayd bo'lsa tashlanadi va
    # slotga navbatdagi nomzod olinadi (3 davragacha). Qolgan bo'sh slotni AI chizadi.
    async with aiohttp.ClientSession(timeout=timeout, headers=_DOWNLOAD_HEADERS, trust_env=True) as session:
        for _ in range(3):
            empty = [slot for slot in range(len(slots)) if result[slot] is None and (queues[slot] or spare)]
            if not empty:
                break
            got = await asyncio.gather(*(next_photo(session, slot) for slot in empty))
            fresh = [(slot, path) for slot, path in zip(empty, got) if path]
            if not fresh:
                break
            bad = await text_heavy([path for _, path in fresh], check, formulas)
            for k, (slot, path) in enumerate(fresh):
                if k in bad:
                    with contextlib.suppress(OSError):
                        os.remove(path)
                else:
                    result[slot] = path
            if bad:
                log.info("Matnli %d ta rasm tashlandi", len(bad))

    found = sum(1 for path in result if path)
    if found:
        ai_usage.record("photo", ai_usage.PHOTO_SITE, found)
    log.info("Brave rasmlari: %d slotdan %d tasiga topildi", len(slots), found)
    return result
