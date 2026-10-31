"""Botda tayyorlanayotgan buyurtmalar — bot qayta ishga tushsa ham mijoz unutilmasin.

Taqdimot, loyiha ishi, hujjat bot jarayonining ichida tayyorlanadi. Jarayon o'lsa (xotira tugab Linux
o'chirsa, server qayta yuklansa, yangilanish) ish yo'qoladi. Ilgari bunda pul oldindan olingan buyurtmalarda
(zamonaviy/3D taqdimot, Stars bilan to'lov) pul qaytmasdi, mijozga esa hech kim hech narsa demasdi — u
taqdimotni kutib qolaverardi.

Endi:
- pul olinib ish boshlanganda qator yoziladi (`start`), ish tugaganda (yuborildi yoki xato bo'lib pul shu
  zahoti qaytarildi) o'chiriladi (`finish`);
- hujjatlar (referat, kurs ishi ...) uchun `document_orders` dagi `generating` qatorlari ham olinadi
  (`adopt_documents`, baza ishga tushirilganda) — ularda pul yuborilgandan keyin yechiladi, ya'ni qaytaradigan
  pul yo'q, lekin mijozga aytish kerak;
- bot ishga tushganda (`recover`) oldingi jarayondan qolgan har qator uchun: olingan pul hisobga qaytariladi va
  mijozga uzr xabari yuboriladi; adminga qisqa hisobot.
"""
import asyncio
import logging
import time
from typing import List, Optional

import aiosqlite

from database import database as _db

log = logging.getLogger(__name__)

STARTED = time.time()            # shu jarayon boshlangan vaqt: undan oldingi qatorlar — uzilgan buyurtmalar
_tasks: set = set()
DOC_WINDOW_HOURS = 6             # hujjat buyurtmasi shundan eski bo'lsa — mijozni bezovta qilmaymiz

SCHEMA = """CREATE TABLE IF NOT EXISTS bot_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    lang TEXT NOT NULL DEFAULT 'uz',
    kind TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    charged INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
)"""

TEXTS = {
    "paid": {
        "uz": "⚠️ Kechirasiz! Server texnik sabab bilan qayta ishga tushdi va «{title}» buyurtmangiz yakunlanmay "
              "qoldi.\n💰 {charged:,} so'm hisobingizga qaytarildi — qaytadan buyurtma bersangiz, darhol tayyorlaymiz.",
        "ru": "⚠️ Извините! Сервер перезапустился по технической причине, и ваш заказ «{title}» не был завершён.\n"
              "💰 {charged:,} сум возвращены на баланс — оформите заказ снова, и мы сразу его подготовим.",
        "en": "⚠️ Sorry! The server restarted for a technical reason and your order “{title}” was not finished.\n"
              "💰 {charged:,} so'm has been returned to your balance — please order again and we will prepare it.",
        "kk": "⚠️ Кешіріңіз! Сервер техникалық себеппен қайта іске қосылды, «{title}» тапсырысыңыз аяқталмады.\n"
              "💰 {charged:,} сўм балансыңызға қайтарылды — қайта тапсырыс беріңіз, бірден дайындаймыз.",
    },
    "free": {
        "uz": "⚠️ Kechirasiz! Server texnik sabab bilan qayta ishga tushdi va «{title}» buyurtmangiz yakunlanmay "
              "qoldi.\nHisobingizdan pul yechilmagan — qaytadan buyurtma bersangiz, darhol tayyorlaymiz.",
        "ru": "⚠️ Извините! Сервер перезапустился по технической причине, и ваш заказ «{title}» не был завершён.\n"
              "Деньги с баланса не списаны — оформите заказ снова, и мы сразу его подготовим.",
        "en": "⚠️ Sorry! The server restarted for a technical reason and your order “{title}” was not finished.\n"
              "Nothing was charged — please order again and we will prepare it.",
        "kk": "⚠️ Кешіріңіз! Сервер техникалық себеппен қайта іске қосылды, «{title}» тапсырысыңыз аяқталмады.\n"
              "Балансыңыздан ақша алынбады — қайта тапсырыс беріңіз, бірден дайындаймыз.",
    },
}


async def _create(conn) -> None:
    await conn.execute(SCHEMA)


async def start(telegram_id: int, chat_id: int, kind: str, title: str = "", charged: int = 0,
                lang: str = "uz") -> Optional[int]:
    """Buyurtma ishlay boshladi. Qator raqamini qaytaradi (yozib bo'lmasa — None; buyurtma to'xtamaydi)."""
    try:
        async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
            await _create(conn)
            cursor = await conn.execute(
                "INSERT INTO bot_orders (telegram_id, chat_id, lang, kind, title, charged, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (int(telegram_id), int(chat_id or telegram_id), lang or "uz", kind or "", (title or "")[:200],
                 max(0, int(charged or 0)), time.time()))
            await conn.commit()
            return cursor.lastrowid
    except Exception as exc:                          # noqa: BLE001
        log.warning("Buyurtma yozilmadi (%s): %s", kind, exc)
        return None


async def finish(order_id: Optional[int]) -> None:
    """Buyurtma tugadi (yuborildi yoki pul shu zahoti qaytarildi)."""
    if not order_id:
        return
    try:
        async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
            await _create(conn)
            await conn.execute("DELETE FROM bot_orders WHERE id = ?", (int(order_id),))
            await conn.commit()
    except Exception as exc:                          # noqa: BLE001
        log.warning("Buyurtma yopilmadi (%s): %s", order_id, exc)


async def adopt_documents(conn) -> int:
    """`init_db` ichida, `document_orders` tozalanishidan OLDIN: uzilib qolgan hujjat buyurtmalari (pul hali
    yechilmagan) mijozga xabar uchun shu jadvalga o'tkaziladi."""
    await _create(conn)
    try:
        async with conn.execute(
                "SELECT u.telegram_id, COALESCE(u.language, 'uz'), d.document_type, d.topic "
                "FROM document_orders d JOIN users u ON u.id = d.user_id "
                "WHERE d.status = 'generating' AND d.created_at >= datetime('now', ?)",
                (f"-{DOC_WINDOW_HOURS} hours",)) as cursor:
            rows = await cursor.fetchall()
    except Exception as exc:                          # noqa: BLE001
        log.warning("Uzilgan hujjatlar o'qilmadi: %s", exc)
        return 0
    now = min(time.time(), STARTED - 1)
    for telegram_id, lang, doc_type, topic in rows:
        await conn.execute(
            "INSERT INTO bot_orders (telegram_id, chat_id, lang, kind, title, charged, created_at) "
            "VALUES (?, ?, ?, ?, ?, 0, ?)", (telegram_id, telegram_id, lang, doc_type, (topic or "")[:200], now))
    return len(rows)


async def take_interrupted() -> List[dict]:
    """Oldingi jarayondan qolgan qatorlarni oladi va o'chiradi (pulni qaytarish chaqiruvchida)."""
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await _create(conn)
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM bot_orders WHERE created_at < ? ORDER BY id", (STARTED,)) as cursor:
            rows = [dict(r) for r in await cursor.fetchall()]
        if rows:
            await conn.execute("DELETE FROM bot_orders WHERE id IN (%s)" % ",".join("?" * len(rows)),
                               [r["id"] for r in rows])
            await conn.commit()
    return rows


def message_for(row: dict) -> str:
    key = "paid" if row.get("charged") else "free"
    lang = (row.get("lang") or "uz").split("-")[0]
    template = TEXTS[key].get(lang) or TEXTS[key]["uz"]
    title = row.get("title") or row.get("kind") or "—"
    return template.format(title=title[:120], charged=int(row.get("charged") or 0))


async def recover(bot) -> int:
    """Bot ishga tushganda: uzilgan buyurtmalar puli qaytariladi, mijozlarga uzr aytiladi. Soni qaytadi."""
    rows = await take_interrupted()
    if not rows:
        return 0
    refunded = 0
    for row in rows:
        if row["charged"] > 0:
            try:
                await _db.Database.update_user_balance(row["telegram_id"], row["charged"])
                refunded += row["charged"]
            except Exception as exc:                  # noqa: BLE001
                log.error("Uzilgan buyurtma puli qaytarilmadi (%s, %s so'm): %s", row["telegram_id"],
                          row["charged"], exc)
    log.warning("Qayta ishga tushish: %d ta buyurtma uzilgan edi, %d so'm qaytarildi", len(rows), refunded)

    async def notify():
        for row in rows:
            try:
                await bot.send_message(row["chat_id"], message_for(row))
            except Exception as exc:                  # noqa: BLE001
                log.debug("Mijozga uzr xabari yuborilmadi (%s): %s", row["chat_id"], exc)
            await asyncio.sleep(0.1)
        try:
            from services import admin_alerts

            admin_alerts.alert("orders_recovered",
                               f"♻️ Bot qayta ishga tushdi: {len(rows)} ta buyurtma uzilib qolgan edi. "
                               f"{refunded:,} so'm mijozlarga qaytarildi, hammasiga uzr xabari yuborildi.")
        except Exception:                             # noqa: BLE001
            pass

    task = asyncio.get_running_loop().create_task(notify())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return len(rows)
