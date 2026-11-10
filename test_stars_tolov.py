"""Telegram Stars to'lovi: pul yechilgach xizmat albatta bajariladi yoki pul balansga tushadi.

Ilgari «Loyiha ishi» routeridagi Stars ishlovchisi filtrsiz edi (`F.successful_payment`) va BARCHA Stars
to'lovlarini ushlab olardi: to'lov o'ziniki bo'lmasa shunchaki `return` qilardi — aiogram uchun bu «hodisa
qayta ishlandi» degani, keyingi routerlarga yetib bormasdi. Natijada mustaqil ish, referat, test, kitob
tarjimasi (balansni Stars bilan to'ldirish) va do'kon xaridlarida Stars yechilib, hech narsa bo'lmasdi.
Taqdimotda esa ishlovchi holatga (FSM) bog'liq edi: holat o'zgargan bo'lsa to'lov ham o'sha yerda yo'qolardi.

Test haqiqiy routerlarni main.py dagi tartibda ulab, Telegram'dan kelgan `successful_payment` xabarini
dispetcherdan o'tkazadi.

    python test_stars_tolov.py
"""
import asyncio, os, sys
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "123456:abc")

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, SuccessfulPayment, Update, User as TgUser

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from config import STARS_RATE, som_to_stars
from bot import checkout as pay
from bot.handlers import converter, premium_presentation as pp, project_work, store, payments
from bot.handlers import documents, book_translate, test as test_service  # noqa: F401 — xizmat belgilari ro'yxatga olinadi

UID = 777
balance = {"v": 0}
sent = []


class DB:
    async def get_user(self, uid):
        return SimpleNamespace(language="uz", balance=balance["v"], first_name="Ali", id=1, telegram_id=uid,
                               username="ali")
    async def update_user_balance(self, uid, delta):
        balance["v"] += delta
    def __getattr__(self, name):
        async def _none(*a, **k): return None
        return _none


async def fake_call(self, method, request_timeout=None):
    """Telegram API chaqiruvlari: hammasi yoziladi, javob — oddiy xabar."""
    sent.append(method)
    return Message(message_id=len(sent) + 100, date=datetime.now(), chat=Chat(id=UID, type="private"))


def paid(payload: str, stars: int) -> Update:
    msg = Message(message_id=1, date=datetime.now(), chat=Chat(id=UID, type="private"),
                  from_user=TgUser(id=UID, is_bot=False, first_name="Ali"),
                  successful_payment=SuccessfulPayment(currency="XTR", total_amount=stars, invoice_payload=payload,
                                                       telegram_payment_charge_id="c1", provider_payment_charge_id="p1"))
    return Update(update_id=1, message=msg)


def texts():
    return " | ".join(str(getattr(m, "text", "") or "") for m in sent)


async def main():
    dp = Dispatcher(storage=MemoryStorage())
    # main.py dagi tartib (Stars ishlovchilari bor routerlar)
    for r in (converter.router, pp.router, project_work.router, store.router, payments.router):
        dp.include_router(r)
    bot = Bot("123456:abc")
    db = DB()
    key = StorageKey(bot_id=bot.id, chat_id=UID, user_id=UID)
    user = await db.get_user(UID)

    async def feed(update):
        sent.clear()
        with mock.patch.object(Bot, "__call__", fake_call):
            await dp.feed_update(bot, update, db=db, user_lang="uz", user=user)

    print("1) Balansni Stars bilan to'ldirish (mustaqil ish, referat, test, kitob tarjimasi shu yo'ldan)")
    balance["v"] = 0
    stars = som_to_stars(6000)
    await feed(paid(f"topup_{stars}_{stars * STARS_RATE}", stars))
    check("Stars balansga tushdi (ilgari «Loyiha ishi» ishlovchisi yutib yuborardi)",
          balance["v"] == stars * STARS_RATE, (balance["v"], texts()))

    print("2) Do'kon xaridi Stars bilan")
    sold = {}
    async def fake_pending(state, uid): return {"id": 5, "price": 8000}
    async def fake_sell(message, item, lang, uid, state, db_, charge=True):
        sold.update(item=item, charge=charge)
    with mock.patch.object(store, "_pending", fake_pending), mock.patch.object(store, "_sell", fake_sell):
        await feed(paid(store.CHECKOUT.payload(UID, 8000), som_to_stars(8000)))
    check("do'kon ishlovchisi ishladi, ish yuborildi (balansdan qayta yechilmadi)",
          sold.get("item", {}).get("id") == 5 and sold.get("charge") is False, sold)

    print("3) Taqdimot — holat (FSM) yo'qolgan bo'lsa ham saqlangan buyurtmadan davom etadi")
    started = {}
    async def fake_confirm(callback, state, db_):
        started.update(data=await state.get_data())
    await dp.storage.set_state(key, None)
    await dp.storage.set_data(key, {})
    order = pay.start({"kind": "modern", "topic": "Iqlim o'zgarishi", "slide_count": 10, "price": 5000})
    pay.remember(UID, pp.CHECKOUT.service, order)
    with mock.patch.object(pp, "premium_ppt_confirm", fake_confirm):
        await feed(paid(pp.CHECKOUT.payload(UID, 5000), som_to_stars(5000)))
    check("taqdimot yasash boshlandi: mavzu va to'lov usuli Stars",
          started.get("data", {}).get("topic") == "Iqlim o'zgarishi"
          and started.get("data", {}).get("payment_method") == "stars", started)

    print("4) Buyurtma butunlay yo'qolgan bo'lsa — Stars balansga qaytadi (pul yo'qolmaydi)")
    pay.forget(UID)
    await dp.storage.set_data(key, {})
    balance["v"] = 0
    with mock.patch.object(pp, "premium_ppt_confirm", fake_confirm):
        await feed(paid(pp.CHECKOUT.payload(UID, 5000), som_to_stars(5000)))
    check("taqdimot: summa balansga qaytdi", balance["v"] == 5000, (balance["v"], texts()))
    balance["v"] = 0
    await feed(paid(project_work.CHECKOUT.payload(UID, 12000), som_to_stars(12000)))
    check("loyiha ishi: summa balansga qaytdi", balance["v"] == 12000, (balance["v"], texts()))
    balance["v"] = 0
    with mock.patch.object(store, "_pending", lambda *a: asyncio.sleep(0, None)):
        await feed(paid(store.CHECKOUT.payload(UID, 8000), som_to_stars(8000)))
    check("do'kon: summa balansga qaytdi", balance["v"] == 8000, (balance["v"], texts()))

    print("5) Hech bir xizmat tanimagan to'lov — balansga yoziladi")
    balance["v"] = 0
    await feed(paid("doc:777:3000", som_to_stars(3000)))
    check("xizmat belgisi bor, lekin ishlovchisi yo'q — yo'qolmaydi", balance["v"] == 3000, (balance["v"], texts()))

    await bot.session.close()
    print()
    print("HAMMASI O'TDI" if not FAILS else f"XATOLAR: {len(FAILS)} — {FAILS}")
    return not FAILS


ok = asyncio.run(main())
sys.exit(0 if ok else 1)
