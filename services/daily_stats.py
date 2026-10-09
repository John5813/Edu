"""Kunlik to'lov statistikasi: bugun /start bosganlardan nechtasi to'lov qildi, nechta to'lov eski mijozdan.

Admin «📈 Kunlik statistika» tugmasi va har kuni adminga yuboriladigan Excel shu yerdan oladi — ikkalasida
raqamlar bir xil chiqadi. Kun O'zbekiston vaqti bilan hisoblanadi (bazadagi vaqtlar UTC da): ilgari soat
00:00–05:00 orasidagi /start va to'lovlar oldingi kunga tushib qolardi.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import aiosqlite

# Bazada CURRENT_TIMESTAMP — UTC. O'zbekiston vaqti UTC+5.
UZT = "+5 hours"


def now_uzt() -> datetime:
    """Hozirgi vaqt O'zbekiston vaqti bilan (server UTC da ishlasa ham)."""
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5)


def today_uzt() -> str:
    """Bugungi sana O'zbekiston vaqti bilan (YYYY-MM-DD)."""
    return now_uzt().strftime("%Y-%m-%d")


def _day(column: str) -> str:
    return f"date(datetime({column}, '{UZT}'))"


async def payment_breakdown(day: str = "") -> Dict[str, int]:
    """Bir kunlik to'lovlar: yangi (shu kuni /start bosgan) va eski mijozlarga ajratilgan.

    Qaytaradi: started — shu kuni /start bosganlar; new_paid_users / new_payments / new_sum — ulardan
    to'lov qilganlar; old_paid_users / old_payments / old_sum — oldin kelgan mijozlarning to'lovlari;
    paid_users / payments / revenue — jami.
    """
    from database.database import DATABASE_FILE

    day = day or today_uzt()
    async with aiosqlite.connect(DATABASE_FILE) as db:
        async with db.execute(f"SELECT COUNT(*) FROM users WHERE {_day('created_at')} = ?", (day,)) as cur:
            started = (await cur.fetchone())[0]
        query = (
            "SELECT CASE WHEN " + _day("u.created_at") + " = ? THEN 'new' ELSE 'old' END AS kind, "
            "COUNT(DISTINCT p.user_id), COUNT(*), COALESCE(SUM(p.amount), 0) "
            "FROM payments p JOIN users u ON u.id = p.user_id "
            "WHERE p.status = 'approved' AND " + _day("p.created_at") + " = ? GROUP BY kind")
        async with db.execute(query, (day, day)) as cur:
            rows = {row[0]: row[1:] for row in await cur.fetchall()}
    new = rows.get("new", (0, 0, 0))
    old = rows.get("old", (0, 0, 0))
    return {
        "started": started,
        "new_paid_users": new[0], "new_payments": new[1], "new_sum": new[2],
        "old_paid_users": old[0], "old_payments": old[1], "old_sum": old[2],
        "paid_users": new[0] + old[0], "payments": new[1] + old[1], "revenue": new[2] + old[2],
    }


def conversion(stats: Dict[str, int]) -> str:
    """Bugun kelganlarning necha foizi to'lov qildi ("—" — hech kim kelmagan bo'lsa)."""
    if not stats["started"]:
        return "—"
    return f"{stats['new_paid_users'] * 100 / stats['started']:.1f}%"


def summary_text(stats: Dict[str, int]) -> str:
    """Admin xabari uchun bo'lak (bugungi kelganlar va to'lovlar)."""
    return (
        f"🆕 Bugun /start bosganlar: {stats['started']} ta\n"
        f"   💳 Shulardan to'lov qilganlar: {stats['new_paid_users']} ta ({conversion(stats)}) — "
        f"{stats['new_sum']:,} so'm\n\n"
        f"👤 Eski mijozlardan to'lovlar: {stats['old_payments']} ta ({stats['old_paid_users']} kishi) — "
        f"{stats['old_sum']:,} so'm\n\n"
        f"💳 Bugun to'lov qilganlar (jami): {stats['paid_users']} ta\n"
        f"📊 Bugun to'lovlar soni: {stats['payments']} ta\n"
        f"💰 Bugungi daromad: {stats['revenue']:,} so'm\n"
    )


async def new_users(day: str = "") -> List[Dict]:
    """Shu kuni ro'yxatdan o'tganlar, har birining tasdiqlangan to'lovlari bilan (soni va summasi)."""
    from database.database import DATABASE_FILE

    day = day or today_uzt()
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        query = (
            "SELECT u.telegram_id, u.first_name, u.username, u.language, u.balance, "
            "datetime(u.created_at, '" + UZT + "') AS joined, "
            "COUNT(p.id) AS paid_count, COALESCE(SUM(p.amount), 0) AS paid_sum "
            "FROM users u LEFT JOIN payments p ON p.user_id = u.id AND p.status = 'approved' "
            "WHERE " + _day("u.created_at") + " = ? GROUP BY u.id ORDER BY u.created_at")
        async with db.execute(query, (day,)) as cur:
            return [dict(row) for row in await cur.fetchall()]


async def payments_of_day(day: str = "") -> List[Dict]:
    """Shu kungi tasdiqlangan to'lovlar: kim, qancha, qachon va mijoz yangi yoki eski."""
    from database.database import DATABASE_FILE

    day = day or today_uzt()
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        query = (
            "SELECT u.telegram_id, u.first_name, u.username, p.amount, p.source, "
            "datetime(p.created_at, '" + UZT + "') AS paid_at, "
            "CASE WHEN " + _day("u.created_at") + " = ? THEN 1 ELSE 0 END AS is_new "
            "FROM payments p JOIN users u ON u.id = p.user_id "
            "WHERE p.status = 'approved' AND " + _day("p.created_at") + " = ? ORDER BY p.created_at")
        async with db.execute(query, (day, day)) as cur:
            return [dict(row) for row in await cur.fetchall()]
