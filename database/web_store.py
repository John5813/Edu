"""Sayt (edufayl.org) uchun jadvallar: kirish tokenlari, sessiyalar va ishlar.

Maxfiylik: bot hujjat mavzulari va fayl yo'llarini saqlamaydi (`document_orders` tozalanadi).
Saytdagi ishlar ham shu tamoyilga bo'ysunadi: tayyor fayl va uning qatori `JOB_TTL_HOURS`
dan keyin o'chiriladi (`purge_expired`), kirish tokenlari esa faqat xesh ko'rinishida turadi.
"""
import hashlib
import json
import logging
import secrets
import time
from typing import Dict, List, Optional

import aiosqlite

from database import database as _db

log = logging.getLogger(__name__)

LOGIN_TTL = 10 * 60            # bot orqali kirish havolasi 10 daqiqa yashaydi
SESSION_TTL = 30 * 24 * 3600   # sessiya 30 kun
JOB_TTL_HOURS = 72             # tayyor fayl 3 kun saqlanadi

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS web_login (
        token_hash TEXT PRIMARY KEY,
        telegram_id INTEGER,
        expires_at REAL NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS web_sessions (
        token_hash TEXT PRIMARY KEY,
        telegram_id INTEGER NOT NULL,
        expires_at REAL NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS web_jobs (
        id TEXT PRIMARY KEY,
        telegram_id INTEGER NOT NULL,
        kind TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        params TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'queued',
        stage TEXT NOT NULL DEFAULT '',
        progress INTEGER NOT NULL DEFAULT 0,
        price INTEGER NOT NULL DEFAULT 0,
        charged INTEGER NOT NULL DEFAULT 0,
        result_path TEXT,
        result_name TEXT,
        error TEXT,
        created_at REAL NOT NULL,
        finished_at REAL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_web_jobs_user ON web_jobs (telegram_id, created_at DESC)",
)


def hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(24)


async def create_tables(conn) -> None:
    for statement in _SCHEMA:
        await conn.execute(statement)


async def ensure_tables() -> None:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        await conn.commit()


# ───────────────────────────────────────────────────────────── kirish va sessiya

async def start_login() -> str:
    """Yangi bir martalik kirish tokeni (ochiq ko'rinishda faqat brauzerga beriladi)."""
    token = new_token()
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        await conn.execute("DELETE FROM web_login WHERE expires_at < ?", (time.time(),))
        await conn.execute("INSERT INTO web_login (token_hash, telegram_id, expires_at) VALUES (?, NULL, ?)",
                           (hash_token(token), time.time() + LOGIN_TTL))
        await conn.commit()
    return token


async def confirm_login(token: str, telegram_id: int) -> bool:
    """Bot foydalanuvchini tasdiqlaydi. False — token yo'q yoki muddati o'tgan."""
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        cursor = await conn.execute(
            "UPDATE web_login SET telegram_id = ? WHERE token_hash = ? AND expires_at >= ? AND telegram_id IS NULL",
            (int(telegram_id), hash_token(token), time.time()))
        await conn.commit()
        return cursor.rowcount == 1


async def poll_login(token: str) -> Optional[str]:
    """Brauzer so'raydi: tasdiqlangan bo'lsa sessiya tokeni (bir marta), aks holda None."""
    key = hash_token(token)
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        async with conn.execute("SELECT telegram_id FROM web_login WHERE token_hash = ? AND expires_at >= ?",
                                (key, time.time())) as cursor:
            row = await cursor.fetchone()
        if not row or row[0] is None:
            return None
        # Bir martalik: o'chirilgach ikkinchi marta sessiya bermaydi.
        removed = await conn.execute("DELETE FROM web_login WHERE token_hash = ?", (key,))
        if removed.rowcount != 1:
            await conn.commit()
            return None
        session = new_token()
        await conn.execute("INSERT INTO web_sessions (token_hash, telegram_id, expires_at) VALUES (?, ?, ?)",
                           (hash_token(session), int(row[0]), time.time() + SESSION_TTL))
        await conn.commit()
        return session


async def session_user(session: str) -> Optional[int]:
    if not session:
        return None
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        async with conn.execute("SELECT telegram_id FROM web_sessions WHERE token_hash = ? AND expires_at >= ?",
                                (hash_token(session), time.time())) as cursor:
            row = await cursor.fetchone()
    return int(row[0]) if row else None


async def end_session(session: str) -> None:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        await conn.execute("DELETE FROM web_sessions WHERE token_hash = ?", (hash_token(session),))
        await conn.commit()


# ──────────────────────────────────────────────────────────────────────── ishlar

_JOB_FIELDS = ("status", "stage", "progress", "charged", "result_path", "result_name", "error", "finished_at",
               "params", "title")


async def create_job(job_id: str, telegram_id: int, kind: str, title: str, params: Dict, price: int,
                     charged: bool = True) -> None:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        await conn.execute(
            "INSERT INTO web_jobs (id, telegram_id, kind, title, params, price, charged, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, int(telegram_id), kind, title, json.dumps(params, ensure_ascii=False), int(price),
             1 if charged else 0, time.time()))
        await conn.commit()


async def update_job(job_id: str, **fields) -> None:
    fields = {key: value for key, value in fields.items() if key in _JOB_FIELDS}
    if not fields:
        return
    if isinstance(fields.get("params"), dict):
        fields["params"] = json.dumps(fields["params"], ensure_ascii=False)
    names = ", ".join(f"{key} = ?" for key in fields)
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        await conn.execute(f"UPDATE web_jobs SET {names} WHERE id = ?", (*fields.values(), job_id))
        await conn.commit()


async def _rows(query: str, args: tuple) -> List[Dict]:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        conn.row_factory = aiosqlite.Row
        async with conn.execute(query, args) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_job(job_id: str, telegram_id: Optional[int] = None) -> Optional[Dict]:
    query, args = "SELECT * FROM web_jobs WHERE id = ?", (job_id,)
    if telegram_id is not None:
        query, args = query + " AND telegram_id = ?", (job_id, int(telegram_id))
    rows = await _rows(query, args)
    return rows[0] if rows else None


async def list_jobs(telegram_id: int, limit: int = 30) -> List[Dict]:
    return await _rows("SELECT * FROM web_jobs WHERE telegram_id = ? ORDER BY created_at DESC LIMIT ?",
                       (int(telegram_id), int(limit)))


async def unfinished_jobs() -> List[Dict]:
    """Qayta ishga tushgandan keyin to'xtab qolgan ishlar (jarayon o'lgan, vazifa yo'q)."""
    return await _rows("SELECT * FROM web_jobs WHERE status IN ('queued', 'running')", ())


async def purge_expired(hours: int = JOB_TTL_HOURS) -> List[str]:
    """Muddati o'tgan ishlar va ularning fayllari ro'yxatini qaytaradi, qatorlarni o'chiradi."""
    cutoff = time.time() - hours * 3600
    rows = await _rows("SELECT id, result_path FROM web_jobs WHERE created_at < ? "
                       "AND status IN ('done', 'failed')", (cutoff,))
    if rows:
        async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
            await conn.executemany("DELETE FROM web_jobs WHERE id = ?", [(row["id"],) for row in rows])
            await conn.execute("DELETE FROM web_sessions WHERE expires_at < ?", (time.time(),))
            await conn.commit()
    return [row["result_path"] for row in rows if row.get("result_path")]
