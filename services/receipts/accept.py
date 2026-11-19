"""Chek sifatida qanday fayl qabul qilinadi: faqat BITTA rasm (skrinshot) yoki PDF, MAX_MB gacha.

PPTX, APK, video, arxiv va boshqa fayllar, juda og'ir fayl, bir nechta birdan tanlangan rasm — qabul qilinmaydi
(bekorga adminga bormasin va server yuklanmasin). Bot (`payments.handle_payment_screenshot`) va sayt
(`receipts.web.submit`, `/api/v1/wallet/receipt`) bir xil qoidadan foydalanadi.
"""
import os
from typing import Optional

MAX_MB = 5
MAX_BYTES = MAX_MB * 1024 * 1024
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")
PDF_EXT = (".pdf",)
_MIMES = ("image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "application/pdf")


def problem(filename: str, mime: str, size: Optional[int]) -> Optional[str]:
    """None — qabul qilinadi; aks holda sabab: "too_big" yoki "bad_file"."""
    if size is not None and size > MAX_BYTES:
        return "too_big"
    ext = os.path.splitext((filename or "").lower())[1]
    mime = (mime or "").split(";")[0].strip().lower()
    if ext:
        return None if ext in IMAGE_EXT + PDF_EXT else "bad_file"
    return None if mime in _MIMES else "bad_file"
