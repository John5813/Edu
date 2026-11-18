"""Sayt rejimi: botda pul, narx va sotuv bilan bog'liq hech narsa qolmasin; o'chirilsa — hammasi avvalgidek.

Bot main.py dagi tartibda (middleware va routerlar) yig'iladi, Telegram serveri o'rnida soxta sessiya:
- rejim yoqiq: eski to'lov tugmalari, chek kutish holati, do'kon havolasi (buy_), kitob tarjimasi, /book,
  PDF → DOCX, Yordam, referal, Narxlar — hammasi saytga yoki «tez orada»ga, summa va «to'lov»siz;
- rejim o'chiq: «To'lov qilish», Yordam, eski tugmalar — avvalgi bot javoblari;
- do'kon: saytda balansdan sotib olish, fayl «Hujjatlarim» va botga, pul yetmasa — yechilmaydi;
- admin-bot: faqat adminlar; to'lov xabarlari sayt rejimida admin-bot orqali; to'lov tasdig'i mijozga — asosiy bot orqali.

    python test_sayt_rejimi_tozalash.py
"""
import asyncio, datetime, os, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import config
import database.database as dbmod
from database.database import Database, init_db
from database import web_accounts, web_store
from services import site_mode, web_jobs, web_kinds  # noqa
import webapp

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "t.db")
web_jobs.RESULTS_DIR = os.path.join(TMP, "results")
webapp.WEBAPP_DOMAIN = "edufayl.org"
webapp.BOT_USERNAME = "Edufayl_bot"

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

USER, ADMIN = 555, (config.ADMIN_IDS[0] if config.ADMIN_IDS else 7001)
if ADMIN not in config.ADMIN_IDS:
    config.ADMIN_IDS.append(ADMIN)


class Session(BaseSession):
    def __init__(self):
        super().__init__(); self.calls = []
    async def close(self): pass
    async def stream_content(self, *a, **k):
        yield b"PPTXDATA"
    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        name = type(method).__name__
        if name == "GetMe":
            return User(id=bot.id, is_bot=True, first_name="bot", username="Edufayl_bot")
        if name in ("SendMessage", "SendDocument", "SendPhoto", "SendVideo", "EditMessageText"):
            return Message(message_id=len(self.calls), date=datetime.datetime.now(), chat=Chat(id=getattr(method, "chat_id", 1) or 1, type="private"),
                           text=getattr(method, "text", None) or "x")
        if name == "GetFile":
            from aiogram.types import File
            return File(file_id=method.file_id, file_unique_id="u", file_path="documents/f.pptx")
        return True
    def texts(self):
        return [(getattr(m, "text", None) or getattr(m, "caption", None) or "") for m in self.calls
                if type(m).__name__ in ("SendMessage", "EditMessageText", "SendDocument")]
    def markups(self):
        return [getattr(m, "reply_markup", None) for m in self.calls if type(m).__name__ == "SendMessage"]


def build():
    """main.py dagi kabi dispatcher (middleware va routerlar o'sha tartibda)."""
    from bot.handlers import (start, documents, payments, admin, settings, samples, media, converter, pptx_converter,
                              abs_converter, book_translate, project_work, store)
    from bot.handlers import prices as prices_handler, test as test_handler
    from bot.handlers import premium_presentation as premium, emoji as emoji_handler, reengage as reengage_handler
    from bot.handlers import site_mode as site_mode_handler
    from bot.middlewares import (BlockedUserMiddleware, CommandResetMiddleware, DatabaseMiddleware,
                                 LanguageMiddleware, UzScriptMiddleware)
    from services import admin_bot
    dp = Dispatcher(storage=MemoryStorage())
    for kind in (dp.message, dp.callback_query, dp.pre_checkout_query):
        kind.middleware(DatabaseMiddleware()); kind.middleware(LanguageMiddleware())
    dp.message.outer_middleware(CommandResetMiddleware())
    for kind in (dp.message, dp.callback_query):
        kind.middleware(BlockedUserMiddleware()); kind.middleware(UzScriptMiddleware())
    dp.update.outer_middleware(admin_bot.gate)
    for r in (admin.router, site_mode_handler.router, reengage_handler.router, settings.router, converter.router,
              pptx_converter.router, abs_converter.router, premium.router, project_work.router, store.router,
              emoji_handler.router, payments.router, samples.router, prices_handler.router, media.router,
              book_translate.router, test_handler.router, documents.router, start.router):
        dp.include_router(r)
    return dp


N = [0]
def _user(uid): return User(id=uid, is_bot=False, first_name="Ali", username="ali")
def msg(text, uid=USER, **kw):
    N[0] += 1
    return Update(update_id=N[0], message=Message(message_id=N[0], date=datetime.datetime.now(),
                  chat=Chat(id=uid, type="private"), from_user=_user(uid), text=text, **kw))
def cb(data, uid=USER):
    N[0] += 1
    m = Message(message_id=N[0], date=datetime.datetime.now(), chat=Chat(id=uid, type="private"), from_user=_user(uid), text="eski")
    return Update(update_id=N[0], callback_query=CallbackQuery(id=str(N[0]), from_user=_user(uid), chat_instance="c",
                                                               data=data, message=m))


MONEY = ("so'm", "сум", "to'lov", "оплат", "karta", "stars", "narx", "цена", "balans")


def clean(text):
    low = (text or "").lower()
    return not any(w in low for w in MONEY)


async def main():
    from translations import get_text
    await init_db()
    db = Database()
    await Database.create_user(USER, "ali", "Ali", "uz")
    await Database.create_user(ADMIN, "adm", "Admin", "uz")
    session = Session()
    bot = Bot(token="42:main", session=session)
    webapp.BOT = bot
    dp = build()

    async def send(update, b=None):
        before = len(session.calls)
        await dp.feed_update(b or bot, update)
        new = session.calls[before:]
        texts = [(getattr(m, "text", None) or getattr(m, "caption", None) or "") for m in new
                 if type(m).__name__ in ("SendMessage", "EditMessageText", "SendDocument")]
        urls = [btn.url for m in new for row in (getattr(getattr(m, "reply_markup", None), "inline_keyboard", None) or [])
                for btn in row if getattr(btn, "url", None)]
        return "\n".join(texts), urls

    print("1) Sayt rejimi YOQIQ: botda pul mavzusi qolmaydi")
    await site_mode.set(db, True)
    for label in ("main_menu.payment", "main_menu.my_account", "main_menu.prices"):
        text, urls = await send(msg(get_text("uz", label)))
        check(f"«{get_text('uz', label)}» → sayt, summasiz", urls and "edufayl.org/go?" in urls[0] and clean(text), (text, urls))
    for data in ("pay_card_start", "pay_20000", "pay_custom", "pay_by_card:20000", "pay_stars_61_10000",
                 "doc_pay", "prem_stars", "store_pay", "pw_recheck", "book_other", "show_referral"):
        text, urls = await send(cb(data))
        check(f"eski tugma «{data}» → eskirgan, sayt", "eskirgan" in text and urls and clean(text.replace("eskirgan", "")), text)
    ctx = dp.fsm.get_context(bot, chat_id=USER, user_id=USER)
    await ctx.set_state("PaymentStates:waiting_for_screenshot")
    text, urls = await send(msg("chek.jpg"))
    check("chek kutib turgan mijoz: bot chek qabul qilmaydi", "eskirgan" in text and await ctx.get_state() is None, text)
    await Database.create_store_item("ABCD1234", "Samarqand tarixi", "FILE1", 15000, work_type="taqdimot", slide_count=12)
    text, urls = await send(msg("/start buy_ABCD1234"))
    check("do'kon havolasi (buy_) → saytda sotib olish, narxsiz", "Samarqand tarixi" in text and urls
          and "to=buy_ABCD1234" in urls[0] and clean(text), (text, urls))
    text, _ = await send(msg("/start buy_ZZZZ9999"))
    check("noma'lum ish — bot do'koni javob bermaydi", "Bu ish topilmadi" not in text, text)
    for label in ("📚 Kitob tarjimasi", "📄 PDF → DOCX", get_text("uz", "main_menu.test")):
        text, _ = await send(msg(label))
        check(f"«{label}» → tez orada saytda", "tez orada" in text.lower() and clean(text), text)
    text, _ = await send(msg("/book"))
    check("/book → tez orada saytda", "tez orada" in text.lower(), text)
    text, _ = await send(msg(get_text("uz", "main_menu.help")))
    check("Yordam: to'lov va narx qatorlarisiz", "Yordam" in text and clean(text), text)
    text, _ = await send(msg("💰 Pul ishlab topish"))
    check("referal: havola bor, summa yo'q", "ref_" in text and "so'm" not in text and "Pul" not in text, text)
    text, urls = await send(msg(get_text("uz", "main_menu.referat")))
    check("xizmat tugmasi → sayt", urls and "to=referat" in urls[0], (text, urls))

    print("2) Sayt rejimi O'CHIQ: hammasi avvalgidek")
    await site_mode.set(db, False)
    text, urls = await send(msg(get_text("uz", "main_menu.payment")))
    check("«To'lov qilish» → botdagi summa tanlash", "to'lov miqdorini" in text.lower() and not urls, text)
    text, _ = await send(msg(get_text("uz", "main_menu.help")))
    check("Yordam: avvalgi matn", text.startswith("📞") and "To'lov" in text, text[:80])
    text, _ = await send(msg("💰 Pul ishlab topish"))
    check("referal: avvalgi matn (summalar bilan)", "so'm" in text, text[:80])
    text, _ = await send(msg("/start buy_ABCD1234"))
    check("do'kon havolasi → botdagi xarid (narx bilan)", "Samarqand tarixi" in text and "so'm" in text, text[:120])
    text, _ = await send(msg(get_text("uz", "site_mode_cabinet_btn")))
    check("eski «Kabinetim» → hisob va to'liq menyu", "hisob" in text.lower(), text[:80])

    print("3) Do'kon: saytda sotib olish (sayt rejimi)")
    await site_mode.set(db, True)
    from aiohttp.test_utils import TestClient, TestServer
    server = TestServer(__import__("webapp.server", fromlist=["x"]).create_web_app())
    client = TestClient(server); await client.start_server()
    client.session.cookie_jar.update_cookies({"edu_session": await web_accounts.create_session(USER)})
    await Database.update_user_balance(USER, 10000)
    d = await (await client.get("/api/v1/store/ABCD1234")).json()
    check("ma'lumot: nom, narx, balans", d["item"]["price"] == 15000 and d["balance"] == 10000 and d["owned"] is False, d)
    r = await client.post("/api/v1/store/ABCD1234/buy")
    check("pul yetmaydi — yechilmaydi, yetishmagan summa aytiladi", r.status == 402 and (await r.json())["missing"] == 5000
          and (await Database.get_user(USER)).balance == 10000)
    await Database.update_user_balance(USER, 10000)
    before = len(session.calls)
    r = await client.post("/api/v1/store/ABCD1234/buy"); d = await r.json()
    job = await web_store.get_job(d.get("job_id", ""))
    sent = [m for m in session.calls[before:] if type(m).__name__ == "SendDocument"]
    check("sotib olindi: balansdan yechildi, fayl «Hujjatlarim» da va botga yuborildi", r.status == 200
          and (await Database.get_user(USER)).balance == 5000 and job and job["status"] == "done"
          and job.get("result_path") and sent and sent[0].chat_id == USER, (d, job))
    r = await client.post("/api/v1/store/ABCD1234/buy")
    check("qayta olish — pul yechilmaydi", r.status == 200 and (await Database.get_user(USER)).balance == 5000)
    from webapp import store as store_page
    check("do'kon sahifasidagi tugma — saytda sotib olish", store_page._buy_url("ABCD1234") == "/app#/buy/ABCD1234")
    await site_mode.set(db, False)
    check("rejim o'chiq — botda sotib olish (avvalgidek)", store_page._buy_url("ABCD1234").startswith("https://t.me/"))
    await site_mode.set(db, True)
    await client.close()

    print("4) Admin-bot")
    from services import admin_bot
    asession = Session()
    abot = Bot(token="43:admin", session=asession)
    admin_bot.BOT = abot
    check("sayt rejimida to'lov xabarlari admin-bot orqali", admin_bot.for_admins(bot) is abot)
    check("mijozga — asosiy bot", admin_bot.user_bot(abot) is bot and admin_bot.user_bot(bot) is bot)
    before = len(asession.calls)
    await dp.feed_update(abot, msg("salom", uid=USER))
    check("admin-botga oddiy mijoz yoza olmaydi (javob yo'q)", len(asession.calls) == before)
    await dp.feed_update(abot, msg("/start", uid=ADMIN))
    check("admin /start → qisqa izoh", any("Admin-bot" in (getattr(m, "text", "") or "") for m in asession.calls[before:]))
    await site_mode.set(db, False)
    check("rejim o'chiq — hammasi asosiy bot orqali", admin_bot.for_admins(bot) is bot)
    from services import click_pay
    await site_mode.set(db, True)
    await Database.update_user_balance(USER, 0)
    inv = {"id": 1, "telegram_id": USER, "amount": 20000, "source": "web"}
    a_before, m_before = len(asession.calls), len(session.calls)
    await click_pay._credit(inv)
    admin_msgs = [m.text for m in asession.calls[a_before:] if type(m).__name__ == "SendMessage"]
    user_msgs = [m for m in session.calls[m_before:] if type(m).__name__ == "SendMessage" and m.chat_id == USER]
    check("Click to'lovi: admin-botga «sayt orqali», mijozga tasdiq — asosiy bot orqali",
          any("sayt orqali" in t for t in admin_msgs) and len(user_msgs) == 1
          and not [m for m in asession.calls[a_before:] if getattr(m, "chat_id", None) == USER], (admin_msgs, user_msgs))
    admin_bot.BOT = None


asyncio.run(main())
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
