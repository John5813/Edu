"""Katta PDF kitobdan matnni olib tarjima qilish — natija toza Word (DOCX).

Kitobning og'irligi deyarli butunlay rasmlarda: 226 betlik darslik 38 MB,
lekin undagi matn bir-ikki megabayt xolos. Rasmlarni saqlab, PDF ni joyida
qayta chizish 2 GB xotirali serverni to'ldirib, botni qotirib qo'ydi.
Shuning uchun rasmlarga umuman tegilmaydi (ular ochilmaydi ham):

  1. har betdan faqat matn bloklari olinadi — abzats, sarlavha, izoh;
     sahifa raqami va har betda takrorlanadigan kolontitullar tashlanadi;
  2. bet chegarasida uzilgan abzats qayta ulanadi;
  3. bo'laklar bir necha so'rovda parallel tarjima qilinadi;
  4. natija sarlavhalari ajratilgan oddiy Word hujjat bo'ladi.

Tarjima qilinmay qolgan bo'lak (model javob bermasa) asl tilida qoladi —
bitta muvaffaqiyatsiz so'rov butun kitobni yiqitmaydi.
"""

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List, Optional


logger = logging.getLogger(__name__)

# Bitta so'rovga ketadigan matn hajmi (belgi). Kattaroq bo'lsa model
# bo'laklarni tashlab ketishi yoki javob uzilib qolishi ehtimoli oshadi.
BATCH_CHARS = 7000
# Bir kitob uchun bir vaqtdagi so'rovlar.
CONCURRENCY = 5

# Shundan kichik matn (izoh belgilari va h.k.) tegilmaydi.
MIN_FONT = 4.0
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
                source_lang: str, require_source: bool = True) -> Optional[Block]:
    spans = [s for line in lines for s in line["spans"] if s["text"].strip()]
    if not spans:
        return None
    size = _dominant([(round(s["size"], 1), len(s["text"])) for s in spans], 10.0)
    if size < MIN_FONT:
        return None
    paragraphs = _join_lines(lines, rect)
    text = " ".join(paragraphs)
    if require_source and not _wanted(text, source_lang):
        return None
    if len(_LETTER.findall(text)) < 2:
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


def extract_blocks(doc, source_lang: str, pages=None,
                   require_source: bool = True) -> List[Block]:
    """Betlardagi matn bloklari (sukut bo'yicha — faqat tarjimaga muhtojlari)."""
    import pymupdf

    flags = (pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_PRESERVE_LIGATURES
             | pymupdf.TEXT_DEHYPHENATE | pymupdf.TEXT_MEDIABOX_CLIP)
    blocks: List[Block] = []
    numbers = range(doc.page_count) if pages is None else pages
    for number in numbers:
        page = doc[number]
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
                                            source_lang, require_source)
                        if block:
                            block.align = "left"
                            blocks.append(block)
                continue
            block = _make_block(number, lines, tuple(raw["bbox"]), width, source_lang,
                                require_source)
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


# ─────────────────────────────────────────────── Matn va Word

_END = (".", "!", "?", ":", ";", "…", "»", '"', ")")


def _is_margin(block: Block, height: float) -> bool:
    """Kolontitul yoki sahifa raqami: betning eng tepasi yoki eng pastida,
    qisqa matn."""
    text = " ".join(block.paragraphs)
    top, bottom = block.rect[1], block.rect[3]
    return len(text) < 120 and (bottom < height * 0.07 or top > height * 0.93)


def extract_paragraphs(src: str, start: int, stop: int, source_lang: str) -> List[dict]:
    """[start, stop) betlardagi abzatslar: matn, sarlavhami, tarjima kerakmi.

    Rasmlar ochilmaydi — faqat matn qatlami o'qiladi, shuning uchun
    rasmga boy kitobda ham xotira kam ketadi.
    """
    doc = _open(src)
    try:
        stop = min(stop, doc.page_count)
        blocks = extract_blocks(doc, source_lang, pages=range(start, stop),
                                require_source=False)
        heights = {n: doc[n].rect.height for n in range(start, stop)}
    finally:
        doc.close()

    blocks = [b for b in blocks if not _is_margin(b, heights.get(b.page, 842))]
    body = _dominant([(b.size, sum(len(p) for p in b.paragraphs)) for b in blocks], 10.0)
    items: List[dict] = []
    for block in blocks:
        for text in block.paragraphs:
            short = len(text) < 160 and not text.rstrip().endswith((".", ";", ","))
            heading = short and (block.size >= body * 1.15 or block.bold)
            items.append({
                "text": text, "page": block.page, "heading": heading,
                "small": block.size < body * 0.88, "italic": block.italic,
                "translate": _wanted(text, source_lang),
            })
    return join_page_breaks(items)


def join_page_breaks(items: List[dict]) -> List[dict]:
    """Bet oxirida uzilib, keyingi betda davom etgan abzatsni ulaydi."""
    joined: List[dict] = []
    for item in items:
        prev = joined[-1] if joined else None
        text = item["text"].lstrip()
        if (prev and prev["page"] != item["page"] and not prev["heading"]
                and not item["heading"] and text[:1].islower()
                and not prev["text"].rstrip().endswith(_END)):
            if prev["text"].endswith(("-", "\xad")):
                prev["text"] = prev["text"].rstrip("-\xad") + text
            else:
                prev["text"] += " " + text
            prev["page"] = item["page"]
            prev["translate"] = prev["translate"] or item["translate"]
            continue
        joined.append(dict(item))
    return joined


def build_docx(items: List[dict], out: str, title: str = "") -> None:
    """Tarjima qilingan abzatslardan oddiy, o'qishga qulay Word hujjat."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    doc = Document()
    for section in doc.sections:
        section.left_margin = section.right_margin = Cm(2)
        section.top_margin = section.bottom_margin = Cm(2)
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(13)
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.15

    if title:
        head = doc.add_paragraph()
        head.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = head.add_run(title)
        run.bold = True
        run.font.size = Pt(16)

    for item in join_page_breaks(items):
        text = (item.get("text") or "").strip()
        if not text:
            continue
        para = doc.add_paragraph()
        run = para.add_run(text)
        if item.get("heading"):
            run.bold = True
            run.font.size = Pt(14)
            para.paragraph_format.space_before = Pt(12)
            para.paragraph_format.keep_with_next = True
        elif item.get("small"):
            run.italic = True
            run.font.size = Pt(11)
        else:
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            para.paragraph_format.first_line_indent = Cm(1)
            run.italic = bool(item.get("italic"))
    doc.save(out)
