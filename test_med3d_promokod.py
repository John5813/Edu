"""3D Anatomiya chegirma promokodlari: admin boshqaruvi, topic flow va usage limit.

    python test_med3d_promokod.py
"""
import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_IDS", "1")

import config
import database.database as db_module

db_module.DATABASE_FILE = os.path.join(tempfile.mkdtemp(), "med3d-promos.db")

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from bot import checkout as pay
from bot.handlers import admin, premium_presentation as pp
from bot.keyboards import get_feature_management_keyboard
from bot.states import AdminStates, PremiumPresentationStates as PS
from database.database import Database, init_db
from services.med3d import auto

FAILS = []


def check(name, condition, detail=""):
    print(("  ok   " if condition else "  XATO ") + name + ("" if condition else f" — {detail}"))
    if not condition:
        FAILS.append(name)


class FakeChat:
    def __init__(self):
        self.sent = []
        self.deleted = []
        self.bot = SimpleNamespace(delete_message=self.delete)

    async def delete(self, chat_id, message_id):
        self.deleted.append(message_id)

    def message(self, text="", user_id=11):
        chat = self
        message = MagicMock()
        message.text = text
        message.chat = SimpleNamespace(id=11)
        message.from_user = SimpleNamespace(id=user_id, first_name="Ali")
        message.bot = self.bot

        async def answer(body, **kwargs):
            sent = SimpleNamespace(message_id=len(chat.sent) + 1)
            chat.sent.append((body, kwargs.get("reply_markup"), sent))
            return sent

        message.answer = answer
        message.edit_text = AsyncMock()
        message.delete = AsyncMock()
        return message


def callback(chat, data, user_id=1):
    result = MagicMock()
    result.data = data
    result.answer = AsyncMock()
    result.message = chat.message()
    result.from_user = SimpleNamespace(id=user_id)
    result.bot = chat.bot
    return result


def buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


async def main():
    config.ADMIN_IDS = [1]
    await init_db()
    db = Database()

    print("1) Admin menyusi va ommaviy yaratish")
    feature_buttons = buttons(get_feature_management_keyboard(True))
    check("funksiyalar boshqaruvida 3D Anatomiya promokod tugmasi",
          any(b.text == "🫀 3D Anatomiya promokod" and b.callback_data == "med3d_promo_manage"
              for b in feature_buttons))

    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=1, user_id=1))
    chat = FakeChat()
    start = callback(chat, "med3d_promo_create")
    await admin.med3d_promo_create_start(start, state)
    prompt_buttons = buttons(start.message.edit_text.await_args.kwargs["reply_markup"])
    check("promokod yaratishning birinchi qadamida Orqaga bor",
          any(b.callback_data == "med3d_promo_back" for b in prompt_buttons))
    await admin.med3d_promo_codes_input(chat.message("heart25, bones25", user_id=1), state)
    check("bir necha kod bitta xabardan qabul qilindi",
          await state.get_state() == AdminStates.waiting_for_med3d_promo_percent.state
          and (await state.get_data())["med3d_promo_codes"] == ["HEART25", "BONES25"])
    await admin.med3d_promo_percent_input(chat.message("25", user_id=1), state)
    check("foiz qadamida Orqaga tugmasi va limit bosqichi",
          await state.get_state() == AdminStates.waiting_for_med3d_promo_limit.state
          and any(b.callback_data == "med3d_promo_back" for b in buttons(chat.sent[-1][1])))
    await admin.med3d_promo_limit_input(chat.message("1", user_id=1), state, db)
    promos = await db.list_med3d_promocodes()
    check("ikkala kod ham 25% va limit 1 bilan yaratildi",
          len(promos) == 2 and all(p["discount_percent"] == 25 and p["usage_limit"] == 1 for p in promos),
          promos)

    print("\n2) Limit, bir martalik ishlatish va o'chirish")
    promo, reason = await db.get_med3d_promocode("heart25", 11)
    check("promokod katta-kichik harfga befarq topiladi", reason == "ok" and promo["code"] == "HEART25")
    reserved, reason = await db.reserve_med3d_promocode("heart25", 11)
    check("birinchi foydalanuvchi limitli kodni band qildi", reason == "ok" and reserved["id"] == promo["id"])
    rejected, reason = await db.reserve_med3d_promocode("heart25", 22)
    check("parallel ikkinchi foydalanuvchiga limitdan oshirib bermaydi",
          rejected is None and reason == "limit_reached", reason)
    check("to'langan foydalanish yakunlandi",
          await db.complete_med3d_promocode("heart25", 11))
    repeated, reason = await db.get_med3d_promocode("heart25", 11)
    check("bitta foydalanuvchi shu koddan ikkinchi marta foydalana olmaydi",
          repeated is None and reason == "already_used", reason)
    check("limitni cheksizga o'zgartirish mumkin",
          await db.update_med3d_promocode_limit(promo["id"], None))
    extra, reason = await db.reserve_med3d_promocode("heart25", 33)
    check("cheksiz limitdan foydalanish mumkin", reason == "ok" and extra is not None)
    check("ikkinchi foydalanish ham qayd etildi",
          await db.complete_med3d_promocode("heart25", 33))
    check("limit ishlatilgan sonidan kichik bo'lmasligi shart",
          not await db.update_med3d_promocode_limit(promo["id"], 1))
    check("kodni admin o'chira oladi", await db.deactivate_med3d_promocode(promo["id"]))
    deleted, reason = await db.get_med3d_promocode("heart25", 33)
    check("o'chirilgan kod mijozga berilmaydi", deleted is None and reason == "not_found")
    await db.create_med3d_promocodes(["RACE1"], 10, 1)
    race = await asyncio.gather(
        db.reserve_med3d_promocode("RACE1", 101),
        db.reserve_med3d_promocode("RACE1", 102),
    )
    check("bir vaqtning o'zida kelgan ikki so'rov limitni oshirmaydi",
          sum(result[1] == "ok" for result in race) == 1, race)

    print("\n3) Mavzu tasdiqlangach kod so'rash va chegirma hisoblash")
    await db.create_med3d_promocodes(["FREE100"], 100, None)
    db.get_user = AsyncMock(return_value=SimpleNamespace(language="uz", balance=100000, first_name="Ali"))
    db.get_active_channels = AsyncMock(return_value=[])
    chat = FakeChat()
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=11, user_id=11))
    await pp.premium_presentation_start(chat.message(pp.MED3D_ENTRY_TEXTS[0]), state, db)
    await pp.premium_med3d_answer(callback(chat, "prem_med3d:ha"), state, db)
    original_check = auto.check_topic
    auto.check_topic = lambda topic, language="uz": {"ok": True, "kind": "anatomy", "reason": ""}
    try:
        await pp.premium_ppt_got_topic(chat.message("Yurakning tuzilishi"), state, db)
    finally:
        auto.check_topic = original_check
    promo_markup = chat.sent[-1][1]
    check("mos mavzudan keyin promokod so'raladi, Skip va Back bor",
          await state.get_state() == PS.waiting_for_med3d_promocode.state
          and [b.callback_data for b in buttons(promo_markup)] ==
          ["prem_m3d_promo:skip", "prem_m3d_promo:back"])
    await pp.premium_med3d_promocode_input(chat.message("free100"), state, db)
    data = await state.get_data()
    base_price = auto.price_for(10)
    check("100% chegirma narxni nolga tushiradi",
          data["med3d_promo_percent"] == 100
          and pp._price_of({**data, "slide_count": 10}, 10) == 0
          and base_price > 0)

    print("\n4) Chegirma ko'rsatilishi")
    await db.create_med3d_promocodes(["SAVE25"], 25, None)
    promo, reason = await db.get_med3d_promocode("SAVE25", 77)
    order = {"kind": pp.KIND_MED3D, "standalone_med3d": True,
             "med3d_promo_code": promo["code"], "med3d_promo_percent": promo["discount_percent"],
             "slide_count": 10, "topic": "Yurak", "presentation_language": "uz"}
    base_price = auto.price_for(10)
    summary, _ = pp._summary(order, "uz")
    check("buyurtma xulosasida promo va tejangan summa ko'rinadi",
          "SAVE25" in summary and "25% chegirma" in summary
          and f"{base_price * 25 // 100:,}" in summary, summary)

    print("\n5) Stars va balans to'lovi chegirmali narxni ishlatadi")
    save25, _ = await db.get_med3d_promocode("SAVE25", 77)
    stars_order = pay.start({
        **order, "med3d_promo_id": save25["id"], "price": pp._price_of(order, 10),
        "slide_count": 10, "client_name": "Ali", "level": 2,
    })
    stars_state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=77, user_id=77))
    await stars_state.set_data(stars_order)
    await stars_state.set_state(PS.waiting_for_payment)
    stars_chat = FakeChat()
    stars_callback = callback(stars_chat, pp.CHECKOUT.pay_stars, user_id=77)
    invoice = {}
    original_invoice = pay.send_invoice

    async def fake_invoice(message, checkout, lang, price, title, description):
        invoice.update(price=price, title=title)
        return True

    pay.send_invoice = fake_invoice
    try:
        await pp.premium_ppt_pay_stars(stars_callback, stars_state, db)
    finally:
        pay.send_invoice = original_invoice
        await db.release_med3d_promocode("SAVE25", 77)
        pay.forget(77)
    check("Stars hisob-fakturasiga chegirmali narx uzatildi",
          invoice.get("price") == pp._price_of(order, 10), invoice)

    await db.create_med3d_promocodes(["BAL25"], 25, None)
    balance_promo, _ = await db.get_med3d_promocode("BAL25", 88)
    user_balance = SimpleNamespace(language="uz", balance=100_000, first_name="Ali")

    async def update_balance(user_id, delta):
        user_balance.balance += delta

    db.get_user = AsyncMock(return_value=user_balance)
    db.update_user_balance = update_balance
    db.get_premium_ai_model = AsyncMock(return_value="")
    db.get_feature_status = AsyncMock(return_value=False)
    balance_order = pay.start({
        "kind": pp.KIND_MED3D, "standalone_med3d": True, "topic": "Yurak",
        "presentation_language": "uz", "slide_count": 10, "price": base_price * 75 // 100,
        "med3d_promo_code": "BAL25", "med3d_promo_percent": 25,
        "med3d_promo_id": balance_promo["id"], "client_name": "Ali", "level": 2,
        "m3d_style": "kobalt", "payment_method": "balance",
    })
    balance_state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=88, user_id=88))
    await balance_state.set_data(balance_order)
    await balance_state.set_state(PS.waiting_for_slide_count)
    balance_chat = FakeChat()
    balance_callback = callback(balance_chat, "prem_ppt_confirm", user_id=88)
    balance_callback.message.answer_document = AsyncMock()
    balance_callback.message.answer_video = AsyncMock()
    temp_file = tempfile.NamedTemporaryFile(suffix=".pptx", delete=False)
    temp_file.write(b"PK")
    temp_file.close()
    original_build = auto.build_deck

    async def fake_build(topic, slide_count, **kwargs):
        return temp_file.name, slide_count

    auto.build_deck = fake_build
    try:
        await pp.premium_ppt_confirm(balance_callback, balance_state, db)
    finally:
        auto.build_deck = original_build
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
    check("balansdan aniq 25% chegirmadan keyingi summa yechildi",
          user_balance.balance == 100_000 - base_price * 75 // 100,
          user_balance.balance)
    bal_list = await db.list_med3d_promocodes()
    check("muvaffaqiyatli balans to'lovida promokod ishlatilgani sanaldi",
          next(p for p in bal_list if p["code"] == "BAL25")["usage_count"] == 1, bal_list)

asyncio.run(main())
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
