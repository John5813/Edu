"""Dizayn namunalari rasmlari: taqdimot turi va uslubini tanlashda hamda «💵 Narxlar» bo'limida.

Rasmlar `tools/taqdimot_namuna.py` bilan haqiqiy chizish kodidan yasaladi (3D Anatomiyaniki va klassik
shablonlarniki avvaldan bor). Telegram'ga bir marta yuklangach `file_id` eslab qolinadi — keyingi
safar rasm qayta yuklanmaydi.
"""
import logging
import os
from typing import Dict, Optional

from aiogram.types import FSInputFile, Message

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PATHS = {
    "turlar": os.path.join(ROOT, "assets", "taqdimot", "turlar.jpg"),        # Infografik / Zamonaviy / Klassik
    "uslublar": os.path.join(ROOT, "assets", "taqdimot", "uslublar.jpg"),    # Zamonaviy: 5 uslub
    "klassik": os.path.join(ROOT, "attached_assets", "shablonlar_raqamli.png"),
    "kat3d": os.path.join(ROOT, "assets", "taqdimot", "uslublar_3d.jpg"),    # 3D taqdimot Pro: 11 uslub
    "med3d": os.path.join(ROOT, "assets", "med3d", "uslublar.jpg"),          # 3D Anatomiya: 12 uslub
}

_FILE_IDS: Dict[str, str] = {}
CAPTION_LIMIT = 1024           # Telegram: rasm ostidagi matn chegarasi (uzun mavzuda savol matn bo'lib ketadi)


def exists(key: str) -> bool:
    return os.path.exists(PATHS.get(key, ""))


def media(key: str):
    """Rasm: oldin yuklangan bo'lsa `file_id`, aks holda fayl."""
    return _FILE_IDS.get(key) or FSInputFile(PATHS[key])


def remember(key: str, sent: Optional[Message]) -> None:
    if sent is not None and getattr(sent, "photo", None):
        _FILE_IDS[key] = sent.photo[-1].file_id


async def send(message: Message, key: str, caption: str = "", **kwargs) -> Optional[Message]:
    """Namuna rasmini yuboradi. Rasm yo'q yoki ketmasa — None (chaqiruvchi matn bilan davom etadi)."""
    if not exists(key) or len(caption) > CAPTION_LIMIT:
        return None
    try:
        sent = await message.answer_photo(media(key), caption=caption or None, **kwargs)
    except Exception as exc:
        if key in _FILE_IDS:                     # eskirgan file_id — fayldan qayta urinadi
            _FILE_IDS.pop(key, None)
            return await send(message, key, caption, **kwargs)
        logger.warning("Namuna rasmi (%s) yuborilmadi: %s", key, exc)
        return None
    remember(key, sent)
    return sent
