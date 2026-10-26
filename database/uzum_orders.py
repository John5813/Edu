"""Uzum Bank orqali balansni to'ldirish: tranzaksiyalar.

Uzum'da to'lov havolasi yo'q: mijoz Uzum ilovasida xizmatni topadi va hisob maydoniga Telegram ID'sini
yozadi. Uzum serveri `/create` bilan tranzaksiya ochadi (`CREATED`), pul yechilgach `/confirm` (`CONFIRMED`)
yoki `/reverse` (`REVERSED`) yuboradi.

Holat o'tishlari shartli UPDATE bilan: Uzum so'rovni ikki marta yuborsa ham balans bir marta qo'shiladi.
"""
import sqlite3
import time
from typing import Dict, Optional

import aiosqlite

from database import database as _db

CREATED, CONFIRMED, REVERSED, FAILED = "CREATED", "CONFIRMED", "REVERSED", "FAILED"

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS uzum_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trans_id TEXT NOT NULL UNIQUE,
        telegram_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        state TEXT NOT NULL DEFAULT 'CREATED',
        test INTEGER NOT NULL DEFAULT 0,
        create_time INTEGER NOT NULL,
        confirm_time INTEGER NOT NULL DEFAULT 0,
        reverse_time INTEGER NOT NULL DEFAULT 0,
        payment_source TEXT NOT NULL DEFAULT '',
        phone TEXT NOT NULL DEFAULT '',
        payment_id INTEGER
    )""",
    "CREATE INDEX IF NOT EXISTS uzum_tx_user ON uzum_transactions(telegram_id)",
)


def now_ms() -> int:
    return int(time.time() * 1000)


async def _conn():
    conn = await aiosqlite.connect(_db.DATABASE_FILE)
    conn.row_factory = aiosqlite.Row
    for statement in SCHEMA:
        await conn.execute(statement)
    return conn


async def _write(sql: str, args: tuple) -> int:
    """UPDATE/INSERT; o'zgargan qatorlar soni."""
    conn = await _conn()
    try:
        cursor = await conn.execute(sql, args)
        await conn.commit()
        return cursor.rowcount
    finally:
        await conn.close()


async def get_tx(trans_id: str) -> Optional[Dict]:
    conn = await _conn()
    try:
        async with conn.execute("SELECT * FROM uzum_transactions WHERE trans_id = ?", (str(trans_id),)) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await conn.close()


async def create_tx(trans_id: str, telegram_id: int, amount: int, test: bool) -> Optional[Dict]:
    """Yangi tranzaksiya (`CREATED`, summa tiyinda). Shu `transId` allaqachon bo'lsa — None."""
    try:
        await _write("INSERT INTO uzum_transactions (trans_id, telegram_id, amount, test, create_time) "
                     "VALUES (?, ?, ?, ?, ?)", (str(trans_id), int(telegram_id), int(amount), int(test), now_ms()))
    except sqlite3.IntegrityError:
        return None
    return await get_tx(trans_id)


async def claim_confirm(trans_id: str, payment_source: str, phone: str) -> bool:
    """CREATED → CONFIRMED, faqat bir marta. True — shu chaqiruv to'lovni o'ziga oldi."""
    return await _write("UPDATE uzum_transactions SET state = ?, confirm_time = ?, payment_source = ?, phone = ? "
                        "WHERE trans_id = ? AND state = ?",
                        (CONFIRMED, now_ms(), payment_source, phone, str(trans_id), CREATED)) == 1


async def unclaim_confirm(trans_id: str) -> None:
    """Balans qo'shilmadi — tranzaksiya qayta CREATED holatga (Uzum /confirm yoki /status'ni qayta yuboradi)."""
    await _write("UPDATE uzum_transactions SET state = ?, confirm_time = 0 WHERE trans_id = ? AND state = ?",
                 (CREATED, str(trans_id), CONFIRMED))


async def set_payment(trans_id: str, payment_id: int) -> None:
    await _write("UPDATE uzum_transactions SET payment_id = ? WHERE trans_id = ?", (payment_id, str(trans_id)))


async def reverse_tx(trans_id: str, from_state: str) -> bool:
    """CREATED/CONFIRMED → REVERSED."""
    return await _write("UPDATE uzum_transactions SET state = ?, reverse_time = ? WHERE trans_id = ? AND state = ?",
                        (REVERSED, now_ms(), str(trans_id), from_state)) == 1
