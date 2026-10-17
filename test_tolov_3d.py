"""3D Anatomiya: mablag' yetmasa buyurtma saqlanib, to'lovdan keyin AYNAN 3D bo'lib davom etadi; 3D Pro menyuda yo'q.

Oqim: mavzu, uslub va slaydlar soni tanlangan → «Balansdan to'lash» → mablag' yetmaydi (buyurtma saqlanadi) →
mijoz balansni to'ldirishga o'tadi (FSM tozalanadi) → bot buyurtmani eslatadi (turi bilan) → «Davom etish» →
3D Anatomiya yig'iladi, 3D narxi yechiladi, fayl 3D nomi bilan yuboriladi. Stars hisob-fakturasida ham turi.

    python test_tolov_3d.py
"""
import asyncio, os, sys, tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "123:abc")

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot import checkout as pay
from bot.handlers import premium_presentation as pp
from services.med3d import auto as med3d_auto

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

balance = {"v": 0}
class DB:
    async def get_user(self, uid):
        return SimpleNamespace(language="uz", balance=balance["v"], first_name="Ali", id=uid)
    async def update_user_balance(self, uid, delta):
        balance["v"] += delta
    async def get_premium_ai_model(self): return ""
    async def get_feature_status(self, *a, **k): return False
    async def get_active_channels(self): return []
    def __getattr__(self, name):                 # qolgan statistika chaqiruvlari — e'tiborsiz
        return AsyncMock(return_value=None)

def message():
    msg = MagicMock()
    msg.chat = SimpleNamespace(id=7)
    msg.edit_text = AsyncMock(return_value=msg)
    msg.answer = AsyncMock(return_value=msg)
    msg.answer_document = AsyncMock(return_value=msg)
    msg.answer_video = AsyncMock(return_value=SimpleNamespace(video=SimpleNamespace(file_id="V")))
    msg.edit_reply_markup = AsyncMock()
    msg.delete = AsyncMock()
    return msg

def callback(data):
    cb = MagicMock(); cb.data = data; cb.answer = AsyncMock()
    cb.from_user = SimpleNamespace(id=7); cb.message = message()
    cb.bot = MagicMock(); cb.bot.send_message = AsyncMock()
    return cb

def texts(mock):
    return " ".join(str(c.args[0]) if c.args else str(c.kwargs.get("text", "")) for c in mock.await_args_list)


async def main():
    db = DB()
    PS = pp.PremiumPresentationStates

    print("1) 3D Pro menyuda yo'q")
    keys = [b.callback_data for row in pp._kind_keyboard("uz").inline_keyboard for b in row]
    check("tur tugmalari: 3D Anatomiya, Infografik, Zamonaviy, Klassik (3D Pro yo'q)",
          [k for k in keys if k.startswith("prem_ppt_kind:")] ==
          ["prem_ppt_kind:med3d", "prem_ppt_kind:info", "prem_ppt_kind:modern", "prem_ppt_kind:classic"], keys)
    st0 = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=9, user_id=9))
    await st0.set_state(PS.waiting_for_kind)
    old = callback("prem_ppt_kind:pro3d")
    await pp.premium_ppt_kind_selected(old, st0, db)
    check("eski xabardagi 3D Pro tugmasi — tur tanlanmaydi, turlar qayta ko'rsatiladi",
          (await st0.get_data()).get("kind") != "pro3d" and await st0.get_state() == PS.waiting_for_kind.state)

    print("2) Mablag' yetmaydi — buyurtma saqlanadi")
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=7, user_id=7))
    price = med3d_auto.price_for(10)
    await state.set_data(pay.start({"kind": "med3d", "topic": "Yurakning tuzilishi", "slide_count": 10,
                                    "price": price, "presentation_language": "uz", "m3d_style": "kobalt",
                                    "client_name": "Ali", "level": 2}))
    await state.set_state(PS.waiting_for_slide_count)
    balance["v"] = 1000
    await pp.premium_ppt_confirm(callback("prem_ppt_confirm"), state, db)          # to'lov oynasi
    check("to'lov oynasi — buyurtma darhol saqlandi", pay.recall(7, pp.CHECKOUT.service).get("kind") == "med3d")
    await state.set_state(PS.waiting_for_payment)
    short = callback(pp.CHECKOUT.pay_balance)
    await pp.premium_ppt_pay_balance(short, state, db)
    saved = pay.recall(7, pp.CHECKOUT.service)
    check("mablag' yetmadi: pul yechilmadi, buyurtma 3D bo'lib saqlandi (uslub, narx bilan)",
          balance["v"] == 1000 and saved.get("kind") == "med3d" and saved.get("m3d_style") == "kobalt"
          and saved.get("price") == price, saved)

    print("3) Stars hisob-fakturasi")
    sent = {}
    orig_invoice = pay.send_invoice
    async def fake_invoice(message, checkout, lang, price_, title, description):
        sent.update(title=title, description=description, price=price_); return True
    pay.send_invoice = fake_invoice
    await state.set_state(PS.waiting_for_payment)
    await pp.premium_ppt_pay_stars(callback(pp.CHECKOUT.pay_stars), state, db)
    pay.send_invoice = orig_invoice
    check("Stars: narx 3D narxi, nomida «3D Anatomiya»", sent.get("price") == price
          and "3D Anatomiya" in sent.get("title", ""), sent)

    print("4) Balans to'ldirildi — eslatma va davom etish")
    await state.clear()                                                              # to'ldirish oqimi FSM ni tozalaydi
    balance["v"] = price + 500
    bot = MagicMock(); bot.send_message = AsyncMock()
    await pay.offer_continue(bot, 7, balance["v"], "uz")
    note = bot.send_message.await_args.args[1] if bot.send_message.await_args else ""
    check("bot buyurtmani o'zi eslatadi: turi 3D Anatomiya, mavzu bilan",
          "3D Anatomiya" in note and "Yurakning tuzilishi" in note, note[:300])

    built = {}
    async def fake_build(topic, count, **kw):
        built.update(topic=topic, count=count, **kw)
        path = os.path.join(tempfile.mkdtemp(), "3D_test.pptx")
        open(path, "wb").write(b"PK")
        return path, count
    orig_build = med3d_auto.build_deck
    med3d_auto.build_deck = fake_build
    pp_sleep = asyncio.sleep
    try:
        go = callback(pp.CHECKOUT.recheck)
        await pp.premium_ppt_recheck(go, state, db)
    finally:
        med3d_auto.build_deck = orig_build
    check("«Davom etish»: 3D Anatomiya yig'ildi (mavzu, slaydlar, uslub saqlangan)",
          built.get("topic") == "Yurakning tuzilishi" and built.get("count") == 10 and built.get("style") == "kobalt",
          built)
    check("3D narxi bir marta yechildi", balance["v"] == 500, balance["v"])
    docs = go.message.answer_document.await_args_list
    name = docs[0].kwargs["document"].filename if docs else ""
    check("fayl 3D nomi bilan yuborildi (ko'rish sharti fayl nomida)", "PowerPoint 2019+" in name, name)
    check("saqlangan buyurtma o'chirildi (ikkinchi marta yechilmaydi)", not pay.recall(7, pp.CHECKOUT.service))

    print()
    print("HAMMASI O'TDI" if not FAILS else f"XATOLAR: {len(FAILS)} — {FAILS}")
    return not FAILS


ok = asyncio.run(main())
sys.exit(0 if ok else 1)
