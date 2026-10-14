"""AI nazorati: kunlik hisob — rasm qayerdan olindi va qaysi AI modeli ishladi.

Admin «🧠 AI nazorati» tugmasi shu yerdan o'qiydi. Uch xil yozuv bor:

    photo  — slaydga qo'yilgan rasm manbasi: "sayt" (Brave qidiruvi) yoki "ai" (chizilgan)
    text   — matn yozgan model (OpenRouter), har muvaffaqiyatli so'rov bitta
    image  — rasm chizgan model (Together), har chiqqan rasm bitta

Hisob yozish hech qachon asosiy ishni to'xtatmasligi kerak: baza band yoki
yo'q bo'lsa yozuv jimgina tashlab ketiladi. Yozish sinxron (sqlite3) — u
oqimlardagi (`asyncio.to_thread`) sinxron kod ichidan ham chaqiriladi.
"""
import logging
import sqlite3
from typing import Dict, List, Tuple

import aiosqlite

import database.database as dbmod
from services.daily_stats import now_uzt, today_uzt

log = logging.getLogger(__name__)

KINDS = ("photo", "text", "image")
PHOTO_SITE = "sayt"
PHOTO_AI = "ai"

_TABLE = ("CREATE TABLE IF NOT EXISTS ai_usage (day TEXT NOT NULL, kind TEXT NOT NULL, "
          "name TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, kind, name))")


def _file() -> str:
    return dbmod.DATABASE_FILE          # testlarda almashtiriladi


def record(kind: str, name: str, count: int = 1) -> None:
    """Bugungi hisobga qo'shadi (O'zbekiston vaqti bilan)."""
    if not name or count <= 0:
        return
    try:
        with sqlite3.connect(_file(), timeout=2) as db:
            db.execute(_TABLE)
            db.execute(
                "INSERT INTO ai_usage (day, kind, name, count) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(day, kind, name) DO UPDATE SET count = count + excluded.count",
                (today_uzt(), kind, str(name)[:120], int(count)))
    except Exception as exc:
        log.debug("AI hisobi yozilmadi (%s/%s): %s", kind, name, exc)


async def day_counts(day: str = "") -> Dict[str, Dict[str, int]]:
    """{kind: {nom: soni}} — bir kun uchun."""
    out: Dict[str, Dict[str, int]] = {kind: {} for kind in KINDS}
    async with aiosqlite.connect(_file()) as db:
        await db.execute(_TABLE)
        async with db.execute("SELECT kind, name, count FROM ai_usage WHERE day = ?",
                              (day or today_uzt(),)) as cursor:
            for kind, name, count in await cursor.fetchall():
                out.setdefault(kind, {})[name] = count
    return out


async def photo_days(days: int = 7) -> List[Tuple[str, int, int]]:
    """Oxirgi kunlar: (sana, saytdan, AI dan) — eng yangisi birinchi."""
    from datetime import timedelta

    today = now_uzt()
    wanted = [(today - timedelta(days=shift)).strftime("%Y-%m-%d") for shift in range(days)]
    rows: Dict[str, Dict[str, int]] = {}
    async with aiosqlite.connect(_file()) as db:
        await db.execute(_TABLE)
        async with db.execute(
                "SELECT day, name, count FROM ai_usage WHERE kind = 'photo' AND day >= ?",
                (wanted[-1],)) as cursor:
            for day, name, count in await cursor.fetchall():
                rows.setdefault(day, {})[name] = count
    return [(day, rows.get(day, {}).get(PHOTO_SITE, 0), rows.get(day, {}).get(PHOTO_AI, 0))
            for day in wanted]


def _share(part: int, whole: int) -> str:
    return f"{part * 100 / whole:.0f}%" if whole else "0%"


def _models_block(title: str, counts: Dict[str, int], top: int = 8) -> str:
    total = sum(counts.values())
    if not total:
        return f"{title}\n  — bugun ishlatilmadi"
    lines = [f"{title} (jami {total} ta)"]
    ranked = sorted(counts.items(), key=lambda item: -item[1])
    for name, count in ranked[:top]:
        lines.append(f"  • {name} — {_share(count, total)} ({count})")
    rest = sum(count for _, count in ranked[top:])
    if rest:
        lines.append(f"  • boshqalar — {_share(rest, total)} ({rest})")
    return "\n".join(lines)


def report_text(today: Dict[str, Dict[str, int]], week: List[Tuple[str, int, int]]) -> str:
    photo = today.get("photo", {})
    site, ai = photo.get(PHOTO_SITE, 0), photo.get(PHOTO_AI, 0)
    total = site + ai
    lines = [
        f"🧠 AI nazorati ({now_uzt().strftime('%d.%m.%Y')})",
        "",
        f"🖼 Bugungi rasmlar: {total} ta",
        f"  • 🌐 Saytdan (Brave): {site} ta — {_share(site, total)}",
        f"  • 🎨 AI chizgan: {ai} ta — {_share(ai, total)}",
        "",
        _models_block("✍️ Matn modellari", today.get("text", {})),
        "",
        _models_block("🎨 Rasm modellari", today.get("image", {})),
    ]
    if any(s or a for _, s, a in week):
        lines += ["", "📅 Oxirgi 7 kun (saytdan / AI):"]
        for day, s, a in week:
            lines.append(f"  {day[8:10]}.{day[5:7]}: 🌐 {s} ({_share(s, s + a)}) · 🎨 {a} ({_share(a, s + a)})")
    return "\n".join(lines)
