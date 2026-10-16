"""Bepul sinov taqdimoti: har akkauntga BIR MARTA, 5 slayd (arzon model, rasmsiz).

Imkoniyat buyurtma berilganda «band qilinadi» (`claim`) — bir vaqtda ikki marta bosilsa ham faqat bittasi
o'tadi (jadvalda telegram_id — asosiy kalit). Taqdimot tayyorlanmay qolsa (xato, bekor qilish, server qayta
ishga tushishi), imkoniyat qaytariladi (`release`) — xuddi pul qaytarilgandek.
"""
import time
from typing import Optional

import aiosqlite

from database import database as _db

SLIDES = 5
MODEL = "google/gemini-2.5-flash-lite"

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS free_trials (
        telegram_id INTEGER PRIMARY KEY,
        job_id TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL
    )""",
    # Sovg'a muddati: faol bo'lmagan mijozga «sovg'angiz 48 soatda tugaydi» deyilgan bo'lsa, shu vaqtdan keyin
    # imkoniyat yopiladi (bot ham, sayt ham) — xabardagi muddat haqiqiy bo'lsin.
    """CREATE TABLE IF NOT EXISTS free_trial_deadlines (
        telegram_id INTEGER PRIMARY KEY,
        expires_at REAL NOT NULL
    )""",
)


async def _create(conn) -> None:
    for statement in SCHEMA:
        await conn.execute(statement)


async def _expired(conn, telegram_id: int) -> bool:
    async with conn.execute("SELECT expires_at FROM free_trial_deadlines WHERE telegram_id = ?",
                            (int(telegram_id),)) as cursor:
        row = await cursor.fetchone()
    return bool(row) and row[0] <= time.time()


async def available(telegram_id: int) -> bool:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        async with conn.execute("SELECT 1 FROM free_trials WHERE telegram_id = ?", (int(telegram_id),)) as cursor:
            if await cursor.fetchone() is not None:
                return False
        return not await _expired(conn, telegram_id)


async def set_deadline(telegram_id: int, expires_at: float) -> None:
    """Sovg'a shu vaqtgacha amal qiladi (avval qo'yilgan muddat uzaytirilmaydi)."""
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        await conn.execute("INSERT OR IGNORE INTO free_trial_deadlines (telegram_id, expires_at) VALUES (?, ?)",
                           (int(telegram_id), float(expires_at)))
        await conn.commit()


async def deadline(telegram_id: int) -> Optional[float]:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        async with conn.execute("SELECT expires_at FROM free_trial_deadlines WHERE telegram_id = ?",
                                (int(telegram_id),)) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else None


async def claim(telegram_id: int, job_id: str) -> bool:
    """Imkoniyatni shu buyurtmaga band qiladi. Avval ishlatilgan yoki muddati o'tgan bo'lsa — False."""
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        if await _expired(conn, telegram_id):
            return False
        try:
            await conn.execute("INSERT INTO free_trials (telegram_id, job_id, created_at) VALUES (?, ?, ?)",
                               (int(telegram_id), job_id, time.time()))
            await conn.commit()
        except aiosqlite.IntegrityError:
            return False
    return True


async def release(telegram_id: int, job_id: Optional[str]) -> bool:
    """Tayyorlanmay qolgan buyurtmaning imkoniyatini qaytaradi (faqat aynan shu buyurtma band qilgan bo'lsa)."""
    if not job_id:
        return False
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        cursor = await conn.execute("DELETE FROM free_trials WHERE telegram_id = ? AND job_id = ?",
                                    (int(telegram_id), job_id))
        await conn.commit()
        return cursor.rowcount > 0


# Botdagi sovg'a taqdimoti shu belgi bilan band qilinadi; mijozga yetib borgach belgi `BOT_DONE` ga almashadi.
BOT_PENDING = "bot-"
BOT_DONE = "bot-sent-"


async def mark_delivered(telegram_id: int, job_id: str) -> None:
    """Botdagi sovg'a taqdimoti mijozga yetdi — endi u qayta ishga tushganda qaytarilmaydi."""
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        await conn.execute("UPDATE free_trials SET job_id = ? WHERE telegram_id = ? AND job_id = ?",
                           (BOT_DONE + job_id[len(BOT_PENDING):], int(telegram_id), job_id))
        await conn.commit()


async def release_unfinished_bot() -> int:
    """Bot qayta ishga tushganda: tayyorlanayotgan paytda uzilib qolgan sovg'alar mijozga qaytariladi.

    Sovg'a taqdimoti bot jarayonining ichida tayyorlanadi — bot yangilansa yoki qayta ishga tushsa ish yo'qoladi.
    Imkoniyat qaytarilmasa, mijoz taqdimotni olmay turib sovg'asidan ayrilardi.
    """
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        cursor = await conn.execute("DELETE FROM free_trials WHERE job_id LIKE ? AND job_id NOT LIKE ?",
                                    (BOT_PENDING + "%", BOT_DONE + "%"))
        await conn.commit()
        return cursor.rowcount

