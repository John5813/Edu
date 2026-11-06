"""Reklama havolalari: bitta Instagram reklamasi uchun kuzatuv havolasi (`/go/<kod>` → botga `?start=ad_<kod>`).

Admin «🎛 Funksiyalar boshqaruvi» → «📈 Reklama havolalari» da havola yaratadi va uni Instagram reklamasining
«Veb-sayt» manziliga qo'yadi (har reklama uchun alohida havola). Havola quyidagini hisoblaydi:

* **bosganlar** — sayt havolasini ochgan odamlar (`ad_link_hits`; Meta tekshiruvchi botlari hisobga olinmaydi);
* **botga kirganlar** — botda Start bosganlar (`ad_link_starts`; har odam bir marta, birinchi kirishi), ular ikkiga bo'linadi:
    - **eski mijozlar** — Start bosilganda bazada avvaldan bor edi (reklama ularni qaytardi — *retarget*);
    - **yangi mijozlar** — birinchi marta shu reklama orqali keldi (*yangi auditoriya*);
* **Start bosmaganlar** — havolani bosgan, lekin botga kirmaganlar: adashib bosganlar yoki Telegram ochilmaganlar.

Reklama natijasi shu uch sonning nisbatiga qarab baholanadi (`verdict`).
"""
import hashlib
import re
import secrets
import string
import time
from typing import Dict, List, Optional

import aiosqlite

from database import database as _db

PREFIX = "ad_"
_CODE = re.compile(r"^[A-Za-z0-9]{4,32}$")
# Reklamani tekshiruvchi va havola ko'rinishini oluvchi botlar — ular «bosgan» hisoblanmaydi.
_BOT_UA = re.compile(r"bot|crawler|spider|facebookexternalhit|facebookcatalog|meta-externalagent|preview|"
                     r"slurp|python-requests|curl|wget|headless|monitor", re.IGNORECASE)

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS ad_links (
        code TEXT PRIMARY KEY,
        title TEXT NOT NULL DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1,
        created_at REAL NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS ad_link_hits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        visitor TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ad_link_hits_code ON ad_link_hits (code)",
    # Asosiy sxemadagi bilan bir xil (database.py): hisobot unga murojaat qiladi, bo'sh bazada ham xato bermasin.
    """CREATE TABLE IF NOT EXISTS balance_spends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS ad_link_starts (
        code TEXT NOT NULL,
        telegram_id INTEGER NOT NULL,
        was_new INTEGER NOT NULL,
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
    """`/start` parametridan reklama havolasi kodi (`ad_<kod>`), aks holda None."""
    if not (start_arg or "").startswith(PREFIX):
        return None
    code = start_arg[len(PREFIX):]
    return code if valid(code) else None


def bot_url(bot_username: str, code: str) -> str:
    return f"https://t.me/{bot_username}?start={PREFIX}{code}"


def is_bot_agent(user_agent: str) -> bool:
    """Reklama tekshiruvchisi, qidiruv boti yoki bo'sh User-Agent — haqiqiy mijoz emas."""
    return not (user_agent or "").strip() or bool(_BOT_UA.search(user_agent))


def visitor_hash(ip: str, user_agent: str) -> str:
    """Bir odamni qayta sanamaslik uchun: IP manzilning o'zi saqlanmaydi, faqat qaytarilmas belgi."""
    return hashlib.sha256(f"{ip}|{user_agent}".encode("utf-8", "ignore")).hexdigest()[:16]


async def create(title: str = "") -> str:
    alphabet = string.ascii_lowercase + string.digits
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(7))
            try:
                await conn.execute("INSERT INTO ad_links (code, title, active, created_at) VALUES (?, ?, 1, ?)",
                                   (code, (title or "").strip()[:60], time.time()))
                await conn.commit()
                return code
            except aiosqlite.IntegrityError:
                continue


async def exists(code: str) -> bool:
    """Havola mavjud (o'chirilgan bo'lsa ham): o'chirilgan havola ham mijozni botga olib boradi, faqat hisoblanmaydi."""
    if not valid(code):
        return False
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        async with conn.execute("SELECT 1 FROM ad_links WHERE code = ?", (code,)) as cursor:
            return await cursor.fetchone() is not None


async def is_active(code: str) -> bool:
    if not valid(code):
        return False
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        async with conn.execute("SELECT active FROM ad_links WHERE code = ?", (code,)) as cursor:
            row = await cursor.fetchone()
    return bool(row and row[0])


async def set_active(code: str, active: bool) -> bool:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        cursor = await conn.execute("UPDATE ad_links SET active = ? WHERE code = ?", (1 if active else 0, code))
        await conn.commit()
        return cursor.rowcount > 0


async def delete(code: str) -> bool:
    """Havola va uning butun hisobi o'chiriladi."""
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        cursor = await conn.execute("DELETE FROM ad_links WHERE code = ?", (code,))
        await conn.execute("DELETE FROM ad_link_hits WHERE code = ?", (code,))
        await conn.execute("DELETE FROM ad_link_starts WHERE code = ?", (code,))
        await conn.commit()
        return cursor.rowcount > 0


async def record_hit(code: str, visitor: str) -> None:
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        await conn.execute("INSERT INTO ad_link_hits (code, visitor, created_at) VALUES (?, ?, ?)",
                           (code, visitor, time.time()))
        await conn.commit()


async def record_start(code: str, telegram_id: int, was_new: bool) -> bool:
    """Botda Start bosildi. Har odam bir marta (birinchi kirishi): `was_new` — shu paytda bazada yo'q edi.
    Faqat mavjud va faol havola hisoblanadi; yangi yozilgan bo'lsa True."""
    if not await is_active(code):
        return False
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        cursor = await conn.execute(
            "INSERT OR IGNORE INTO ad_link_starts (code, telegram_id, was_new, created_at) VALUES (?, ?, ?, ?)",
            (code, int(telegram_id), 1 if was_new else 0, time.time()))
        await conn.commit()
        return cursor.rowcount > 0


async def links() -> List[Dict]:
    """Hamma havolalar qisqa hisobi bilan (yangisi birinchi)."""
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        async with conn.execute("SELECT code, title, active, created_at FROM ad_links ORDER BY created_at DESC") as cur:
            rows = await cur.fetchall()
    return [{"code": r[0], "title": r[1], "active": bool(r[2]), "created_at": r[3]} for r in rows]


async def stats(code: str) -> Optional[Dict]:
    """Bitta havola hisoboti: bosganlar, botga kirganlar (yangi / eski) va ulardan nechtasi xizmatdan foydalangan.

    «Foydalangan» — Start bosgandan keyin balansdan yechim bo'lgan (`balance_spends`): hujjat yoki taqdimot buyurtma qilgan.
    """
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        async with conn.execute("SELECT code, title, active, created_at FROM ad_links WHERE code = ?", (code,)) as cur:
            head = await cur.fetchone()
        if not head:
            return None
        async with conn.execute("SELECT COUNT(*), COUNT(DISTINCT visitor) FROM ad_link_hits WHERE code = ?",
                                (code,)) as cur:
            hits, unique = await cur.fetchone()
        async with conn.execute(
                "SELECT s.was_new, COUNT(*), "
                "SUM(CASE WHEN EXISTS (SELECT 1 FROM balance_spends b WHERE b.telegram_id = s.telegram_id "
                "AND strftime('%s', b.created_at) + 0 >= s.created_at) THEN 1 ELSE 0 END) "
                "FROM ad_link_starts s WHERE s.code = ? GROUP BY s.was_new", (code,)) as cur:
            groups = {int(r[0]): (r[1], r[2] or 0) for r in await cur.fetchall()}
    new, new_used = groups.get(1, (0, 0))
    old, old_used = groups.get(0, (0, 0))
    return {"code": head[0], "title": head[1], "active": bool(head[2]), "created_at": head[3],
            "hits": hits, "unique": unique, "new": new, "new_used": new_used, "old": old, "old_used": old_used,
            "starts": new + old}


def _pct(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


def verdict(s: Dict) -> str:
    """Natijaning qisqa bahosi: reklama kimga yetyapti — eski mijozlargami, yangilargami yoki adashib bosganlargami."""
    starts, clicks = s["starts"], s["unique"]
    if clicks < 20 and starts < 10:
        return "⏳ Hali ma'lumot oz (kamida 20 ta bosish kerak). Reklama ishlashda davom etsin."
    notes = []
    stray = max(clicks - starts, 0)
    if clicks and _pct(stray, clicks) >= 60:
        notes.append(f"🙈 Bosganlarning {_pct(stray, clicks)}% i botga kirmagan: ko'pchilik reklamani adashib bosgan "
                     "yoki Telegram ochilmagan. Reklama matni va rasmini aniqroq qiling.")
    if starts:
        if _pct(s["old"], starts) >= 60:
            notes.append(f"🔄 Botga kirganlarning {_pct(s['old'], starts)}% i ESKI mijoz: reklama asosan retarget "
                         "(avvalgi mijozlarni qaytarish) bo'lib ishlayapti, yangi auditoriya kam.")
        elif _pct(s["new"], starts) >= 60:
            notes.append(f"🆕 Botga kirganlarning {_pct(s['new'], starts)}% i YANGI mijoz: reklama yangi auditoriya "
                         "olib kelyapti.")
        else:
            notes.append(f"⚖️ Eski ({_pct(s['old'], starts)}%) va yangi ({_pct(s['new'], starts)}%) mijozlar "
                         "taxminan teng: reklama ikkalasiga ham yetyapti.")
        if s["new"] >= 10 and _pct(s["new_used"], s["new"]) < 10:
            notes.append("⚠️ Yangi mijozlarning deyarli hech biri xizmatdan foydalanmagan: sifatsiz yoki tasodifiy trafik bo'lishi mumkin.")
    return "\n".join(notes) or "Hozircha aniq xulosa yo'q."
