"""Tekin taqdimot havolalari (masalan, Instagram avtojavobi uchun): `t.me/<bot>?start=g_<kod>`.

Admin «🎛 Funksiyalar boshqaruvi» → «🔗 Tekin taqdimot havolalari» da havola yaratadi. Havola orqali kelgan har
bir mijoz — YANGI bo'lsa ham, bazada avvaldan bo'lsa ham, bepul sinovni ishlatgan bo'lsa ham — shu havoladan
BIR MARTA 5 slaydli tekin taqdimot oladi (botdagi sovg'a oqimi, `bot/handlers/reengage.py`).

Imkoniyat buyurtma berilganda band qilinadi (`claim`; jadvalda (kod, telegram_id) — asosiy kalit, ikki marta
bosilsa ham bittasi o'tadi). Taqdimot tayyorlanmay qolsa qaytariladi (`release`), mijozga yetgach belgilanadi
(`mark_delivered`) — bepul sinovdagi (`database.free_trial`) bilan bir xil tartib.
"""
import re
import secrets
import string
import time
from typing import Dict, List, Optional

import aiosqlite

from database import database as _db

PREFIX = "g_"
PENDING = "bot-"
DONE = "bot-sent-"
_CODE = re.compile(r"^[A-Za-z0-9]{4,32}$")

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS gift_links (
        code TEXT PRIMARY KEY,
        title TEXT NOT NULL DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1,
        created_at REAL NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS gift_link_clicks (
        code TEXT NOT NULL,
        telegram_id INTEGER NOT NULL,
        created_at REAL NOT NULL,
        PRIMARY KEY (code, telegram_id)
    )""",
    """CREATE TABLE IF NOT EXISTS gift_link_uses (
        code TEXT NOT NULL,
        telegram_id INTEGER NOT NULL,
        job_id TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        PRIMARY KEY (code, telegram_id)
    )""",
)


async def _create(conn) -> None:
    for statement in SCHEMA:
        await conn.execute(statement)


def valid(code: str) -> bool:
    return bool(_CODE.match(code or ""))


def code_of(start_arg: str) -> Optional[str]:
    """`/start` parametridan havola kodi (`g_<kod>`), aks holda None."""
    if not (start_arg or "").startswith(PREFIX):
        return None
    code = start_arg[len(PREFIX):]
    return code if valid(code) else None


def url(bot_username: str, code: str) -> str:
    return f"https://t.me/{bot_username}?start={PREFIX}{code}"


async def create(title: str = "") -> str:
    alphabet = string.ascii_letters + string.digits
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(8))
            try:
                await conn.execute("INSERT INTO gift_links (code, title, active, created_at) VALUES (?, ?, 1, ?)",
                                   (code, (title or "")[:60], time.time()))
                await conn.commit()
                return code
            except aiosqlite.IntegrityError:
                continue


async def is_active(code: str) -> bool:
    if not valid(code):
        return False
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        async with conn.execute("SELECT active FROM gift_links WHERE code = ?", (code,)) as cursor:
            row = await cursor.fetchone()
    return bool(row and row[0])


async def deactivate(code: str) -> bool:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        cursor = await conn.execute("UPDATE gift_links SET active = 0 WHERE code = ?", (code,))
        await conn.commit()
        return cursor.rowcount > 0


async def record_click(code: str, telegram_id: int) -> None:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        await conn.execute("INSERT OR IGNORE INTO gift_link_clicks (code, telegram_id, created_at) VALUES (?, ?, ?)",
                           (code, int(telegram_id), time.time()))
        await conn.commit()


async def available(code: str, telegram_id: int) -> bool:
    """Havola faol va mijoz undan hali taqdimot olmagan."""
    if not await is_active(code):
        return False
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        async with conn.execute("SELECT 1 FROM gift_link_uses WHERE code = ? AND telegram_id = ?",
                                (code, int(telegram_id))) as cursor:
            return await cursor.fetchone() is None


async def claim(code: str, telegram_id: int, job_id: str) -> bool:
    if not await is_active(code):
        return False
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        try:
            await conn.execute("INSERT INTO gift_link_uses (code, telegram_id, job_id, created_at) VALUES (?, ?, ?, ?)",
                               (code, int(telegram_id), job_id, time.time()))
            await conn.commit()
        except aiosqlite.IntegrityError:
            return False
    return True


async def release(code: str, telegram_id: int, job_id: Optional[str]) -> bool:
    if not job_id:
        return False
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        cursor = await conn.execute("DELETE FROM gift_link_uses WHERE code = ? AND telegram_id = ? AND job_id = ?",
                                    (code, int(telegram_id), job_id))
        await conn.commit()
        return cursor.rowcount > 0


async def mark_delivered(code: str, telegram_id: int, job_id: str) -> None:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        await conn.execute("UPDATE gift_link_uses SET job_id = ? WHERE code = ? AND telegram_id = ? AND job_id = ?",
                           (DONE + job_id[len(PENDING):], code, int(telegram_id), job_id))
        await conn.commit()


async def release_unfinished_bot() -> int:
    """Bot qayta ishga tushganda: tayyorlanayotgan paytda uzilib qolgan taqdimotlar mijozga qaytariladi."""
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        cursor = await conn.execute("DELETE FROM gift_link_uses WHERE job_id LIKE ? AND job_id NOT LIKE ?",
                                    (PENDING + "%", DONE + "%"))
        await conn.commit()
        return cursor.rowcount


async def links(active_only: bool = True) -> List[Dict]:
    """Havolalar hisobi bilan: bosganlar va taqdimot olganlar soni (yangisi birinchi)."""
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        query = ("SELECT l.code, l.title, l.active, l.created_at, "
                 "(SELECT COUNT(*) FROM gift_link_clicks c WHERE c.code = l.code), "
                 "(SELECT COUNT(*) FROM gift_link_uses u WHERE u.code = l.code AND u.job_id LIKE ?) "
                 "FROM gift_links l" + (" WHERE l.active = 1" if active_only else "") + " ORDER BY l.created_at DESC")
        async with conn.execute(query, (DONE + "%",)) as cursor:
            rows = await cursor.fetchall()
    return [{"code": r[0], "title": r[1], "active": bool(r[2]), "created_at": r[3], "clicks": r[4], "delivered": r[5]}
            for r in rows]
