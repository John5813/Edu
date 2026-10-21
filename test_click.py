"""Click SHOP API orqali balansni to'ldirish.

- havola: service_id, merchant_id, summa va invoys raqami;
- Prepare/Complete: MD5 imzo, summa, invoys, amal turi tekshiriladi, Click xato kodlari qaytadi;
- Complete ikki marta kelsa ham balans bir marta qo'shiladi; Click bekor qilsa invoys yopiladi;
- balans qo'shilmasa (-7) invoys qayta to'lanadigan holatga qaytadi;
- haqiqiy oqim: to'lov yozuvi (source=click, approved), balans, mijozga xabar; HTTP manzillari.

    python test_click.py
"""
import asyncio
import hashlib
import os
import sys
import tempfile
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        FAILS.append(name)


import config
import database.database as dbmod

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "test.db")
config.CLICK_SERVICE_ID, config.CLICK_MERCHANT_ID, config.CLICK_SECRET_KEY = "111", "222", "sir"
config.CLICK_MERCHANT_USER_ID, config.CLICK_RETURN_URL, config.CLICK_EMOJI_ID = "", "", ""

from database import click_invoices
from database.database import Database, init_db
from services import click_pay

SECRET = "sir"


def signed(invoice_id, amount, action, trans="9001", prepare_id=None, error="0", secret=SECRET):
    p = {"click_trans_id": trans, "service_id": "111", "click_paydoc_id": "77", "merchant_trans_id": str(invoice_id),
         "amount": amount, "action": str(action), "error": error, "error_note": "", "sign_time": "2026-10-21 10:00:00"}
    if prepare_id is not None:
        p["merchant_prepare_id"] = str(prepare_id)
    raw = (p["click_trans_id"] + p["service_id"] + secret + p["merchant_trans_id"]
           + (p.get("merchant_prepare_id", "") if action == 1 else "") + p["amount"] + p["action"] + p["sign_time"])
    p["sign_string"] = hashlib.md5(raw.encode()).hexdigest()
    return p


credited = []


async def fake_credit(invoice):
    credited.append(invoice["id"])
    return 500 + invoice["id"]


async def main():
    await init_db()

    print("1) Havola")
    check("kalitlar bo'lsa Click yoqiq", click_pay.enabled())
    url = await click_pay.new_payment(42, 15000, "bot")
    q = parse_qs(urlparse(url).query)
    check("my.click.uz havolasi: service_id, merchant_id, summa, invoys",
          url.startswith("https://my.click.uz/services/pay?") and q["service_id"] == ["111"]
          and q["merchant_id"] == ["222"] and q["amount"] == ["15000"] and q["transaction_param"][0].isdigit(), url)
    inv = int(q["transaction_param"][0])
    import webapp
    config.CLICK_MERCHANT_USER_ID = "93259"
    webapp.BOT_USERNAME = "Edufayl_bot"
    q = parse_qs(urlparse(await click_pay.new_payment(42, 1000, "bot")).query)
    check("havolada merchant_user_id yo'q (Click «Поставщик не найден» derdi)", "merchant_user_id" not in q, q)
    check("return_url — bot (sozlama bo'lmasa)", q.get("return_url") == ["https://t.me/Edufayl_bot"], q)
    config.CLICK_RETURN_URL = "https://example.uz/ok"
    q = parse_qs(urlparse(await click_pay.new_payment(42, 1000, "bot")).query)
    check("CLICK_RETURN_URL bo'lsa o'sha", q.get("return_url") == ["https://example.uz/ok"], q)
    config.CLICK_MERCHANT_USER_ID, config.CLICK_RETURN_URL, webapp.BOT_USERNAME = "", "", ""
    for bad in (500, "abc", 10_000_000):
        try:
            await click_pay.new_payment(42, bad, "bot")
            check(f"noto'g'ri summa rad etiladi ({bad})", False)
        except ValueError:
            check(f"noto'g'ri summa rad etiladi ({bad})", True)

    print("\n2) Prepare")
    r = await click_pay.handle(signed(inv, "15000.00", 0, secret="boshqa"))
    check("imzo noto'g'ri → -1", r["error"] == -1, r)
    r = await click_pay.handle(signed(inv, "14000", 0))
    check("summa boshqa → -2", r["error"] == -2, r)
    r = await click_pay.handle(signed(999999, "15000", 0))
    check("invoys yo'q → -5", r["error"] == -5, r)
    r = await click_pay.handle(signed(inv, "15000", 0), action=1)
    check("Complete manziliga Prepare kelsa → -3", r["error"] == -3, r)
    r = await click_pay.handle(signed(inv, "15000.00", 0))
    check("to'g'ri Prepare → 0 va merchant_prepare_id", r["error"] == 0 and r["merchant_prepare_id"] == inv, r)
    check("javobda Click maydonlari", r["click_trans_id"] == "9001" and r["merchant_trans_id"] == str(inv), r)

    print("\n3) Complete")
    r = await click_pay.complete(signed(inv, "15000", 1, prepare_id=inv, secret="x"), fake_credit)
    check("imzo noto'g'ri → -1", r["error"] == -1 and not credited, r)
    r = await click_pay.complete(signed(inv, "15000", 1, prepare_id=inv + 1), fake_credit)
    check("boshqa prepare_id → -6", r["error"] == -6 and not credited, r)
    r = await click_pay.complete(signed(inv, "15000", 1, prepare_id=inv, trans="1234"), fake_credit)
    check("boshqa click_trans_id → -6", r["error"] == -6 and not credited, r)
    r = await click_pay.complete(signed(inv, "15000", 1, prepare_id=inv), fake_credit)
    check("to'g'ri Complete → 0, balans bir marta", r["error"] == 0 and credited == [inv]
          and r["merchant_confirm_id"] == 500 + inv, r)
    r = await click_pay.complete(signed(inv, "15000", 1, prepare_id=inv), fake_credit)
    check("takroriy Complete → -4, balans ikkinchi marta qo'shilmaydi", r["error"] == -4 and credited == [inv], r)
    r = await click_pay.handle(signed(inv, "15000", 0))
    check("to'langan invoysga Prepare → -4", r["error"] == -4, r)

    print("\n4) Bekor qilish va xato")
    inv2 = await click_invoices.create(42, 20000, "web")
    await click_pay.handle(signed(inv2, "20000", 0, trans="5"))
    r = await click_pay.complete(signed(inv2, "20000", 1, trans="5", prepare_id=inv2, error="-5017"), fake_credit)
    row = await click_invoices.get(inv2)
    check("Click bekor qilsa → -9, invoys yopiladi, balans yo'q",
          r["error"] == -9 and row["status"] == "cancelled" and credited == [inv], (r, row["status"]))
    r = await click_pay.handle(signed(inv2, "20000", 0, trans="6"))
    check("bekor qilingan invoysga Prepare → -9", r["error"] == -9, r)

    inv3 = await click_invoices.create(42, 30000, "web")
    await click_pay.handle(signed(inv3, "30000", 0, trans="7"))

    async def broken(invoice):
        raise RuntimeError("baza band")

    r = await click_pay.complete(signed(inv3, "30000", 1, trans="7", prepare_id=inv3), broken)
    row = await click_invoices.get(inv3)
    check("balans qo'shilmasa → -7, invoys qayta to'lanadigan holatda", r["error"] == -7 and row["status"] == "prepared",
          (r, row["status"]))
    r = await click_pay.complete(signed(inv3, "30000", 1, trans="7", prepare_id=inv3), fake_credit)
    check("Click qayta yuborganda to'lov o'tadi", r["error"] == 0 and credited[-1] == inv3, r)

    print("\n5) Haqiqiy oqim: to'lov yozuvi, balans, xabar")
    import webapp

    sent = []

    class Bot:
        async def send_message(self, chat_id, text, **kw):
            sent.append((chat_id, text))

    webapp.BOT = Bot()
    user = await Database.create_user(77, "u77", "U77", "uz")
    inv4 = await click_invoices.create(77, 25000, "bot")
    await click_pay.handle(signed(inv4, "25000", 0, trans="8"))
    r = await click_pay.handle(signed(inv4, "25000", 1, trans="8", prepare_id=inv4))
    fresh = await Database.get_user(77)
    payment = await Database.get_payment_by_id(r.get("merchant_confirm_id") or 0)
    check("balans 25 000 ga oshdi", fresh.balance - user.balance == 25000, (user.balance, fresh.balance))
    check("to'lov yozuvi: click, approved", payment is not None and payment.source == "click"
          and payment.status == "approved" and payment.amount == 25000, payment)
    check("mijozga Click xabari", any(chat == 77 and "Click" in text for chat, text in sent), sent)
    r = await click_pay.handle(signed(inv4, "25000", 1, trans="8", prepare_id=inv4))
    check("takroriy Complete balansni oshirmaydi", r["error"] == -4
          and (await Database.get_user(77)).balance == fresh.balance, r)

    print("\n6) HTTP manzillari")
    from aiohttp.test_utils import TestClient, TestServer
    from webapp.server import create_web_app

    inv5 = await click_invoices.create(77, 12000, "web")
    async with TestClient(TestServer(create_web_app())) as client:
        resp = await client.post("/click/prepare", data=signed(inv5, "12000", 0, trans="9"))
        body = await resp.json()
        check("/click/prepare → 200, error 0", resp.status == 200 and body["error"] == 0, body)
        resp = await client.post("/click/complete", data=signed(inv5, "12000", 1, trans="9", prepare_id=inv5))
        body = await resp.json()
        check("/click/complete → 200, error 0", resp.status == 200 and body["error"] == 0, body)
        resp = await client.post("/click/complete", data={"action": "1"})
        body = await resp.json()
        check("chala so'rov → -8", resp.status == 200 and body["error"] == -8, body)
        resp = await client.post("/api/v1/wallet/click", json={"amount": 10000})
        check("sayt Click havolasi kirishsiz berilmaydi", resp.status == 401, resp.status)

    print("\n7) Bot: summa tanlangach «Click» va «Karta» tugmalari")
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import ReplyKeyboardMarkup
    from bot.handlers import payments
    from bot.states import PaymentStates

    class Msg:
        def __init__(self):
            self.out = []

        async def answer(self, text, **kw):
            self.out.append((text, kw.get("reply_markup")))

        async def edit_text(self, text, **kw):
            self.out.append((text, kw.get("reply_markup")))

    def fsm():
        return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=77, user_id=77))

    msg, state = Msg(), fsm()
    await payments._choose_method(msg, 77, 20000, state, "uz", edit=True)
    rows = msg.out[0][1].inline_keyboard if msg.out else []
    check("ikki tugma: Click havolasi va «Karta orqali»",
          len(rows) == 2 and rows[0][0].url.startswith("https://my.click.uz/") and "amount=20000" in rows[0][0].url
          and rows[1][0].callback_data == "pay_by_card:20000" and "20,000" in msg.out[0][0], msg.out)
    check("usul tanlanmaguncha chek kutilmaydi", await state.get_state() is None, await state.get_state())

    check("ikonka sozlanmagan bo'lsa ⚡ belgisi", rows and rows[0][0].text.startswith("⚡")
          and not rows[0][0].icon_custom_emoji_id, rows)

    config.CLICK_EMOJI_ID = "5368324170671202286"
    msg = Msg()
    await payments._choose_method(msg, 77, 20000, fsm(), "uz")
    button = msg.out[0][1].inline_keyboard[0][0]
    check("CLICK_EMOJI_ID bo'lsa tugmada Click ikonkasi, ⚡ yo'q",
          button.icon_custom_emoji_id == "5368324170671202286" and "⚡" not in button.text, button)

    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import SendMessage

    class Strict(Msg):
        async def answer(self, text, **kw):
            markup = kw.get("reply_markup")
            if markup and markup.inline_keyboard[0][0].icon_custom_emoji_id:
                raise TelegramBadRequest(SendMessage(chat_id=77, text=text), "Bad Request: BUTTON_ICON_INVALID")
            self.out.append((text, markup))

    msg = Strict()
    await payments._choose_method(msg, 77, 20000, fsm(), "uz")
    button = msg.out[0][1].inline_keyboard[0][0] if msg.out else None
    check("Telegram ikonkani rad etsa — tugma ikonkasiz yuboriladi",
          button is not None and not button.icon_custom_emoji_id and button.url.startswith("https://my.click.uz/"),
          msg.out)
    config.CLICK_EMOJI_ID = ""

    from types import SimpleNamespace
    from bot.handlers import admin as admin_handlers
    entity = SimpleNamespace(type="custom_emoji", custom_emoji_id="123456")
    note = SimpleNamespace(entities=[entity], caption_entities=None)
    check("/emojiid maxsus emoji ID sini topadi", admin_handlers._custom_emoji_ids(note) == ["123456"])

    msg = Msg()
    await payments._show_card(msg, state, 20000, "uz", edit=True)
    check("«Karta orqali» → rekvizitlar va chek kutish",
          "Karta 1" in msg.out[0][0] and isinstance(msg.out[-1][1], ReplyKeyboardMarkup)
          and await state.get_state() == PaymentStates.waiting_for_screenshot.state
          and (await state.get_data())["payment_amount"] == 20000, msg.out)

    from services.receipts import web as receipt_web
    check("saytda Click usuli yoqiq", any(m["key"] == "click" and m["enabled"] for m in receipt_web.methods()))

    # Admin paneldagi «⚡ Click orqali to'lov» tugmasi
    db = dbmod.Database()
    check("sukut: admin tugmasi yoqiq", await click_pay.available())
    await db.set_feature_status(click_pay.FEATURE, False)
    check("admin o'chirsa Click mavjud emas", not await click_pay.available())
    check("admin o'chirsa ham Prepare/Complete ishlaydi (kalitlar bor)", click_pay.enabled())
    check("admin o'chirsa saytda Click o'chiq",
          not any(m["key"] == "click" and m["enabled"] for m in receipt_web.methods(click_on=await click_pay.available())))
    msg, state = Msg(), fsm()
    await payments._choose_method(msg, 77, 20000, state, "uz")
    check("admin o'chirsa botda darhol karta ko'rsatmasi",
          len(msg.out) == 1 and "Karta 1" in msg.out[0][0]
          and await state.get_state() == PaymentStates.waiting_for_screenshot.state, msg.out)
    from bot.keyboards import get_feature_management_keyboard as fkb
    btns = [b for row in fkb(True, click_enabled=False).inline_keyboard for b in row]
    check("adminda Click tugmasi «o'chirilgan» va yoqish callback'i",
          any(b.callback_data == "toggle_click_pay_on" and "O'chirilgan" in b.text for b in btns))
    await db.set_feature_status(click_pay.FEATURE, True)
    check("admin qayta yoqsa Click mavjud", await click_pay.available())
    config.CLICK_SECRET_KEY = ""
    check("kalit bo'lmasa Click o'chiq", not click_pay.enabled()
          and not any(m["key"] == "click" and m["enabled"] for m in receipt_web.methods()))
    msg, state = Msg(), fsm()
    await payments._choose_method(msg, 77, 20000, state, "uz")
    check("kalit bo'lmasa usul so'ralmaydi — darhol karta ko'rsatmasi",
          len(msg.out) == 1 and "Karta 1" in msg.out[0][0]
          and await state.get_state() == PaymentStates.waiting_for_screenshot.state, msg.out)


asyncio.run(main())
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
