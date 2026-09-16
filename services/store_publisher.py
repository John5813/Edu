"""Tayyor ishni mijoz izidan tozalab, do'kon katalogiga qo'yadi.

Oqim: tozalash → ko'rgazma rasmlari → yopiq Telegram kanaliga yuklash →
katalogga yozuv. Faylning o'zi hech qachon saytda turmaydi; sayt faqat
rasmlarni ko'rsatadi, fayl esa kanaldan `file_id` orqali olinadi.
"""

import logging
import os
import re
import shutil
import time
import uuid

from config import (
    STORE_PREVIEW_DIR,
    STORE_PREVIEW_MAX,
    STORE_VAULT_CHAT_ID,
    STORE_WATERMARK,
    TEMP_DIR,
)

logger = logging.getLogger(__name__)

# Avtomatik nashr yetkazishni buzmasligi uchun xatoni yutadi. Admin nima
# bo'lganini ko'ra olishi uchun oxirgisi shu yerda saqlanadi.
LAST_ERROR: dict = {}

# "Tayyorladi:", "Автор —", "Prepared by" kabi satrlar. Mijoz ismi noma'lum
# bo'lganda ham shu satrlar orqali topiladi.
_LABEL = (
    r"tayyorladi|bajardi|topshirdi|muallif|ism[\s\-]*familiya|ismi|talaba|"
    r"выполнил(?:а)?|подготовил(?:а)?|автор|студент|"
    r"prepared\s+by|author|submitted\s+by|student"
)
_LABEL_ONLY_RE = re.compile(rf"^\s*(?:{_LABEL})\s*[:\-–—]?\s*$", re.IGNORECASE)
_LABEL_VALUE_RE = re.compile(rf"^\s*(?:{_LABEL})\s*[:\-–—]\s*(.+)$", re.IGNORECASE)


def _looks_like_person(text: str) -> bool:
    """Ism-familiyaga o'xshaydimi.

    Kitob muallifi haqidagi jumla tasodifan o'chib ketmasligi uchun:
    faqat raqamsiz, tinish belgisiz, 1-4 so'zli qisqa matn ism deb qaraladi.
    """
    value = text.strip(" .,;")
    if not value or len(value) > 60:
        return False
    if any(ch.isdigit() for ch in value):
        return False
    words = value.split()
    return 1 <= len(words) <= 4 and all(w.replace("'", "").replace("`", "").isalpha() for w in words)


def _iter_shapes(shapes):
    """Guruhlangan shakllar ichidagilarni ham qaytaradi."""
    for shape in shapes:
        yield shape
        if getattr(shape, "shape_type", None) == 6:  # MSO_SHAPE_TYPE.GROUP
            try:
                yield from _iter_shapes(shape.shapes)
            except Exception:
                pass


def _blank_paragraph(para) -> None:
    for run in para.runs:
        run.text = ""


def _blank_paragraph_all(paragraphs) -> None:
    for para in paragraphs:
        _blank_paragraph(para)


def _scrub_paragraphs(paragraphs, name_re) -> int:
    """Mijozga ishora qiluvchi satrlarni bo'shatadi, sonini qaytaradi.

    Word ham, PowerPoint ham paragrafni bir xil ko'rsatadi (`.text`,
    `.runs`), shuning uchun bitta funksiya ikkalasiga ham yetadi.
    """
    removed = 0
    after_label = False
    for para in paragraphs:
        text = para.text
        if not text.strip():
            continue
        label_only = bool(_LABEL_ONLY_RE.match(text))
        hit = False
        if name_re is not None and name_re.search(text):
            hit = True
        elif label_only:
            hit = True
        else:
            match = _LABEL_VALUE_RE.match(text)
            if match and _looks_like_person(match.group(1)):
                hit = True
            elif after_label and _looks_like_person(text):
                # "Tayyorladi:" alohida satrda, ism esa undan keyin turadi.
                hit = True
        if hit:
            _blank_paragraph(para)
            removed += 1
        after_label = label_only
    return removed


def _scrub_table_row(cells, name_re) -> int:
    """Jadval satrini tozalaydi.

    "Talaba | Ism Familiya" ko'rinishida yorliq bir katakda, ism yonidagida
    turadi — shuning uchun kataklar bir-biriga qarab baholanadi.
    """
    before = [cell.text for cell in cells]
    removed = sum(_scrub_paragraphs(_cell_paragraphs(cell), name_re) for cell in cells)
    if not any(_LABEL_ONLY_RE.match(text) for text in before):
        return removed
    for cell, text in zip(cells, before):
        if _LABEL_ONLY_RE.match(text):
            continue
        if cell.text.strip() and _looks_like_person(cell.text):
            _blank_paragraph_all(_cell_paragraphs(cell))
            removed += 1
    return removed


def _cell_paragraphs(cell):
    """Jadval katagidagi paragraflar. Word'da to'g'ridan-to'g'ri, PowerPoint'da
    matn ramkasi ichida turadi."""
    frame = getattr(cell, "text_frame", None)
    return frame.paragraphs if frame is not None else cell.paragraphs


def _name_pattern(customer_name: str):
    """Mijoz ismini topadigan naqsh. Ism qisqa bo'lsa None."""
    cleaned = (customer_name or "").strip()
    if len(cleaned) < 3:
        return None
    # Ism bo'laklari alohida ham qidiriladi: ishda faqat familiya yozilgan
    # bo'lishi mumkin.
    parts = [re.escape(p) for p in cleaned.split() if len(p) >= 3]
    return re.compile("|".join(parts), re.IGNORECASE) if parts else None


def _download_name(title: str, extension: str, fallback: str) -> str:
    """Xaridorga ko'rinadigan fayl nomi.

    Ombordagi fayl mavzu nomi bilan saqlanadi: sotib olgan mijoz faylni
    `F60ABXI.docx` ko'rinishida emas, mavzusi bilan oladi — ichki kod unga
    hech narsa anglatmaydi.
    """
    cleaned = re.sub(r"[^\w\s.-]", "", title or "", flags=re.UNICODE).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)[:60].strip("._-")
    return (cleaned or fallback) + extension


def _staged_path(extension: str) -> str:
    os.makedirs(TEMP_DIR, exist_ok=True)
    return os.path.join(TEMP_DIR, f"store_{uuid.uuid4().hex[:8]}{extension}")


def _clear_properties(props) -> None:
    """Fayl xossalari: Word/PowerPoint «Muallif» maydonini o'zi to'ldiradi."""
    props.author = ""
    props.last_modified_by = ""
    props.comments = ""
    props.category = ""
    props.keywords = ""
    props.subject = ""
    props.identifier = ""
    props.revision = 1


def anonymize(src_path: str, customer_name: str = "", out_path: str = "") -> str:
    """Fayl turiga qarab tozalaydi — .pptx ham, .docx ham."""
    if src_path.lower().endswith(".docx"):
        return anonymize_docx(src_path, customer_name, out_path)
    return anonymize_pptx(src_path, customer_name, out_path)


def anonymize_pptx(src_path: str, customer_name: str = "", out_path: str = "") -> str:
    """Nusxani tozalab, yangi fayl yo'lini qaytaradi. Asl fayl tegilmaydi."""
    from pptx import Presentation

    out_path = out_path or _staged_path(".pptx")
    name_re = _name_pattern(customer_name)
    prs = Presentation(src_path)

    removed = 0
    for slide in prs.slides:
        for shape in _iter_shapes(slide.shapes):
            if getattr(shape, "has_text_frame", False):
                removed += _scrub_paragraphs(shape.text_frame.paragraphs, name_re)
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    removed += _scrub_table_row(list(row.cells), name_re)
        # Slayd izohlari — ekranda ko'rinmaydi, shuning uchun eng oson
        # e'tibordan chetda qoladigan joy.
        if getattr(slide, "has_notes_slide", False):
            try:
                _blank_paragraph_all(slide.notes_slide.notes_text_frame.paragraphs)
            except Exception:
                pass

    _clear_properties(prs.core_properties)
    prs.save(out_path)
    logger.info("Tozalandi: %s → %s (%s satr olib tashlandi)",
                os.path.basename(src_path), os.path.basename(out_path), removed)
    return out_path


def anonymize_docx(src_path: str, customer_name: str = "", out_path: str = "") -> str:
    """Word hujjatini tozalaydi: matn, jadval, kolontitul va fayl xossalari.

    Kurs va mustaqil ishlarda mijoz ismi odatda titul varag'ida —
    "Bajardi:" yorlig'i ostida yoki jadval katagida turadi.
    """
    from docx import Document

    out_path = out_path or _staged_path(".docx")
    name_re = _name_pattern(customer_name)
    doc = Document(src_path)

    removed = _scrub_paragraphs(doc.paragraphs, name_re)
    for table in doc.tables:
        for row in table.rows:
            removed += _scrub_table_row(list(row.cells), name_re)

    # Kolontitullar har sahifada takrorlanadi — ism u yerda qolsa, tozalash
    # bekor bo'lardi.
    for section in doc.sections:
        for part in (section.header, section.footer,
                     section.first_page_header, section.first_page_footer):
            if part is None:
                continue
            try:
                removed += _scrub_paragraphs(part.paragraphs, name_re)
                for table in part.tables:
                    for row in table.rows:
                        removed += _scrub_table_row(list(row.cells), name_re)
            except Exception:
                pass

    _clear_properties(doc.core_properties)
    doc.save(out_path)
    logger.info("Tozalandi: %s → %s (%s satr olib tashlandi)",
                os.path.basename(src_path), os.path.basename(out_path), removed)
    return out_path


PREVIEW_WIDTH = 1000
THUMB_WIDTH = 480


def _font_path() -> str:
    """Shtamp uchun shrift. Matplotlib har doim loyihada bor."""
    import matplotlib

    bundled = os.path.join(os.path.dirname(matplotlib.__file__),
                           "mpl-data", "fonts", "ttf", "DejaVuSans-Bold.ttf")
    if os.path.exists(bundled):
        return bundled
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _watermark(image, text: str = ""):
    """Butun rasm bo'ylab qiya, yarim shaffof shtamp qo'yadi.

    Naqsh matnning ustiga tushadi: ko'rgazma ishni baholashga yetadi,
    lekin tayyor ish o'rnida ishlatib bo'lmaydi. Oq harf qora chiziq
    bilan chiziladi — shunda ham och, ham to'q slaydda ko'rinadi.
    """
    from PIL import Image, ImageDraw, ImageFont

    text = (text or STORE_WATERMARK).strip()
    if not text:
        return image

    width, height = image.size
    # Qiya naqsh burchaklarni ham qoplashi uchun diagonal bo'yicha chiziladi.
    span = int((width ** 2 + height ** 2) ** 0.5) + 2
    layer = Image.new("RGBA", (span, span), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    try:
        font = ImageFont.truetype(_font_path(), size=max(16, width // 24))
    except OSError:
        font = ImageFont.load_default()

    box = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = box[2] - box[0], box[3] - box[1]
    step_x = text_w + max(60, width // 10)
    step_y = text_h * 5

    for row, y in enumerate(range(0, span, step_y)):
        # Har qatorni surib chizish naqshni tik ustunlarga tushib qolishdan saqlaydi.
        offset = (row % 2) * (step_x // 2)
        for x in range(-step_x, span, step_x):
            draw.text((x + offset, y), text, font=font,
                      fill=(255, 255, 255, 66),
                      stroke_width=2, stroke_fill=(0, 0, 0, 74))

    rotated = layer.rotate(30, resample=Image.BICUBIC)
    left, top = (span - width) // 2, (span - height) // 2
    stamp = rotated.crop((left, top, left + width, top + height))

    return Image.alpha_composite(image.convert("RGBA"), stamp).convert("RGB")


def _shrink_and_stamp(image, width: int):
    """Kerakli kenglikka keltirib, so'ng shtamp bosadi."""
    from PIL import Image

    if image.width > width:
        height = round(image.height * width / image.width)
        image = image.resize((width, height), Image.LANCZOS)
    return _watermark(image)


def render_previews(source_path: str, public_code: str, limit: int = 0) -> int:
    """Har varaqni shtampli JPG qilib saqlaydi, nechtasi saqlangani qaytadi.

    Saytda butun ish varaqma-varaq ko'riladi — faylning o'zi esa berilmaydi,
    shu sababli har rasmga shtamp bosiladi. LibreOffice .pptx ni ham,
    .docx ni ham avval PDF'ga aylantiradi, shuning uchun bitta yo'l ikkala
    turga yetadi.
    """
    from PIL import Image

    from services.premium_presentation.qa import discard_images, pptx_to_images

    limit = limit or STORE_PREVIEW_MAX
    out_dir = os.path.join(STORE_PREVIEW_DIR, public_code)
    os.makedirs(out_dir, exist_ok=True)

    images = pptx_to_images(source_path)
    if not images:
        logger.error("Ko'rgazma rasmlari yaratilmadi: %s", source_path)
        return 0

    saved = 0
    try:
        for source in images[:limit]:
            try:
                with Image.open(source) as raw:
                    clean = raw.convert("RGB")
                    saved += 1
                    _shrink_and_stamp(clean, PREVIEW_WIDTH).save(
                        os.path.join(out_dir, f"{saved}.jpg"),
                        format="JPEG", quality=80, optimize=True)
                    if saved == 1:
                        # Katalog to'ridagi kichik rasm — har kartochkaga
                        # to'liq o'lchamli slayd yuklanmasin. Shtamp shu
                        # o'lchamda bosiladi: tayyorini kichraytirsak, naqsh
                        # mayda-mayda bo'lib kartochkani ifloslantirardi.
                        _shrink_and_stamp(clean, THUMB_WIDTH).save(
                            os.path.join(out_dir, "thumb.jpg"),
                            format="JPEG", quality=78, optimize=True)
            except Exception as exc:
                logger.warning("Ko'rgazma rasmi tayyorlanmadi (%s): %s", source, exc)
    finally:
        discard_images(images)

    return saved


def discard_previews(public_code: str) -> None:
    """Katalogdan olib tashlangan ishning rasmlarini o'chiradi."""
    shutil.rmtree(os.path.join(STORE_PREVIEW_DIR, public_code), ignore_errors=True)


def _slide_count(path: str, fallback: int) -> int:
    """Taqdimotda slaydlar soni. Word'da varaq sonini faqat chizib bilamiz,
    shuning uchun u yerda ko'rgazma rasmlari soni ishlatiladi."""
    if not path.lower().endswith(".pptx"):
        return fallback
    try:
        from pptx import Presentation

        return len(Presentation(path).slides)
    except Exception:
        return fallback


async def publish_work(
    bot,
    source_path: str,
    title: str,
    price: int,
    *,
    customer_name: str = "",
    description: str = "",
    category: str = "",
    work_type: str = "",
    language: str = "uz",
    keywords: str = "",
) -> dict:
    """Ishni tozalab, omborga yuklab, katalogga qo'yadi (.pptx yoki .docx).

    Katalogga yozuv faqat fayl omborga yetib borgandan keyin qo'shiladi —
    aks holda saytda yuklab bo'lmaydigan ish paydo bo'lardi.
    """
    from aiogram.types import FSInputFile

    from database.database import Database
    from services.store_taxonomy import classify

    if not STORE_VAULT_CHAT_ID:
        raise RuntimeError(
            "STORE_VAULT_CHAT_ID sozlanmagan — ombor kanali ko'rsatilishi kerak"
        )

    extension = ".docx" if source_path.lower().endswith(".docx") else ".pptx"
    file_type = extension.lstrip(".")

    # Fan ko'rsatilmagan bo'lsa mavzudan aniqlanadi: har bir ish saytda
    # o'z bo'limiga tushishi kerak, aks holda filtrlar bo'sh qoladi.
    category = category or classify(title, description, keywords)

    public_code = await Database.generate_store_code()
    cleaned_path = anonymize(source_path, customer_name)

    try:
        preview_count = render_previews(cleaned_path, public_code)
        if not preview_count:
            raise RuntimeError("ko'rgazma rasmlari tayyorlanmadi")

        message = await bot.send_document(
            chat_id=STORE_VAULT_CHAT_ID,
            document=FSInputFile(
                cleaned_path,
                filename=_download_name(title, extension, public_code)),
            caption=f"{public_code} — {title}",
            parse_mode=None,
        )
        if not message.document:
            raise RuntimeError("ombor javobida hujjat yo'q")

        await Database.create_store_item(
            public_code=public_code,
            title=title,
            file_id=message.document.file_id,
            price=price,
            description=description,
            category=category,
            work_type=work_type,
            language=language,
            keywords=keywords,
            slide_count=_slide_count(cleaned_path, preview_count),
            file_type=file_type,
            preview_count=preview_count,
        )
    except Exception:
        # Yarim qolgan nashrdan rasm qolib ketmasin.
        discard_previews(public_code)
        raise
    finally:
        if cleaned_path != source_path:
            try:
                os.remove(cleaned_path)
            except OSError:
                pass

    logger.info("Katalogga qo'shildi: %s — %s (%s)", public_code, title, file_type)
    return {
        "public_code": public_code,
        "title": title,
        "price": price,
        "file_type": file_type,
        "slide_count": _slide_count(source_path, preview_count),
        "preview_count": preview_count,
    }


def schedule_publish(bot, file_path: str, title: str, work_type: str, *,
                     customer_name: str = "", language: str = "uz") -> None:
    """Yetkazilgan ishni fonda katalogga qo'yadi.

    Chaqiruvchi faylni darhol o'chiradi, shuning uchun nusxa shu yerda,
    qaytishdan oldin olinadi. Nashr fon vazifasida ketadi va xato bo'lsa
    faqat jurnalga yoziladi — mijozga yetkazishga hech qanday ta'siri yo'q.
    """
    import asyncio

    from config import STORE_AUTO_PUBLISH, store_price

    if not STORE_AUTO_PUBLISH or not STORE_VAULT_CHAT_ID:
        return
    extension = os.path.splitext(file_path)[1].lower()
    if extension not in (".pptx", ".docx"):
        return
    if not (title or "").strip():
        return

    try:
        staged = _staged_path(extension)
        shutil.copy2(file_path, staged)
    except OSError as exc:
        logger.warning("Katalog uchun nusxa olinmadi (%s): %s", file_path, exc)
        return

    async def run() -> None:
        try:
            await publish_work(
                bot, staged, title.strip()[:300], store_price(work_type),
                customer_name=customer_name, language=language,
                work_type=work_type,
            )
        except Exception as exc:
            logger.error("Avtomatik nashr bo'lmadi (%s): %s", work_type, exc)
            LAST_ERROR.update(work_type=work_type, title=title.strip()[:80],
                              error=f"{type(exc).__name__}: {exc}"[:300],
                              at=time.strftime("%d.%m %H:%M"))
        else:
            LAST_ERROR.clear()
        finally:
            try:
                os.remove(staged)
            except OSError:
                pass

    try:
        asyncio.get_running_loop().create_task(run())
    except RuntimeError:
        # Hodisalar halqasi yo'q — bu yo'l botdan tashqarida chaqirilgan.
        logger.warning("Avtomatik nashr o'tkazib yuborildi: halqa yo'q")
        try:
            os.remove(staged)
        except OSError:
            pass
