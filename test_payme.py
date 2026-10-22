"""Payme Merchant API orqali balansni to'ldirish (Payme «Песочница» ssenariylari).

- havola: checkout.paycom.uz / test.paycom.uz, base64 ichida merchant, order_id, summa tiyinda;
- avtorizatsiya: noto'g'ri kalit, test kaliti ishlab chiqarishda → -32504; ChangePassword;
- CheckPerformTransaction: summa (-31001), buyurtma yo'q (-31050), band (-31051), to'langan (-31052);
- CreateTransaction / PerformTransaction / CancelTransaction / CheckTransaction / GetStatement;
- takroriy so'rovlar balansni ikki marta qo'shmaydi; 12 soatlik muddat; yakunlangandan keyin bekor qilish;
- haqiqiy oqim: to'lov yozuvi (source=payme, approved), balans, mijozga xabar; HTTP manzili; bot tugmalari.

    python test_payme.py
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
config.CLICK_SERVICE_ID = config.CLICK_MERCHANT_ID = config.CLICK_SECRET_KEY = ""
config.PAYME_MERCHANT_ID, config.PAYME_KEY, config.PAYME_TEST_KEY = "65f0aa11", "jangovar", "sinov"
config.PAYME_TEST, config.PAYME_ACCOUNT, config.PAYME_RETURN_URL = True, "order_id", ""

from database import payme_orders as orders
from database.database import Database, init_db
from services import payme_pay


def auth(key="sinov", login="Paycom"):
    return "Basic " + base64.b64encode(f"{login}:{key}".encode()).decode()


async def rpc(method, key="sinov", **params):
    return await payme_pay.handle({"jsonrpc": "2.0", "id": 7, "method": method, "params": params}, auth(key))


def code(r):
    return (r.get("error") or {}).get("code")


credited = []


async def fake_credit(order):
    credited.append(order["id"])
    return 900 + order["id"]


async def main():
    await init_db()
    T = orders.now_ms()

    print("1) Havola")
    check("kalitlar bo'lsa Payme yoqiq", payme_pay.enabled())
    url = await payme_pay.new_payment(42, 15000, "bot", return_url="https://t.me/bot")
    check("test rejimida test.paycom.uz", url.startswith("https://test.paycom.uz/"), url)
    raw = base64.b64decode(url.rsplit("/", 1)[1]).decode()
    fields = dict(part.split("=", 1) for part in raw.split(";"))
    check("havolada merchant, order_id, summa tiyinda, qaytish",
          fields["m"] == "65f0aa11" and fields["ac.order_id"].isdigit() and fields["a"] == "1500000"
          and fields["c"] == "https://t.me/bot", raw)
    order = int(fields["ac.order_id"])
    for bad in (500, "abc", 10_000_000):
        try:
            await payme_pay.new_payment(42, bad, "bot")
            check(f"noto'g'ri summa rad etiladi ({bad})", False)
        except ValueError:
            check(f"noto'g'ri summa rad etiladi ({bad})", True)

    print("\n2) Avtorizatsiya va so'rov")
    r = await rpc("CheckPerformTransaction", key="boshqa", amount=1500000, account={"order_id": str(order)})
    check("noto'g'ri kalit → -32504", code(r) == -32504, r)
    r = await payme_pay.handle({"method": "CheckTransaction", "params": {}}, "")
    check("kalitsiz → -32504", code(r) == -32504, r)
    r = await rpc("CheckPerformTransaction", key="jangovar", amount=1500000, account={"order_id": str(order)})
    check("test rejimida jangovar kalit qabul qilinmaydi", code(r) == -32504, r)
    r = await payme_pay.handle(None, auth())
    check("JSON xato → -32700", code(r) == -32700, r)
    r = await rpc("Nimadir")
    check("noma'lum usul → -32601", code(r) == -32601, r)
    check("xato xabari uch tilda", set(r["error"]["message"]) == {"ru", "uz", "en"}, r)
    r = await rpc("ChangePassword", password="yangi1")
    check("ChangePassword → success", r.get("result") == {"success": True}, r)
    r = await rpc("CheckPerformTransaction", key="sinov", amount=1500000, account={"order_id": str(order)})
    check("eski kalit endi → -32504", code(r) == -32504, r)
    r = await rpc("ChangePassword", key="yangi1", password="yangi2")
    check("yangi kalit bilan yana almashtirish → success", r.get("result") == {"success": True}, r)
    r = await rpc("CheckPerformTransaction", key="yangi1", amount=1500000, account={"order_id": str(order)})
    check("oldingi yangi kalit ham → -32504", code(r) == -32504, r)
    r = await rpc("ChangePassword", key="yangi2", password="")
    check("bo'sh parol → -32600", code(r) == -32600, r)
    config.PAYME_TEST_KEY = "sinov-env"
    r = await rpc("CheckPerformTransaction", key="sinov-env", amount=1500000, account={"order_id": str(order)})
    check(".env qo'lda yangilansa — .env kaliti ishlaydi", code(r) != -32504, r)
    r = await rpc("CheckPerformTransaction", key="yangi2", amount=1500000, account={"order_id": str(order)})
    check(".env yangilangach saqlangan kalit eskirgan", code(r) == -32504, r)
    config.PAYME_TEST_KEY = "sinov"
    await orders.set_key("test", "sinov", "sinov")      # keyingi tekshiruvlar uchun asl kalit

    print("\n3) CheckPerformTransaction")
    r = await rpc("CheckPerformTransaction", amount=1400000, account={"order_id": str(order)})
    check("summa boshqa → -31001", code(r) == -31001, r)
    r = await rpc("CheckPerformTransaction", amount="1500000", account={"order_id": str(order)})
    check("summa matn → -31001", code(r) == -31001, r)
    r = await rpc("CheckPerformTransaction", amount=1500000, account={"order_id": "999999"})
    check("buyurtma yo'q → -31050", code(r) == -31050 and r["error"]["data"] == "order_id", r)
    r = await rpc("CheckPerformTransaction", amount=1500000, account={"order_id": "abc"})
    check("buyurtma raqami noto'g'ri → -31050", code(r) == -31050, r)
    r = await rpc("CheckPerformTransaction", amount=1500000, account={"order_id": str(order)})
    check("to'g'ri → allow", r.get("result") == {"allow": True} and r["id"] == 7, r)

    print("\n4) CreateTransaction")
    r = await rpc("CreateTransaction", id="tx-a", time=T, amount=1500000, account={"order_id": str(order)})
    res = r.get("result") or {}
    check("yangi tranzaksiya → state 1", res.get("state") == 1 and res.get("transaction") and res.get("create_time"), r)
    r2 = await rpc("CreateTransaction", id="tx-a", time=T, amount=1500000, account={"order_id": str(order)})
    check("takroriy Create → o'sha javob", r2.get("result") == res, r2)
    r = await rpc("CreateTransaction", id="tx-b", time=T, amount=1500000, account={"order_id": str(order)})
    check("buyurtmada boshqa faol tranzaksiya → -31051", code(r) == -31051, r)
    r = await rpc("CheckPerformTransaction", amount=1500000, account={"order_id": str(order)})
    check("band buyurtmaga Check → -31051", code(r) == -31051, r)
    r = await rpc("CheckTransaction", id="tx-a")
    check("CheckTransaction: state 1, vaqtlar", r["result"]["state"] == 1 and r["result"]["perform_time"] == 0
          and r["result"]["reason"] is None, r)

    print("\n5) PerformTransaction")
    r = await rpc("PerformTransaction", id="yoq")
    check("tranzaksiya yo'q → -31003", code(r) == -31003, r)
    original = payme_pay._credit
    payme_pay._credit = fake_credit

    async def broken(o):
        raise RuntimeError("baza band")

    payme_pay._credit = broken
    r = await rpc("PerformTransaction", id="tx-a")
    tx = await orders.get_tx("tx-a")
    check("balans qo'shilmasa → -31008, tranzaksiya 1 holatda qoladi", code(r) == -31008 and tx["state"] == 1, (r, tx))
    payme_pay._credit = fake_credit
    r = await rpc("PerformTransaction", id="tx-a")
    check("Perform → state 2, balans bir marta", r["result"]["state"] == 2 and r["result"]["perform_time"] > 0
          and credited == [order], r)
    r2 = await rpc("PerformTransaction", id="tx-a")
    check("takroriy Perform → o'sha javob, balans qayta qo'shilmaydi", r2.get("result") == r["result"]
          and credited == [order], r2)
    r = await rpc("CheckPerformTransaction", amount=1500000, account={"order_id": str(order)})
    check("to'langan buyurtmaga Check → -31052", code(r) == -31052, r)
    r = await rpc("CreateTransaction", id="tx-c", time=T, amount=1500000, account={"order_id": str(order)})
    check("to'langan buyurtmaga Create → -31052", code(r) == -31052, r)
    r = await rpc("CreateTransaction", id="tx-a", time=T, amount=1500000, account={"order_id": str(order)})
    check("yakunlangan tranzaksiyaga Create → -31008", code(r) == -31008, r)

    print("\n6) CancelTransaction")
    order2 = await orders.create_order(42, 20000, "web")
    await rpc("CreateTransaction", id="tx-d", time=T, amount=2000000, account={"order_id": str(order2)})
    r = await rpc("CancelTransaction", id="tx-d", reason=3)
    check("yakunlanmagan → -1", r["result"]["state"] == -1 and r["result"]["cancel_time"] > 0, r)
    r2 = await rpc("CancelTransaction", id="tx-d", reason=3)
    check("takroriy Cancel → o'sha javob", r2.get("result") == r["result"], r2)
    r = await rpc("PerformTransaction", id="tx-d")
    check("bekor qilinganni Perform → -31008", code(r) == -31008, r)
    r = await rpc("CheckTransaction", id="tx-d")
    check("CheckTransaction: -1, sabab 3", r["result"]["state"] == -1 and r["result"]["reason"] == 3, r)
    r = await rpc("CheckPerformTransaction", amount=2000000, account={"order_id": str(order2)})
    check("bekor qilingan buyurtma → -31052", code(r) == -31052, r)

    print("\n7) 12 soatlik muddat")
    order3 = await orders.create_order(42, 10000, "web")
    await rpc("CreateTransaction", id="tx-e", time=T, amount=1000000, account={"order_id": str(order3)})
    await orders._write("UPDATE payme_transactions SET create_time = create_time - ? WHERE payme_id = ?",
                        (payme_pay.TIMEOUT_MS + 1000, "tx-e"))
    r = await rpc("PerformTransaction", id="tx-e")
    tx = await orders.get_tx("tx-e")
    check("muddati o'tgan → -31008, bekor (sabab 4)", code(r) == -31008 and tx["state"] == -1 and tx["reason"] == 4,
          (r, tx))
    payme_pay._credit = original

    print("\n8) Haqiqiy oqim va yakunlangandan keyin bekor qilish")
    import webapp

    sent = []

    class Bot:
        async def send_message(self, chat_id, text, **kw):
            sent.append((chat_id, text))

    webapp.BOT = Bot()
    user = await Database.create_user(77, "u77", "U77", "uz")
    order4 = await orders.create_order(77, 25000, "bot")
    await rpc("CreateTransaction", id="tx-f", time=T, amount=2500000, account={"order_id": str(order4)})
    r = await rpc("PerformTransaction", id="tx-f")
    fresh = await Database.get_user(77)
    tx = await orders.get_tx("tx-f")
    payment = await Database.get_payment_by_id(tx["payment_id"] or 0)
    check("balans 25 000 ga oshdi", r["result"]["state"] == 2 and fresh.balance - user.balance == 25000,
          (r, user.balance, fresh.balance))
    check("to'lov yozuvi: payme, approved", payment is not None and payment.source == "payme"
          and payment.status == "approved" and payment.amount == 25000, payment)
    check("mijozga Payme xabari", any(chat == 77 and "Payme" in text for chat, text in sent), sent)
    r = await rpc("CancelTransaction", id="tx-f", reason=5)
    after = await Database.get_user(77)
    payment = await Database.get_payment_by_id(tx["payment_id"])
    check("yakunlanganni bekor qilish → -2, balansdan yechildi", r["result"]["state"] == -2
          and after.balance == user.balance and payment.status == "rejected", (r, after.balance))
    r2 = await rpc("CancelTransaction", id="tx-f", reason=5)
    check("takroriy Cancel balansni qayta yechmaydi", r2.get("result") == r["result"]
          and (await Database.get_user(77)).balance == after.balance, r2)

    order5 = await orders.create_order(77, 30000, "bot")
    await rpc("CreateTransaction", id="tx-g", time=T, amount=3000000, account={"order_id": str(order5)})
    await rpc("PerformTransaction", id="tx-g")
    await Database.charge_balance(77, (await Database.get_user(77)).balance)       # mijoz hammasini sarfladi
    r = await rpc("CancelTransaction", id="tx-g", reason=5)
    check("pul sarflangan bo'lsa ham bekor → -2, balans manfiy", r.get("result", {}).get("state") == -2
          and (await Database.get_user(77)).balance == -30000, r)
    r = await rpc("CheckTransaction", id="tx-g")
    check("CheckTransaction: -2, sabab 5, cancel_time", r["result"]["state"] == -2 and r["result"]["reason"] == 5
          and r["result"]["cancel_time"] > 0, r)
    r2 = await rpc("CancelTransaction", id="tx-g", reason=5)
    check("takroriy Cancel balansni qayta yechmaydi", r2["result"]["state"] == -2
          and (await Database.get_user(77)).balance == -30000, r2)

    print("\n9) GetStatement")
    r = await rpc("GetStatement", **{"from": T - 1000, "to": T + 1000})
    txs = r["result"]["transactions"]
    check("oraliqdagi tranzaksiyalar", {t["id"] for t in txs} == {"tx-a", "tx-d", "tx-e", "tx-f", "tx-g"}
          and all(t["account"]["order_id"] for t in txs), txs)
    r = await rpc("GetStatement", **{"from": T + 5000, "to": T + 9000})
    check("bo'sh oraliq", r["result"]["transactions"] == [], r)

    print("\n10) HTTP manzili")
    from aiohttp.test_utils import TestClient, TestServer
    from webapp.server import create_web_app

    order6 = await orders.create_order(77, 12000, "web")
    async with TestClient(TestServer(create_web_app())) as client:
        body = {"jsonrpc": "2.0", "id": 1, "method": "CheckPerformTransaction",
                "params": {"amount": 1200000, "account": {"order_id": str(order6)}}}
        resp = await client.post("/payme", json=body, headers={"Authorization": auth()})
        data = await resp.json()
        check("/payme → 200, allow", resp.status == 200 and data.get("result") == {"allow": True}, data)
        resp = await client.post("/payme", json=body)
        data = await resp.json()
        check("/payme kalitsiz → 200, -32504", resp.status == 200 and code(data) == -32504, data)
        resp = await client.post("/payme", data="{buzuq", headers={"Authorization": auth()})
        data = await resp.json()
        check("/payme buzuq JSON → -32700", code(data) == -32700, data)
        resp = await client.post("/api/v1/wallet/payme", json={"amount": 10000})
        check("sayt Payme havolasi kirishsiz berilmaydi", resp.status == 401, resp.status)

    print("\n11) Bot va sayt")
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage
    from bot.handlers import payments
    from bot.states import PaymentStates
    from services.receipts import web as receipt_web

    class Msg:
        def __init__(self):
            self.out = []

        async def answer(self, text, **kw):
            self.out.append((text, kw.get("reply_markup")))

        async def edit_text(self, text, **kw):
            self.out.append((text, kw.get("reply_markup")))

    def fsm():
        return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=77, user_id=77))

    msg = Msg()
    await payments._choose_method(msg, 77, 20000, fsm(), "uz", edit=True)
    rows = msg.out[0][1].inline_keyboard if msg.out else []
    check("faqat Payme ulangan: Payme va «Karta orqali»",
          len(rows) == 2 and rows[0][0].url.startswith("https://test.paycom.uz/")
          and rows[1][0].callback_data == "pay_by_card:20000" and "Payme" in msg.out[0][0]
          and "Click" not in msg.out[0][0], msg.out)

    config.CLICK_SERVICE_ID, config.CLICK_MERCHANT_ID, config.CLICK_SECRET_KEY = "111", "222", "sir"
    msg = Msg()
    await payments._choose_method(msg, 77, 20000, fsm(), "ru")
    rows = msg.out[0][1].inline_keyboard
    check("ikkalasi ulangan: Click, Payme, Karta", len(rows) == 3 and "my.click.uz" in rows[0][0].url
          and "paycom.uz" in rows[1][0].url and "Payme" in rows[1][0].text, rows)
    config.CLICK_SERVICE_ID = config.CLICK_MERCHANT_ID = config.CLICK_SECRET_KEY = ""

    check("saytda Payme usuli yoqiq", any(m["key"] == "payme" and m["enabled"] for m in receipt_web.methods()))
    db = dbmod.Database()
    await db.set_feature_status(payme_pay.FEATURE, False)
    check("admin o'chirsa Payme mavjud emas, /payme ishlaydi", not await payme_pay.available() and payme_pay.enabled())
    msg, state = Msg(), fsm()
    await payments._choose_method(msg, 77, 20000, state, "uz")
    check("admin o'chirsa botda darhol karta ko'rsatmasi", "Karta 1" in msg.out[0][0]
          and await state.get_state() == PaymentStates.waiting_for_screenshot.state, msg.out)
    from bot.keyboards import get_feature_management_keyboard as fkb
    btns = [b for row in fkb(True, payme_enabled=False).inline_keyboard for b in row]
    check("adminda Payme tugmasi va yoqish callback'i",
          any(b.callback_data == "toggle_payme_pay_on" and "O'chirilgan" in b.text for b in btns))
    await db.set_feature_status(payme_pay.FEATURE, True)

    config.PAYME_TEST = False
    url = await payme_pay.new_payment(42, 15000, "bot")
    check("ishlab chiqarishda checkout.paycom.uz", url.startswith("https://checkout.paycom.uz/"), url)
    r = await rpc("CheckTransaction", key="sinov", id="tx-a")
    check("ishlab chiqarishda test kaliti → -32504", code(r) == -32504, r)
    r = await rpc("CheckTransaction", key="jangovar", id="tx-a")
    check("ishlab chiqarishda jangovar kalit ishlaydi", r.get("result", {}).get("state") == 2, r)


asyncio.run(main())
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
