"""Uzum Bank Merchant API orqali balansni to'ldirish (Uzum qo'lda sinov ssenariylari).

- avtorizatsiya (Basic login:parol) va serviceId: 10001, 10006; noma'lum amal 10003, JSON xato 10002;
- /check: mijoz Telegram ID bo'yicha, topilmasa 10007; params qiymati oddiy yoki {"value": ...};
- /create: summa tiyinda, chegaralar (10011-10013), takroriy transId → 10010;
- /confirm: balans bir marta, takroriy → 10016, balans qo'shilmasa CREATED holatga qaytadi; 30 daqiqa → 10015;
- /reverse: CREATED va CONFIRMED (balansdan yechiladi), takroriy → 10018; /status;
- sinov rejimi (UZUM_TEST=1) balansga tegmaydi; haqiqiy oqim va HTTP manzil.

    python test_uzum.py
"""
import asyncio
import base64
import os
import sys
import tempfile

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
config.UZUM_SERVICE_ID, config.UZUM_LOGIN, config.UZUM_PASSWORD = "498611", "uzum", "maxfiy"
config.UZUM_ACCOUNT, config.UZUM_TEST = "user_id", False

from database import uzum_orders as orders
from database.database import Database, init_db
from services import uzum_pay


def auth(login="uzum", password="maxfiy"):
    return "Basic " + base64.b64encode(f"{login}:{password}".encode()).decode()


async def call(action, header=None, **fields):
    body = {"serviceId": 498611, "timestamp": orders.now_ms(), **fields}
    return await uzum_pay.handle(action, body, auth() if header is None else header)


def err(r):
    return r[0] == 400 and r[1].get("status") == "FAILED" and r[1].get("errorCode")


credited = []


async def fake_credit(tx):
    credited.append(tx["trans_id"])
    return 500 + len(credited)


async def main():
    await init_db()
    import webapp

    sent = []

    class Bot:
        async def send_message(self, chat_id, text, **kw):
            sent.append((chat_id, text))

    webapp.BOT = Bot()
    user = await Database.create_user(77, "u77", "Ali", "uz")
    acc = {"user_id": "77"}

    print("1) Avtorizatsiya va so'rov")
    check("sozlangan bo'lsa yoqiq", uzum_pay.enabled())
    check("noto'g'ri parol → 10001", err(await call("check", auth(password="x"), params=acc)) == "10001")
    check("noto'g'ri login → 10001", err(await call("check", auth(login="x"), params=acc)) == "10001")
    check("sarlavhasiz → 10001", err(await call("check", "", params=acc)) == "10001")
    check("noma'lum amal → 10003", err(await call("pay", params=acc)) == "10003")
    check("JSON xato → 10002", err(await uzum_pay.handle("check", None, auth())) == "10002")
    r = await uzum_pay.handle("check", {"serviceId": 1, "timestamp": 1, "params": acc}, auth())
    check("boshqa serviceId → 10006", err(r) == "10006", r)
    r = await uzum_pay.handle("check", {"serviceId": 498611, "params": acc}, auth())
    check("timestamp yo'q → 10005", err(r) == "10005", r)

    print("\n2) /check")
    r = await call("check", params=acc)
    check("mijoz topildi → OK, account va fio", r[0] == 200 and r[1]["status"] == "OK"
          and r[1]["data"] == {"account": {"value": "77"}, "fio": {"value": "Ali"}} and r[1]["serviceId"] == 498611, r)
    r = await call("check", params={"user_id": {"value": 77}})
    check("{\"value\": ...} ko'rinishi ham", r[0] == 200, r)
    check("mijoz yo'q → 10007", err(await call("check", params={"user_id": "999"})) == "10007")
    check("ID raqam emas → 10007", err(await call("check", params={"user_id": "abc"})) == "10007")
    check("params yo'q → 10005", err(await call("check")) == "10005")
    check("boshqa maydon → 10005", err(await call("check", params={"order_id": "77"})) == "10005")

    print("\n3) /create")
    for amount, code in ((50000, "10012"), (600_000_000, "10013"), (1500050, "10011"), ("abc", "10011")):
        check(f"summa {amount} → {code}", err(await call("create", transId="t0", params=acc, amount=amount)) == code)
    check("mijoz yo'q → 10007",
          err(await call("create", transId="t0", params={"user_id": "999"}, amount=1500000)) == "10007")
    r = await call("create", transId="t1", params=acc, amount=1500000)
    check("yangi → CREATED, transTime, summa, data'siz", r[0] == 200 and r[1]["status"] == "CREATED" and r[1]["transTime"] > 0
          and "data" not in r[1]
          and r[1]["amount"] == 1500000 and r[1]["transId"] == "t1", r)
    r = await call("create", transId="t1", params=acc, amount=1500000)
    check("takroriy transId → 10010", err(r) == "10010" and r[1].get("transId") == "t1", r)
    r = await call("status", transId="t1")
    check("/status: CREATED", r[0] == 200 and r[1]["status"] == "CREATED" and r[1]["confirmTime"] is None, r)
    check("/status data = /check data", r[1]["data"] == (await call("check", params=acc))[1]["data"]
          == {"account": {"value": "77"}, "fio": {"value": "Ali"}}, r)
    check("/status: yo'q → 10014", err(await call("status", transId="yoq")) == "10014")

    print("\n4) /confirm")
    original = uzum_pay._credit
    check("yo'q → 10014", err(await call("confirm", transId="yoq", paymentSource="UZCARD", phone="998")) == "10014")

    async def broken(tx):
        raise RuntimeError("baza band")

    uzum_pay._credit = broken
    r = await call("confirm", transId="t1", paymentSource="UZCARD", phone="998901234567")
    tx = await orders.get_tx("t1")
    check("balans qo'shilmasa → 99999, CREATED holatda qoladi", err(r) == "99999" and tx["state"] == "CREATED", (r, tx))
    uzum_pay._credit = fake_credit
    r = await call("confirm", transId="t1", paymentSource="UZCARD", phone="998901234567")
    check("→ CONFIRMED, balans bir marta, data'siz", r[0] == 200 and r[1]["status"] == "CONFIRMED" and r[1]["confirmTime"] > 0
          and "data" not in r[1]
          and credited == ["t1"], r)
    r = await call("confirm", transId="t1", paymentSource="UZCARD", phone="998901234567")
    check("takroriy → 10016, qayta qo'shilmaydi", err(r) == "10016" and credited == ["t1"], r)
    tx = await orders.get_tx("t1")
    check("to'lov ID, manba va telefon saqlandi", tx["payment_id"] == 501 and tx["payment_source"] == "UZCARD"
          and tx["phone"] == "998901234567", tx)
    r = await call("status", transId="t1")
    check("/status: CONFIRMED", r[1]["status"] == "CONFIRMED" and r[1]["confirmTime"] > 0, r)

    print("\n5) /reverse va muddat")
    await call("create", transId="t2", params=acc, amount=2000000)
    r = await call("reverse", transId="t2")
    check("CREATED → REVERSED, data'siz", r[0] == 200 and r[1]["status"] == "REVERSED" and r[1]["reverseTime"] > 0
          and "data" not in r[1], r)
    check("takroriy → 10018", err(await call("reverse", transId="t2")) == "10018")
    check("bekor qilinganni confirm → 10015",
          err(await call("confirm", transId="t2", paymentSource="HUMO", phone="998")) == "10015")
    check("yo'q → 10014", err(await call("reverse", transId="yoq")) == "10014")
    await call("create", transId="t3", params=acc, amount=1000000)
    await orders._write("UPDATE uzum_transactions SET create_time = create_time - ? WHERE trans_id = ?",
                        (uzum_pay.TIMEOUT_MS + 1000, "t3"))
    r = await call("confirm", transId="t3", paymentSource="HUMO", phone="998")
    tx = await orders.get_tx("t3")
    check("30 daqiqadan keyin confirm → 10015, REVERSED", err(r) == "10015" and tx["state"] == "REVERSED", (r, tx))
    uzum_pay._credit = original

    print("\n6) Haqiqiy oqim va tasdiqlangandan keyin bekor qilish")
    await call("create", transId="t4", params=acc, amount=2500000)
    r = await call("confirm", transId="t4", paymentSource="UZCARD", phone="998")
    fresh = await Database.get_user(77)
    tx = await orders.get_tx("t4")
    payment = await Database.get_payment_by_id(tx["payment_id"] or 0)
    check("balans 25 000 ga oshdi", r[0] == 200 and fresh.balance - user.balance == 25000, (r, fresh.balance))
    check("to'lov yozuvi: uzum, approved", payment is not None and payment.source == "uzum"
          and payment.status == "approved", payment)
    check("mijoz va adminlarga xabar", any(c == 77 and "Uzum" in t for c, t in sent), sent)
    r = await call("reverse", transId="t4")
    after = await Database.get_user(77)
    payment = await Database.get_payment_by_id(tx["payment_id"])
    check("CONFIRMED → REVERSED, balans qaytdi, to'lov rad etilgan", r[0] == 200 and after.balance == user.balance
          and payment.status == "rejected", (r, after.balance, payment.status))

    print("\n7) Sinov rejimi")
    config.UZUM_TEST = True
    before = (await Database.get_user(77)).balance
    await call("create", transId="t5", params=acc, amount=3000000)
    r = await call("confirm", transId="t5", paymentSource="UZCARD", phone="998")
    check("sinovda CONFIRMED, balans o'zgarmaydi", r[0] == 200 and r[1]["status"] == "CONFIRMED"
          and (await Database.get_user(77)).balance == before, r)
    r = await call("reverse", transId="t5")
    check("sinovda reverse balansga tegmaydi", r[0] == 200 and (await Database.get_user(77)).balance == before, r)
    config.UZUM_TEST = False

    print("\n8) Deeplink va tugmalar")
    from urllib.parse import parse_qs, urlparse
    url = await uzum_pay.new_payment(77, 15000, "bot")
    q = parse_qs(urlparse(url).query)
    check("deeplink: uzumbank.uz/open-service, serviceId, user_id, summa tiyinda",
          url.startswith("https://uzumbank.uz/open-service?") and q == {"serviceId": ["498611"], "user_id": ["77"],
                                                                    "amount": ["1500000"]}, url)
    for bad in (500, "abc", 10_000_000):
        try:
            await uzum_pay.new_payment(77, bad, "bot")
            check(f"noto'g'ri summa rad etiladi ({bad})", False)
        except ValueError:
            check(f"noto'g'ri summa rad etiladi ({bad})", True)
    check("ishlab chiqarish rejimida tugma mavjud", await uzum_pay.available())
    config.UZUM_TEST = True
    check("sinov rejimida tugma yo'q", not await uzum_pay.available())
    config.UZUM_TEST = False
    db = dbmod.Database()
    await db.set_feature_status(uzum_pay.FEATURE, False)
    check("admin o'chirsa tugma yo'q, webhook ishlaydi", not await uzum_pay.available() and uzum_pay.enabled())
    await db.set_feature_status(uzum_pay.FEATURE, True)

    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage
    from bot.handlers import payments
    from services.receipts import web as receipt_web

    class Msg:
        def __init__(self):
            self.out = []

        async def answer(self, text, **kw):
            self.out.append((text, kw.get("reply_markup")))

        async def edit_text(self, text, **kw):
            self.out.append((text, kw.get("reply_markup")))

    msg = Msg()
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=77, user_id=77))
    await payments._choose_method(msg, 77, 20000, state, "uz")
    rows = msg.out[0][1].inline_keyboard
    check("botda: Uzum Bank tugmasi deeplink bilan va «Karta orqali»",
          len(rows) == 2 and rows[0][0].url.startswith("https://uzumbank.uz/open-service?")
          and "amount=2000000" in rows[0][0].url and "Uzum" in rows[0][0].text
          and rows[1][0].callback_data == "pay_by_card:20000" and "Uzum Bank" in msg.out[0][0], msg.out)
    check("saytda Uzum usuli yoqiq", any(m["key"] == "uzum" and m["enabled"] for m in receipt_web.methods()))
    from bot.keyboards import get_feature_management_keyboard as fkb
    btns = [b for row in fkb(True, uzum_enabled=False).inline_keyboard for b in row]
    check("adminda Uzum tugmasi", any(b.callback_data == "toggle_uzum_pay_on" for b in btns))

    print("\n9) HTTP manzil")
    from aiohttp.test_utils import TestClient, TestServer
    from webapp.server import create_web_app

    async with TestClient(TestServer(create_web_app())) as client:
        resp = await client.post("/uzum/webhook/check", json={"serviceId": 498611, "timestamp": 1, "params": acc},
                                 headers={"Authorization": auth()})
        data = await resp.json()
        check("POST /uzum/webhook/check → 200 OK", resp.status == 200 and data["status"] == "OK", data)
        resp = await client.post("/uzum/webhook/check", json={"serviceId": 498611, "timestamp": 1, "params": acc})
        data = await resp.json()
        check("avtorizatsiyasiz → HTTP 400, 10001", resp.status == 400 and data["errorCode"] == "10001", data)
        resp = await client.post("/uzum/webhook/status", data="{buzuq", headers={"Authorization": auth()})
        data = await resp.json()
        check("buzuq JSON → HTTP 400, 10002", resp.status == 400 and data["errorCode"] == "10002", data)
        resp = await client.post("/api/v1/wallet/uzum", json={"amount": 15000})
        check("sayt: kirishsiz /wallet/uzum → 401", resp.status == 401, resp.status)


asyncio.run(main())
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
