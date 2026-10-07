"""Chek tekshiruvining to'liq oqimi: haqiqiy baza (vaqtinchalik), soxta Telegram va soxta Claude.

    python test_chek_oqim.py
"""
import asyncio, os, sys, tempfile, types
from datetime import datetime, timedelta

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
from services.receipts import flow, reader, rules, store

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "test.db")
NOW = datetime(2026, 10, 6, 20, 10)
rules.now_tashkent = lambda: NOW
ADMIN = config.ADMIN_IDS[0]
config.RECEIPT_AUTO = True          # ixtiyoriy avto-tasdiq rejimi shu qismda sinaladi (sukut — qo'lda tasdiqlash)

# ── soxta Telegram
class Sent:
    def __init__(self, chat_id, text, kw, message_id):
        self.chat = types.SimpleNamespace(id=chat_id); self.message_id = message_id
        self.text, self.kw = text, kw
class FakeBot:
    def __init__(self):
        self.sent, self.copied, self.n = [], [], 1000
    async def send_message(self, chat_id, text, **kw):
        self.n += 1; item = Sent(chat_id, text, kw, self.n); self.sent.append(item); return item
    async def copy_message(self, chat_id, from_chat_id, message_id, **kw):
        self.copied.append((chat_id, from_chat_id, message_id, kw)); self.n += 1
        return types.SimpleNamespace(message_id=self.n)
class FakeMessage:
    counter = 0
    def __init__(self, bot, tg, data=b"x"):
        FakeMessage.counter += 1
        self.bot, self.chat, self.message_id = bot, types.SimpleNamespace(id=tg), FakeMessage.counter
        self.photo = [types.SimpleNamespace(file_id=f"f{FakeMessage.counter}", file_size=len(data))]
        self.document, self.answers, self.data = None, [], data
    async def answer(self, text, **kw):
        self.answers.append((text, kw))
        async def delete(): pass
        return types.SimpleNamespace(delete=delete)

# ── soxta Claude: navbat bo'yicha javob (birinchi o'qish, tasdiqlovchi o'qish)
QUEUE = []
def fake_call(kind, images, text, now):
    item = QUEUE.pop(0) if QUEUE else {}
    if isinstance(item, Exception): raise item
    return item
reader._call = fake_call
reader.prepare = lambda data, filename="", mime="": reader.Prepared(images=[b"img"], text="", meta_flags=[])

CURRENT_BYTES = {"v": b"A"}
async def fake_download(bot, file_id): return CURRENT_BYTES["v"]
flow._download = fake_download

def raw(amount=10_000, rid="5333277563", date=(10, 6, 20, 4), clock="20:04", battery=28, receiver="986016****6655",
        sender="986012******6989", name="FARXOD N.", **kw):
    base = {"doc_type": "transfer", "status": "success", "readable": True, "amount": amount, "fee": 110, "currency": "UZS",
            "date": {"year": 2026, "month": date[0], "day": date[1], "hour": date[2], "minute": date[3]},
            "ids": [rid] if rid else [], "sender_name": name, "sender_card": sender,
            "receiver_name": "JAVLONBEK M.", "receiver_card": receiver, "app": "click",
            "screenshot": {"is_screenshot": True, "clock": clock, "battery": battery}, "cropped": False,
            "tamper": "none", "confidence": 0.95}
    base.update(kw)
    return base

async def main():
    await init_db()
    users = {}
    for tg in (100, 200, 300):
        users[tg] = await Database.create_user(tg, f"user{tg}", f"U{tg}", "uz")
    bot = FakeBot()
    state = {"payment_amount": 10_000, "payment_started_at": (NOW - timedelta(minutes=15)).isoformat()}

    async def send(tg, data=b"A", claimed=10_000):
        CURRENT_BYTES["v"] = data
        msg = FakeMessage(bot, tg, data)
        out = await flow.process(msg, {**state, "payment_amount": claimed}, Database, users[tg], "uz", keyboard="KB")
        return out, msg

    async def balance(tg):
        return (await Database.get_user(tg)).balance

    print("1) Yaxshi chek avtomatik tasdiqlanadi")
    QUEUE[:] = [raw(), raw()]
    out, msg = await send(100, b"A")
    check("avto-tasdiq", out and out.verdict == rules.AUTO, out)
    check("pul hisobga qo'shildi", await balance(100) == 10_000, await balance(100))
    pay = await Database.get_payment_by_id(out.payment_id)
    check("to'lov 'approved'", pay.status == "approved" and pay.amount == 10_000)
    check("mijozga xabar va asosiy klaviatura", any("tasdiqlandi" in m.text and m.kw.get("reply_markup") == "KB" for m in bot.sent if m.chat.id == 100), [m.text for m in bot.sent])
    log = [m for m in bot.sent if m.chat.id == ADMIN]
    check("admin chatida chek nusxasi va ma'lumot kartasi qoldi", bot.copied and log and "AVTOMATIK TASDIQLANDI" in log[-1].text and "5333277563" in log[-1].text, log[-1].text if log else "")
    check("karta jim (bildirishnomasiz)", log[-1].kw.get("disable_notification") is True)
    check("chek va kalitlar bazada", (await store.get_receipt(out.receipt_id))["verdict"] == "auto")

    print("2) O'sha chekni mijozning o'zi yana yubordi (ikki marta bosdi)")
    QUEUE[:] = [raw()]
    out2, msg2 = await send(100, b"A")
    check("jazosiz «allaqachon qabul qilingan», pul ikki marta qo'shilmadi", out2.verdict == rules.OWN_PENDING and await balance(100) == 10_000, (out2.verdict, await balance(100)))
    check("mijozga tushuntirish", "qabul qilingan" in msg2.answers[-1][0])

    print("3) Boshqa mijoz o'sha chekni yubordi — takroriy/soxta")
    QUEUE[:] = [raw()]
    out3, msg3 = await send(200, b"A")
    check("takroriy deb topildi, pul qo'shilmadi", out3.verdict == rules.DUPLICATE and await balance(200) == 0, (out3.verdict, await balance(200)))
    last = msg3.answers[-1][0]
    check("mijoz ogohlantirildi va admin manzili berildi", "avval ishlatilgan" in last and config.ADMIN_CONTACT in last, last)
    check("adminga HECH NARSA bormadi (karta ham, tugma ham, fayl nusxasi ham)",
          not [m for m in bot.sent if m.chat.id == ADMIN and "TAKRORIY" in m.text] and not [c for c in bot.copied if c[3].get("disable_notification") is False] ,
          [m.text[:40] for m in bot.sent if m.chat.id == ADMIN])
    check("to'lov yozuvi yaratilmadi", out3.payment_id is None and len(await Database.get_pending_payments()) == 0)

    print("4) ID tahrirlangan chek (soat va batareya o'sha)")
    QUEUE[:] = [raw(rid="5333277999")]
    out4, msg4 = await send(200, b"B")
    check("ushlandi (summa+vaqt+yuboruvchi/skrinshot belgisi)", out4.verdict == rules.DUPLICATE, (out4.verdict, out4))

    print("5) Ko'p takroriy/soxta urinish — mijoz BLOKLANMAYDI, adminga ham bormaydi")
    admin_before = len([m for m in bot.sent if m.chat.id == ADMIN])
    for i in range(6):
        QUEUE[:] = [raw(rid="5333277111", date=(10, 6, 20, 4), clock="20:04", battery=28)]
        out5, msg5 = await send(200, b"C" + bytes([i]))
    check("6 ta takroriy urinishdan keyin ham bloklanmadi", not await Database.is_user_blocked(200))
    check("har safar oddiy rad javobi", out5.verdict == rules.DUPLICATE and "avval ishlatilgan" in msg5.answers[-1][0], (out5.verdict, msg5.answers[-1][0]))
    check("adminga hech narsa bormadi", len([m for m in bot.sent if m.chat.id == ADMIN]) == admin_before)
    check("«bloklandi» xabari yo'q", not [m for m in bot.sent if m.chat.id == 200 and "bloklandi" in m.text])

    print("6) Eski chek (3 kun) — admin, mijozga admin manzili")
    QUEUE[:] = [raw(rid="7000000001", date=(10, 3, 12, 0), clock=None, battery=None)]
    out6, msg6 = await send(300, b"D")
    check("admin tekshiradi, pul qo'shilmadi", out6.verdict == rules.REVIEW and await balance(300) == 0, (out6.verdict, await balance(300)))
    check("mijozga: chek eski + admin manzili", "eski" in msg6.answers[-1][0] and config.ADMIN_CONTACT in msg6.answers[-1][0], msg6.answers[-1][0])
    stale_cards = [m for m in bot.sent if m.chat.id == ADMIN and "TEKSHIRISH KERAK" in m.text and "Chek eski" in m.text]
    check("adminga karta tugmalar bilan", stale_cards and stale_cards[-1].kw.get("reply_markup") is not None)
    pay6 = await Database.get_payment_by_id(out6.payment_id)
    check("to'lov summasi chekdagi summa", pay6.amount == 10_000 and pay6.status == "pending")

    print("7) Soliq cheki — chek emas, qayta so'raladi")
    QUEUE[:] = [{"doc_type": "tax_receipt", "status": "success", "amount": 26, "readable": True}]
    n_payments = len(await Database.get_pending_payments())
    out7, msg7 = await send(300, b"E")
    check("to'lov yaratilmadi, holat saqlanadi (qayta yuboradi)", out7.verdict == rules.NOT_RECEIPT and not out7.clear_state
          and len(await Database.get_pending_payments()) == n_payments)
    check("mijozga tushuntirish", "to'lov cheki emas" in msg7.answers[-1][0])
    check("soliq cheki adminga bormadi", all(c[2] != msg7.message_id for c in bot.copied))

    print("7b) Faqat summa va brend — asl chek so'raladi, «Chekni qayta yuborish» tugmasi bilan")
    QUEUE[:] = [{"doc_type": "payment", "status": "success", "readable": True, "amount": 10000, "app": "click",
                 "screenshot": {"is_screenshot": True, "clock": "20:05", "battery": 90}}]
    out7b, msg7b = await send(300, b"E2")
    text7b, kw7b = msg7b.answers[-1]
    check("qabul qilinmadi, holat saqlanadi", out7b.verdict == rules.NOT_RECEIPT and not out7b.clear_state and await balance(300) == 0)
    check("mijozga: to'lov tarixidan asl chek so'raldi", "To'lov tarixidan" in text7b and "faqat summa" in text7b, text7b)
    markup = kw7b.get("reply_markup")
    button = markup.inline_keyboard[0][0] if markup else None
    check("«Chekni qayta yuborish» tugmasi bor", button and "qayta yuborish" in button.text and button.callback_data.startswith("rcpt_resend:10000:"), button)
    check("tugma ma'lumoti Telegram chegarasida (64 bayt)", button and len(button.callback_data.encode()) <= 64)
    for q in ({"doc_type": "tax_receipt", "readable": True}, {"doc_type": "other", "readable": True},
              {"doc_type": "transfer", "status": "failed", "readable": True}, {"doc_type": "transfer", "readable": False}):
        QUEUE[:] = [q]
        _, m_ = await send(300, b"E3")
        mk = m_.answers[-1][1].get("reply_markup")
        check(f"qayta so'rash tugmasi: {q.get('doc_type')}/{q.get('status', '')}", mk and mk.inline_keyboard[0][0].callback_data.startswith("rcpt_resend:"), m_.answers[-1])

    print("7c) Boshqa karta, tahrirlangan chek — adminga bormaydi")
    copied_before, sent_before = len(bot.copied), len([m for m in bot.sent if m.chat.id == ADMIN])
    QUEUE[:] = [raw(rid="6100000001", receiver="986016****1234", date=(10, 6, 19, 50), clock="19:50", battery=12)]
    out_w, msg_w = await send(300, b"W1")
    check("boshqa karta: adminga tekshirish uchun boradi (qaror odamda)", out_w.verdict == rules.WRONG_RECEIVER and out_w.payment_id is not None
          and "adminga yuborildi" in msg_w.answers[-1][0], (out_w.verdict, msg_w.answers[-1][0]))
    QUEUE[:] = [raw(rid="6100000002", date=(10, 6, 19, 48), clock="19:48", battery=13)]
    _old_prepare = reader.prepare
    reader.prepare = lambda data, filename="", mime="": reader.Prepared(images=[b"img"], meta_flags=["exif:Adobe Photoshop 25"])
    out_f, msg_f = await send(300, b"W2")
    reader.prepare = _old_prepare
    check("fayl izida Photoshop bor chek: RAD ETILMAYDI — adminga ogohlantirish bilan boradi",
          out_f.verdict == rules.REVIEW and out_f.payment_id is not None and "tahrirlangan" not in msg_f.answers[-1][0],
          (out_f.verdict, msg_f.answers[-1][0]))
    card = [m for m in bot.sent if m.chat.id == ADMIN][-1].text
    check("admin kartochkasida fayl belgisi ko'rsatilgan", "exif:Adobe Photoshop 25" in card and "metama'lumot" in card, card)
    check("ikkala cheki ham adminga bordi", len(bot.copied) == copied_before + 2 and len([m for m in bot.sent if m.chat.id == ADMIN]) == sent_before + 2)

    print("7d) Click «O'tkazma amalga oshirildi» ekrani: qabul qiluvchi telefon raqami, karta/ism/ID yo'q")
    config.RECEIPT_AUTO = False
    QUEUE[:] = [{"doc_type": "transfer", "status": "success", "readable": True, "amount": 5000, "currency": "UZS",
                 "date": {"year": None, "month": 10, "day": 6, "hour": 20, "minute": 5},
                 "ids": [], "sender_name": "", "sender_card": "", "receiver_name": "", "receiver_card": "99890*****58",
                 "app": "click", "screenshot": {"is_screenshot": True, "clock": "20:05", "battery": None},
                 "cropped": False, "tamper": "none", "confidence": 0.9}]
    a_before = len([m for m in bot.sent if m.chat.id == ADMIN])
    out_ph, msg_ph = await send(300, b"PH1", claimed=5000)
    config.RECEIPT_AUTO = True
    check("telefon raqami karta deb olinmadi — «boshqa karta» deb rad etilmadi", out_ph.verdict == rules.REVIEW, out_ph.verdict)
    card_ph = [m for m in bot.sent if m.chat.id == ADMIN][-1]
    check("adminga tugmalar bilan uzatildi", len([m for m in bot.sent if m.chat.id == ADMIN]) == a_before + 1 and card_ph.kw.get("reply_markup") is not None)
    check("kartada «qabul qiluvchi aniqlanmadi» ogohlantirishi", "Qabul qiluvchi aniqlanmadi" in card_ph.text, card_ph.text)

    print("8) Ikkinchi o'qish mos kelmasa — admin")
    QUEUE[:] = [raw(rid="8000000001", date=(10, 6, 20, 6), clock="20:06", battery=33), raw(rid="8000000001", amount=18_000, date=(10, 6, 20, 6), clock="20:06", battery=33)]
    out8, _ = await send(300, b"F")
    check("summa ikki o'qishda har xil — pul qo'shilmadi", out8.verdict == rules.REVIEW and await balance(300) == 0, (out8.verdict, await balance(300)))

    print("9) AI ishlamasa — avvalgi qo'lda tekshiruvga qaytadi")
    QUEUE[:] = [RuntimeError("tarmoq")]
    out9, _ = await send(300, b"G")
    check("None qaytdi (chaqiruvchi avvalgi oqimga o'tadi)", out9 is None)
    config.RECEIPT_AI = False
    out9b, _ = await send(300, b"G")
    check("RECEIPT_AI=0 bo'lsa ham None", out9b is None)
    config.RECEIPT_AI = True

    print("10) Summa farqi: chekdagi summa qo'shiladi")
    QUEUE[:] = [raw(amount=5_000, rid="9000000001", date=(10, 6, 20, 7), clock="20:07", battery=40)] * 2
    out10, msg10 = await send(300, b"H", claimed=10_000)
    check("5 000 qo'shildi, 10 000 emas", out10.verdict == rules.AUTO and await balance(300) == 5_000, (out10.verdict, await balance(300)))
    text10 = [m.text for m in bot.sent if m.chat.id == 300][-1]
    check("mijozga farq tushuntirildi", "5 000" in text10 and "10 000" in text10, text10)

    print("11) Bir vaqtda kelgan ikki bir xil chek (poyga) — pul faqat bir marta")
    u_a, u_b = users[100], users[300]
    QUEUE[:] = [raw(rid="9100000001", date=(10, 6, 20, 8), clock="20:08", battery=51)] * 4
    CURRENT_BYTES["v"] = b"R"
    ma, mb = FakeMessage(bot, 100, b"R"), FakeMessage(bot, 300, b"R")
    before_a, before_b = await balance(100), await balance(300)
    ra, rb = await asyncio.gather(
        flow.process(ma, {**state}, Database, users[100], "uz"),
        flow.process(mb, {**state}, Database, users[300], "uz"))
    gained = (await balance(100) - before_a) + (await balance(300) - before_b)
    check("jami faqat 10 000 qo'shildi", gained == 10_000, (gained, ra.verdict if ra else None, rb.verdict if rb else None))
    check("ikkinchisi takroriy deb belgilandi", sorted([ra.verdict, rb.verdict]) == [rules.AUTO, rules.DUPLICATE], (ra.verdict, rb.verdict))

    print("12) Tasdiqlangan kartochkada AI ma'lumoti qoladi")
    from bot.handlers.admin import decided_card_text
    entry = (await Database.get_payment_admin_messages(out6.payment_id))[0]
    fake_msg = types.SimpleNamespace(chat=types.SimpleNamespace(id=entry["chat"]), message_id=entry["msg"])
    result = await decided_card_text(out6.payment_id, fake_msg, "✅ @admin tasdiqladi", "QISQA")
    check("chek ma'lumoti + qaror", "Chek #" in result and "tasdiqladi" in result and "7000000001" in result, result[:200])
    plain = await Database.create_payment(users[100].id, 5000, "fx", "")
    check("oddiy to'lovda avvalgi qisqa matn", await decided_card_text(plain, fake_msg, "v", "QISQA") == "QISQA")

    print("13) Soya rejimi (RECEIPT_AUTO=0)")
    config.RECEIPT_AUTO = False
    QUEUE[:] = [raw(rid="9200000001", date=(10, 6, 20, 1), clock="20:01", battery=60)]
    b0 = await balance(300)
    out13, _ = await send(300, b"S")
    config.RECEIPT_AUTO = True
    check("hamma narsa joyida bo'lsa ham admin tasdiqlaydi", out13.verdict == rules.REVIEW and await balance(300) == b0, (out13, await balance(300), b0))
    check("soya/qo'lda rejimda karta adminga tugmalar bilan boradi", [m for m in bot.sent if m.chat.id == ADMIN][-1].kw.get("reply_markup") is not None)

    print("14) Admin o'zi sinab ko'rsa bloklanmaydi")
    admin_user = await Database.create_user(ADMIN, "adm", "Adm", "uz")
    users[ADMIN] = admin_user
    QUEUE[:] = [raw(rid="9300000001", date=(10, 6, 20, 5), clock="20:05", battery=70)] * 2
    await send(ADMIN, b"T")
    for i in range(4):
        QUEUE[:] = [raw(rid="9300000001", date=(10, 6, 20, 5), clock="20:05", battery=70)]
        await send(ADMIN, b"T" + bytes([i]))
    check("adminga blok qo'llanmaydi", not await Database.is_user_blocked(ADMIN))
    QUEUE[:] = [raw()]                       # 1-chek (mijoz 100 ishlatgan) — admin uchun takroriy
    _, admin_msg = await send(ADMIN, b"T9")
    check("admin sinab ko'rsa sababni ko'radi (oddiy mijoz ko'rmaydi)", "admin ko'rinishi" in admin_msg.answers[-1][0] and "ID avval ishlatilgan" in admin_msg.answers[-1][0], admin_msg.answers[-1][0])
    QUEUE[:] = [raw()]
    _, plain_msg = await send(300, b"T10")
    check("oddiy mijozda sabab ko'rinmaydi", "admin ko'rinishi" not in plain_msg.answers[-1][0])

    print("15) To'lov handleri: AI yo'li va avvalgi yo'lga qaytish")
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage
    from bot.handlers import payments as pay_handlers
    from bot.states import PaymentStates

    async def run_handler(tg, data, canned):
        QUEUE[:] = canned
        CURRENT_BYTES["v"] = data
        ctx_state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=tg, user_id=tg))
        await ctx_state.set_state(PaymentStates.waiting_for_screenshot)
        await ctx_state.update_data(**state)
        message = FakeMessage(bot, tg, data)
        await pay_handlers.handle_payment_screenshot(message, ctx_state, Database, "uz", users[tg])
        return ctx_state, message
    b = await balance(300)
    st, m = await run_handler(300, b"Z1", [raw(rid="9400000001", date=(10, 6, 19, 58), clock="19:58", battery=80)] * 2)
    check("handler: avto-tasdiq, holat tozalandi", await st.get_state() is None and await balance(300) == b + 10_000, (await st.get_state(), await balance(300) - b))
    st, m = await run_handler(300, b"Z2", [{"doc_type": "tax_receipt", "readable": True}])
    check("handler: soliq cheki — holat saqlanadi, mijoz qayta yuboradi", await st.get_state() == PaymentStates.waiting_for_screenshot.state)
    n_before = len(await Database.get_pending_payments())
    st, m = await run_handler(300, b"Z3", [RuntimeError("AI o'chgan")])
    check("handler: AI ishlamasa avvalgidek qo'lda tekshiruv (to'lov yaratildi, admin xabardor)",
          len(await Database.get_pending_payments()) == n_before + 1 and await st.get_state() is None
          and any("Yangi to'lov" in x.text for x in bot.sent if x.chat.id == ADMIN))

    print("19) Kunlik statistika: adminga yetmagan (rad etilgan) cheklar hisobi")
    from services.receipts import texts as receipt_texts
    import aiosqlite
    counts = await store.today_counts()
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        async with conn.execute("SELECT verdict, COUNT(*) FROM payment_receipts GROUP BY verdict") as cur:
            direct = {r[0]: r[1] for r in await cur.fetchall()}
    check("bugungi sonlar bazadagi cheklarga teng", counts == direct and counts.get("duplicate", 0) >= 7 and counts.get("not_receipt", 0) >= 5, (counts, direct))
    stats = receipt_texts.daily_stats_text({"review": 4, "wrong_receiver": 1, "auto": 2, "not_receipt": 3, "duplicate": 5, "fake": 1, "own_pending": 2})
    check("statistika matni: adminga yuborilgan 5, rad etilgan 11", "Adminga yuborilgan: 5 ta" in stats and "Adminga yetmagan (rad etilgan): 11 ta" in stats, stats)
    check("statistika matni: sabablar bo'yicha", all(x in stats for x in ("chek emas / bekorchi fayl: 3 ta", "takroriy: 5 ta", "tahrirlangan: 1 ta", "o'zi qayta yuborgan: 2 ta")), stats)
    check("avto-tasdiq qatori faqat bo'lsa chiqadi", "Avtomatik tasdiqlangan: 2 ta" in stats and "Avtomatik" not in receipt_texts.daily_stats_text({"review": 1}))
    check("bo'sh kun nol ko'rsatadi", "rad etilgan): 0 ta" in receipt_texts.daily_stats_text({}))

    print("20) Admin «Kunlik statistika» tugmasi cheklar blokini ko'rsatadi")
    from bot.handlers.admin import handle_daily_statistics
    stat_out = []
    class StatMsg:
        from_user = types.SimpleNamespace(id=ADMIN)
        async def answer(self, text, **kw): stat_out.append(text)
    await handle_daily_statistics(StatMsg(), Database)
    check("kunlik statistikada cheklar bloki bor", stat_out and "Bugungi cheklar (AI tekshiruvi)" in stat_out[0]
          and "Adminga yetmagan (rad etilgan)" in stat_out[0] and "Bugungi daromad" in stat_out[0], stat_out[:1])

    print("17) Reply-tugmalar («To'lov chekini yuborish», «Orqaga»)")
    up_state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=300, user_id=300))
    await up_state.set_state(PaymentStates.waiting_for_screenshot)
    out_msgs = []
    class BtnMsg:
        def __init__(self, text): self.text = text
        async def answer(self, text, **kw): out_msgs.append((text, kw))
    await pay_handlers.handle_upload_button(BtnMsg("📤 To'lov chekini yuborish"), up_state, "uz")
    check("«yuborish» tugmasi: chek so'raydi va holat saqlanadi", "Chekni yuboring" in out_msgs[-1][0] and await up_state.get_state() == PaymentStates.waiting_for_screenshot.state)
    await pay_handlers.handle_back_button(BtnMsg("🔙 Orqaga qaytish"), up_state, "uz")
    check("«orqaga» tugmasi: holat tozalandi, asosiy menyu va summa tanlash", await up_state.get_state() is None and len(out_msgs) >= 3 and "miqdorini tanlang" in out_msgs[-1][0], out_msgs[-1][0])
    router_src = [h for h in pay_handlers.router.message.handlers if h.callback.__name__ in ("handle_upload_button", "handle_back_button")]
    check("ikkala tugma handleri ro'yxatdan o'tgan", len(router_src) == 2)

    print("16) «Chekni qayta yuborish» tugmasi holatni tiklaydi")
    rs_state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=300, user_id=300))
    answers16 = []
    async def cb_answer(*a, **k): pass
    async def msg_answer(text, **k): answers16.append(text)
    epoch = int((NOW - timedelta(minutes=12)).replace(tzinfo=rules.TASHKENT).timestamp())
    callback = types.SimpleNamespace(data=f"rcpt_resend:15000:{epoch}", answer=cb_answer,
                                     message=types.SimpleNamespace(answer=msg_answer))
    await pay_handlers.handle_receipt_resend(callback, rs_state, "uz")
    data16 = await rs_state.get_data()
    check("holat: chek kutilmoqda", await rs_state.get_state() == PaymentStates.waiting_for_screenshot.state)
    check("summa va to'lov boshlangan vaqt tiklandi", data16.get("payment_amount") == 15000
          and data16.get("payment_started_at") == (NOW - timedelta(minutes=12)).isoformat(), data16)
    check("mijozga «chekni yuboring» deyildi", answers16 and "Chekni yuboring" in answers16[0], answers16)

    print("18) SUKUT REJIM: qo'lda tasdiqlash, bitta arzon o'qish")
    config.RECEIPT_AUTO = False
    reads = {"n": 0}
    _orig_call = reader._call
    def counting_call(kind, images, text, now):
        reads["n"] += 1
        return _orig_call(kind, images, text, now)
    reader._call = counting_call
    admin_before = len([m for m in bot.sent if m.chat.id == ADMIN]); copied_before = len(bot.copied)
    bal0 = await balance(100)
    QUEUE[:] = [raw(rid="6600000001", date=(10, 6, 20, 0), clock="20:00", battery=77)]
    reads["n"] = 0
    out_m, msg_m = await send(100, b"M1")
    check("haqiqiy chek adminga tugmalar bilan boradi, pul avtomatik qo'shilmadi", out_m.verdict == rules.REVIEW and await balance(100) == bal0
          and (await Database.get_payment_by_id(out_m.payment_id)).status == "pending", (out_m.verdict, await balance(100) - bal0))
    check("AI faqat BIR marta chaqirildi", reads["n"] == 1, reads["n"])
    card = [m for m in bot.sent if m.chat.id == ADMIN][-1]
    check("admin kartasi: tugmalar bor, avto-tasdiq shovqini yo'q", card.kw.get("reply_markup") is not None and "avto-tasdiq" not in card.text and "chegarasidan" not in card.text, card.text)
    check("mijozga avvalgi «adminga yuborildi» xabari", "adminga yuborildi" in msg_m.answers[-1][0] and msg_m.answers[-1][1].get("parse_mode") == "Markdown", msg_m.answers[-1])
    # bekorchi narsalar adminga bormaydi
    for junk in ({"doc_type": "other", "readable": True}, {"doc_type": "tax_receipt", "readable": True},
                 {"doc_type": "transfer", "status": "failed", "readable": True}):
        QUEUE[:] = [junk]
        a0, c0 = len([m for m in bot.sent if m.chat.id == ADMIN]), len(bot.copied)
        out_j, _ = await send(100, b"J" + bytes([len(str(junk))]))
        check(f"{junk['doc_type']}: adminga bormadi", out_j.verdict == rules.NOT_RECEIPT and len([m for m in bot.sent if m.chat.id == ADMIN]) == a0 and len(bot.copied) == c0)
    # aynan o'sha fayl: AI chaqirilmaydi (bepul)
    reads["n"] = 0
    QUEUE[:] = []
    out_d, msg_d = await send(200, b"M1")          # boshqa mijoz o'sha faylni yubordi
    check("takroriy fayl AI'siz aniqlandi (pul sarflanmadi)", reads["n"] == 0 and out_d.verdict == rules.DUPLICATE, (reads["n"], out_d.verdict))
    check("takroriy fayl adminga bormadi", len([m for m in bot.sent if m.chat.id == ADMIN]) == len([m for m in bot.sent if m.chat.id == ADMIN]) and
          all(c[2] != msg_d.message_id for c in bot.copied))
    out_own, msg_own = await send(100, b"M1")      # mijozning o'zi qayta yubordi (tekshirilmoqda)
    check("o'zining kutilayotgan cheki AI'siz: «tekshirilmoqda»", reads["n"] == 0 and out_own.verdict == rules.OWN_PENDING and "tekshirilmoqda" in msg_own.answers[-1][0], (reads["n"], msg_own.answers[-1][0]))
    reader._call = _orig_call
    config.RECEIPT_AUTO = True

asyncio.run(main())
print("\nXATO:" if FAILS else "\nOqim HAMMASI YAXSHI", FAILS or "")
sys.exit(1 if FAILS else 0)
