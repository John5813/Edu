"""Sayt (edufayl.org) uchun jadvallar: kirish tokenlari, sessiyalar va ishlar.

Maxfiylik: bot hujjat mavzulari va fayl yo'llarini saqlamaydi (`document_orders` tozalanadi).
Saytdagi ishlar: tayyor fayl yopiq Telegram guruhiga (ombor, `services/web_archive.py`) yuklanadi va «Hujjatlarim»
da `ARCHIVE_TTL_HOURS` (30 kun) turadi; serverdagi nusxasi esa `JOB_TTL_HOURS` (3 kun) dan keyin o'chadi (kerak
bo'lsa ombordan qayta olinadi). Omborga yetmagan fayl — 3 kun. Kirish tokenlari faqat xesh ko'rinishida turadi.
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
GO_TTL = 15 * 60               # botdagi «saytda ochish» tugmasi 15 daqiqa amal qiladi (bir marta)
JOB_TTL_HOURS = 72             # serverdagi nusxa 3 kun (omborga yetmagan fayl — buyurtmasi bilan birga)
ARCHIVE_TTL_HOURS = 30 * 24    # omborga (yopiq guruh) yetgan fayl «Hujjatlarim» da 30 kun turadi
PENDING_TTL = 6 * 3600         # to'lovni kutayotgan buyurtma 6 soat eslab turiladi
DRAFT_TTL = 7 * 24 * 3600      # chala buyurtma qoralamasi 7 kun

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
    # To'lovni kutayotgan buyurtma (har akkauntga bitta): balans to'lishi bilan o'zi boshlanadi.
    # job_id: NULL — kutmoqda, 'starting' — boshlanmoqda, aks holda boshlangan ish.
    """CREATE TABLE IF NOT EXISTS web_pending (
        telegram_id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        params TEXT NOT NULL DEFAULT '{}',
        price INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL,
        job_id TEXT
    )""",
    # Botdan saytga havolalar: berilgan, ishlatilgan (saytga kirdi), eskirgan holda ochilgan (kunlik statistika uchun).
    """CREATE TABLE IF NOT EXISTS web_go_log (
        token_hash TEXT PRIMARY KEY,
        telegram_id INTEGER NOT NULL,
        issued_at REAL NOT NULL,
        used_at REAL,
        late_at REAL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_web_go_log_issued ON web_go_log (issued_at)",
    # Chala buyurtma qoralamasi (har akkauntga bitta): botdan qayta kelganda tanlovlar qaytadi.
    """CREATE TABLE IF NOT EXISTS web_drafts (
        telegram_id INTEGER PRIMARY KEY,
        data TEXT NOT NULL,
        updated_at REAL NOT NULL
    )""",
)


def hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(24)


_MIGRATED = set()


async def create_tables(conn) -> None:
    for statement in _SCHEMA:
        await conn.execute(statement)
    db_file = _db.DATABASE_FILE
    if db_file not in _MIGRATED:
        # tg_sent: tayyor fayl Telegramga yetdimi (0 — hali/kerak emas, 1 — fayl, 2 — havola, -1 — yetmadi).
        async with conn.execute("PRAGMA table_info(web_jobs)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        if "tg_sent" not in columns:
            await conn.execute("ALTER TABLE web_jobs ADD COLUMN tg_sent INTEGER NOT NULL DEFAULT 0")
        # vault_file_id: yopiq guruhdagi (ombordagi) nusxa — server qayta ishga tushsa yoki nusxa o'chsa ham fayl
        # shundan olinadi; vault_version — o'sha nusxa qaysi fayl holatidan (tahrirdan keyin yangisi yuklanadi).
        for column in ("vault_file_id", "vault_version"):
            if column not in columns:
                await conn.execute(f"ALTER TABLE web_jobs ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        # tg_version: Telegramga yuborilgan fayl nusxasi (hajm-vaqt) — tahrirdan keyin yangisi qayta yuboriladi.
        if "tg_version" not in columns:
            await conn.execute("ALTER TABLE web_jobs ADD COLUMN tg_version TEXT NOT NULL DEFAULT ''")
        _MIGRATED.add(db_file)


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


async def start_go(telegram_id: int) -> str:
    """Botdan saytga bir bosishda kirish: tasdiqlangan bir martalik token (bot tugmasiga qo'yiladi).

    Token `web_login` ga oldindan tasdiqlangan holda yoziladi, shuning uchun uni `poll_login` bir marta
    sessiyaga almashtiradi. Ochiq ko'rinishda faqat bot tugmasida turadi.
    """
    token = new_token()
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        await conn.execute("DELETE FROM web_login WHERE expires_at < ?", (time.time(),))
        await conn.execute("INSERT INTO web_login (token_hash, telegram_id, expires_at) VALUES (?, ?, ?)",
                           (hash_token(token), int(telegram_id), time.time() + GO_TTL))
        await conn.execute("INSERT OR IGNORE INTO web_go_log (token_hash, telegram_id, issued_at) VALUES (?, ?, ?)",
                           (hash_token(token), int(telegram_id), time.time()))
        await conn.execute("DELETE FROM web_go_log WHERE issued_at < ?", (time.time() - 60 * 24 * 3600,))
        await conn.commit()
    return token


async def go_seen(token: str, used: bool) -> None:
    """Botdagi havola orqali sayt ochildi: `used` — kirdi; aks holda havola eskirgan/ishlatilgan holda ochildi."""
    column = "used_at" if used else "late_at"
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        await conn.execute(f"UPDATE web_go_log SET {column} = ? WHERE token_hash = ? AND {column} IS NULL",
                           (time.time(), hash_token(token)))
        await conn.commit()


async def go_login_seen(telegram_id: int, key: str) -> None:
    """Telegram «Login URL» tugmasi orqali kirdi (havola oldindan berilmaydi — berilgan va ishlatilgan birga)."""
    now = time.time()
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        await conn.execute("INSERT OR IGNORE INTO web_go_log (token_hash, telegram_id, issued_at, used_at) "
                           "VALUES (?, ?, ?, ?)", ("tg:" + key, int(telegram_id), now, now))
        await conn.commit()


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
               "params", "title", "tg_sent", "tg_version", "vault_file_id", "vault_version")


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


async def archived_old(hours: int = JOB_TTL_HOURS) -> List[Dict]:
    """Omborda turgan, serverdagi nusxasi `hours` dan eski ishlar (nusxani o'chirsa bo'ladi — ombordan qaytadi)."""
    return await _rows("SELECT id, result_path FROM web_jobs WHERE status = 'done' AND COALESCE(vault_file_id, '') != '' "
                       "AND created_at < ?", (time.time() - hours * 3600,))


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


def expires_at(job: Dict) -> float:
    """Ish «Hujjatlarim» dan qachon o'chadi: omborga yetgan — 30 kun, aks holda — 3 kun."""
    hours = ARCHIVE_TTL_HOURS if (job.get("vault_file_id") or "") else JOB_TTL_HOURS
    return float(job["created_at"]) + hours * 3600


async def purge_expired(hours: int = JOB_TTL_HOURS, archive_hours: int = ARCHIVE_TTL_HOURS) -> List[str]:
    """Muddati o'tgan ishlar va ularning fayllari ro'yxatini qaytaradi, qatorlarni o'chiradi.

    Omborga yetgan tayyor ish — `archive_hours` (30 kun), qolganlari (omborsiz, bajarilmagan) — `hours` (3 kun)."""
    now = time.time()
    rows = await _rows("SELECT id, result_path FROM web_jobs WHERE status IN ('done', 'failed') AND ("
                       "created_at < ? OR (created_at < ? AND (COALESCE(vault_file_id, '') = '' OR status = 'failed')))",
                       (now - archive_hours * 3600, now - hours * 3600))
    if rows:
        async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
            await conn.executemany("DELETE FROM web_jobs WHERE id = ?", [(row["id"],) for row in rows])
            await conn.execute("DELETE FROM web_sessions WHERE expires_at < ?", (time.time(),))
            await conn.commit()
    return [row["result_path"] for row in rows if row.get("result_path")]


# ─────────────────────────────────────────── to'lovni kutayotgan buyurtma va qoralama

async def set_pending(telegram_id: int, kind: str, title: str, params: Dict, price: int) -> None:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        await conn.execute(
            "INSERT OR REPLACE INTO web_pending (telegram_id, kind, title, params, price, created_at, job_id) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL)",
            (int(telegram_id), kind, title, json.dumps(params, ensure_ascii=False), int(price), time.time()))
        await conn.commit()


async def get_pending(telegram_id: int) -> Optional[Dict]:
    rows = await _rows("SELECT * FROM web_pending WHERE telegram_id = ?", (int(telegram_id),))
    if not rows:
        return None
    row = rows[0]
    if time.time() - row["created_at"] > PENDING_TTL and not row.get("job_id"):
        await clear_pending(telegram_id)
        return None
    row["params"] = json.loads(row.get("params") or "{}")
    return row


async def claim_pending(telegram_id: int) -> bool:
    """Bir marta boshlash: ikki to'lov bir vaqtda kelsa ham buyurtma bitta bo'ladi."""
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        cursor = await conn.execute("UPDATE web_pending SET job_id = 'starting' WHERE telegram_id = ? AND job_id IS NULL",
                                    (int(telegram_id),))
        await conn.commit()
        return cursor.rowcount == 1


async def mark_pending(telegram_id: int, job_id: Optional[str]) -> None:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        await conn.execute("UPDATE web_pending SET job_id = ? WHERE telegram_id = ?", (job_id, int(telegram_id)))
        await conn.commit()


async def clear_pending(telegram_id: int) -> None:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        await conn.execute("DELETE FROM web_pending WHERE telegram_id = ?", (int(telegram_id),))
        await conn.commit()


async def save_draft(telegram_id: int, data: Dict) -> None:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        await conn.execute("INSERT OR REPLACE INTO web_drafts (telegram_id, data, updated_at) VALUES (?, ?, ?)",
                           (int(telegram_id), json.dumps(data, ensure_ascii=False), time.time()))
        await conn.execute("DELETE FROM web_drafts WHERE updated_at < ?", (time.time() - DRAFT_TTL,))
        await conn.commit()


async def get_draft(telegram_id: int) -> Optional[Dict]:
    rows = await _rows("SELECT data, updated_at FROM web_drafts WHERE telegram_id = ? AND updated_at >= ?",
                       (int(telegram_id), time.time() - DRAFT_TTL))
    if not rows:
        return None
    try:
        return {"data": json.loads(rows[0]["data"]), "updated_at": rows[0]["updated_at"]}
    except ValueError:
        return None


async def clear_draft(telegram_id: int) -> None:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await create_tables(conn)
        await conn.execute("DELETE FROM web_drafts WHERE telegram_id = ?", (int(telegram_id),))
        await conn.commit()
