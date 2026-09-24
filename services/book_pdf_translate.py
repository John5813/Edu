"""Katta PDF kitobni joyida tarjima qilish — rasmlar o'z o'rnida qoladi.

Kitobning og'irligi deyarli butunlay rasmlarda: 226 betlik darslik 38 MB,
lekin undagi matn bir-ikki megabayt xolos. Ilgari PDF avval `pdf2docx`
bilan Word'ga aylantirilardi (yuzlab betda juda sekin va xotirani yeydi),
keyin tarjima yangi, bo'sh hujjatga yozilardi — rasmlar umuman tushib
qolardi. Tibbiyot darsligida esa rasmlarsiz matnning qadri yo'q.

Bu yerda PDF ning o'zi tahrirlanadi:

  1. har betdagi matn bloklari o'rni, shrifti, rangi bilan olinadi;
  2. bloklar bo'laklarga bo'linib, bir necha so'rov parallel tarjima qilinadi;
  3. asl matn faqat matn qatlamidan o'chiriladi (rasm va chiziqlarga
     tegilmaydi) va tarjima o'sha to'rtburchakka yoziladi — sig'masa
     pastdagi bo'sh joyga cho'ziladi, baribir sig'masa shrift kichrayadi;
  4. rasmlar o'qish uchun yetarli aniqlikka (150 dpi) siqiladi — fayl
     bir necha barobar yengillashadi, telefonda farqi ko'rinmaydi.

Tarjima qilinmay qolgan blok (model javob bermasa) asl holida qoladi —
bitta muvaffaqiyatsiz so'rov butun kitobni yiqitmaydi.
"""

import asyncio
import html
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List, Optional

from config import TEMP_DIR

logger = logging.getLogger(__name__)

# Bitta so'rovga ketadigan matn hajmi (belgi). Kattaroq bo'lsa model
# bo'laklarni tashlab ketishi yoki javob uzilib qolishi ehtimoli oshadi.
BATCH_CHARS = 7000
# Bir kitob uchun bir vaqtdagi so'rovlar.
CONCURRENCY = 5
# Bir vaqtda nechta kitob tarjima qilinadi: har biri o'nlab so'rov yuboradi.
_JOBS = asyncio.Semaphore(2)

# Shundan kichik matn (izoh belgilari va h.k.) tegilmaydi.
MIN_FONT = 4.0
# Siqilgan rasm aniqligi. 150 dpi — ekranda va oddiy chop etishda yetarli.
IMAGE_DPI = 150
IMAGE_QUALITY = 78

_CYRILLIC = re.compile(r"[а-яёА-ЯЁўқғҳЎҚҒҲ]")
_LATIN = re.compile(r"[A-Za-z]")
_LETTER = re.compile(r"[^\W\d_]")
_BULLET = re.compile(r"^\s*(?:[•●▪■◦\-–—*]|\d{1,3}[.)]|[а-яa-z][.)])\s")
_MARK = re.compile(r"\[\[(\d+)\]\]")

LANG_NAMES = {"uz": "Uzbek (Latin script)", "ru": "Russian", "en": "English"}


class BookTranslateError(RuntimeError):
    """Kitobni tarjima qilib bo'lmadi (mijozga umumiy xato aytiladi)."""


class BookNoCredits(BookTranslateError):
    """OpenRouter hisobida mablag' tugagan — qolgan so'rovlar ham yiqiladi."""


class ScannedBook(BookTranslateError):
    """Kitob skaner qilingan: matn qatlami yo'q, faqat rasm."""


@dataclass
class BookInfo:
    total_pages: int
    text_pages: int
    scanned_pages: int
    words: int
    chars: int
    source_lang: str

    @property
    def is_scanned(self) -> bool:
        """Betlarning ko'pchiligi matnsiz rasm — tarjimaga OCR kerak."""
        if not self.total_pages:
            return False
        return self.scanned_pages > max(3, self.total_pages * 0.4)


@dataclass
class Block:
    page: int
    rect: tuple
    paragraphs: List[str]
    size: float
    color: str
    bold: bool
    italic: bool
    serif: bool
    align: str
    segments: List[int] = field(default_factory=list)


@dataclass
class TranslateResult:
    path: str
    pages: int
    blocks: int
    failed: int
    size: int

    @property
    def failed_share(self) -> float:
        return self.failed / self.blocks if self.blocks else 0.0


# ─────────────────────────────────────────────── PDF ni o'qish

def _open(path: str):
    import pymupdf

    return pymupdf.open(path)


def _page_is_scanned(page) -> bool:
    """Matni deyarli yo'q, lekin betning katta qismini rasm egallagan."""
    if len(page.get_text("text").strip()) >= 40:
        return False
    area = abs(page.rect)
    covered = 0.0
    for info in page.get_image_info():
        covered += abs(page.rect & info["bbox"])
    return area > 0 and covered / area > 0.5


def detect_language(text: str) -> str:
    sample = text[:20000]
    cyr = len(_CYRILLIC.findall(sample))
    lat = len(_LATIN.findall(sample))
    return "ru" if cyr > lat else "en"


def inspect_pdf(path: str, page_from: int = None, page_to: int = None) -> BookInfo:
    """Kitob haqida tezkor ma'lumot: betlar, so'zlar, til, skanermi."""
    doc = _open(path)
    try:
        start, stop = _range(doc.page_count, page_from, page_to)
        words = chars = text_pages = scanned = 0
        sample = []
        for number in range(start, stop):
            page = doc[number]
            text = page.get_text("text")
            if text.strip():
                text_pages += 1
            if _page_is_scanned(page):
                scanned += 1
            words += len(text.split())
            chars += len(text)
            if len(sample) < 40:
                sample.append(text)
        return BookInfo(total_pages=stop - start, text_pages=text_pages,
                        scanned_pages=scanned, words=words, chars=chars,
                        source_lang=detect_language(" ".join(sample)))
    finally:
        doc.close()


def _range(count: int, page_from: Optional[int], page_to: Optional[int]) -> tuple:
    start = max(1, int(page_from or 1)) - 1
    stop = min(count, int(page_to or count))
    return start, max(start, stop)


def _hex(color: int) -> str:
    return f"#{int(color) & 0xFFFFFF:06x}"


def _is_serif(span: dict) -> bool:
    name = (span.get("font") or "").lower()
    if any(word in name for word in ("times", "serif", "roman", "georgia",
                                     "garamond", "minion", "baskerville",
                                     "cambria", "book", "petersburg")):
        return "sans" not in name
    return bool(span.get("flags", 0) & 4)


def _dominant(values: list, default):
    """Belgilar soni bo'yicha eng ko'p uchragan qiymat."""
    weight: Dict = {}
    for value, count in values:
        weight[value] = weight.get(value, 0) + count
    return max(weight, key=weight.get) if weight else default


def _join_lines(lines: List[dict], block_rect) -> List[str]:
    """Blok qatorlarini abzatslarga yig'adi.

    Bitta PDF blokida bir necha abzats (ro'yxat bandlari) bo'lishi mumkin.
    Qator oldingisi nuqta bilan tugab, qisqa bo'lsa yoki band belgisi bilan
    boshlansa — yangi abzats. Satr oxiridagi bo'g'in ko'chirish olib
    tashlanadi.
    """
    x0, _, x1, _ = block_rect
    width = max(1.0, x1 - x0)
    paragraphs: List[str] = []
    current = ""
    prev_end = x1
    prev_text = ""
    for line in lines:
        text = "".join(span["text"] for span in line["spans"]).strip()
        if not text:
            continue
        line_x0 = line["bbox"][0]
        new_para = False
        if current:
            ended = prev_text.rstrip().endswith((".", ":", ";", "!", "?"))
            short = prev_end < x1 - width * 0.12
            indented = line_x0 > x0 + 8
            if _BULLET.match(text) or (ended and (short or indented)):
                new_para = True
        if new_para:
            paragraphs.append(current)
            current = text
        elif not current:
            current = text
        elif current.endswith(("-", "\xad")) and text[:1].islower():
            current = current.rstrip("-\xad") + text
        else:
            current += " " + text
        prev_end = line["bbox"][2]
        prev_text = text
    if current:
        paragraphs.append(current)
    return paragraphs


def _align(lines: List[dict], block_rect, page_width: float) -> str:
    x0, _, x1, _ = block_rect
    if len(lines) >= 3:
        full = sum(1 for line in lines[:-1] if line["bbox"][2] > x1 - 3)
        if full >= (len(lines) - 1) * 0.7:
            return "justify"
    centre = (x0 + x1) / 2
    if abs(centre - page_width / 2) < 12:
        offsets = [abs((l["bbox"][0] + l["bbox"][2]) / 2 - centre) for l in lines]
        if max(offsets) < 6 and (x1 - x0) < page_width * 0.8:
            return "center"
    return "left"


def _wanted(text: str, source_lang: str) -> bool:
    """Tarjimaga muhtojmi: manba tili harflari bormi."""
    if len(_LETTER.findall(text)) < 2:
        return False
    if source_lang == "ru":
        return bool(_CYRILLIC.search(text))
    return bool(_LATIN.search(text))


def _line_pieces(line: dict) -> List[dict]:
    """Qatorni katta bo'shliqlar bo'yicha bo'laklaydi.

    Jadvalning bir qatoridagi kataklar PDF da ko'pincha bitta "qator"
    bo'lib keladi: "Ko'rsatkich        Qiymat". Ular birga tarjima qilinib,
    bitta katakka yozilsa jadval buziladi.
    """
    pieces: List[dict] = []
    for span in line["spans"]:
        if not span["text"].strip():
            continue
        gap = max(8.0, span["size"] * 1.6)
        if pieces and span["bbox"][0] - pieces[-1]["bbox"][2] <= gap:
            last = pieces[-1]
            last["spans"].append(span)
            last["bbox"] = (min(last["bbox"][0], span["bbox"][0]),
                            min(last["bbox"][1], span["bbox"][1]),
                            max(last["bbox"][2], span["bbox"][2]),
                            max(last["bbox"][3], span["bbox"][3]))
        else:
            pieces.append({"spans": [span], "bbox": tuple(span["bbox"]),
                           "dir": line.get("dir", (1, 0))})
    return pieces


def _side_by_side(lines: List[dict]) -> bool:
    """Blokdagi ikki qator bir balandlikda yonma-yon turibdimi (jadval kataklari)."""
    boxes = [line["bbox"] for line in lines]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            overlap = min(a[3], b[3]) - max(a[1], b[1])
            height = min(a[3] - a[1], b[3] - b[1])
            apart = a[2] <= b[0] + 1 or b[2] <= a[0] + 1
            if height > 0 and overlap > height * 0.5 and apart:
                return True
    return False


def _make_block(number: int, lines: List[dict], rect: tuple, width: float,
                source_lang: str) -> Optional[Block]:
    spans = [s for line in lines for s in line["spans"] if s["text"].strip()]
    if not spans:
        return None
    size = _dominant([(round(s["size"], 1), len(s["text"])) for s in spans], 10.0)
    if size < MIN_FONT:
        return None
    paragraphs = _join_lines(lines, rect)
    if not _wanted(" ".join(paragraphs), source_lang):
        return None
    bold = _dominant([(bool(s["flags"] & 16) or "bold" in s["font"].lower(),
                       len(s["text"])) for s in spans], False)
    italic = _dominant([(bool(s["flags"] & 2) or "italic" in s["font"].lower()
                         or "oblique" in s["font"].lower(), len(s["text"]))
                        for s in spans], False)
    return Block(
        page=number, rect=rect, paragraphs=paragraphs, size=size,
        color=_hex(_dominant([(s["color"], len(s["text"])) for s in spans], 0)),
        bold=bold, italic=italic,
        serif=_dominant([(_is_serif(s), len(s["text"])) for s in spans], True),
        align=_align(lines, rect, width),
    )


def extract_blocks(doc, source_lang: str) -> List[Block]:
    """Hamma betdagi tarjima qilinadigan matn bloklari."""
    import pymupdf

    flags = (pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_PRESERVE_LIGATURES
             | pymupdf.TEXT_DEHYPHENATE | pymupdf.TEXT_MEDIABOX_CLIP)
    blocks: List[Block] = []
    for number, page in enumerate(doc):
        width = page.rect.width
        for raw in page.get_text("dict", flags=flags)["blocks"]:
            if raw.get("type") != 0 or not raw.get("lines"):
                continue
            lines = raw["lines"]
            # Burilgan (vertikal) matn joyida qoladi.
            if any(abs(line.get("dir", (1, 0))[1]) > 0.01 for line in lines):
                continue
            split = [_line_pieces(line) for line in lines]
            if any(len(pieces) > 1 for pieces in split) or _side_by_side(lines):
                # Jadvalga o'xshaydi: har bo'lak alohida, o'z o'rnida.
                for pieces in split:
                    for piece in pieces:
                        block = _make_block(number, [piece], piece["bbox"], width,
                                            source_lang)
                        if block:
                            block.align = "left"
                            blocks.append(block)
                continue
            block = _make_block(number, lines, tuple(raw["bbox"]), width, source_lang)
            if block:
                blocks.append(block)
    return blocks


# ─────────────────────────────────────────────── Tarjima

def _client():
    from openai import AsyncOpenAI

    return AsyncOpenAI(
        api_key=(os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY")
                 or os.environ.get("OPENROUTER_API_KEY") or "dummy-key"),
        base_url=(os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL")
                  or os.environ.get("OPENROUTER_BASE_URL")
                  or "https://openrouter.ai/api/v1"),
        timeout=240,
    )


def _models() -> List[str]:
    from config import BOOK_TRANSLATE_MODELS

    chosen = os.getenv("BOOK_TRANSLATE_MODEL", "").strip()
    chain = [chosen] if chosen else []
    for model in BOOK_TRANSLATE_MODELS:
        if model not in chain:
            chain.append(model)
    return chain


def _system_prompt(source_lang: str, target_lang: str) -> str:
    source = LANG_NAMES.get(source_lang, source_lang)
    target = LANG_NAMES.get(target_lang, target_lang)
    uzbek = ""
    if target_lang == "uz":
        uzbek = (
            "- Write ONLY in the Uzbek Latin alphabet, never Cyrillic. Use oʻ, gʻ, "
            "sh, ch, ng and the apostrophe ʼ correctly (maktab, oʻquvchi, gʻoya, taʼlim).\n"
            "- Use the terminology of Uzbek university textbooks. Keep established "
            "international and Latin terms (parodont, gingivit, periodontit, "
            "alveola, mikroflora) rather than inventing new words.\n"
            "- Figure/table references: «Рис. 12» → «12-rasm», «Табл. 3» → «3-jadval», "
            "«Глава 2» → «2-bob».\n"
        )
    return (
        f"You are a professional translator of university textbooks. Translate every "
        f"numbered segment from {source} into {target}.\n"
        "Rules:\n"
        "- Translate faithfully and completely: do not summarise, shorten, explain or "
        "add anything. Every sentence of the source must be present.\n"
        "- Keep numbers, units, dosages, formulas, chemical names, abbreviations "
        "and bibliographic references exactly as they are.\n"
        "- Use the same term for the same concept everywhere.\n"
        f"{uzbek}"
        "- A segment may be a heading, a caption, a table cell or a fragment of a "
        "sentence that continues in the next segment — translate it as it is, "
        "without completing it.\n"
        "Output format: for each input segment output its marker [[n]] followed by "
        "the translation, each segment on its own line, in the same order and with "
        "the same markers. No other text, no markdown."
    )


def _thinking_body(model: str) -> dict:
    # Gemini 2.5 Flash/Pro sukut bo'yicha uzoq "o'ylaydi" — tarjimaga bu
    # kerak emas, faqat vaqt va pul ketadi.
    if re.match(r"^google/gemini-2\.5-(?:flash|pro)(?!-lite)", model):
        return {"reasoning": {"max_tokens": 1024, "exclude": True}}
    return {}


def _parse(raw: str, ids: List[int]) -> Dict[int, str]:
    wanted = set(ids)
    parts = _MARK.split(raw or "")
    found: Dict[int, str] = {}
    for index in range(1, len(parts) - 1, 2):
        try:
            number = int(parts[index])
        except ValueError:
            continue
        text = parts[index + 1].strip().strip("*").strip()
        if number in wanted and text:
            found[number] = text
    return found


def _acceptable(text: str, target_lang: str) -> bool:
    """O'zbekcha tarjimada kirill harflari ko'p bo'lsa — javob yaroqsiz."""
    if target_lang != "uz":
        return True
    letters = len(_LETTER.findall(text))
    return not letters or len(_CYRILLIC.findall(text)) / letters < 0.2


async def _ask(client, model: str, system: str, items: List[tuple]) -> tuple:
    """(javob matni, uzilib qoldimi)."""
    body = "\n".join(f"[[{i}]] {text}" for i, text in items)
    chars = sum(len(text) for _, text in items)
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": body}],
        temperature=0.2,
        max_tokens=min(32000, 1500 + chars),
        extra_body=_thinking_body(model) or None,
    )
    choice = response.choices[0]
    return (choice.message.content or ""), choice.finish_reason == "length"


def _status(exc: Exception) -> int:
    return int(getattr(exc, "status_code", 0) or 0)


async def _translate_items(client, system: str, items: List[tuple],
                           target_lang: str) -> Dict[int, str]:
    """Bitta bo'lakni tarjima qiladi; model yiqilsa keyingisiga o'tadi.

    Javob uzilib qolsa (juda uzun) bo'lak ikkiga bo'linadi.
    """
    last_error = None
    for model in _models():
        for attempt in range(2):
            try:
                raw, cut = await _ask(client, model, system, items)
            except Exception as exc:
                if _status(exc) == 402:
                    raise BookNoCredits(str(exc)) from exc
                last_error = exc
                logger.warning("Kitob tarjimasi: %s xato berdi (%s): %s",
                               model, attempt + 1, exc)
                await asyncio.sleep(2 + attempt * 3)
                continue
            found = _parse(raw, [i for i, _ in items])
            found = {i: t for i, t in found.items() if _acceptable(t, target_lang)}
            if cut and len(items) > 1 and len(found) < len(items):
                half = len(items) // 2
                first = await _translate_items(client, system, items[:half], target_lang)
                second = await _translate_items(client, system, items[half:], target_lang)
                return {**found, **first, **second}
            if found:
                return found
            last_error = RuntimeError("bo'sh javob")
    logger.error("Kitob tarjimasi: bo'lak tarjima qilinmadi: %s", last_error)
    return {}


def _batches(items: List[tuple], limit: int = BATCH_CHARS) -> List[List[tuple]]:
    batches, current, size = [], [], 0
    for item in items:
        length = len(item[1])
        if current and size + length > limit:
            batches.append(current)
            current, size = [], 0
        current.append(item)
        size += length
    if current:
        batches.append(current)
    return batches


Progress = Optional[Callable[[int, int], Awaitable[None]]]


async def translate_texts(texts: List[str], source_lang: str, target_lang: str,
                          progress: Progress = None, translator=None) -> List[Optional[str]]:
    """Matnlar ro'yxatini tarjima qiladi. Tarjima qilinmaganlari — None.

    `translator(system, items) -> {id: tarjima}` sinovlar uchun almashtiriladi.
    """
    items = [(i, text) for i, text in enumerate(texts)]
    system = _system_prompt(source_lang, target_lang)
    client = None
    if translator is None:
        client = _client()

        async def translator(system_text, chunk):
            return await _translate_items(client, system_text, chunk, target_lang)

    results: Dict[int, str] = {}
    batches = _batches(items)
    total = sum(len(t) for t in texts) or 1
    done = 0
    gate = asyncio.Semaphore(CONCURRENCY)
    no_credits: List[Exception] = []

    async def run(chunk):
        nonlocal done
        async with gate:
            if no_credits:
                return
            try:
                results.update(await translator(system, chunk))
            except BookNoCredits as exc:
                no_credits.append(exc)
                return
            done += sum(len(t) for _, t in chunk)
            if progress:
                try:
                    await progress(done, total)
                except Exception:
                    pass

    await asyncio.gather(*(run(chunk) for chunk in batches))
    if no_credits:
        raise no_credits[0]

    # Tushib qolgan bo'laklar kichikroq guruhlarda yana bir marta so'raladi.
    missing = [(i, t) for i, t in items if i not in results]
    if missing:
        logger.info("Kitob tarjimasi: %d ta bo'lak qayta so'ralmoqda", len(missing))
        await asyncio.gather(*(run(chunk) for chunk in _batches(missing, BATCH_CHARS // 4)))
        if no_credits:
            raise no_credits[0]
    if client is not None:
        try:
            await client.close()
        except Exception:
            pass
    return [results.get(i) for i in range(len(texts))]


# ─────────────────────────────────────────────── PDF ga yozish

def _obstacles(page, own: List[tuple]) -> List[tuple]:
    """Tarjima cho'zilganda kirib ketmasligi kerak bo'lgan joylar."""
    rects = [tuple(r) for r in own]
    for info in page.get_image_info():
        rects.append(tuple(info["bbox"]))
    try:
        for drawing in page.get_drawings():
            rect = drawing.get("rect")
            if rect is not None and (rect.width > 0 or rect.height > 0):
                rects.append(tuple(rect))
    except Exception:
        pass
    return rects


def _grown(block: Block, obstacles: List[tuple], page_rect, margin: float) -> tuple:
    """Blokni pastga (va chap tekislangan bo'lsa o'ngga) bo'sh joygacha cho'zadi."""
    x0, y0, x1, y1 = block.rect

    def contains(rect) -> bool:
        return (rect[0] <= x0 + 1 and rect[1] <= y0 + 1
                and rect[2] >= x1 - 1 and rect[3] >= y1 - 1)

    others = [r for r in obstacles if r != block.rect and not contains(r)]
    right = x1
    if block.align == "left":
        right = max(x1, page_rect.width - margin)
        for r in others:
            if r[1] < y1 and r[3] > y0 and r[0] >= x1 - 1:
                right = min(right, r[0] - 3)
        right = max(right, x1)
    bottom = max(y1, page_rect.height - 18)
    for r in others:
        if r[0] < right and r[2] > x0 and r[1] >= y1 - 1:
            bottom = min(bottom, r[1] - 2)
    return (x0, y0, right, max(bottom, y1))


def _html(block: Block, paragraphs: List[str]) -> tuple:
    family = "serif" if block.serif else "sans-serif"
    css = (
        f"* {{font-family: {family}; font-size: {block.size:.1f}px; color: {block.color};"
        f" line-height: 1.15;}}"
        f" p {{margin: 0; text-align: {block.align};"
        f" font-weight: {'bold' if block.bold else 'normal'};"
        f" font-style: {'italic' if block.italic else 'normal'};}}"
    )
    body = "".join(f"<p>{html.escape(text)}</p>" for text in paragraphs)
    return body, css


def _write_page(page, blocks: List[Block], texts: Dict[int, List[str]]) -> None:
    import pymupdf

    todo = [b for b in blocks if id(b) in texts]
    if not todo:
        return
    all_rects = [b.rect for b in blocks]
    obstacles = _obstacles(page, all_rects)
    margin = max(18.0, min((b.rect[0] for b in blocks), default=36.0))
    for block in todo:
        page.add_redact_annot(pymupdf.Rect(block.rect), fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    for block in todo:
        body, css = _html(block, texts[id(block)])
        own = pymupdf.Rect(block.rect)
        wide = pymupdf.Rect(_grown(block, obstacles, page.rect, margin))
        # Avval asl o'lchamda, keyin bo'sh joyga cho'zib, oxiri kichraytirib.
        for rect, scale in ((own, 1), (wide, 1), (wide, 0)):
            try:
                spare, _ = page.insert_htmlbox(rect, body, css=css, scale_low=scale)
            except Exception as exc:
                logger.warning("Blok yozilmadi (%d-bet): %s", block.page + 1, exc)
                break
            if spare >= 0:
                break


def _compress(doc) -> None:
    try:
        doc.rewrite_images(dpi_threshold=IMAGE_DPI + 20, dpi_target=IMAGE_DPI,
                           quality=IMAGE_QUALITY)
    except Exception as exc:
        logger.warning("Rasmlar siqilmadi: %s", exc)
    try:
        doc.subset_fonts()
    except Exception as exc:
        logger.debug("Shriftlar qisqartirilmadi: %s", exc)


def _assign_segments(blocks: List[Block]) -> List[str]:
    texts: List[str] = []
    for block in blocks:
        block.segments = []
        for paragraph in block.paragraphs:
            block.segments.append(len(texts))
            texts.append(paragraph)
    return texts


def _output_path(source: str, target_lang: str) -> str:
    base = os.path.splitext(os.path.basename(source))[0][:60] or "kitob"
    os.makedirs(TEMP_DIR, exist_ok=True)
    return os.path.join(TEMP_DIR, f"{base}_{target_lang}_{uuid.uuid4().hex[:6]}.pdf")


async def translate_pdf(path: str, target_lang: str, source_lang: str = None,
                        page_from: int = None, page_to: int = None,
                        progress: Progress = None, translator=None) -> TranslateResult:
    """PDF kitobni tarjima qiladi va yangi PDF yo'lini qaytaradi."""
    async with _JOBS:
        doc = await asyncio.to_thread(_open, path)
        try:
            start, stop = _range(doc.page_count, page_from, page_to)
            if (start, stop) != (0, doc.page_count):
                await asyncio.to_thread(doc.select, list(range(start, stop)))
            if source_lang is None:
                source_lang = detect_language(
                    " ".join(doc[i].get_text() for i in range(min(20, doc.page_count))))
            blocks = await asyncio.to_thread(extract_blocks, doc, source_lang)
            if not blocks:
                scanned = sum(1 for page in doc if _page_is_scanned(page))
                if scanned > doc.page_count * 0.4:
                    raise ScannedBook("matn qatlami yo'q")
                raise BookTranslateError("tarjima qilinadigan matn topilmadi")

            texts = _assign_segments(blocks)
            logger.info("Kitob tarjimasi: %d bet, %d blok, %d bo'lak, %d belgi",
                        doc.page_count, len(blocks), len(texts), sum(map(len, texts)))
            translated = await translate_texts(texts, source_lang, target_lang,
                                               progress=progress, translator=translator)

            by_page: Dict[int, List[Block]] = {}
            for block in blocks:
                by_page.setdefault(block.page, []).append(block)
            ready: Dict[int, List[str]] = {}
            failed = 0
            for block in blocks:
                parts = [translated[i] for i in block.segments]
                if all(parts):
                    ready[id(block)] = parts
                else:
                    failed += 1

            def write():
                for number, page_blocks in by_page.items():
                    _write_page(doc[number], page_blocks, ready)
                _compress(doc)
                out = _output_path(path, target_lang)
                doc.save(out, garbage=3, deflate=True, clean=True)
                return out

            out = await asyncio.to_thread(write)
            return TranslateResult(path=out, pages=doc.page_count, blocks=len(blocks),
                                   failed=failed, size=os.path.getsize(out))
        finally:
            doc.close()


def read_text(path: str, limit: int = 60000) -> str:
    """Tarjima qilingan PDF matni — kitob asosida hujjat yozish uchun."""
    doc = _open(path)
    try:
        parts, size = [], 0
        for page in doc:
            text = page.get_text("text").strip()
            if text:
                parts.append(text)
                size += len(text)
            if size >= limit:
                break
        return "\n\n".join(parts)[:limit]
    finally:
        doc.close()
