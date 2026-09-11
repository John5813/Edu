"""Mijoz bergan manbani matnga aylantirish.

Loyiha ishi qo'llanmadan, taqdimotdan, muassasa saytidan yoki mijozning o'z
tushuntirishidan kelib chiqishi mumkin. Bu modul har qaysisini bitta narsaga
— matnga — keltiradi, keyin mazmun generatori o'shanga tayanadi.
"""

import logging
from dataclasses import dataclass

from services import document_source

logger = logging.getLogger(__name__)

KIND_AI = "ai"          # AI o'zi yozadi, tashqi manba yo'q
KIND_TEXT = "text"      # mijoz matn bilan tushuntirgan
KIND_FILE = "file"      # DOCX / PDF / PPTX
KIND_URL = "url"        # bir yoki bir nechta sayt

# Bir manbadan olinadigan maksimal matn. Undan ortig'i baribir promptga
# sig'maydi va sifatga hissa qo'shmaydi.
_MAX_SOURCE_CHARS = 60_000


@dataclass
class SourceMaterial:
    kind: str = KIND_AI
    text: str = ""
    label: str = ""

    @property
    def has_content(self) -> bool:
        return bool(self.text.strip())


def _trim(text: str) -> str:
    text = (text or "").strip()
    return text[:_MAX_SOURCE_CHARS]


def from_instructions(text: str) -> SourceMaterial:
    return SourceMaterial(kind=KIND_TEXT, text=_trim(text), label="")


async def from_file(local_path: str, file_name: str) -> SourceMaterial:
    """DOCX, PDF yoki PPTX fayldan matn ajratadi.

    O'qish `services.document_source` orqali ketadi: u betma-bet o'qiydi,
    kerakli hajmga yetganda to'xtaydi va og'ir ishlarni navbatga qo'yadi —
    ya'ni katta kitob botni yiqitmaydi.
    """
    return from_extract(await document_source.read(local_path, file_name), file_name)


def from_extract(extract, file_name: str) -> SourceMaterial:
    """Allaqachon o'qilgan matnni manba obyektiga aylantiradi.

    Faylni `bot.uploads` o'qib bergan bo'lsa, uni ikkinchi marta o'qish
    shart emas.
    """
    label = file_name
    if extract.is_partial:
        label = f"{file_name} ({extract.used_units}/{extract.total_units} {extract.unit})"
    return SourceMaterial(kind=KIND_FILE, text=_trim(extract.text), label=label)


async def from_urls(urls: list) -> SourceMaterial:
    """Bir yoki bir nechta sayt manzilidan matn yig'adi."""
    from services.url_book_service import fetch_multiple_urls

    result = await fetch_multiple_urls(urls)
    text = result.get("combined_content") or ""
    if result.get("total_word_count", 0) < 20 or not text.strip():
        failures = [r.get("error") or "fetch_failed" for r in result.get("results", []) if not r.get("ok")]
        raise ValueError(failures[0] if failures else "saytdan yetarli matn olinmadi")

    reached = [r["url"] for r in result.get("results", []) if r.get("ok")]
    labels = ", ".join(_domain(url) for url in reached) or ", ".join(_domain(u) for u in urls)
    return SourceMaterial(kind=KIND_URL, text=_trim(text), label=labels)


def _domain(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return urlparse(url).netloc or url
    except Exception:
        return url
