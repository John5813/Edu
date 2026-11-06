"""Reklama havolalari (Instagram reklamasini kuzatish): `/go/<kod>` → `t.me/<bot>?start=ad_<kod>`.

- admin «Funksiyalar boshqaruvi»da havola yaratadi; bosganlar, botga kirganlar (yangi / eski mijoz) va adashib
  bosganlar hisoblanadi, xulosa chiqariladi;
- bot, tekshiruvchi va tez qayta bosish sanalmaydi; bir odam bir marta botga kirgan hisoblanadi;
- o'chirilgan / to'xtatilgan havola hisoblanmaydi, lekin mijozni baribir botga olib boradi.

    python test_reklama_havola.py
"""
import asyncio, os, sys, tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_IDS", "1")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import database.database as dbmod
dbmod.DATABASE_FILE = os.path.join(tempfile.mkdtemp(), "t.db")
from database import ad_links
from database.database import Database


async def main():
    import aiosqlite
    import webapp
    from aiohttp.test_utils import TestClient, TestServer
    from webapp import ad_track
    from webapp.server import create_web_app

    await Database.init_db() if hasattr(Database, "init_db") else None

    print("1) Havola kodi va manzil")
    check("ad_<kod> o'qiladi", ad_links.code_of("ad_abc1234") == "abc1234")
    check("boshqa parametrlar reklama emas", ad_links.code_of("g_abc1234") is None and ad_links.code_of("ref_x") is None
          and ad_links.code_of("ad_") is None and ad_links.code_of("ad_a b") is None)
    code = await ad_links.create("Noyabr — retarget")
    check("yangi havola faol, kodi to'g'ri", await ad_links.is_active(code) and ad_links.valid(code), code)
    check("bot havolasi", ad_links.bot_url("EDUbot", code) == f"https://t.me/EDUbot?start=ad_{code}")
    check("mavjud emas kod — faol emas", not await ad_links.is_active("zzzzzzz") and not await ad_links.exists("zz"))

    print("2) Botga kirish: yangi va eski mijoz")
    check("yangi mijoz yoziladi", await ad_links.record_start(code, 100, was_new=True))
    check("ikkinchi marta bosish qayta sanalmaydi", not await ad_links.record_start(code, 100, was_new=False))
    check("eski mijoz yoziladi", await ad_links.record_start(code, 200, was_new=False))
    await ad_links.record_start(code, 201, was_new=False)
    await ad_links.record_start(code, 101, was_new=True)
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS balance_spends (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                           "telegram_id INTEGER NOT NULL, amount INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        await conn.execute("INSERT INTO balance_spends (telegram_id, amount, created_at) VALUES (100, 1000, datetime('now', '+1 minute'))")
        await conn.execute("INSERT INTO balance_spends (telegram_id, amount, created_at) VALUES (200, 1000, datetime('now', '-30 days'))")
        await conn.commit()
    s = await ad_links.stats(code)
    check("yangi 2, eski 2, jami 4", (s["new"], s["old"], s["starts"]) == (2, 2, 4), s)
    check("foydalanganlar: start dan keyin yechim bo'lgani hisoblanadi, oldingisi emas",
          (s["new_used"], s["old_used"]) == (1, 0), s)

    print("3) Sayt havolasi /go/<kod>")
    webapp.BOT_USERNAME = "EDUbot"
    app = create_web_app()
    async with TestClient(TestServer(app)) as client:
        human = {"User-Agent": "Mozilla/5.0 (iPhone) Instagram 300.0", "X-Forwarded-For": "5.5.5.5"}
        r = await client.get(f"/go/{code}", headers=human, allow_redirects=False)
        check("botga yo'naltiradi", r.status == 302 and r.headers["Location"] == f"https://t.me/EDUbot?start=ad_{code}",
              (r.status, r.headers.get("Location")))
        check("keshlanmaydi", r.headers.get("Cache-Control") == "no-store")
        await client.get(f"/go/{code}", headers=human, allow_redirects=False)           # tez qayta bosish
        await client.get(f"/go/{code}", headers={"User-Agent": "Mozilla/5.0 (Android)", "X-Forwarded-For": "6.6.6.6"},
                         allow_redirects=False)
        await client.get(f"/go/{code}", headers={"User-Agent": "facebookexternalhit/1.1"}, allow_redirects=False)
        await client.get(f"/go/{code}", headers={"User-Agent": ""}, allow_redirects=False)
        s = await ad_links.stats(code)
        check("2 odam bosdi (tekshiruvchi botlar va tez takror sanalmadi)", (s["hits"], s["unique"]) == (2, 2), s)
        r = await client.get("/go/yoq-kod!", headers=human, allow_redirects=False)
        check("noto'g'ri kod — botga kod bilan emas, oddiy yo'naltiradi", r.status == 302
              and "ad_" not in r.headers["Location"], r.headers.get("Location"))
        await ad_links.set_active(code, False)
        r = await client.get(f"/go/{code}", headers={"User-Agent": "Mozilla/5.0", "X-Forwarded-For": "7.7.7.7"},
                             allow_redirects=False)
        s = await ad_links.stats(code)
        check("to'xtatilgan havola hisoblanmaydi, lekin mijozni botga olib boradi",
              r.status == 302 and "ad_" in r.headers["Location"] and s["hits"] == 2, s)
        check("to'xtatilganda yangi Start ham hisoblanmaydi", not await ad_links.record_start(code, 300, was_new=True))
        await ad_links.set_active(code, True)

    print("4) Xulosa")
    base = dict(hits=0, unique=100, new=0, new_used=0, old=0, old_used=0, starts=0)
    check("ma'lumot oz", "Hali ma'lumot oz" in ad_links.verdict(dict(base, unique=5)))
    v = ad_links.verdict(dict(base, starts=40, old=34, new=6))
    check("retarget: eski mijoz ko'p", "retarget" in v and "ESKI" in v, v)
    v = ad_links.verdict(dict(base, starts=40, old=5, new=35, new_used=10))
    check("yangi mijoz ko'p", "YANGI" in v and "retarget" not in v.split("ESKI")[0], v)
    v = ad_links.verdict(dict(base, unique=200, starts=40, old=20, new=20, new_used=10))
    check("adashib bosganlar ko'p", "adashib bosgan" in v and "80%" in v, v)
    v = ad_links.verdict(dict(base, starts=40, old=20, new=20, new_used=10))
    check("teng nisbat", "teng" in v, v)
    v = ad_links.verdict(dict(base, starts=40, old=0, new=40, new_used=1))
    check("yangi mijoz foydalanmasa ogohlantiradi", "foydalanmagan" in v, v)
    check("agent aniqlash", ad_links.is_bot_agent("Mozilla/5.0 (compatible; Googlebot/2.1)")
          and ad_links.is_bot_agent("") and not ad_links.is_bot_agent("Mozilla/5.0 (iPhone) Instagram"))
    check("tashrifchi belgisi IPni saqlamaydi", "5.5.5.5" not in ad_links.visitor_hash("5.5.5.5", "ua"))

    print("5) /start ad_<kod> — bot oqimi")
    from bot.handlers import start as start_handler
    code2 = await ad_links.create("Boshqa reklama")
    db = Database()
    db.get_active_channels = AsyncMock(return_value=[])
    db.get_user = AsyncMock(side_effect=[None, SimpleNamespace(telegram_id=9, language="uz", balance=0)])
    msg = MagicMock(); msg.text = f"/start ad_{code2}"; msg.from_user = SimpleNamespace(id=9, username="u", first_name="U")
    msg.answer = AsyncMock(); msg.bot = MagicMock(); msg.bot.send_message = AsyncMock()
    state = MagicMock(); state.clear = AsyncMock(); state.update_data = AsyncMock(); state.set_state = AsyncMock()
    db.create_user = AsyncMock(return_value=SimpleNamespace(telegram_id=9, language="uz", balance=0))
    db.get_feature_status = AsyncMock(return_value=False)
    try:
        await start_handler.start_command(msg, state, db)
    except Exception as exc:                                       # keyingi (til tanlash) qadamlar mock bilan to'liq emas
        print("  (oqimning davomi mock bilan to'xtadi:", type(exc).__name__, ")")
    s2 = await ad_links.stats(code2)
    check("yangi mijoz Start bosdi — 'yangi' deb yozildi", (s2["new"], s2["old"]) == (1, 0), s2)
    db.get_user = AsyncMock(return_value=SimpleNamespace(telegram_id=10, language="uz", balance=0))
    msg.from_user = SimpleNamespace(id=10, username="o", first_name="O")
    try:
        await start_handler.start_command(msg, state, db)
    except Exception as exc:
        print("  (oqimning davomi mock bilan to'xtadi:", type(exc).__name__, ")")
    s2 = await ad_links.stats(code2)
    check("bazada bor mijoz — 'eski' deb yozildi", (s2["new"], s2["old"]) == (1, 1), s2)

    print("6) O'chirish")
    check("o'chiriladi va hisobi ham ketadi", await ad_links.delete(code2) and await ad_links.stats(code2) is None)
    check("havolalar ro'yxati", [x["code"] for x in await ad_links.links()] == [code])


asyncio.run(main())
print("HAMMASI OK" if not FAILS else f"{len(FAILS)} ta XATO: {FAILS}")
sys.exit(1 if FAILS else 0)
