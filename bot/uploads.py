"""Fayl qabul qilishning yagona yo'li — hamma xizmat shu yerdan o'tadi.

Ilgari har xizmat faylni o'zicha qabul qilardi: biri hajmni tekshirardi,
ikkinchisi tekshirmasdi, uchinchisi boshqa formatlar ro'yxatini qo'llardi
va xato xabarlari ham har xil edi. Natijada katta kitob yuklangan xizmat
botni yiqitardi, mijoz esa qaysi xizmatda nima yuklash mumkinligini
bilolmasdi.

Bu modul bitta tartib beradi:

  1. kengaytma xizmat qabul qiladigan ro'yxatga mos keladimi;
  2. hajm — YUKLASHDAN OLDIN tekshiriladi, Telegram bergan `file_size`
     bo'yicha, ya'ni katta fayl diskka umuman tushmaydi;
  3. yuklab olish va kerak bo'lsa matnni xavfsiz ajratib olish;
  4. bir xil, tarjima qilingan xato xabarlari.
"""

import logging
import os
import uuid
from dataclasses import dataclass

from config import TEMP_DIR
from services import document_source
from translations import get_text

logger = logging.getLogger(__name__)

# Xizmatlar qabul qiladigan formatlar. Ro'yxat shu yerda turadi, shuning
# uchun yangi format qo'shish bitta joyda hal bo'ladi.
DOCUMENTS = (".pdf", ".docx", ".pptx")
TEXT_SOURCES = (".pdf", ".docx")
SLIDES = (".pptx",)

_LABELS = {".pdf": "PDF", ".docx": "Word", ".pptx": "PowerPoint"}


@dataclass
class Upload:
    """Muvaffaqiyatli qabul qilingan fayl."""
    path: str
    file_name: str
    extension: str
    size: int
    extract: document_source.Extract | None = None

    @property
    def text(self) -> str:
        return self.extract.text if self.extract else ""


def describe(accept) -> str:
    """«PDF, Word» kabi o'qiladigan ro'yxat — xato xabarlari uchun."""
    return ", ".join(_LABELS.get(ext, ext.upper().lstrip(".")) for ext in accept)


def _extension(file_name: str, accept) -> str | None:
    lowered = (file_name or "").lower()
    for ext in accept:
        if lowered.endswith(ext):
            return ext
    return None


async def receive(message, language: str, accept=DOCUMENTS, prefix: str = "upload",
                  extract: bool = True) -> Upload | None:
    """Faylni tekshirib, yuklab oladi. Xato bo'lsa mijozga aytadi va None qaytaradi.

    `extract=False` — fayl matn uchun emas, o'zi kerak bo'lganda (masalan
    konvertatsiya): u holda faqat yuklab olinadi.
    """
    document = getattr(message, "document", None)
    if document is None:
        await message.answer(
            get_text(language, "upload_wrong_type", formats=describe(accept))
        )
        return None

    file_name = document.file_name or ""
    extension = _extension(file_name, accept)
    if extension is None:
        await message.answer(
            get_text(language, "upload_wrong_type", formats=describe(accept))
        )
        return None

    # Hajm yuklashdan OLDIN tekshiriladi: aks holda 200 MB lik kitob
    # diskka tushib, botni yiqitardi.
    try:
        document_source.check_size(document.file_size)
    except document_source.SourceTooLarge:
        await message.answer(
            get_text(language, "upload_too_large",
                     limit=document_source.MAX_UPLOAD_BYTES // (1024 * 1024))
        )
        return None

    os.makedirs(TEMP_DIR, exist_ok=True)
    local_path = os.path.join(TEMP_DIR, f"{prefix}_{uuid.uuid4().hex[:10]}{extension}")
    try:
        telegram_file = await message.bot.get_file(document.file_id)
        await message.bot.download_file(telegram_file.file_path, local_path)
    except Exception as e:
        logger.error("Fayl yuklab olinmadi (%s): %s", file_name, e)
        document_source.cleanup(local_path)
        await message.answer(get_text(language, "upload_failed"))
        return None

    result = Upload(path=local_path, file_name=file_name, extension=extension,
                    size=document.file_size or 0)
    if not extract:
        return result

    try:
        result.extract = await document_source.read(local_path, file_name)
    except document_source.SourceTooLarge:
        document_source.cleanup(local_path)
        await message.answer(
            get_text(language, "upload_too_large",
                     limit=document_source.MAX_UPLOAD_BYTES // (1024 * 1024))
        )
        return None
    except document_source.SourceUnreadable as e:
        logger.warning("Fayl o'qilmadi (%s): %s", file_name, e)
        document_source.cleanup(local_path)
        await message.answer(get_text(language, "upload_unreadable"))
        return None
    except Exception as e:
        # Kutilmagan xato ham mijozning oqimini uzib qo'ymasin.
        logger.exception("Faylni o'qishda kutilmagan xato (%s): %s", file_name, e)
        document_source.cleanup(local_path)
        await message.answer(get_text(language, "upload_unreadable"))
        return None

    if not (result.text or "").strip():
        document_source.cleanup(local_path)
        await message.answer(get_text(language, "upload_empty"))
        return None

    return result


def discard(upload: Upload | None) -> None:
    """Vaqtinchalik faylni o'chiradi."""
    if upload is not None:
        document_source.cleanup(upload.path)
