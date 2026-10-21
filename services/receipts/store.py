"""Cheklar va takrorlanmas kalitlar bazasi."""
import json
import logging
from typing import Dict, Iterable, List, Optional, Tuple

import aiosqlite

import database.database as dbmod
from .rules import STRONG_KINDS, Prior

logger = logging.getLogger(__name__)


def _file() -> str:
    return dbmod.DATABASE_FILE          # testlarda almashtiriladi


async def find_priors(keys: List[Tuple[str, str]]) -> Dict[Tuple[str, str], Prior]:
    """Berilgan kalitlar bo'yicha avval saqlangan cheklar."""
    if not keys:
        return {}
    out: Dict[Tuple[str, str], Prior] = {}
    async with aiosqlite.connect(_file()) as db:
        for kind, value in keys:
            async with db.execute(
                "SELECT r.id, r.user_tg, r.verdict, r.payment_id, COALESCE(p.status, ''), r.created_at, "
                "(julianday('now') - julianday(r.created_at)) * 1440 "
                "FROM receipt_keys k JOIN payment_receipts r ON r.id = k.receipt_id "
                "LEFT JOIN payments p ON p.id = r.payment_id WHERE k.key = ?",
                (f"{kind}:{value}",)
            ) as cursor:
                row = await cursor.fetchone()
            if row:
                out[(kind, value)] = Prior(receipt_id=row[0], user_tg=row[1], verdict=row[2],
                                           payment_id=row[3], payment_status=row[4],
                                           created_at=str(row[5]), kind=kind,
                                           age_min=float(row[6] or 0))
    return out


async def save_receipt(user_tg: int, verdict: str, fraud: bool, amount: Optional[int],
                       claimed: int, reasons: List[str], data: dict,
                       keys: List[Tuple[str, str]], payment_id: Optional[int] = None,
                       takeover: Iterable[int] = ()) -> Tuple[int, bool]:
    """Chekni va kalitlarini bitta tranzaksiyada saqlaydi.

    Qaytaradi: (chek raqami, kalit bandmi). Kalit boshqa chekka tegishli bo'lsa (poyga: ikki chek
    bir vaqtda keldi) `INSERT OR IGNORE` uni o'zgartirmaydi — birinchi egasi qoladi; shunda pul
    ikki marta qo'shilmaydi.

    `takeover` — shu mijozning AI rad etgan oldingi cheklari: mijoz o'sha to'lovning to'g'ri chekini qayta
    yubordi, kalitlar yangi chekka o'tadi (aks holda tuzatilgan chek «takroriy» deb topilardi).
    """
    taken = False
    takeover = [int(x) for x in takeover]
    async with aiosqlite.connect(_file()) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "INSERT INTO payment_receipts (payment_id, user_tg, verdict, fraud, amount, claimed, "
                "reasons, data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (payment_id, user_tg, verdict, 1 if fraud else 0, amount, claimed,
                 json.dumps(reasons), json.dumps(data, ensure_ascii=False, default=str)))
            receipt_id = cursor.lastrowid
            if verdict not in ("not_receipt", "own_pending"):
                if takeover:
                    marks = ",".join("?" * len(takeover))
                    await db.execute(
                        f"UPDATE receipt_keys SET receipt_id = ? WHERE receipt_id IN ({marks}) AND receipt_id IN "
                        f"(SELECT id FROM payment_receipts WHERE user_tg = ? AND verdict = 'rejected')",
                        (receipt_id, *takeover, user_tg))
                for kind, value in keys:
                    key = f"{kind}:{value}"
                    result = await db.execute(
                        "INSERT OR IGNORE INTO receipt_keys (key, receipt_id, kind) VALUES (?, ?, ?)",
                        (key, receipt_id, kind))
                    if result.rowcount == 0 and kind in STRONG_KINDS:
                        async with db.execute("SELECT receipt_id FROM receipt_keys WHERE key = ?", (key,)) as cur:
                            owner = await cur.fetchone()
                        if not owner or owner[0] != receipt_id:
                            taken = True
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return receipt_id, taken


async def attach_payment(receipt_id: int, payment_id: int, verdict: Optional[str] = None) -> None:
    async with aiosqlite.connect(_file()) as db:
        if verdict:
            await db.execute("UPDATE payment_receipts SET payment_id = ?, verdict = ? WHERE id = ?",
                             (payment_id, verdict, receipt_id))
        else:
            await db.execute("UPDATE payment_receipts SET payment_id = ? WHERE id = ?",
                             (payment_id, receipt_id))
        await db.commit()


async def get_receipt(receipt_id: int) -> Optional[dict]:
    async with aiosqlite.connect(_file()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM payment_receipts WHERE id = ?", (receipt_id,)) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


async def mark(receipt_id: int, verdict: str, fraud: Optional[bool] = None) -> None:
    async with aiosqlite.connect(_file()) as db:
        if fraud is None:
            await db.execute("UPDATE payment_receipts SET verdict = ? WHERE id = ?", (verdict, receipt_id))
        else:
            await db.execute("UPDATE payment_receipts SET verdict = ?, fraud = ? WHERE id = ?",
                             (verdict, 1 if fraud else 0, receipt_id))
        await db.commit()


async def reasons_of(receipt_id: int) -> List[str]:
    """Saqlangan chekning sabablari (rad etilgan chek qayta yuborilganda AI'siz o'sha javob beriladi)."""
    row = await get_receipt(receipt_id)
    try:
        return list(json.loads(row["reasons"])) if row else []
    except (TypeError, ValueError):
        return []


async def reopen_rejected(payment_id: int) -> bool:
    """AI rad etgan to'lovni admin «baribir tasdiqlash» uchun qayta ochadi (bir marta: ikki admin bosa olmaydi)."""
    async with aiosqlite.connect(_file()) as db:
        cursor = await db.execute(
            "UPDATE payments SET status = 'pending' WHERE id = ? AND status = 'rejected' AND id IN "
            "(SELECT payment_id FROM payment_receipts WHERE verdict = 'rejected' AND payment_id IS NOT NULL)",
            (payment_id,))
        reopened = cursor.rowcount == 1
        if reopened:
            # Endi bu chek admin qarori bilan yopilgan: mijoz uni qayta yuborsa yangi chek sifatida o'qilmaydi.
            await db.execute("UPDATE payment_receipts SET verdict = 'review' WHERE payment_id = ? AND verdict = 'rejected'",
                             (payment_id,))
        await db.commit()
        return reopened


async def by_payment(payment_id: int) -> Optional[dict]:
    """To'lovga biriktirilgan AI-chek yozuvi (yo'q bo'lsa None)."""
    async with aiosqlite.connect(_file()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM payment_receipts WHERE payment_id = ? ORDER BY id DESC LIMIT 1",
                              (payment_id,)) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


async def today_counts() -> dict:
    """Bugungi cheklar soni verdict bo'yicha (kunlik statistika uchun; sana boshqa statistikalardagidek)."""
    async with aiosqlite.connect(_file()) as db:
        async with db.execute(
            "SELECT verdict, COUNT(*) FROM payment_receipts WHERE date(created_at) = date('now') GROUP BY verdict"
        ) as cursor:
            return {row[0]: row[1] for row in await cursor.fetchall()}
