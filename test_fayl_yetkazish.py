"""Saytda buyurtma qilingan tayyor fayl botga yetkaziladi (services/web_jobs.deliver_to_telegram).

- xabar mijozning tilida (qozoqcha ham), mavzu nomi bilan;
- 50 MB dan katta fayl — fayl o'rniga «Saytda ochish» tugmali xabar;
- tarmoq xatosi va Telegram cheklovida qayta urinadi; bot bloklangan bo'lsa darhol to'xtaydi;
- natija buyurtmaga yoziladi (saytda «Telegramga yuborildi» belgisi), bajarilmagan buyurtma haqida ham yoziladi;
- «Saytda ochish» bosilganda yangi bir martalik havola beriladi.

    python test_fayl_yetkazish.py
"""
import asyncio, os, sys, tempfile, time, types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import database.database as dbmod
from database.database import Database, init_db
from database import web_store
from services import web_jobs, web_kinds  # noqa
import webapp
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "test.db")
web_jobs.RESULTS_DIR = os.path.join(TMP, "results")
webapp.WEBAPP_DOMAIN = "edufayl.org"
webapp.BOT_USERNAME = "Edufayl_bot"


class FakeBot:
    def __init__(self, fail=()):
        self.fail = list(fail)      # navbatdagi urinishlarda ko'tariladigan xatolar
        self.docs, self.msgs = [], []
    async def _maybe_fail(self):
        if self.fail:
            raise self.fail.pop(0)
    async def send_document(self, chat_id, document, caption=None, **kw):
        await self._maybe_fail(); self.docs.append((chat_id, document.filename, caption)); return types.SimpleNamespace()
    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        await self._maybe_fail(); self.msgs.append((chat_id, text, reply_markup)); return types.SimpleNamespace()


def blocked(): return TelegramForbiddenError(method=None, message="Forbidden: bot was blocked by the user")
def network(): return TelegramNetworkError(method=None, message="Request timeout")
def flood(): return TelegramRetryAfter(method=None, message="Too Many Requests", retry_after=0)


def make_file(size=1000):
    path = os.path.join(TMP, f"f{time.time_ns()}.pptx")
    with open(path, "wb") as f:
        f.seek(size - 1); f.write(b"\0")
    return path


async def main():
    await init_db()
    await Database.create_user(555, "ali", "Ali", "uz")
    await Database.create_user(777, "vali", "Vali", "ru")
    await Database.create_user(888, "aset", "Aset", "kk")   # qozoq: bazada "kk"
    sleeps = []
    async def no_sleep(s): sleeps.append(s)
    web_jobs._pause = no_sleep

    print("1) Oddiy fayl — mijoz tilida, mavzu bilan")
    bot = FakeBot()
    r = await web_jobs.deliver_to_telegram(bot, 555, "Iqtisodiyot asoslari", make_file(), "Iqtisodiyot.pptx")
    check("yuborildi (1)", r == 1 and len(bot.docs) == 1, (r, bot.docs))
    check("o'zbekcha matn, mavzu nomi", "«Iqtisodiyot asoslari» tayyor" in bot.docs[0][2] and "72 soat" in bot.docs[0][2], bot.docs)
    await web_jobs.deliver_to_telegram(bot, 777, "Экономика", make_file(), "x.pptx")
    check("ruscha mijozga ruscha", "готово" in bot.docs[-1][2], bot.docs[-1])
    await web_jobs.deliver_to_telegram(bot, 888, "Экономика", make_file(), "x.pptx")
    check("qozoq mijozga qozoqcha", "дайын" in bot.docs[-1][2], bot.docs[-1])

    print("2) Katta fayl — havola")
    old_limit = web_jobs.TG_FILE_LIMIT
    web_jobs.TG_FILE_LIMIT = 500
    bot = FakeBot()
    r = await web_jobs.deliver_to_telegram(bot, 555, "Diplom ishi", make_file(2000), "Diplom.docx")
    web_jobs.TG_FILE_LIMIT = old_limit
    check("fayl o'rniga xabar (2)", r == 2 and not bot.docs and len(bot.msgs) == 1, (r, bot.msgs))
    btn = bot.msgs[0][2].inline_keyboard[0][0]
    check("«Saytda ochish» tugmasi yangi havola so'raydi", btn.callback_data == "golink:docs", btn)

    print("3) Xatolar")
    bot = FakeBot([network(), flood()])
    r = await web_jobs.deliver_to_telegram(bot, 555, "T", make_file(), "t.pptx")
    check("tarmoq xatosi va cheklovdan keyin qayta urinib yetkazdi", r == 1 and len(bot.docs) == 1 and len(sleeps) == 2, (r, sleeps))
    bot = FakeBot([blocked()])
    r = await web_jobs.deliver_to_telegram(bot, 555, "T", make_file(), "t.pptx")
    check("bot bloklangan — darhol to'xtaydi (-1)", r == -1 and not bot.fail, r)
    bot = FakeBot([network(), network(), network()])
    r = await web_jobs.deliver_to_telegram(bot, 555, "T", make_file(), "t.pptx")
    check("uch marta ham bo'lmasa — -1", r == -1)

    print("4) Buyurtma oqimi: natija saytda ko'rinadi")
    bot = FakeBot([blocked()]); webapp.BOT = bot
    async def fake_run(params, report):
        return make_file(), "Referat.docx"
    kind = web_jobs.KINDS["referat"]
    kind_run, kind.run = kind.run, fake_run
    await Database.update_user_balance(555, 100000)
    job = await web_jobs.submit(555, "referat", {"topic": "Globallashuv va iqtisodiyot", "language": "uz", "size": "10_15"})
    for _ in range(100):
        row = await web_store.get_job(job["id"])
        if row["status"] == "done" and row.get("tg_sent"): break
        await asyncio.sleep(0.05)
    pub = web_jobs.public(await web_store.get_job(job["id"]))
    check("bloklangan bot — saytda «yuborib bo'lmadi» (-1)", pub["telegram"] == -1, pub)
    async def boom(params, report): raise RuntimeError("model javob bermadi")
    kind.run = boom
    bot = FakeBot(); webapp.BOT = bot
    job = await web_jobs.submit(555, "referat", {"topic": "Raqamli iqtisodiyot", "language": "uz", "size": "10_15"})
    for _ in range(100):
        if (await web_store.get_job(job["id"]))["status"] == "failed" and bot.msgs: break
        await asyncio.sleep(0.05)
    check("bajarilmadi — botga xabar (pulsiz matn, saytga tugma)", bot.msgs and "bajarilmadi" in bot.msgs[-1][1]
          and "so'm" not in bot.msgs[-1][1] and bot.msgs[-1][2].inline_keyboard[0][0].callback_data == "golink:docs", bot.msgs)
    kind.run = kind_run

    print("5) «Saytda ochish» — yangi bir martalik havola")
    from bot.handlers import site_mode as handler
    sent = []
    async def answer(*a, **k): pass
    async def msg_answer(text, reply_markup=None, **k): sent.append((text, reply_markup))
    cb = types.SimpleNamespace(data="golink:docs", from_user=types.SimpleNamespace(id=555), answer=answer,
                               message=types.SimpleNamespace(answer=msg_answer))
    await handler.fresh_link(cb, "uz")
    url = sent[-1][1].inline_keyboard[0][0].url
    check("havola /go?t=...&to=docs", url.startswith("https://edufayl.org/go?t=") and url.endswith("&to=docs"), url)
    cb.data = "golink:https://evil"
    await handler.fresh_link(cb, "uz")
    check("noma'lum joy — hujjatlar sahifasi", sent[-1][1].inline_keyboard[0][0].url.endswith("&to=docs"))


asyncio.run(main())
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
