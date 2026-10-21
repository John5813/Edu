"""To'liq avtomatik to'lov: AI chekni o'zi tasdiqlaydi yoki kamchiliklarini aytib rad etadi.

Haqiqiy baza (vaqtinchalik), soxta Telegram va soxta AI.

    python test_chek_toliq_avto.py
"""
import asyncio, json, os, sys, tempfile, types
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
from services.receipts import flow, reader, rules, store, texts

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "test.db")
NOW = datetime(2026, 10, 6, 20, 10)
rules.now_tashkent = lambda: NOW
ADMIN = config.ADMIN_IDS[0]
config.RECEIPT_AI = True
config.RECEIPT_AUTO = False          # to'liq avto rejim bu bayroqqa bog'liq emas
config.RECEIPT_FULL_AUTO = True


class Sent:
    def __init__(self, chat_id, text, kw, message_id):
        self.chat = types.SimpleNamespace(id=chat_id); self.message_id = message_id
        self.text, self.kw = text, kw
class FakeBot:
    def __init__(self):
        self.sent, self.copied, self.edited, self.n = [], [], [], 1000
    async def send_message(self, chat_id, text, **kw):
        self.n += 1; item = Sent(chat_id, text, kw, self.n); self.sent.append(item); return item
    async def copy_message(self, chat_id, from_chat_id, message_id, **kw):
        self.copied.append((chat_id, from_chat_id, message_id, kw)); self.n += 1
        return types.SimpleNamespace(message_id=self.n)
    async def edit_message_text(self, **kw): self.edited.append(kw)
    async def edit_message_reply_markup(self, **kw): self.edited.append(kw)
    async def edit_message_caption(self, **kw): self.edited.append(kw)

class FakeMessage:
    counter = 0
    def __init__(self, bot, tg, data=b"x", uid=None, filename=None):
        FakeMessage.counter += 1
        self.bot, self.chat, self.message_id = bot, types.SimpleNamespace(id=tg), FakeMessage.counter
        uid = uid or f"u{FakeMessage.counter}"
        if filename:
            self.photo = None
            self.document = types.SimpleNamespace(file_id=f"d{FakeMessage.counter}", file_unique_id=uid,
                                                  file_name=filename, mime_type="image/jpeg", file_size=len(data))
        else:
            self.photo = [types.SimpleNamespace(file_id=f"f{FakeMessage.counter}", file_unique_id=uid, file_size=len(data))]
            self.document = None
        self.answers = []
    async def answer(self, text, **kw):
        self.answers.append((text, kw))
        async def delete(): pass
        return types.SimpleNamespace(delete=delete)

QUEUE = []
CALLS = {"n": 0}
def fake_call(kind, images, text, now):
    CALLS["n"] += 1
    item = QUEUE.pop(0) if QUEUE else {}
    if isinstance(item, Exception): raise item
    return item
reader._call = fake_call
def fake_prepare(data, filename="", mime=""):
    moment = reader.name_time(filename)
    return reader.Prepared(images=[b"img"], text="", meta_flags=[], file_time=moment,
                           file_time_src="name" if moment else "")
reader.prepare = fake_prepare

CURRENT = {"v": b"A"}
async def fake_download(bot, file_id): return CURRENT["v"]
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
    for tg in (100, 200, 300, 400):
        users[tg] = await Database.create_user(tg, f"user{tg}", f"U{tg}", "uz")
    users[500] = await Database.create_user(500, "user500", "U500", "ru")
    bot = FakeBot()
    state = {"payment_amount": 10_000, "payment_started_at": (NOW - timedelta(minutes=15)).isoformat()}

    async def send(tg, data, canned, claimed=10_000, uid=None, filename=None, lang=None):
        QUEUE[:] = canned
        CURRENT["v"] = data
        msg = FakeMessage(bot, tg, data, uid=uid, filename=filename)
        out = await flow.process(msg, {**state, "payment_amount": claimed}, Database, users[tg],
                                 lang or users[tg].language, keyboard="KB")
        return out, msg

    async def balance(tg):
        return (await Database.get_user(tg)).balance

    def admin_msgs():
        return [m for m in bot.sent if m.chat.id == ADMIN]

    print("1) Rejim yoqilgan: yaxshi chek admin aralashuvisiz tasdiqlanadi")
    check("to'liq avto rejim yoqilgan (muhit + panel)", await flow.full_auto_enabled())
    out, msg = await send(100, b"A", [raw(), raw()])
    check("avto-tasdiq (RECEIPT_AUTO=0 bo'lsa ham)", out.verdict == rules.AUTO and await balance(100) == 10_000, (out.verdict, await balance(100)))

    print("2) Eski chek — RAD ETILADI, chek tagida kamchiliklar ro'yxati")
    a0 = len(admin_msgs())
    out, msg = await send(200, b"B", [raw(rid="7000000001", date=(10, 6, 12, 0), clock="12:01", battery=40)])
    text, kw = msg.answers[-1]
    check("verdict «rejected», pul qo'shilmadi, holat saqlanadi (qayta yuborishi mumkin)",
          out.verdict == rules.REJECTED and not out.clear_state and await balance(200) == 0, (out.verdict, out.clear_state))
    check("«To'lov rad etildi» + «Quyidagi kamchiliklar»", text.startswith("❌ To'lov rad etildi.") and "Quyidagi kamchiliklar aniqlandi:" in text, text)
    check("sabab: chek eski (necha soat oldin)", "• Chek eski — to'lov 8 soat oldin qilingan" in text, text)
    check("«qaytadan urining … yoki adminga murojaat qiling» + admin manzili",
          "Qaytadan urinib ko'ring" in text and "adminga murojaat qiling" in text and config.ADMIN_CONTACT in text, text)
    rp = kw.get("reply_parameters")
    check("javob aynan chek TAGIGA (reply)", rp is not None and rp.message_id == msg.message_id, kw)
    rows = kw["reply_markup"].inline_keyboard
    check("tugmalar: «Chekni qayta yuborish» va «Adminga murojaat» (t.me havola)",
          rows[0][0].callback_data.startswith("rcpt_resend:10000:") and rows[1][0].url == "https://t.me/" + config.ADMIN_CONTACT.lstrip("@"),
          [[b.text for b in r] for r in rows])
    pay = await Database.get_payment_by_id(out.payment_id)
    check("to'lov yozuvi «rejected» holatida", pay and pay.status == "rejected", pay and pay.status)
    card = admin_msgs()[-1]
    check("adminga JIM karta + «Baribir tasdiqlash» tugmasi", len(admin_msgs()) == a0 + 1 and card.kw.get("disable_notification") is True
          and card.kw["reply_markup"].inline_keyboard[0][0].callback_data == f"rcpt_force_{out.payment_id}"
          and "AI RAD ETDI" in card.text, card.text)
    rejected_pid = out.payment_id

    print("3) Bir nechta kamchilik birdan aytiladi")
    out, msg = await send(300, b"C", [raw(rid="", sender="", name="", clock=None, battery=None, cropped=True,
                                          tamper="high", date=(10, 6, 19, 40))])
    text = msg.answers[-1][0]
    check("qirqilgan + tahrirlangan + ID yo'q — hammasi ro'yxatda",
          out.verdict == rules.REJECTED and "qirqilgan" in text and "tahrirlanganga o'xshaydi" in text
          and "to'lov ID" in text, text)
    check("har kamchilik alohida qator", text.count("\n• ") >= 3, text)

    print("4) Mijoz o'sha to'lovning TO'G'RI chekini yubordi — takroriy deb topilmaydi, tasdiqlanadi")
    out_bad, msg_bad = await send(400, b"D1", [raw(rid="7100000001", date=(10, 6, 19, 44), clock="19:44", battery=50, cropped=True)])
    check("avval: qirqilgan chek rad etildi", out_bad.verdict == rules.REJECTED and "qirqilgan" in msg_bad.answers[-1][0], msg_bad.answers[-1][0])
    out_ok, msg_ok = await send(400, b"D2", [raw(rid="7100000001", date=(10, 6, 19, 44), clock="19:44", battery=50)] * 2)
    check("tuzatilgan chek avto-tasdiqlandi (kalitlar yangi chekka o'tdi)", out_ok.verdict == rules.AUTO and await balance(400) == 10_000,
          (out_ok.verdict, msg_ok.answers[-1][0] if msg_ok.answers else "", await balance(400)))
    out_again, _ = await send(200, b"D3", [raw(rid="7100000001", date=(10, 6, 19, 44), clock="19:44", battery=50)])
    check("endi boshqa mijoz o'sha chekni yuborsa — takroriy", out_again.verdict == rules.DUPLICATE, out_again.verdict)

    print("5) Aynan o'sha rad etilgan fayl qayta yuborildi — AI chaqirilmaydi, o'sha kamchiliklar aytiladi")
    CALLS["n"] = 0
    out, msg = await send(200, b"B", [])
    check("AI chaqirilmadi, «rad etildi» va o'sha sabab", CALLS["n"] == 0 and out.verdict == rules.REJECTED
          and "Chek eski" in msg.answers[-1][0], (CALLS["n"], msg.answers[-1][0]))

    print("6) Boshqa mijoz ishlatilgan chekni yubordi — rad, sabab «takroriy», blok yo'q")
    out, msg = await send(300, b"E", [raw()])
    text = msg.answers[-1][0]
    check("takroriy: rad etildi, sabab aytildi", out.verdict == rules.DUPLICATE and "rad etildi" in text and "avval ishlatilgan" in text, text)
    for i in range(5):
        await send(300, b"E" + bytes([i]), [raw()])
    check("ko'p urinishdan keyin ham bloklanmadi", not await Database.is_user_blocked(300))
    check("«bloklandi» degan xabar yo'q", not any("blok" in t.lower() for t, _ in msg.answers))

    print("7) Telegram fayl raqami (file_unique_id): bayti boshqa bo'lsa ham o'sha fayl — AI'siz ushlanadi")
    out1, _ = await send(100, b"F1", [raw(rid="7200000001", date=(10, 6, 19, 48), clock="19:48", battery=60)] * 2, uid="AgADfile777")
    check("birinchi yuborilish tasdiqlandi", out1.verdict == rules.AUTO)
    CALLS["n"] = 0
    out2, msg2 = await send(300, b"F1-recompressed", [], uid="AgADfile777")
    check("boshqa mijoz o'sha Telegram faylini uzatdi: AI chaqirilmadi, takroriy",
          CALLS["n"] == 0 and out2.verdict == rules.DUPLICATE and "avval ishlatilgan" in msg2.answers[-1][0], (CALLS["n"], out2.verdict))
    rec2 = await store.get_receipt(out2.receipt_id)
    check("sabab «duplicate_fuid» bazada", "duplicate_fuid" in json.loads(rec2["reasons"]), rec2["reasons"])

    print("8) Fayl nomidagi raqamlar: eski skrinshot va to'lovdan oldingi fayl")
    out, msg = await send(300, b"G1", [raw(rid="7300000001", date=(10, 6, 19, 52), clock="19:52", battery=61)],
                          filename="Screenshot_20261005_195200.jpg")
    check("kecha olingan skrinshot (bugungi sana yozilgan): rad, «Fayl eski»", out.verdict == rules.REJECTED and "Fayl eski" in msg.answers[-1][0], msg.answers[-1][0])
    out, msg = await send(300, b"G2", [raw(rid="7300000002", date=(10, 6, 19, 56), clock="19:56", battery=62)],
                          filename="Screenshot_20261006_194000.jpg")
    check("fayl to'lovdan 16 daqiqa oldin yaratilgan: rad", out.verdict == rules.REJECTED and "to'lovdan oldin yaratilgan" in msg.answers[-1][0], msg.answers[-1][0])
    out, msg = await send(300, b"G3", [raw(rid="7300000003", date=(10, 6, 20, 0), clock="20:01", battery=63)] * 2,
                          filename="Screenshot_20261006_200100.jpg")
    check("to'g'ri fayl (to'lovdan 1 daqiqa keyin) — tasdiqlandi", out.verdict == rules.AUTO, (out.verdict, msg.answers[-1][0]))

    print("9) Chek emas va boshqa karta — ham bir xil «rad etildi» shaklida")
    out, msg = await send(300, b"H1", [{"doc_type": "tax_receipt", "status": "success", "amount": 26, "readable": True}])
    check("soliq cheki", out.verdict == rules.NOT_RECEIPT and "rad etildi" in msg.answers[-1][0] and "soliq cheki" in msg.answers[-1][0], msg.answers[-1][0])
    out, msg = await send(300, b"H2", [raw(rid="7400000001", receiver="986016****1234", date=(10, 6, 19, 36), clock="19:36", battery=64)])
    check("boshqa karta: rad, «bizning kartaga o'tkazilmagan»", out.verdict == rules.REJECTED and "bizning kartaga o'tkazilmagan" in msg.answers[-1][0], msg.answers[-1][0])

    print("10) Mijoz tuzata olmaydigan holat (katta summa) — rad etilmaydi, adminga boradi")
    a0 = len(admin_msgs())
    out, msg = await send(300, b"I", [raw(amount=500_000, rid="7500000001", date=(10, 6, 19, 32), clock="19:32", battery=65)], claimed=500_000)
    check("katta summa: admin tasdig'i (tugmalar bilan)", out.verdict == rules.REVIEW and len(admin_msgs()) == a0 + 1
          and admin_msgs()[-1].kw["reply_markup"].inline_keyboard[0][0].callback_data.startswith("approve_payment_"), out.verdict)
    check("mijozga «rad etildi» deyilmadi", "rad etildi" not in msg.answers[-1][0], msg.answers[-1][0])

    print("11) Admin «Baribir tasdiqlash» — pul bir marta qo'shiladi")
    from bot.handlers import admin as admin_handlers
    class CB:
        def __init__(self, data):
            self.data, self.from_user, self.bot, self.answers = data, types.SimpleNamespace(id=ADMIN, username="adm", full_name="Adm"), bot, []
            self.message = types.SimpleNamespace(text="karta", chat=types.SimpleNamespace(id=ADMIN), message_id=1,
                                                 edit_text=self._edit, edit_reply_markup=self._edit)
        async def _edit(self, *a, **k): pass
        async def answer(self, text="", **kw): self.answers.append(text)
    b0 = await balance(200)
    await admin_handlers.force_approve_rejected(CB(f"rcpt_force_{rejected_pid}"), Database)
    check("mijoz hisobiga qo'shildi, to'lov «approved»", await balance(200) == b0 + 10_000
          and (await Database.get_payment_by_id(rejected_pid)).status == "approved", await balance(200) - b0)
    check("mijozga «tasdiqlandi» xabari", any(m.chat.id == 200 and "tasdiqlandi" in m.text for m in bot.sent))
    second = CB(f"rcpt_force_{rejected_pid}")
    await admin_handlers.force_approve_rejected(second, Database)
    check("ikkinchi bosish: pul qayta qo'shilmadi", await balance(200) == b0 + 10_000 and "allaqachon" in second.answers[-1], second.answers)
    stranger = CB(f"rcpt_force_{rejected_pid}"); stranger.from_user = types.SimpleNamespace(id=123456789)
    await admin_handlers.force_approve_rejected(stranger, Database)
    check("admin bo'lmagan odam bosa olmaydi", await balance(200) == b0 + 10_000)
    out, _ = await send(200, b"B-again", [raw(rid="7000000001", date=(10, 6, 12, 0), clock="12:01", battery=40)])
    check("admin tasdiqlagan chekni mijoz qayta yuborsa — yangidan baholanmaydi, pul qayta qo'shilmaydi",
          out.verdict in (rules.OWN_PENDING, rules.DUPLICATE) and await balance(200) == b0 + 10_000, out.verdict)

    print("12) Rus tilida")
    out, msg = await send(500, b"J", [raw(rid="7600000001", date=(10, 6, 11, 0), clock="11:00", battery=11)])
    text = msg.answers[-1][0]
    check("«Платёж отклонён» + недостатки + админ", text.startswith("❌ Платёж отклонён.") and "Чек старый" in text
          and config.ADMIN_CONTACT in text, text)

    print("13) To'lov handleri: rad etilgandan keyin chek kutish holati saqlanadi")
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage
    from bot.handlers import payments as pay_handlers
    from bot.states import PaymentStates
    st = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=300, user_id=300))
    await st.set_state(PaymentStates.waiting_for_screenshot)
    await st.update_data(**state)
    QUEUE[:] = [raw(rid="7700000001", date=(10, 6, 10, 0), clock="10:00", battery=12)]
    CURRENT["v"] = b"K"
    await pay_handlers.handle_payment_screenshot(FakeMessage(bot, 300, b"K"), st, Database, "uz", users[300])
    check("holat: hali chek kutilmoqda", await st.get_state() == PaymentStates.waiting_for_screenshot.state, await st.get_state())

    print("14) Admin paneldan o'chirilsa — avvalgidek admin tasdig'i")
    from bot.keyboards import get_feature_management_keyboard
    kb = get_feature_management_keyboard(True, True, True, receipt_full_auto_enabled=True)
    btn = [b for row in kb.inline_keyboard for b in row if "To'liq avto" in b.text]
    check("panelda «To'liq avto to'lov» tugmasi", btn and btn[0].callback_data == "toggle_receipt_full_off", [b.text for row in kb.inline_keyboard for b in row])
    class TCB:
        def __init__(self, data): self.data, self.from_user, self.answers = data, types.SimpleNamespace(id=ADMIN), []; self.message = self
        async def answer(self, text="", **kw): self.answers.append(text)
        async def edit_text(self, text, reply_markup=None): self.kb = reply_markup
    t = TCB("toggle_receipt_full_off")
    await admin_handlers.toggle_receipt_full(t, Database())
    check("o'chirildi", not await flow.full_auto_enabled() and "o'chirildi" in t.answers[0], t.answers)
    out, msg = await send(300, b"L", [raw(rid="7800000001", date=(10, 6, 9, 0), clock="09:00", battery=13)])
    check("eski chek endi adminga boradi (rad etilmaydi)", out.verdict == rules.REVIEW and "rad etildi" not in msg.answers[-1][0], (out.verdict, msg.answers[-1][0]))
    await admin_handlers.toggle_receipt_full(TCB("toggle_receipt_full_on"), Database())
    check("qayta yoqildi", await flow.full_auto_enabled())

    print("15) Kunlik statistika: AI rad etgan cheklar alohida qator")
    stats = texts.daily_stats_text(await store.today_counts())
    check("statistikada «kamchiligi bor (AI rad etdi)»", "kamchiligi bor (AI rad etdi)" in stats, stats)

    print("16) Sayt orqali yuklangan chek: rad etilsa «kutilmoqda» emas, qayta yuborish mumkin")
    from services.receipts import web as receipt_web
    QUEUE[:] = [raw(rid="7900000001", date=(10, 6, 8, 0), clock="08:00", battery=14)]
    res = await receipt_web.submit(bot, 300, 10_000, state["payment_started_at"], b"WEB1", "chek.jpg", "image/jpeg")
    check("sayt: rad etildi, sabablar bilan; pending=False, retry=True",
          res["verdict"] == rules.REJECTED and "rad etildi" in res["message"] and "Chek eski" in res["message"]
          and res["pending"] is False and res["retry"] is True and res["credited"] is None, res)

asyncio.run(main())
print("\nXATO:" if FAILS else "\nTo'liq avto HAMMASI YAXSHI", FAILS or "")
sys.exit(1 if FAILS else 0)
