"""Payme orqali balansni to'ldirish: buyurtmalar va Payme tranzaksiyalari.

Mijoz summani tanlaganda buyurtma (`payme_orders`, `new`) yaratiladi; uning raqami Payme'ga
`account.order_id` bo'lib boradi. Payme serveri tranzaksiya ochadi (`payme_transactions`, holat 1),
keyin uni yakunlaydi (2) yoki bekor qiladi (-1 — yakunlanmasdan, -2 — yakunlangandan keyin).

Bir buyurtmada bir vaqtda faqat bitta faol (1) yoki yakunlangan (2) tranzaksiya bo'ladi — buni
qisman UNIQUE indeks kafolatlaydi. Holat o'tishlari shartli UPDATE bilan: Payme so'rovni ikki marta
yuborsa ham balans bir marta qo'shiladi.
"""
import sqlite3
import time
from typing import Dict, List, Optional

import aiosqlite

from database import database as _db

NEW, PAID, CANCELLED = "new", "paid", "cancelled"
CREATED, PERFORMED, CANCELLED_CREATED, CANCELLED_PERFORMED = 1, 2, -1, -2

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS payme_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'new',
        source TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS payme_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payme_id TEXT NOT NULL UNIQUE,
        order_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        state INTEGER NOT NULL DEFAULT 1,
        reason INTEGER,
        payme_time INTEGER NOT NULL,
        create_time INTEGER NOT NULL,
        perform_time INTEGER NOT NULL DEFAULT 0,
        cancel_time INTEGER NOT NULL DEFAULT 0,
        payment_id INTEGER
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS payme_one_active ON payme_transactions(order_id) WHERE state IN (1, 2)",
    "CREATE INDEX IF NOT EXISTS payme_tx_time ON payme_transactions(payme_time)",
    # ChangePassword: Payme yuborgan yangi kalit. `env_key` — o'shanda .env da turgan kalit;
    # .env qo'lda o'zgartirilsa, saqlangan kalit eskirgan hisoblanadi.
    """CREATE TABLE IF NOT EXISTS payme_keys (
        mode TEXT PRIMARY KEY,
        env_key TEXT NOT NULL,
        key TEXT NOT NULL,
        updated_at REAL NOT NULL
    )""",
)


def now_ms() -> int:
    return int(time.time() * 1000)


async def _conn():
    conn = await aiosqlite.connect(_db.DATABASE_FILE)
    conn.row_factory = aiosqlite.Row
    for statement in SCHEMA:
        await conn.execute(statement)
    return conn


async def _one(sql: str, args: tuple) -> Optional[Dict]:
    conn = await _conn()
    try:
        async with conn.execute(sql, args) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await conn.close()


async def _write(sql: str, args: tuple) -> int:
    """UPDATE/INSERT; o'zgargan qatorlar soni."""
    conn = await _conn()
    try:
        cursor = await conn.execute(sql, args)
        await conn.commit()
        return cursor.rowcount
    finally:
        await conn.close()


# ─────────────────────────────────────────────────────────────── buyurtmalar

async def create_order(telegram_id: int, amount: int, source: str = "") -> int:
    now = time.time()
    conn = await _conn()
    try:
        cursor = await conn.execute(
            "INSERT INTO payme_orders (telegram_id, amount, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (telegram_id, int(amount), source, now, now))
        await conn.commit()
        return cursor.lastrowid
    finally:
        await conn.close()


async def get_order(order_id: int) -> Optional[Dict]:
    return await _one("SELECT * FROM payme_orders WHERE id = ?", (order_id,))


async def set_order_status(order_id: int, status: str) -> None:
    await _write("UPDATE payme_orders SET status = ?, updated_at = ? WHERE id = ?", (status, time.time(), order_id))


# ─────────────────────────────────────────────────────────────── tranzaksiyalar

async def get_tx(payme_id: str) -> Optional[Dict]:
    return await _one("SELECT * FROM payme_transactions WHERE payme_id = ?", (str(payme_id),))


async def active_tx(order_id: int) -> Optional[Dict]:
    """Buyurtmaning faol (1) yoki yakunlangan (2) tranzaksiyasi."""
    return await _one("SELECT * FROM payme_transactions WHERE order_id = ? AND state IN (1, 2)", (order_id,))


async def create_tx(payme_id: str, order_id: int, amount: int, payme_time: int) -> Optional[Dict]:
    """Yangi tranzaksiya (holat 1). Buyurtmada boshqa faol tranzaksiya bo'lsa — None."""
    try:
        await _write("INSERT INTO payme_transactions (payme_id, order_id, amount, payme_time, create_time) "
                     "VALUES (?, ?, ?, ?, ?)", (str(payme_id), order_id, int(amount), int(payme_time), now_ms()))
    except sqlite3.IntegrityError:
        return None
    return await get_tx(payme_id)


async def claim_perform(payme_id: str) -> bool:
    """1 → 2, faqat bir marta. True — shu chaqiruv to'lovni o'ziga oldi."""
    return await _write("UPDATE payme_transactions SET state = 2, perform_time = ? WHERE payme_id = ? AND state = 1",
                        (now_ms(), str(payme_id))) == 1


async def unclaim_perform(payme_id: str) -> None:
    """Balans qo'shilmadi — tranzaksiya qayta 1 holatga (Payme PerformTransaction'ni qayta yuboradi)."""
    await _write("UPDATE payme_transactions SET state = 1, perform_time = 0 WHERE payme_id = ? AND state = 2",
                 (str(payme_id),))


async def set_payment(payme_id: str, payment_id: int) -> None:
    await _write("UPDATE payme_transactions SET payment_id = ? WHERE payme_id = ?", (payment_id, str(payme_id)))


async def cancel_tx(payme_id: str, from_state: int, reason: Optional[int]) -> bool:
    """1 → -1 yoki 2 → -2."""
    return await _write("UPDATE payme_transactions SET state = ?, reason = ?, cancel_time = ? "
                        "WHERE payme_id = ? AND state = ?",
                        (-abs(from_state), reason, now_ms(), str(payme_id), from_state)) == 1


async def statement(start: int, end: int) -> List[Dict]:
    """GetStatement: Payme vaqti bo'yicha [start, end] oralig'idagi tranzaksiyalar."""
    conn = await _conn()
    try:
        async with conn.execute("SELECT * FROM payme_transactions WHERE payme_time BETWEEN ? AND ? ORDER BY payme_time",
                                (int(start), int(end))) as cursor:
            return [dict(row) for row in await cursor.fetchall()]
    finally:
        await conn.close()


# ─────────────────────────────────────────────────────────────── kalit (ChangePassword)

async def get_key(mode: str) -> Optional[Dict]:
    return await _one("SELECT * FROM payme_keys WHERE mode = ?", (mode,))


async def set_key(mode: str, env_key: str, key: str) -> None:
    await _write("INSERT INTO payme_keys (mode, env_key, key, updated_at) VALUES (?, ?, ?, ?) "
                 "ON CONFLICT(mode) DO UPDATE SET env_key = excluded.env_key, key = excluded.key, "
                 "updated_at = excluded.updated_at", (mode, env_key, key, time.time()))
