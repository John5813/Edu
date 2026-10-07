"""Skaner qilingan kitobni (betlar faqat rasm) matnga o'tkazish.

Betlar rasmga aylantirilib ko'rish AI ga beriladi (`llm_client`, `ocr` zanjiri); AI sahifadagi matnni
aynan ko'chiradi. Natija `book_pdf_translate` ishlatadigan abzats ro'yxati bilan bir xil shaklda
(`text`, `page`, `heading`, ...) qaytadi — shuning uchun tayyor DOCX yig'ish, bet oxiridagi abzatsni
ulash va tarjima shu kodning o'zi bilan ishlaydi.

Matn qatlami bor betlar (aralash kitob) AI ga yuborilmaydi: matni to'g'ridan-to'g'ri olinadi — bepul va aniq.
"""
import base64
import io
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

from services import book_pdf_translate as bpt

log = logging.getLogger(__name__)

MAX_SIDE = 1800            # uzun tomon (px): matn o'qiladi, token ko'p ketmaydi
WORKERS = 3                # bir vaqtda nechta bet AI ga ketadi
PAGE_TRIES = 2
EMPTY_MARK = "[bo'sh]"
FIGURE_MARK = "[rasm]"
UNREADABLE_MARK = "[?]"

PROMPT = (
    "Transcribe this scanned book page exactly as printed.\n"
    "Rules:\n"
    "- Output ONLY the page text: no commentary, no code fences, no translation.\n"
    "- Keep the original language and script (Uzbek Latin or Cyrillic, Russian, English, Kazakh, ...). "
    "Keep Uzbek apostrophes in words such as o', g', and special letters (ў, қ, ғ, ҳ, ә, ң, ү, ұ, ө) as printed.\n"
    "- One paragraph per line, paragraphs separated by one blank line. Join lines that were broken only by "
    "the page width, and join words hyphenated at line ends.\n"
    "- Headings (chapter or section titles, short large or bold lines): start the line with '# '.\n"
    "- Tables: one row per line, cells separated by ' | '.\n"
    "- Lists: one item per line, keep the marker (-, •, 1.) at the start.\n"
    "- Skip running headers/footers and page numbers.\n"
    f"- Photos, drawings, diagrams: write {FIGURE_MARK} once where they are (and the printed caption text, if any).\n"
    f"- Unreadable fragment: {UNREADABLE_MARK}. Never guess or invent missing text.\n"
    f"- If the page contains no text at all, output exactly {EMPTY_MARK}.\n"
)

_LETTERS = re.compile(r"[A-Za-zА-Яа-яЁёЎўҚқҒғҲҳӘәІіҢңҮүҰұӨөҺһ]")
_FENCE = re.compile(r"^```[a-z]*\s*|\s*```$", re.IGNORECASE)


class OcrError(bpt.BookTranslateError):
    """Sahifani o'qib bo'lmadi."""


# ───────────────────────────────────────────────────────────── bitta bet

def _jpeg(pixmap) -> bytes:
    from PIL import Image

    image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")
    if max(image.size) > MAX_SIDE:
        image.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=82)
    return out.getvalue()


def render_page(page) -> bytes:
    """Betni JPEG rasmga aylantiradi (uzun tomoni `MAX_SIDE` dan oshmaydi)."""
    import pymupdf

    longest = max(page.rect.width, page.rect.height) or 842
    zoom = max(1.0, min(3.0, MAX_SIDE / longest * 1.15))
    return _jpeg(page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False))


def _ask(image: bytes) -> str:
    from services.premium_presentation import llm_client

    payload = {"temperature": 0.0, "max_tokens": 3500,
               "messages": [{"role": "user", "content": [
                   {"type": "text", "text": PROMPT},
                   {"type": "image_url", "image_url": {
                       "url": "data:image/jpeg;base64," + base64.b64encode(image).decode()}}]}]}
    data = llm_client._request("ocr", payload, timeout=150)
    return llm_client._content(data)


def read_image(image: bytes) -> str:
    """Bitta bet rasmini matnga o'giradi (ikki urinish). Mablag' tugasa `BookNoCredits`."""
    from services.premium_presentation import llm_client

    last: Optional[Exception] = None
    for _ in range(PAGE_TRIES):
        try:
            return _clean(_ask(image))
        except llm_client.NoCredits as exc:
            raise bpt.BookNoCredits(str(exc)) from exc
        except Exception as exc:                      # tarmoq yoki bo'sh javob: yana bir urinish
            last = exc
            log.warning("OCR urinishi muvaffaqiyatsiz: %s", exc)
    raise OcrError(str(last or "bo'sh javob"))


def _clean(raw: str) -> str:
    text = _FENCE.sub("", (raw or "").strip()).strip()
    return "" if text == EMPTY_MARK else text


# ───────────────────────────────────────────────────────────── tahlil

def parse_page(text: str, page: int) -> List[dict]:
    """AI matnini abzatslarga ajratadi: `# ` — sarlavha, ` | ` — jadval qatori, bo'sh qator — abzats chegarasi."""
    items: List[dict] = []
    block: List[str] = []

    def push(body: str, heading: bool = False, table: bool = False) -> None:
        body = re.sub(r"\s+", " ", body).strip() if not table else body.strip()
        if not body:
            return
        items.append({"text": body, "page": page, "heading": heading, "small": False, "italic": False,
                      "translate": bool(_LETTERS.search(body)) and body not in (FIGURE_MARK, UNREADABLE_MARK)})

    def flush() -> None:
        if block:
            push(" ".join(block))
            block.clear()

    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
        elif stripped.startswith("#"):
            flush()
            push(stripped.lstrip("# ").strip(), heading=True)
        elif " | " in stripped or re.match(r"^[-•*–—]\s+|^\d+[.)]\s+", stripped):
            flush()                                           # jadval qatori yoki ro'yxat bandi — alohida
            push(stripped, table=True)
        else:
            if block and block[-1].endswith(("-", "­")) and not block[-1].endswith(" -"):
                block[-1] = block[-1].rstrip("-­")       # so'z bo'g'inidan uzilgan: ulab yoziladi
                block.append("\x00" + stripped)
            else:
                block.append(stripped)
    flush()
    for item in items:
        item["text"] = item["text"].replace(" \x00", "").replace("\x00", "")
    return items


# ───────────────────────────────────────────────────── butun qism (bir necha bet)

def read_pages(src: str, start: int, stop: int, source_lang: str = "ru") -> Tuple[List[dict], List[int]]:
    """[start, stop) betlarni o'qiydi. Qaytadi: (abzatslar, o'qib bo'lmagan betlar raqami, 1 dan).

    Matn qatlami bor betlar AI siz olinadi. Blokirovka qiluvchi funksiya: `asyncio.to_thread` bilan chaqiring.
    """
    doc = bpt._open(src)
    jobs: List[Tuple[int, str, object]] = []
    try:
        stop = min(stop, doc.page_count)
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for number in range(start, stop):
                page = doc[number]
                if not bpt._page_is_scanned(page) and len(page.get_text("text").strip()) >= 40:
                    jobs.append((number, "layer", None))
                else:
                    jobs.append((number, "ai", pool.submit(read_image, render_page(page))))
            results = []
            for number, kind, future in jobs:
                if kind == "layer":
                    results.append((number, kind, None))
                else:
                    try:
                        results.append((number, kind, future.result()))
                    except bpt.BookNoCredits:
                        raise
                    except Exception as exc:
                        log.warning("%d-bet o'qilmadi: %s", number + 1, exc)
                        results.append((number, kind, None))
    finally:
        doc.close()

    items: List[dict] = []
    failed: List[int] = []
    for number, kind, text in results:
        if kind == "layer":
            items.extend(bpt.extract_paragraphs(src, number, number + 1, source_lang))
        elif text is None:
            failed.append(number + 1)
            items.append({"text": f"[{number + 1}-bet o'qib bo'lmadi]", "page": number, "heading": False,
                          "small": True, "italic": True, "translate": False})
        else:
            items.extend(parse_page(text, number))
    return items, failed


_UZ_WORDS = re.compile(r"\b(va|bilan|uchun|ham|bo['ʻ’‘`]?lib|yoki|kerak|bo['ʻ’‘`]?ladi|qilish|lekin|degan)\b", re.IGNORECASE)
_UZ_LETTERS = re.compile(r"\b\w*[oOgG]['ʻ’‘`]\w*", re.UNICODE)


def guess_language(items: List[dict]) -> str:
    """O'qilgan matn tili (tarjima uchun): uz (lotin) / ru / en / kk."""
    sample = " ".join(i["text"] for i in items[:200])[:20000]
    lang = bpt.detect_language(sample)
    if lang == "en" and len(_UZ_WORDS.findall(sample)) + len(_UZ_LETTERS.findall(sample)) >= max(5, len(sample) // 800):
        return "uz"
    return lang
