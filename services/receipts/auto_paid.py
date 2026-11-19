"""Click, Payme yoki Uzum orqali to'langan pulning chekini mijoz yana «Kartaga o'tkazma» orqali yuborsa.

Bunday to'lov avtomatik qabul qilingan va balansga allaqachon qo'shilgan; chek adminga borsa, uni karta
o'tkazmasi deb tasdiqlab, pulni ikki marta qo'shib yuborish mumkin. AI'siz, faqat baza bo'yicha:

- mijozning so'nggi BLOCK_HOURS soat ichidagi avtomatik (Click/Payme/Uzum) to'lovi aynan shu summada bo'lsa —
  chek adminga BORMAYDI, mijozga «bu to'lov Payme orqali allaqachon qabul qilingan» deyiladi. Bitta avtomatik
  to'lov faqat bitta chekni to'xtatadi: mijoz haqiqatan alohida karta o'tkazmasi qilgan bo'lsa, chekni yana
  yuboradi va u adminga boradi (ogohlantirish bilan);
- adminga boradigan har bir chek kartochkasiga NOTE_HOURS soat ichidagi avtomatik to'lovlari yoziladi:
  «⚠️ Mijoz 14:32 da Payme orqali 50 000 so'm to'lagan (avtomatik qabul qilingan)».
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import aiosqlite

import database.database as dbmod

log = logging.getLogger(__name__)

AUTO = ("click", "payme", "uzum")
NAMES = {"click": "Click", "payme": "Payme", "uzum": "Uzum"}
BLOCK_HOURS = 6        # shu vaqt ichidagi bir xil summadagi avtomatik to'lov — chek adminga bormaydi
NOTE_HOURS = 48        # adminga boradigan chek kartochkasida shu vaqt ichidagi avtomatik to'lovlar ko'rsatiladi
TASHKENT = timedelta(hours=5)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _ensure(db) -> None:
    await db.execute("CREATE TABLE IF NOT EXISTS receipt_auto_match (payment_id INTEGER PRIMARY KEY, "
                     "user_tg INTEGER NOT NULL, created_at REAL NOT NULL)")


def _local(created_at: str) -> Optional[datetime]:
    """Baza vaqti (SQLite CURRENT_TIMESTAMP — UTC) → Toshkent vaqti."""
    try:
        return datetime.fromisoformat(str(created_at)[:19]) + TASHKENT
    except (TypeError, ValueError):
        return None


async def recent(user_tg: int, hours: float) -> List[dict]:
    """Mijozning so'nggi `hours` soatdagi tasdiqlangan avtomatik to'lovlari (yangisi birinchi)."""
    since = (_utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    marks = ",".join("?" * len(AUTO))
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as db:
        await _ensure(db)
        async with db.execute(
                f"SELECT p.id, p.amount, p.source, p.created_at, m.payment_id IS NOT NULL FROM payments p "
                f"JOIN users u ON u.id = p.user_id LEFT JOIN receipt_auto_match m ON m.payment_id = p.id "
                f"WHERE u.telegram_id = ? AND p.status = 'approved' AND p.source IN ({marks}) AND p.created_at >= ? "
                f"ORDER BY p.id DESC", (int(user_tg), *AUTO, since)) as cur:
            rows = await cur.fetchall()
    return [{"payment_id": pid, "amount": int(amount), "source": source, "at": _local(created), "used": bool(used)}
            for pid, amount, source, created, used in rows]


async def match(user_tg: int, amount) -> Optional[dict]:
    """Shu summadagi, hali hech bir chekni to'xtatmagan avtomatik to'lov topilsa — uni «ishlatilgan» deb belgilab
    qaytaradi (chek adminga yuborilmaydi). Topilmasa yoki xato bo'lsa — None (chek odatdagidek davom etadi)."""
    try:
        amount = int(amount)
        for row in await recent(user_tg, BLOCK_HOURS):
            if row["amount"] == amount and not row["used"]:
                async with aiosqlite.connect(dbmod.DATABASE_FILE) as db:
                    await _ensure(db)
                    await db.execute("INSERT OR IGNORE INTO receipt_auto_match (payment_id, user_tg, created_at) "
                                     "VALUES (?, ?, ?)", (row["payment_id"], int(user_tg), time.time()))
                    await db.execute("DELETE FROM receipt_auto_match WHERE created_at < ?",
                                     (time.time() - NOTE_HOURS * 3600,))
                    await db.commit()
                return row
    except Exception as exc:
        log.warning("Avtomatik to'lov bilan solishtirib bo'lmadi (%s): %s", user_tg, exc)
    return None


def _money(amount: int) -> str:
    return f"{int(amount):,}".replace(",", " ")


def _when(at: Optional[datetime]) -> str:
    if not at:
        return ""
    today = (_utcnow() + TASHKENT).date()
    return at.strftime("%H:%M") if at.date() == today else at.strftime("%d.%m %H:%M")


def user_reply(lang: str, row: dict) -> str:
    from . import texts
    return texts.user_text(lang if lang in ("uz", "ru", "en") else "ru", "auto_paid",
                           method=NAMES.get(row["source"], row["source"]), amount=_money(row["amount"]),
                           time=_when(row["at"]))


async def admin_note(user_tg: int) -> str:
    """Admin chek kartochkasi uchun ogohlantirish (avtomatik to'lov bo'lmasa — bo'sh)."""
    try:
        rows = await recent(user_tg, NOTE_HOURS)
    except Exception as exc:
        log.warning("Avtomatik to'lovlar o'qilmadi (%s): %s", user_tg, exc)
        return ""
    if not rows:
        return ""
    lines = ["⚠️ Diqqat: bu mijoz yaqinda avtomatik to'lov qilgan (balansiga allaqachon qo'shilgan):"]
    for row in rows[:3]:
        lines.append(f" • {_when(row['at'])} — {NAMES.get(row['source'], row['source'])} orqali "
                     f"{_money(row['amount'])} so'm (to'lov ID {row['payment_id']})")
    lines.append("Bu chek o'sha to'lovning cheki bo'lsa — tasdiqlamang, aks holda pul ikki marta qo'shiladi.")
    return "\n".join(lines)
