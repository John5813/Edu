"""Click orqali balansni to'ldirish buyurtmalari (invoyslar).

Mijoz summani tanlaganda invoys yaratiladi (`new`); uning raqami Click'ga `merchant_trans_id`
bo'lib boradi. Click serveri avval Prepare (`prepared`), keyin Complete (`paid`) yuboradi.
`payments` jadvaliga yozuv faqat pul haqiqatan tushganda tushadi — to'lanmagan havolalar
admin kutish ro'yxatini to'ldirmasin.

`paid` ga o'tish shartli UPDATE bilan bajariladi: Click Complete'ni ikki marta yuborsa ham
balans bir marta qo'shiladi.
"""
import time
from typing import Dict, Optional

import aiosqlite

from database import database as _db

NEW, PREPARED, PAID, CANCELLED = "new", "prepared", "paid", "cancelled"

SCHEMA = """CREATE TABLE IF NOT EXISTS click_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    click_trans_id TEXT NOT NULL DEFAULT '',
    click_paydoc_id TEXT NOT NULL DEFAULT '',
    payment_id INTEGER,
    source TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
)"""


async def _conn():
    conn = await aiosqlite.connect(_db.DATABASE_FILE)
    conn.row_factory = aiosqlite.Row
    await conn.execute(SCHEMA)
    return conn


async def create(telegram_id: int, amount: int, source: str = "") -> int:
    now = time.time()
    conn = await _conn()
    try:
        cursor = await conn.execute(
            "INSERT INTO click_invoices (telegram_id, amount, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (telegram_id, int(amount), source, now, now))
        await conn.commit()
        return cursor.lastrowid
    finally:
        await conn.close()


async def get(invoice_id: int) -> Optional[Dict]:
    conn = await _conn()
    try:
        async with conn.execute("SELECT * FROM click_invoices WHERE id = ?", (invoice_id,)) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await conn.close()


async def prepare(invoice_id: int, click_trans_id: str, click_paydoc_id: str) -> bool:
    """`new`/`prepared` → `prepared` (Click qayta urinsa yangi tranzaksiya raqami yoziladi)."""
    conn = await _conn()
    try:
        cursor = await conn.execute(
            "UPDATE click_invoices SET status = ?, click_trans_id = ?, click_paydoc_id = ?, updated_at = ? "
            "WHERE id = ? AND status IN (?, ?)",
            (PREPARED, str(click_trans_id), str(click_paydoc_id), time.time(), invoice_id, NEW, PREPARED))
        await conn.commit()
        return cursor.rowcount == 1
    finally:
        await conn.close()


async def claim_paid(invoice_id: int, click_trans_id: str) -> bool:
    """`prepared` → `paid`, faqat bir marta. True — shu chaqiruv to'lovni o'ziga oldi."""
    conn = await _conn()
    try:
        cursor = await conn.execute(
            "UPDATE click_invoices SET status = ?, updated_at = ? WHERE id = ? AND status = ? AND click_trans_id = ?",
            (PAID, time.time(), invoice_id, PREPARED, str(click_trans_id)))
        await conn.commit()
        return cursor.rowcount == 1
    finally:
        await conn.close()


async def set_payment(invoice_id: int, payment_id: int) -> None:
    conn = await _conn()
    try:
        await conn.execute("UPDATE click_invoices SET payment_id = ?, updated_at = ? WHERE id = ?",
                           (payment_id, time.time(), invoice_id))
        await conn.commit()
    finally:
        await conn.close()


async def set_status(invoice_id: int, status: str, only_from: tuple = ()) -> bool:
    """Holatni o'zgartiradi (`only_from` — faqat shu holatlardan)."""
    conn = await _conn()
    try:
        if only_from:
            marks = ", ".join("?" for _ in only_from)
            cursor = await conn.execute(
                f"UPDATE click_invoices SET status = ?, updated_at = ? WHERE id = ? AND status IN ({marks})",
                (status, time.time(), invoice_id, *only_from))
        else:
            cursor = await conn.execute("UPDATE click_invoices SET status = ?, updated_at = ? WHERE id = ?",
                                        (status, time.time(), invoice_id))
        await conn.commit()
        return cursor.rowcount == 1
    finally:
        await conn.close()
