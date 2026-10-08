"""Sayt akkauntlari: Google bilan kirish, Telegramsiz akkaunt va keyinchalik Telegramni ulash.

Botdagi hamma narsa (balans, to'lovlar, buyurtmalar) `users.telegram_id` ga bog'langan. Google bilan kelgan
odamga ham shu jadvalda qator ochiladi, faqat Telegram o'rniga **manfiy sayt raqami** beriladi
(`-(WEB_ID_BASE + n)`): u Telegram raqamlari (musbat) va admin qo'shgan vaqtinchalik qatorlar (`-vaqt`)
bilan to'qnashmaydi. Keyinroq odam Telegramni ulasa, sayt akkaunti Telegram akkauntiga **birlashtiriladi**
(balans, to'lovlar, buyurtmalar ko'chadi), Google esa o'sha akkauntga bog'lanib qoladi.

Xavfsizlik: Google kimligi faqat `sub` bo'yicha (email bo'yicha emas); birlashtirish faqat ikki tomonning
aniq tasdig'i bilan (sayt sessiyasi + botdagi "Ha" tugmasi) bajariladi.
"""
import logging
import time
from typing import Dict, Optional

import aiosqlite

from database import database as _db
from database import web_store

log = logging.getLogger(__name__)

WEB_ID_BASE = 9_000_000_000_000        # sayt akkauntlari: telegram_id <= -WEB_ID_BASE
LINK_TTL = 10 * 60                     # Telegramni ulash havolasi 10 daqiqa yashaydi
LANGUAGES = ("uz", "ru", "en", "kk")
DEFAULT_LANGUAGE = "uz"

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS web_identities (
        provider TEXT NOT NULL,
        subject TEXT NOT NULL,
        telegram_id INTEGER NOT NULL,
        email TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        PRIMARY KEY (provider, subject)
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_web_identities_user ON web_identities (telegram_id, provider)",
    """CREATE TABLE IF NOT EXISTS web_link (
        token_hash TEXT PRIMARY KEY,
        web_telegram_id INTEGER NOT NULL,
        expires_at REAL NOT NULL
    )""",
)


def is_web_only(telegram_id) -> bool:
    """Telegramsiz (faqat saytdagi) akkauntmi."""
    try:
        return int(telegram_id) <= -WEB_ID_BASE
    except (TypeError, ValueError):
        return False


def user_language(user) -> str:
    """Foydalanuvchi tili: bazada qozoq "kk" deb saqlanadi, `User` esa uni "ru" + `kazakh` ko'rinishida beradi."""
    code = getattr(user, "language", "") or ""
    if getattr(user, "kazakh", False) and code == "ru":
        return "kk"
    return clean_language(code)


def clean_language(value) -> str:
    value = str(value or "").strip().lower()
    return value if value in LANGUAGES else DEFAULT_LANGUAGE


async def ensure_tables() -> None:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        await conn.commit()


async def _create(conn) -> None:
    from database import free_trial

    await web_store.create_tables(conn)
    for statement in _SCHEMA + free_trial.SCHEMA:
        await conn.execute(statement)


# ───────────────────────────────────────────────────────────── kimlik va akkaunt

async def identity_by_subject(provider: str, subject: str) -> Optional[Dict]:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM web_identities WHERE provider = ? AND subject = ?",
                                (provider, subject)) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


async def identity_of(telegram_id: int, provider: str = "google") -> Optional[Dict]:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM web_identities WHERE telegram_id = ? AND provider = ?",
                                (int(telegram_id), provider)) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


async def _next_web_id(conn) -> int:
    async with conn.execute("SELECT MIN(telegram_id) FROM users WHERE telegram_id <= ?", (-WEB_ID_BASE,)) as cursor:
        row = await cursor.fetchone()
    lowest = row[0] if row and row[0] is not None else -WEB_ID_BASE
    return int(lowest) - 1


async def create_web_user(provider: str, subject: str, email: str, name: str, language: str) -> int:
    """Yangi sayt akkaunti (Telegramsiz) va unga Google kimligi. Qaytaradi: yangi (manfiy) telegram_id."""
    from database.database import Database

    language = clean_language(language)
    referral_code = await Database.generate_referral_code()
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        await conn.execute("BEGIN IMMEDIATE")
        try:
            tid = await _next_web_id(conn)
            # `username` ataylab bo'sh: u botdagi "adminning oldindan qo'shgan" qatorlari bilan aralashmasin.
            await conn.execute(
                "INSERT INTO users (telegram_id, username, first_name, language, referral_code) VALUES (?, NULL, ?, ?, ?)",
                (tid, (name or email.split("@")[0])[:80], language, referral_code))
            await conn.execute(
                "INSERT INTO web_identities (provider, subject, telegram_id, email, name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (provider, subject, tid, email, name or "", time.time()))
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return tid


async def create_session(telegram_id: int) -> str:
    """Sayt sessiyasi (cookie uchun token)."""
    session = web_store.new_token()
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        await conn.execute("INSERT INTO web_sessions (token_hash, telegram_id, expires_at) VALUES (?, ?, ?)",
                           (web_store.hash_token(session), int(telegram_id), time.time() + web_store.SESSION_TTL))
        await conn.commit()
    return session


async def attach_identity(telegram_id: int, provider: str, subject: str, email: str, name: str) -> None:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        await conn.execute(
            "INSERT INTO web_identities (provider, subject, telegram_id, email, name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (provider, subject, int(telegram_id), email, name or "", time.time()))
        await conn.commit()


# ───────────────────────────────────────────────────────── akkauntlarni birlashtirish

class MergeError(Exception):
    """Birlashtirib bo'lmadi (mijozga ko'rsatiladigan sabab)."""


async def merge(src_tid: int, dst_tid: int) -> int:
    """Sayt akkauntini (`src`) Telegram akkauntiga (`dst`) ko'chiradi. Qaytaradi: ko'chirilgan balans.

    Balans qo'shiladi; to'lovlar, cheklar, buyurtmalar, sessiyalar va Google kimligi `dst` ga o'tadi;
    `src` qatori o'chadi. Hammasi bitta tranzaksiyada: xato bo'lsa hech narsa o'zgarmaydi.
    """
    src_tid, dst_tid = int(src_tid), int(dst_tid)
    if not is_web_only(src_tid) or is_web_only(dst_tid) or src_tid == dst_tid:
        raise MergeError("Bu akkauntlarni birlashtirib bo'lmaydi.")
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        conn.row_factory = aiosqlite.Row
        await conn.execute("BEGIN IMMEDIATE")
        try:
            async with conn.execute("SELECT id, balance FROM users WHERE telegram_id = ?", (src_tid,)) as cursor:
                src = await cursor.fetchone()
            async with conn.execute("SELECT id FROM users WHERE telegram_id = ?", (dst_tid,)) as cursor:
                dst = await cursor.fetchone()
            if not src or not dst:
                raise MergeError("Akkaunt topilmadi.")
            async with conn.execute("SELECT COUNT(*) FROM web_identities WHERE telegram_id = ? AND provider = 'google'",
                                    (dst_tid,)) as cursor:
                if (await cursor.fetchone())[0]:
                    raise MergeError("Bu Telegram akkauntga boshqa Google akkaunt allaqachon ulangan.")
            moved = int(src["balance"] or 0)
            await conn.execute("UPDATE users SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                               (moved, dst_tid))
            await conn.execute("UPDATE payments SET user_id = ? WHERE user_id = ?", (dst["id"], src["id"]))
            await conn.execute("UPDATE document_orders SET user_id = ? WHERE user_id = ?", (dst["id"], src["id"]))
            await conn.execute("UPDATE payment_receipts SET user_tg = ? WHERE user_tg = ?", (dst_tid, src_tid))
            await conn.execute("UPDATE web_jobs SET telegram_id = ? WHERE telegram_id = ?", (dst_tid, src_tid))
            await conn.execute("UPDATE web_sessions SET telegram_id = ? WHERE telegram_id = ?", (dst_tid, src_tid))
            await conn.execute("UPDATE web_identities SET telegram_id = ? WHERE telegram_id = ?", (dst_tid, src_tid))
            # Bepul sinov bir odamga bir marta: ikkalasidan birida ishlatilgan bo'lsa — birlashganda ham ishlatilgan.
            await conn.execute("UPDATE OR IGNORE free_trials SET telegram_id = ? WHERE telegram_id = ?", (dst_tid, src_tid))
            await conn.execute("DELETE FROM free_trials WHERE telegram_id = ?", (src_tid,))
            await conn.execute("DELETE FROM web_link WHERE web_telegram_id = ?", (src_tid,))
            await conn.execute("DELETE FROM users WHERE telegram_id = ?", (src_tid,))
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    log.info("Sayt akkaunti %s Telegram akkaunti %s ga birlashtirildi (balans %s)", src_tid, dst_tid, moved)
    return moved


# ───────────────────────────────────────────────── Telegramni ulash (sayt → bot → tasdiq)

async def start_link(web_tid: int) -> str:
    """Telegramni ulash uchun bir martalik token (faqat sayt akkaunti uchun)."""
    if not is_web_only(web_tid):
        raise MergeError("Telegram allaqachon ulangan.")
    token = web_store.new_token()
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        await conn.execute("DELETE FROM web_link WHERE expires_at < ?", (time.time(),))
        await conn.execute("INSERT INTO web_link (token_hash, web_telegram_id, expires_at) VALUES (?, ?, ?)",
                           (web_store.hash_token(token), int(web_tid), time.time() + LINK_TTL))
        await conn.commit()
    return token


async def link_preview(token: str) -> Optional[Dict]:
    """Bot tasdiq so'rashdan oldin ko'rsatadigan ma'lumot: qaysi Google akkaunt ulanmoqda."""
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT web_telegram_id FROM web_link WHERE token_hash = ? AND expires_at >= ?",
                                (web_store.hash_token(token), time.time())) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        async with conn.execute("SELECT email, name FROM web_identities WHERE telegram_id = ? AND provider = 'google'",
                                (row["web_telegram_id"],)) as cursor:
            identity = await cursor.fetchone()
        async with conn.execute("SELECT balance FROM users WHERE telegram_id = ?", (row["web_telegram_id"],)) as cursor:
            user = await cursor.fetchone()
    return {"web_telegram_id": int(row["web_telegram_id"]), "email": (identity["email"] if identity else ""),
            "name": (identity["name"] if identity else ""), "balance": int(user["balance"] or 0) if user else 0}


async def complete_link(token: str, telegram_id: int) -> int:
    """Botdagi tasdiqdan keyin: sayt akkaunti shu Telegram akkauntiga birlashadi. Qaytaradi: ko'chgan balans."""
    info = await link_preview(token)
    if not info:
        raise MergeError("Havola eskirgan. Saytdan qaytadan urinib ko'ring.")
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        removed = await conn.execute("DELETE FROM web_link WHERE token_hash = ?", (web_store.hash_token(token),))
        await conn.commit()
        if removed.rowcount != 1:
            raise MergeError("Havola allaqachon ishlatilgan.")
    return await merge(info["web_telegram_id"], int(telegram_id))


# ───────────────────────────────────────────────────────────────────── profil

async def profile(telegram_id: int) -> Optional[Dict]:
    from database.database import Database

    user = await Database.get_user(telegram_id)
    if not user:
        return None
    identity = await identity_of(telegram_id)
    return {"id": int(telegram_id), "name": user.first_name or "", "language": user_language(user),
            "balance": int(user.balance or 0), "username": user.username or "",
            "telegram": not is_web_only(telegram_id), "email": (identity or {}).get("email", ""),
            "google": identity is not None}


async def update_profile(telegram_id: int, name: Optional[str], language: Optional[str]) -> None:
    sets, args = [], []
    if name is not None:
        name = " ".join(str(name).split())[:80]
        if len(name) < 2:
            raise ValueError("Ism kamida 2 ta belgidan iborat bo'lsin.")
        sets.append("first_name = ?"); args.append(name)
    if language is not None:
        if str(language).strip().lower() not in LANGUAGES:
            raise ValueError("Bunday til yo'q.")
        sets.append("language = ?"); args.append(str(language).strip().lower())
    if not sets:
        return
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await conn.execute(f"UPDATE users SET {', '.join(sets)}, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                           (*args, int(telegram_id)))
        await conn.commit()


def label(user, email: str = "") -> str:
    """Admin xabarlarida foydalanuvchini ko'rsatish: Telegram havolasi yoki «🌐 sayt: ism, email»."""
    if not is_web_only(user.telegram_id):
        return f"@{user.username}" if getattr(user, "username", None) else f"tg://user?id={user.telegram_id}"
    email = email or getattr(user, "web_email", "")
    return (f"🌐 sayt: {user.first_name or '—'}" + (f", {email}" if email else "")
            + f" (#{abs(int(user.telegram_id)) - WEB_ID_BASE})")


async def admin_label(user) -> str:
    if is_web_only(user.telegram_id):
        identity = await identity_of(user.telegram_id)
        return label(user, (identity or {}).get("email", ""))
    return label(user)
