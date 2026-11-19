"""Bir chek — bir marta: mijoz adminga yetib borgan chekini qayta yuborsa, u adminga qayta bormaydi.

AI'siz, avtomatik tekshiruv — faqat chek faylining o'zi bo'yicha va faqat O'SHA MIJOZNING o'z cheklari orasida:
- faylning raqamli izi (SHA-256): aynan o'sha fayl (PDF yoki rasm) qayta yuborildi;
- Telegram fayl raqami (file_unique_id): botda chek qayta uzatildi yoki qayta yuborildi — o'zgarmaydi;
- rasmning ko'rinish izi: rasm kulrang 256×256 ga kichraytirilib piksellari solishtiriladi — galereyadan qayta
  tanlangan (Telegram qayta siqqan) o'sha skrinshot ham taniladi. Tepadagi holat qatori (soat) hisobga
  olinmaydi. Boshqa summa yoki vaqt yozilgan boshqa chekda raqamlar o'rnida piksellar keskin farq qiladi —
  u yangi chek hisoblanadi.

Mijozga holatiga qarab javob beriladi: kutilmoqda — «tasdiqlanishini kuting», tasdiqlangan — «allaqachon qabul
qilingan», rad etilgan — «ko'rib chiqilgan». Bot ham, sayt ham, AI tekshiruvi yoqilgan-o'chiqligidan qat'i nazar.
"""
import hashlib
import io
import logging
import time
import zlib
from typing import Optional

import aiosqlite
import numpy as np

import database.database as dbmod

log = logging.getLogger(__name__)

SIG = 256                     # ko'rinish izi: SIG×SIG kulrang (128 da «2» va «3» raqamlari ajralmasdi)
TOP_CUT = 0.07                # tepadagi holat qatori (soat, batareya) — har skrinshotda boshqacha
# Qayta siqilgan o'sha rasm: o'rtacha va eng katta piksel farqi shundan oshmaydi (sinovda: o'sha chek — eng
# ko'pi 12; summa, vaqt yoki ID'dagi bitta raqami boshqa chek — kamida 130).
MEAN_DIFF, MAX_DIFF = 3.5, 48
LOOKBACK_DAYS = 120
LIMIT = 200


def _file() -> str:
    return dbmod.DATABASE_FILE


async def _ensure(db) -> None:
    await db.execute("CREATE TABLE IF NOT EXISTS receipt_once (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                     "user_tg INTEGER NOT NULL, sha TEXT, uid TEXT, sig BLOB, ratio REAL, payment_id INTEGER, "
                     "created_at REAL)")
    await db.execute("CREATE INDEX IF NOT EXISTS ix_receipt_once_user ON receipt_once (user_tg, created_at)")


def signature(data: bytes) -> Optional[tuple]:
    """Rasmning ko'rinish izi: (kulrang SIG×SIG baytlar, eni/bo'yi nisbati). Rasm bo'lmasa — None."""
    try:
        from PIL import Image, ImageOps
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im).convert("L")
            w, h = im.size
            if w < 32 or h < 32:
                return None
            im = im.crop((0, int(h * TOP_CUT), w, h))
            return im.resize((SIG, SIG), Image.BILINEAR).tobytes(), round(w / h, 4)
    except Exception:
        return None


def same_picture(a: bytes, b: bytes) -> bool:
    x = np.frombuffer(a, np.uint8).astype(np.int16)
    y = np.frombuffer(b, np.uint8).astype(np.int16)
    if x.shape != y.shape:
        return False
    d = np.abs(x - y)
    return float(d.mean()) <= MEAN_DIFF and int(d.max()) <= MAX_DIFF


async def find(user_tg: int, data: bytes, uid: str = "") -> Optional[dict]:
    """Shu mijoz bu chekni avval yuborgan va u to'lov sifatida ko'rib chiqishga tushganmi.

    Qaytaradi: {"payment_id", "status"} (pending / approved / rejected) yoki None — yangi chek."""
    sha = hashlib.sha256(data).hexdigest()
    sig = signature(data)
    since = time.time() - LOOKBACK_DAYS * 86400
    async with aiosqlite.connect(_file()) as db:
        await _ensure(db)
        async with db.execute(
            "SELECT o.sha, o.uid, o.sig, o.ratio, o.payment_id, COALESCE(p.status, '') FROM receipt_once o "
            "LEFT JOIN payments p ON p.id = o.payment_id WHERE o.user_tg = ? AND o.created_at >= ? "
            "ORDER BY o.id DESC LIMIT ?", (int(user_tg), since, LIMIT)) as cursor:
            rows = await cursor.fetchall()
    for r_sha, r_uid, r_sig, r_ratio, payment_id, status in rows:
        if not status:                         # to'lov yozuvi yo'q (o'chirilgan) — to'sib qo'yilmaydi
            continue
        hit = r_sha == sha or (uid and r_uid == uid)
        if not hit and sig and r_sig and r_ratio and abs(r_ratio - sig[1]) <= 0.02 * max(r_ratio, sig[1]):
            try:
                hit = same_picture(sig[0], zlib.decompress(r_sig))
            except zlib.error:
                hit = False
        if hit:
            return {"payment_id": payment_id, "status": status}
    return None


async def remember(user_tg: int, data: bytes, uid: str, payment_id: Optional[int]) -> None:
    """Adminga (yoki avtomatik tasdiqqa) tushgan chek izini saqlaydi. Xato bo'lsa ham to'lov jarayoni to'xtamaydi."""
    if not payment_id:
        return
    try:
        sig = signature(data)
        async with aiosqlite.connect(_file()) as db:
            await _ensure(db)
            await db.execute(
                "INSERT INTO receipt_once (user_tg, sha, uid, sig, ratio, payment_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (int(user_tg), hashlib.sha256(data).hexdigest(), uid or "", zlib.compress(sig[0], 6) if sig else None,
                 sig[1] if sig else None, int(payment_id), time.time()))
            await db.commit()
    except Exception as exc:
        log.warning("Chek izi saqlanmadi (%s): %s", user_tg, exc)


def reply_key(status: str) -> str:
    """Takror chekka javob matni kaliti (`texts.user_text`)."""
    return {"approved": "own_done", "rejected": "once_rejected"}.get(status, "once_pending")
