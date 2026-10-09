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


async def _has_table(db, name: str) -> bool:
    async with db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)) as cur:
        return await cur.fetchone() is not None


async def cohort(days: int, day: str = "") -> Dict[str, int]:
    """Oxirgi `days` kunda (bugun bilan) /start bosgan yangi foydalanuvchilar: kim to'lov qildi, kim foydalandi.

    "Foydalangan" — balansdan pul yechilgan (hujjat, taqdimot, do'kon; `balance_spends`), saytda buyurtmasi
    bor yoki bepul sinovdan foydalangan. Yechimlar jadvali paydo bo'lishidan oldingilar uchun qo'shimcha
    belgi: to'lagan summasidan balansi kam qolgan (demak sarflagan).

    Qaytaradi: started; paid_users, paid_sum; paid_used (to'lab foydalangan), paid_unused (to'lagan, hali
    foydalanmagan); free_used (to'lovsiz — bonus/sinov bilan foydalangan); unused (umuman foydalanmagan).
    """
    from database.database import DATABASE_FILE

    day = day or today_uzt()
    async with aiosqlite.connect(DATABASE_FILE) as db:
        used = ["(u.balance < COALESCE(p.paid_sum, 0))"]
        if await _has_table(db, "balance_spends"):
            used.append("EXISTS (SELECT 1 FROM balance_spends s WHERE s.telegram_id = u.telegram_id)")
        if await _has_table(db, "web_jobs"):
            used.append("EXISTS (SELECT 1 FROM web_jobs j WHERE j.telegram_id = u.telegram_id "
                        "AND j.status IN ('done', 'running', 'queued'))")
        if await _has_table(db, "free_trials"):
            used.append("EXISTS (SELECT 1 FROM free_trials f WHERE f.telegram_id = u.telegram_id)")
        query = (
            "SELECT COALESCE(p.paid_sum, 0) > 0 AS paid, COALESCE(p.paid_sum, 0) AS paid_sum, "
            "(" + " OR ".join(used) + ") AS used "
            "FROM users u LEFT JOIN (SELECT user_id, SUM(amount) AS paid_sum FROM payments "
            "WHERE status = 'approved' GROUP BY user_id) p ON p.user_id = u.id "
            "WHERE " + _day("u.created_at") + " BETWEEN date(?, ?) AND ?")
        async with db.execute(query, (day, f"-{max(int(days), 1) - 1} days", day)) as cur:
            rows = await cur.fetchall()
    result = {"days": int(days), "started": len(rows), "paid_users": 0, "paid_sum": 0,
              "paid_used": 0, "paid_unused": 0, "free_used": 0, "unused": 0}
    for paid, paid_sum, used_flag in rows:
        if paid:
            result["paid_users"] += 1
            result["paid_sum"] += paid_sum
            result["paid_used" if used_flag else "paid_unused"] += 1
        else:
            result["free_used" if used_flag else "unused"] += 1
    return result


def _share(part: int, whole: int) -> str:
    return f"{part * 100 / whole:.0f}%" if whole else "—"


def cohort_text(stats: Dict[str, int]) -> str:
    """Umumiy statistikadagi bo'lim: N kunlik yangi foydalanuvchilar."""
    n = stats["started"]
    return (
        f"📅 Oxirgi {stats['days']} kun — /start bosganlar: {n} ta\n"
        f"   💳 To'lov qilganlar: {stats['paid_users']} ta ({_share(stats['paid_users'], n)}) — "
        f"{stats['paid_sum']:,} so'm\n"
        f"   ✅ To'lov qilib foydalanganlar: {stats['paid_used']} ta\n"
        f"   ⏳ To'lagan, hali foydalanmagan: {stats['paid_unused']} ta\n"
        f"   🎁 To'lovsiz foydalanganlar (bonus/bepul): {stats['free_used']} ta\n"
        f"   💤 Umuman foydalanmaganlar: {stats['unused']} ta ({_share(stats['unused'], n)})\n"
    )
