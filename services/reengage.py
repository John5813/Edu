"""Qayta jalb: faol bo'lmagan mijozlarga vaqti-vaqti bilan ism bilan, tugmali xabar.

Statistika: oxirgi 30 kunda /start bosganlarning 96 foizi hech narsadan foydalanmagan. Ularga «qaytib keling»
emas, aniq sovg'a beriladi — 5 slaydli bepul taqdimot (`database.free_trial`), bir bosishda.

Guruhlar (har mijoz bittasiga tushadi):
  * new          — so'nggi 30 kunda kelgan, hech narsadan foydalanmagan va to'lamagan: 5 xabar (2 soat, 1, 3, 7,
                   14 kun) — sovg'a, namuna, boshqa xizmatlar, «Pul ishlab topish», sovg'a muddati (48 soat);
  * old          — eski bazadagi shunday mijozlar: o'sha 5 xabar, kuniga ko'pi bilan `OLD_DAILY` kishi boshlaydi;
                   botni to'sganlar ko'p bo'lsa ham TO'XTAMAYDI (to'sganlarga baribir qayta xabar bormaydi) —
                   ulush `PAUSE_RATE` dan oshsa adminga kuniga bir marta ma'lumot beriladi;
  * paid_unused  — to'lagan, lekin foydalanmagan: «hisobingizda X so'm turibdi» (3 xabar);
  * trial        — bepul taqdimotni olgan, to'lamagan: birinchi to'lovga +20% bonus, 7 kun (3 xabar);
  * lapsed       — foydalangan (to'lab yoki bonus bilan), 14 kundan beri kelmagan (2 xabar).
Bulardan tashqari har juma hammaga «💎 Juma bonusi» (`weekly_plan`): 20 000 so'mdan +25%, 30 000 so'mdan +30%;
mijozlarning yarmiga ertalab, qolgan yarmiga kechqurun.

Bonus FAQAT xabardagi maxsus tugma bosilganda faollashadi (`arm_offer`) va admin TASDIQLAGAN summaga hisoblanadi:
mijoz 20 000 deb 5 000 to'lasa, admin 5 000 ni tasdiqlaydi — bonus 5 000 dan. Admin bonusni ko'rmaydi, u
mijoz hisobiga alohida qo'shiladi.

Qoidalar: xabar faqat 10:00–21:00 (O'zbekiston vaqti), bir mijozga ikki xabar orasi kamida 20 soat, mijoz
foydalansa yoki to'lasa ketma-ketlik o'zi to'xtaydi (u boshqa guruhga o'tadi), xabar yetib bormagan (to'sgan
yoki yuborib bo'lmagan) mijozga u qayta faol bo'lmaguncha boshqa xabar bormaydi, admin bloklaganlar va adminlar chetda. Har xabarda tugma bor; bosilgani yoziladi (hisobot).
"""
import asyncio
import calendar
import contextlib
import html
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import aiosqlite

from services import reengage_texts as T

log = logging.getLogger(__name__)

HOUR = 3600
DAY = 24 * HOUR

QUIET = (10, 21)                 # xabar yuboriladigan soatlar (O'zbekiston vaqti): 10:00–20:59
MIN_GAP = 20 * HOUR              # bir mijozga ikki xabar orasi
NEW_WINDOW = 30 * DAY            # shundan yangi kelganlar "new", eskilari "old"
OFFSETS = {                      # har xabar guruh boshlanishidan necha soat keyin (keyingilari — oraliq saqlanadi)
    "new": (2, 24, 72, 168, 336),
    "old": (0, 24, 72, 168, 336),
    "paid_unused": (24, 72, 168),
    "trial": (24, 72, 168),
    "lapsed": (336, 720),
}
STEPS = {"new": "inactive", "old": "inactive", "paid_unused": "paid_unused", "trial": "trial", "lapsed": "lapsed",
         "weekly": "weekly"}
PRIORITY = ("trial", "paid_unused", "new", "lapsed", "old")
FLOW_NAMES = {"new": "🆕 Yangi, foydalanmagan", "old": "🗂 Eski baza, foydalanmagan",
              "paid_unused": "⏳ To'lagan, foydalanmagan", "trial": "🎁 Bepul sinovdan keyin",
              "lapsed": "💤 Foydalangan, 14+ kun kelmagan", "weekly": "💎 Juma bonusi (hammaga)"}
LAPSE = 14 * DAY
MIN_BALANCE = 3000               # "hisobingizda X so'm" — shundan kam bo'lsa xabar ma'nosiz
OLD_DAILY = 2500                 # eski bazadan kuniga shuncha kishi ketma-ketlikni boshlaydi
TICK_LIMIT = 600                 # bir aylanishda (10 daqiqa) ko'pi bilan shuncha xabar
TICK_SECONDS = 600
SEND_PAUSE = 0.05                # ~20 xabar/soniya — Telegram chegarasidan past
PAUSE_RATE = 0.20                # eski bazada to'sganlar ulushi shundan oshsa — adminga ma'lumot (to'xtamaydi)
PAUSE_MIN = 200                  # ulush shuncha xabardan keyin baholanadi
GIFT_HOURS = 48                  # oxirgi xabardagi sovg'a muddati
BONUS_PERCENT = 20
BONUS_DAYS = 7
WEEKLY_DAY = 4                   # juma (dushanba = 0)
WEEKLY_SLOTS = ((10, 13), (18, 21))   # mijozlarning 1-yarmi ertalab, 2-yarmi kechqurun (O'zbekiston vaqti)
WEEKLY_TIERS = ((30000, 30), (20000, 25))   # (to'lov kamida, bonus %) — kattasidan boshlab
WEEKLY_TICK = 1500               # juma xabari: bir aylanishda ko'pi bilan
UNDELIVERED = ("blocked", "failed")

FEATURE = "reengage"             # hammasi (admin «Funksiyalar boshqaruvi»da yoqadi/o'chiradi)
FEATURE_OLD = "reengage_old"     # eski baza to'lqini
FEATURE_WEEKLY = "reengage_weekly"   # har juma hammaga bonus xabari

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS nudges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER NOT NULL,
        flow TEXT NOT NULL,
        step INTEGER NOT NULL,
        sent_at REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        clicked_at REAL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_nudges_user ON nudges (telegram_id)",
    "CREATE INDEX IF NOT EXISTS idx_nudges_flow ON nudges (flow, sent_at)",
    """CREATE TABLE IF NOT EXISTS reengage_bonus (
        telegram_id INTEGER PRIMARY KEY,
        percent INTEGER NOT NULL,
        granted_at REAL NOT NULL,
        expires_at REAL NOT NULL,
        used_at REAL,
        amount INTEGER NOT NULL DEFAULT 0
    )""",
    "CREATE TABLE IF NOT EXISTS reengage_state (key TEXT PRIMARY KEY, value REAL)",
    # Bonus takliflari: trial (birinchi to'lovga +20%) va weekly (juma bonusi). Tugma bosilgach armed_at yoziladi.
    """CREATE TABLE IF NOT EXISTS reengage_offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER NOT NULL,
        kind TEXT NOT NULL,
        granted_at REAL NOT NULL,
        expires_at REAL NOT NULL,
        armed_at REAL,
        used_at REAL,
        amount INTEGER NOT NULL DEFAULT 0,
        UNIQUE (telegram_id, kind, granted_at)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_offers_user ON reengage_offers (telegram_id)",
    # Eski jadvaldagi bonuslar (tugmasiz berilgan) — bir marta ko'chiriladi.
    """INSERT OR IGNORE INTO reengage_offers (telegram_id, kind, granted_at, expires_at, used_at, amount)
       SELECT telegram_id, 'trial', granted_at, expires_at, used_at, amount FROM reengage_bonus""",
)


def _db_file() -> str:
    from database.database import DATABASE_FILE
    return DATABASE_FILE


async def _create(conn) -> None:
    for statement in SCHEMA:
        await conn.execute(statement)


async def _has_table(conn, name: str) -> bool:
    async with conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)) as cur:
        return await cur.fetchone() is not None


def _epoch(value) -> Optional[float]:
    """Bazadagi vaqt (UTC matn yoki epoch) → epoch soniya."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).replace("T", " ")[:19]
        return float(calendar.timegm(datetime.strptime(text, "%Y-%m-%d %H:%M:%S").timetuple()))
    except ValueError:
        return None


def uzt(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, timezone.utc).replace(tzinfo=None) + timedelta(hours=5)


def quiet(now: float) -> bool:
    """Hozir xabar yuborilmaydigan vaqtmi (kechasi va erta tong)."""
    return not (QUIET[0] <= uzt(now).hour < QUIET[1])


def _uzt_day_start(now: float) -> float:
    local = uzt(now)
    return now - (local.hour * HOUR + local.minute * 60 + local.second)


# ─────────────────────────────────────────────────────────────── kim kimga

@dataclass
class Person:
    telegram_id: int
    name: str = ""
    language: str = "uz"
    balance: int = 0
    created_at: float = 0.0
    paid: int = 0
    last_paid: Optional[float] = None
    last_spend: Optional[float] = None
    last_job: Optional[float] = None
    trial_at: Optional[float] = None
    excluded: bool = False          # admin bloklagan yoki admin

    @property
    def used(self) -> bool:
        # Balansdan yechimlar jadvali yangi: undan oldingi foydalanish "to'laganidan kam balans" bilan bilinadi.
        return bool(self.last_spend or self.last_job or self.trial_at
                    or (self.paid and self.balance < self.paid))

    @property
    def activity_at(self) -> Optional[float]:
        moments = [t for t in (self.last_paid, self.last_spend, self.last_job, self.trial_at) if t]
        return max(moments) if moments else None


@dataclass
class Row:
    id: int
    telegram_id: int
    flow: str
    step: int
    sent_at: float
    status: str
    clicked_at: Optional[float] = None


@dataclass
class Due:
    person: Person
    flow: str
    step: int


def segment(now: float, person: Person, rows: List[Row]) -> Tuple[str, float]:
    """(guruh, boshlanish vaqti) — yoki ("", 0) agar hozir hech qaysi guruhga tushmasa."""
    paid, used = person.paid > 0, person.used
    if person.trial_at and not paid:
        return "trial", person.trial_at
    if paid and not used:
        return ("paid_unused", person.last_paid or person.created_at) if person.balance >= MIN_BALANCE else ("", 0)
    if used:            # to'lab yoki bonus bilan foydalangan — uzoq kelmasa eslatma
        activity = person.activity_at or person.created_at
        return ("lapsed", activity) if now - activity >= LAPSE else ("", 0)
    old = [r.sent_at for r in rows if r.flow == "old"]
    if old:
        return "old", min(old)
    if any(r.flow == "new" for r in rows) or now - person.created_at <= NEW_WINDOW:
        return "new", person.created_at
    return "old", 0.0


def silenced(person: Person, rows: List[Row]) -> bool:
    """Xabar yetib bormagan (to'sgan yoki yuborib bo'lmagan) va shundan keyin faol bo'lmagan mijoz."""
    activity = person.activity_at or 0
    return any(r.status in UNDELIVERED and r.sent_at > activity for r in rows)


def weekly_half(telegram_id: int) -> int:
    """Juma xabari: 0 — ertalab, 1 — kechqurun (mijozlar teng ikkiga bo'linadi)."""
    return int(telegram_id) % 2


def weekly_plan(now: float, people: List[Person], history: Dict[int, List[Row]],
                limit: int = WEEKLY_TICK) -> List[Due]:
    """Juma bonusi xabari: hozir (juma, o'z yarmining vaqti) kimga ketadi."""
    local = uzt(now)
    if local.weekday() != WEEKLY_DAY:
        return []
    half = next((i for i, (start, end) in enumerate(WEEKLY_SLOTS) if start <= local.hour < end), None)
    if half is None:
        return []
    day_start = _uzt_day_start(now)
    result: List[Due] = []
    for person in people:
        if len(result) >= limit:
            break
        if person.excluded or weekly_half(person.telegram_id) != half:
            continue
        rows = history.get(person.telegram_id, [])
        if silenced(person, rows) or any(r.flow == "weekly" and r.sent_at >= day_start for r in rows):
            continue
        result.append(Due(person, "weekly", 0))
    return result


def plan(now: float, people: List[Person], history: Dict[int, List[Row]], *,
         old_budget: int = OLD_DAILY, limit: int = TICK_LIMIT, old_enabled: bool = True,
         skip: frozenset = frozenset()) -> List[Due]:
    """Hozir kimga qaysi xabar ketishi kerak (sof hisob — yuborish alohida)."""
    found: List[Tuple[int, Due]] = []
    for person in people:
        if person.excluded:
            continue
        rows = history.get(person.telegram_id, [])
        if silenced(person, rows) or person.telegram_id in skip:
            continue
        sent = [r.sent_at for r in rows if r.status in ("sent", "pending")]
        if sent and now - max(sent) < MIN_GAP:
            continue
        flow, anchor = segment(now, person, rows)
        if not flow or (flow == "old" and not old_enabled):
            continue
        offsets = OFFSETS[flow]
        done = sorted((r for r in rows if r.flow == flow and r.sent_at >= anchor and r.status != "blocked"),
                      key=lambda r: r.sent_at)
        step = len(done)
        if step >= len(offsets):
            continue
        if step == 0:
            if now < anchor + offsets[0] * HOUR:
                continue
        elif now < done[-1].sent_at + (offsets[step] - offsets[step - 1]) * HOUR:
            continue
        found.append((PRIORITY.index(flow), Due(person, flow, step)))
    found.sort(key=lambda item: item[0])
    result = []
    for _, due in found:
        if len(result) >= limit:
            break
        if due.flow == "old" and due.step == 0:
            if old_budget <= 0:
                continue
            old_budget -= 1
        result.append(due)
    return result


# ─────────────────────────────────────────────────────────────── matn

_NAME = re.compile(r"^[A-Za-zА-Яа-яЁёЎўҚқҒғҲҳӘәІіҢңӨөҰұҮүҺһ][A-Za-zА-Яа-яЁёЎўҚқҒғҲҳӘәІіҢңӨөҰұҮүҺһʻʼ'’`\-]{1,19}$")
_NOT_NAMES = {"user", "admin", "bot", "test", "telegram", "deleted", "account", "name", "ism", "none", "null"}


def clean_name(first_name: str) -> str:
    """Mijozning haqiqiy ismi (birinchi so'z) — emoji, raqam, "user123" va shu kabilar bo'lsa bo'sh."""
    word = (first_name or "").strip().split(" ")[0] if (first_name or "").strip() else ""
    if not word or not _NAME.match(word) or word.lower() in _NOT_NAMES:
        return ""
    if word.isupper() and len(word) > 3:
        word = word.capitalize()
    return word[0].upper() + word[1:]


def language_of(code: str) -> str:
    code = (code or "uz").lower()
    if code.startswith("uz"):
        return "uz"
    return code if code in T.LANGS else "uz"


def _fill(template: str, *, name: str, language: str, **values) -> str:
    hello_with, hello_without = T.HELLO[language]
    safe = html.escape(name)
    hello = hello_with.replace("{name}", safe) if name else hello_without
    text = template
    if not name:
        text = re.sub(r"^\{name\},\s*", "", text)
        text = text.replace("{name}, ", "").replace("{name}", "")
        # Ismsiz gap katta harf bilan boshlansin.
        text = text[:1].upper() + text[1:]
    text = text.replace("{hello}", hello).replace("{name}", safe)
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def _date(epoch: float, language: str) -> str:
    local = uzt(epoch)
    return local.strftime("%d.%m.%Y %H:%M")


def message_for(flow: str, step: int, person: Person, now: float) -> Tuple[str, List[Tuple[str, str]], Dict]:
    """(matn, [(maqsad, tugma yozuvi)], qo'shimcha) — qo'shimchada: sovg'a muddati, bonus muddati, namuna."""
    language = language_of(person.language)
    item = T.STEPS[STEPS[flow]][step]
    extra: Dict = {}
    values = {"balance": f"{int(person.balance):,}".replace(",", " "), "bonus": BONUS_PERCENT}
    if flow == "weekly":
        extra["weekly_until"] = weekly_until(now)
        values["date"] = _date(extra["weekly_until"], language)
    if item.get("deadline"):
        extra["gift_until"] = now + GIFT_HOURS * HOUR
        values["date"] = _date(extra["gift_until"], language)
    if flow == "trial":
        extra["bonus_until"] = person_bonus_until(person, now)
        values["date"] = _date(extra["bonus_until"], language)
    template = (item.get("old") or {}).get(language) if flow == "old" else None
    text = _fill(template or item[language], name=clean_name(person.name), language=language, **values)
    if item.get("icon") and not text.startswith(item["icon"]):
        text = f"{item['icon']} {text}"
    buttons = [(target, labels.get(language) or labels["uz"]) for target, labels in item["buttons"]]
    if item.get("sample"):
        extra["sample"] = True
    return text, buttons, extra


# Bonus muddati: birinchi xabarda beriladi, keyingi xabarlar o'sha sanani aytadi.
_BONUS_CACHE: Dict[int, float] = {}


def person_bonus_until(person: Person, now: float) -> float:
    return _BONUS_CACHE.get(person.telegram_id) or now + BONUS_DAYS * DAY


def weekly_until(now: float) -> float:
    """Juma bonusi yakshanba 23:59 gacha (O'zbekiston vaqti)."""
    days_left = 6 - uzt(now).weekday()
    return _uzt_day_start(now) + (days_left + 1) * DAY - 60


def offer_percent(kind: str, amount: int) -> int:
    """Taklif turi va tasdiqlangan summa bo'yicha bonus foizi (0 — bonus yo'q)."""
    if kind == "trial":
        return BONUS_PERCENT
    if kind == "weekly":
        return next((percent for floor, percent in WEEKLY_TIERS if amount >= floor), 0)
    return 0


# ─────────────────────────────────────────────────────────────── baza

async def load(now: float) -> Tuple[List[Person], Dict[int, List[Row]]]:
    from config import ADMIN_IDS

    people: Dict[int, Person] = {}
    by_db_id: Dict[int, Person] = {}
    history: Dict[int, List[Row]] = {}
    async with aiosqlite.connect(_db_file()) as conn:
        await _create(conn)
        async with conn.execute("SELECT id, telegram_id, first_name, language, balance, created_at FROM users") as cur:
            async for db_id, tg, name, language, balance, created in cur:
                person = Person(int(tg), name or "", language or "uz", int(balance or 0), _epoch(created) or now)
                person.excluded = int(tg) in ADMIN_IDS
                people[int(tg)] = by_db_id[int(db_id)] = person
        if await _has_table(conn, "blocked_users"):
            async with conn.execute("SELECT telegram_id FROM blocked_users") as cur:
                async for (tg,) in cur:
                    if int(tg) in people:
                        people[int(tg)].excluded = True
        async with conn.execute("SELECT user_id, SUM(amount), MAX(created_at) FROM payments "
                                "WHERE status = 'approved' GROUP BY user_id") as cur:
            async for db_id, total, last in cur:
                if int(db_id) in by_db_id:
                    by_db_id[int(db_id)].paid = int(total or 0)
                    by_db_id[int(db_id)].last_paid = _epoch(last)
        if await _has_table(conn, "balance_spends"):
            async with conn.execute("SELECT telegram_id, MAX(created_at) FROM balance_spends GROUP BY telegram_id") as cur:
                async for tg, last in cur:
                    if int(tg) in people:
                        people[int(tg)].last_spend = _epoch(last)
        if await _has_table(conn, "web_jobs"):
            async with conn.execute("SELECT telegram_id, MAX(created_at) FROM web_jobs "
                                    "WHERE status IN ('done', 'running', 'queued') GROUP BY telegram_id") as cur:
                async for tg, last in cur:
                    if int(tg) in people:
                        people[int(tg)].last_job = _epoch(last)
        if await _has_table(conn, "free_trials"):
            async with conn.execute("SELECT telegram_id, created_at FROM free_trials") as cur:
                async for tg, created in cur:
                    if int(tg) in people:
                        people[int(tg)].trial_at = _epoch(created)
        async with conn.execute("SELECT id, telegram_id, flow, step, sent_at, status, clicked_at FROM nudges") as cur:
            async for row in cur:
                history.setdefault(int(row[1]), []).append(Row(*row))
        async with conn.execute("SELECT telegram_id, MAX(expires_at) FROM reengage_offers WHERE kind = 'trial' "
                                "GROUP BY telegram_id") as cur:
            async for tg, expires in cur:
                _BONUS_CACHE[int(tg)] = float(expires)
    return list(people.values()), history


async def _record(telegram_id: int, flow: str, step: int, now: float) -> int:
    async with aiosqlite.connect(_db_file()) as conn:
        await _create(conn)
        cur = await conn.execute("INSERT INTO nudges (telegram_id, flow, step, sent_at, status) VALUES (?, ?, ?, ?, 'pending')",
                                 (telegram_id, flow, step, now))
        await conn.commit()
        return cur.lastrowid


async def _set_status(row_id: int, status: str) -> None:
    async with aiosqlite.connect(_db_file()) as conn:
        await conn.execute("UPDATE nudges SET status = ? WHERE id = ?", (status, row_id))
        await conn.commit()


async def clicked(row_id: int) -> Optional[Tuple[int, str, int]]:
    """Tugma bosildi: birinchi bosilish vaqti yoziladi. (telegram_id, guruh, qadam) qaytaradi."""
    async with aiosqlite.connect(_db_file()) as conn:
        await _create(conn)
        await conn.execute("UPDATE nudges SET clicked_at = ? WHERE id = ? AND clicked_at IS NULL", (time.time(), row_id))
        await conn.commit()
        async with conn.execute("SELECT telegram_id, flow, step FROM nudges WHERE id = ?", (row_id,)) as cur:
            row = await cur.fetchone()
    return tuple(row) if row else None


async def grant_bonus(telegram_id: int, now: float, until: float, kind: str = "trial") -> None:
    """Taklif beriladi (hali faol emas — mijoz xabardagi tugmani bosishi kerak). trial — bir marta."""
    async with aiosqlite.connect(_db_file()) as conn:
        await _create(conn)
        if kind == "trial":
            async with conn.execute("SELECT 1 FROM reengage_offers WHERE telegram_id = ? AND kind = 'trial'",
                                    (telegram_id,)) as cur:
                if await cur.fetchone():
                    return
        await conn.execute("INSERT OR IGNORE INTO reengage_offers (telegram_id, kind, granted_at, expires_at) "
                           "VALUES (?, ?, ?, ?)", (telegram_id, kind, now, until))
        await conn.commit()
    if kind == "trial":
        _BONUS_CACHE.setdefault(telegram_id, until)


async def arm_offer(telegram_id: int, kind: str = "", now: Optional[float] = None) -> Optional[Tuple[str, float]]:
    """Mijoz bonus tugmasini bosdi: amaldagi taklif faollashadi. (tur, muddat) yoki None (taklif yo'q/tugagan)."""
    now = now or time.time()
    async with aiosqlite.connect(_db_file()) as conn:
        await _create(conn)
        query = ("SELECT id, kind, expires_at FROM reengage_offers WHERE telegram_id = ? AND used_at IS NULL "
                 "AND expires_at >= ?")
        args: tuple = (telegram_id, now)
        if kind:
            query += " AND kind = ?"
            args += (kind,)
        async with conn.execute(query + " ORDER BY expires_at DESC", args) as cur:
            rows = await cur.fetchall()
        if not rows:
            return None
        await conn.executemany("UPDATE reengage_offers SET armed_at = COALESCE(armed_at, ?) WHERE id = ?",
                               [(now, row[0]) for row in rows])
        await conn.commit()
    return rows[0][1], float(rows[0][2])


async def take_bonus(telegram_id: int, user_db_id: int, amount: int, now: Optional[float] = None) -> int:
    """Tasdiqlangan to'lov uchun bonus summasi (0 — bonus yo'q).

    Faqat tugma bilan faollashtirilgan, muddati o'tmagan, ishlatilmagan taklif; trial — faqat birinchi to'lov.
    Bir nechta taklif bo'lsa, eng kattasi ishlatiladi (bir to'lovga bitta bonus).
    """
    now = now or time.time()
    async with aiosqlite.connect(_db_file()) as conn:
        await _create(conn)
        async with conn.execute("SELECT id, kind FROM reengage_offers WHERE telegram_id = ? AND used_at IS NULL "
                                "AND armed_at IS NOT NULL AND expires_at >= ?", (telegram_id, now)) as cur:
            offers = await cur.fetchall()
        if not offers:
            return 0
        async with conn.execute("SELECT COUNT(*) FROM payments WHERE user_id = ? AND status = 'approved'",
                                (user_db_id,)) as cur:
            approved = (await cur.fetchone())[0]
        best, best_id = 0, None
        for offer_id, kind in offers:
            if kind == "trial" and approved != 1:     # faqat birinchi to'lov (shu to'lov allaqachon tasdiqlangan)
                continue
            bonus = int(amount) * offer_percent(kind, int(amount)) // 100
            if bonus > best:
                best, best_id = bonus, offer_id
        if not best_id:
            return 0
        cur = await conn.execute("UPDATE reengage_offers SET used_at = ?, amount = ? WHERE id = ? AND used_at IS NULL",
                                 (now, best, best_id))
        await conn.commit()
        return best if cur.rowcount else 0


async def on_payment_approved(bot, db, user, amount: int) -> int:
    """To'lov tasdiqlangach: bonus bo'lsa hisobga qo'shadi va mijozga aytadi. Xato to'lovni buzmaydi."""
    try:
        bonus = await take_bonus(int(user.telegram_id), int(user.id), int(amount))
        if not bonus:
            return 0
        await db.update_user_balance(user.telegram_id, bonus)
        language = "kk" if getattr(user, "kazakh", False) else language_of(user.language)
        try:
            await bot.send_message(user.telegram_id, T.BONUS_PAID[language].replace(
                "{amount}", f"{bonus:,}".replace(",", " ")))
        except Exception as exc:
            log.warning("Bonus xabari yuborilmadi (%s): %s", user.telegram_id, exc)
        log.info("Qayta jalb bonusi: %s ga +%s so'm", user.telegram_id, bonus)
        return bonus
    except Exception as exc:
        log.error("Qayta jalb bonusi berilmadi (%s): %s", getattr(user, "telegram_id", "?"), exc)
        return 0


# ─────────────────────────────────────────────────────────────── yuborish

def sample_photo() -> Optional[str]:
    """Katalogdagi zamonaviy taqdimotlardan biri — birinchi varag'ining rasmi (yo'q bo'lsa None)."""
    from config import STORE_PREVIEW_DIR

    try:
        folders = [d for d in os.listdir(STORE_PREVIEW_DIR)
                   if os.path.isfile(os.path.join(STORE_PREVIEW_DIR, d, "1.jpg"))]
    except OSError:
        return None
    return os.path.join(STORE_PREVIEW_DIR, random.choice(folders), "1.jpg") if folders else None


_PHOTO_IDS: Dict[str, str] = {}


def keyboard(row_id: int, buttons: List[Tuple[str, str]]):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=f"nz:{row_id}:{target}")]
                                                 for target, label in buttons])


async def deliver(bot, due: Due, now: float) -> str:
    """Bitta xabarni yuboradi: 'sent' | 'blocked' | 'failed'."""
    from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
    from aiogram.types import FSInputFile

    text, buttons, extra = message_for(due.flow, due.step, due.person, now)
    row_id = await _record(due.person.telegram_id, due.flow, due.step, now)
    markup = keyboard(row_id, buttons)
    photo = sample_photo() if extra.get("sample") else None
    status = "failed"
    for attempt in range(2):
        try:
            if photo:
                # Bir rasm har mijozga qayta yuklanmasin: Telegram bergan file_id eslab qolinadi.
                sent = await bot.send_photo(due.person.telegram_id, _PHOTO_IDS.get(photo) or FSInputFile(photo),
                                            caption=text, parse_mode="HTML", reply_markup=markup)
                with contextlib.suppress(Exception):
                    _PHOTO_IDS.setdefault(photo, sent.photo[-1].file_id)
            else:
                await bot.send_message(due.person.telegram_id, text, parse_mode="HTML", reply_markup=markup)
            status = "sent"
            break
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
        except TelegramForbiddenError:
            status = "blocked"
            break
        except Exception as exc:
            log.warning("Qayta jalb xabari yuborilmadi (%s, %s/%s): %s", due.person.telegram_id, due.flow, due.step, exc)
            if photo:                     # rasm bilan bo'lmasa — matnning o'zi
                photo = None
                continue
            break
    await _set_status(row_id, status)
    if status == "sent":
        if extra.get("gift_until"):
            from database import free_trial
            await free_trial.set_deadline(due.person.telegram_id, extra["gift_until"])
        if extra.get("bonus_until") and due.step == 0:
            await grant_bonus(due.person.telegram_id, now, extra["bonus_until"])
        if extra.get("weekly_until"):
            await grant_bonus(due.person.telegram_id, now, extra["weekly_until"], kind="weekly")
    return status


async def _enabled(name: str) -> bool:
    from database.database import Database

    try:
        return bool(await Database().get_feature_status(name))
    except Exception:
        return True


async def _old_today(now: float) -> int:
    start = _uzt_day_start(now)
    async with aiosqlite.connect(_db_file()) as conn:
        await _create(conn)
        async with conn.execute("SELECT COUNT(*) FROM nudges WHERE flow = 'old' AND step = 0 AND sent_at >= ?",
                                (start,)) as cur:
            return (await cur.fetchone())[0]


async def _old_block_rate(now: float) -> Tuple[int, float]:
    async with aiosqlite.connect(_db_file()) as conn:
        await _create(conn)
        async with conn.execute("SELECT COUNT(*), SUM(status = 'blocked') FROM nudges WHERE flow = 'old' "
                                "AND status IN ('sent', 'blocked') AND sent_at >= ?", (now - DAY,)) as cur:
            total, blocked = await cur.fetchone()
    total = int(total or 0)
    return total, (int(blocked or 0) / total if total else 0.0)


async def _warn_old(bot, now: float, total: int, rate: float) -> None:
    """To'sganlar ko'p — adminga kuniga bir marta MA'LUMOT. Yuborish to'xtamaydi.

    Ilgari bunda eski baza to'lqini o'zi o'chirilardi: xabar hammaga yetib bormasa ham
    yetib borganlari orasida qaytib, to'lab ketayotganlar bor edi, to'xtash ularni yo'qotardi.
    To'sgan mijozga baribir qayta xabar bormaydi (`plan`).
    """
    day = _uzt_day_start(now)
    # Kun bazada eslanadi: bot qayta ishga tushsa ham ma'lumot takrorlanmaydi.
    async with aiosqlite.connect(_db_file()) as conn:
        await _create(conn)
        async with conn.execute("SELECT value FROM reengage_state WHERE key = 'old_warned_day'") as cur:
            row = await cur.fetchone()
        if row and row[0] == day:
            return
        await conn.execute("INSERT OR REPLACE INTO reengage_state (key, value) VALUES ('old_warned_day', ?)", (day,))
        await conn.commit()
    from config import ADMIN_IDS

    log.warning("Eski bazada to'sganlar ko'p: %d xabardan %.0f%% (yuborish davom etadi)", total, rate * 100)
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, (
                "ℹ️ Eski bazaga qayta jalb: oxirgi 24 soatda "
                f"{total} ta xabardan {(1 - rate) * 100:.0f}% yetib bordi, {rate * 100:.0f}% botni to'sgan.\n"
                "Yuborish davom etadi — to'sganlarga boshqa xabar bormaydi.\n"
                "To'xtatish kerak bo'lsa: «🎛 Funksiyalar boshqaruvi» → «🗂 Eski bazaga xabarlar»."))
        except Exception:
            pass


async def tick(bot, now: Optional[float] = None) -> Dict[str, int]:
    """Bir aylanish: vaqti kelgan xabarlarni yuboradi. Natija: {'sent': .., 'blocked': .., 'failed': ..}."""
    fixed = now is not None
    now = now or time.time()
    result = {"sent": 0, "blocked": 0, "failed": 0}
    if quiet(now) or not await _enabled(FEATURE):
        return result
    old_enabled = await _enabled(FEATURE_OLD)
    people, history = await load(now)
    weekly = weekly_plan(now, people, history) if await _enabled(FEATURE_WEEKLY) else []
    due = weekly + plan(now, people, history, old_budget=max(0, OLD_DAILY - await _old_today(now)),
                        old_enabled=old_enabled, skip=frozenset(d.person.telegram_id for d in weekly))
    for item in due:
        status = await deliver(bot, item, now if fixed else time.time())
        result[status] = result.get(status, 0) + 1
        await asyncio.sleep(SEND_PAUSE)
    if old_enabled:
        total, rate = await _old_block_rate(now)
        if total >= PAUSE_MIN and rate > PAUSE_RATE:
            await _warn_old(bot, now, total, rate)
    if any(result.values()):
        log.info("Qayta jalb: %s", result)
    return result


async def run(bot) -> None:
    """Fon jarayoni: har 10 daqiqada bir aylanish."""
    await asyncio.sleep(60)
    while True:
        try:
            await tick(bot)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("Qayta jalb aylanishida xato: %s", exc)
        await asyncio.sleep(TICK_SECONDS)


# ─────────────────────────────────────────────────────────────── hisobot

async def report(days: int = 30, now: Optional[float] = None) -> str:
    """Admin uchun: har guruh va xabar bo'yicha yuborildi / to'sdi / bosdi / bepul oldi / to'ladi."""
    now = now or time.time()
    since = now - days * DAY
    async with aiosqlite.connect(_db_file()) as conn:
        await _create(conn)
        trials = {}
        if await _has_table(conn, "free_trials"):
            async with conn.execute("SELECT telegram_id, created_at FROM free_trials") as cur:
                trials = {int(tg): float(at) for tg, at in await cur.fetchall()}
        async with conn.execute("SELECT u.telegram_id, p.amount, p.created_at FROM payments p JOIN users u "
                                "ON u.id = p.user_id WHERE p.status = 'approved' AND p.created_at >= ?",
                                (datetime.fromtimestamp(since - 30 * DAY, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),)) as cur:
            pays: Dict[int, List[Tuple[float, int]]] = {}
            for tg, amount, created in await cur.fetchall():
                pays.setdefault(int(tg), []).append((_epoch(created) or 0, int(amount)))
        async with conn.execute("SELECT telegram_id, flow, step, sent_at, status, clicked_at FROM nudges "
                                "WHERE sent_at >= ? ORDER BY sent_at", (since,)) as cur:
            rows = await cur.fetchall()
        async with conn.execute("SELECT kind, COUNT(*), COALESCE(SUM(amount), 0) FROM reengage_offers "
                                "WHERE used_at >= ? GROUP BY kind", (since,)) as cur:
            bonuses = {kind: (int(count), int(total)) for kind, count, total in await cur.fetchall()}
    stats: Dict[Tuple[str, int], Dict[str, int]] = {}
    for tg, flow, step, sent_at, status, clicked_at in rows:
        item = stats.setdefault((flow, step), {"sent": 0, "blocked": 0, "clicked": 0, "trial": 0, "paid": 0, "sum": 0})
        if status == "blocked":
            item["blocked"] += 1
            continue
        if status != "sent":
            continue
        item["sent"] += 1
        item["clicked"] += 1 if clicked_at else 0
        if tg in trials and sent_at <= trials[tg] <= sent_at + 7 * DAY:
            item["trial"] += 1
        paid = [amount for at, amount in pays.get(tg, []) if sent_at <= at <= sent_at + 7 * DAY]
        if paid:
            item["paid"] += 1
            item["sum"] += sum(paid)
    lines = [f"🔁 <b>Qayta jalb xabarlari — oxirgi {days} kun</b>",
             "<i>yuborildi / to'sdi / bosdi / bepul oldi / 7 kunda to'ladi</i>", ""]
    for flow in PRIORITY + ("weekly",):
        steps = sorted(s for f, s in stats if f == flow)
        if not steps:
            continue
        lines.append(f"<b>{FLOW_NAMES[flow]}</b>")
        for step in steps:
            s = stats[(flow, step)]
            lines.append(f"  {step + 1}-xabar: {s['sent']} / {s['blocked']} / {s['clicked']} / {s['trial']} / "
                         f"{s['paid']} ({s['sum']:,} so'm)")
        lines.append("")
    if len(lines) == 3:
        lines.append("Hali xabar yuborilmagan.")
    total = {k: sum(s[k] for s in stats.values()) for k in ("sent", "blocked", "clicked", "trial", "paid", "sum")}
    lines.append(f"Jami: {total['sent']} yuborildi, {total['blocked']} to'sdi, {total['clicked']} bosdi, "
                 f"{total['trial']} bepul oldi, {total['paid']} to'ladi — {total['sum']:,} so'm")
    count, total_sum = bonuses.get("trial", (0, 0))
    lines.append(f"🎁 Birinchi to'lovga +{BONUS_PERCENT}% bonus: {count} ta, {total_sum:,} so'm")
    count, total_sum = bonuses.get("weekly", (0, 0))
    lines.append(f"💎 Juma bonusi: {count} ta, {total_sum:,} so'm")
    return "\n".join(lines)
