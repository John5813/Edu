"""Tekin taqdimot havolalari (Instagram avtojavobi): `t.me/<bot>?start=g_<kod>`.

- admin «Funksiyalar boshqaruvi»da havola yaratadi, ko'radi (bosganlar / olganlar), o'chiradi;
- havola orqali kelgan mijoz — bazada avvaldan bo'lsa ham, bepul sinovni ishlatgan bo'lsa ham — bir marta
  5 slaydli tekin taqdimot oladi; ikkinchi marta olmaydi, o'chirilgan havola ishlamaydi;
- taqdimot tayyorlanmasa imkoniyat qaytadi; bot qayta ishga tushganda uzilganlar qaytariladi.

    python test_tekin_havola.py
"""
import asyncio, os, sys, tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_IDS", "1")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import database.database as dbmod
dbmod.DATABASE_FILE = os.path.join(tempfile.mkdtemp(), "t.db")
from database import free_trial, gift_links
from database.database import Database


async def main():
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage
    from bot.handlers import reengage as handler
    from bot.states import GiftStates

    print("1) Havola kodi")
    check("g_<kod> o'qiladi", gift_links.code_of("g_Ab12Cd34") == "Ab12Cd34")
    check("boshqa parametrlar havola emas", gift_links.code_of("ref_ABC") is None and gift_links.code_of("g_..") is None)
    code = await gift_links.create()
    check("yangi havola faol", await gift_links.is_active(code) and gift_links.valid(code))
    check("havola manzili", gift_links.url("EDUfail_bot", code) == f"https://t.me/EDUfail_bot?start=g_{code}")

    db = Database()
    db.get_active_channels = AsyncMock(return_value=[])
    db.get_user = AsyncMock(return_value=SimpleNamespace(language="uz", kazakh=False))
    said = []

    async def answer(text, **kw):
        said.append((text, kw.get("reply_markup")))
        return SimpleNamespace(delete=AsyncMock(), edit_text=AsyncMock(side_effect=lambda t, **k: said.append((t, k.get("reply_markup")))))

    def msg(uid, text=""):
        return SimpleNamespace(text=text, from_user=SimpleNamespace(id=uid), answer=answer,
                               answer_document=AsyncMock(), bot=MagicMock(), chat=SimpleNamespace(id=uid))

    print("\n2) Bazada avvaldan bor, bepul sinovni ishlatgan mijoz ham oladi")
    await free_trial.claim(500, "bot-sent-old")
    check("mijoz bepul sinovni ishlatgan", not await free_trial.available(500))
    await handler.offer_link_gift(msg(500), db, code)
    buttons = [b.callback_data for r in said[-1][1].inline_keyboard for b in r]
    check("sovg'a taklifi va tugma", "tekin taqdimot" in said[-1][0] and buttons == [f"gl:{code}"], said[-1:])
    check("bosgani yozildi", (await gift_links.links())[0]["clicks"] == 1)

    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=500, user_id=500))
    cb = SimpleNamespace(data=f"gl:{code}", answer=AsyncMock(), message=msg(500), from_user=SimpleNamespace(id=500))
    await handler.gift_link_button(cb, state, db)
    check("mavzu so'raldi", await state.get_state() == GiftStates.waiting_for_topic.state
          and (await state.get_data()).get("gift_link") == code, said[-1:])

    tmp = tempfile.NamedTemporaryFile(suffix=".pptx", delete=False); tmp.write(b"x"); tmp.close()
    topic = msg(500, "Amir Temur davlati")
    with patch.object(handler, "_build", AsyncMock(return_value=tmp.name)) as build:
        await handler.gift_topic(topic, state, db)
    check("taqdimot yuborildi", build.await_count == 1 and topic.answer_document.await_count == 1)
    check("havoladan olindi (bepul sinov hisobiga tegilmadi)",
          not await gift_links.available(code, 500) and (await gift_links.links())[0]["delivered"] == 1)

    print("\n3) Ikkinchi marta bermaydi")
    said.clear()
    await handler.offer_link_gift(msg(500), db, code)
    check("«allaqachon olgansiz»", "allaqachon olgansiz" in said[-1][0], said[-1:])
    said.clear()
    await handler.start_gift(msg(500), state, db, 500, link=code)
    check("tugmani qayta bossa ham bermaydi", "allaqachon olgansiz" in said[-1][0], said[-1:])

    print("\n4) Xato bo'lsa imkoniyat qaytadi")
    state2 = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=501, user_id=501))
    await handler.start_gift(msg(501), state2, db, 501, link=code)
    with patch.object(handler, "_build", AsyncMock(side_effect=RuntimeError("model"))):
        await handler.gift_topic(msg(501, "Suv aylanishi"), state2, db)
    check("tayyorlanmadi — sovg'a qaytdi", await gift_links.available(code, 501))
    retry = [b.callback_data for r in said[-1][1].inline_keyboard for b in r]
    check("qayta urinish tugmasi havola bilan", retry == [f"gift:start:{code}"], retry)
    check("bepul sinov ham tegilmagan", await free_trial.available(501))

    print("\n5) Bot qayta ishga tushganda uzilgan taqdimot qaytadi")
    await gift_links.claim(code, 502, "bot-abc")
    check("band", not await gift_links.available(code, 502))
    check("qaytarildi", await gift_links.release_unfinished_bot() == 1 and await gift_links.available(code, 502))

    print("\n6) O'chirilgan havola ishlamaydi")
    await gift_links.deactivate(code)
    said.clear()
    await handler.offer_link_gift(msg(503), db, code)
    check("«muddati tugagan»", "muddati tugagan" in said[-1][0], said[-1:])
    check("o'chirilgan havola ro'yxatda yo'q", all(i["code"] != code for i in await gift_links.links()))

    print("\n7) /start g_<kod> sovg'a taklifini chiqaradi")
    from bot.handlers import start as start_handler
    code2 = await gift_links.create()
    existing = SimpleNamespace(telegram_id=600, language="uz", kazakh=False)
    db.get_user = AsyncMock(return_value=existing)
    state6 = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=600, user_id=600))
    said.clear()
    with patch.object(start_handler, "check_subscription_and_show_menu", AsyncMock()):
        await start_handler.start_command(msg(600, f"/start g_{code2}"), state6, db)
    check("eski mijozga ham sovg'a taklifi", any(f"gl:{code2}" in str(m[1]) for m in said), said)

    print("\n8) Admin paneli")
    from bot.keyboards import get_feature_management_keyboard
    from bot.handlers import admin
    kb = get_feature_management_keyboard(True)
    check("«Funksiyalar boshqaruvi»da tugma", any(b.callback_data == "giftlinks" for r in kb.inline_keyboard for b in r))
    bot = MagicMock(); bot.get_me = AsyncMock(return_value=SimpleNamespace(username="EDUfail_bot"))
    text, markup = await admin._gift_links_view(bot)
    datas = [b.callback_data for r in markup.inline_keyboard for b in r]
    check("ro'yxatda havola, hisob va tugmalar", f"start=g_{code2}" in text and "bosganlar" in text
          and f"giftlink_off:{code2}" in datas and "giftlink_new" in datas and "back_to_features" in datas, text)
    edit = AsyncMock(); sent = AsyncMock()
    cb = SimpleNamespace(data="giftlink_new", answer=AsyncMock(), from_user=SimpleNamespace(id=1), bot=bot,
                         message=SimpleNamespace(edit_text=edit, answer=sent))
    before = len(await gift_links.links())
    await admin.gift_link_new(cb)
    check("yangi havola yaratildi va alohida yuborildi", len(await gift_links.links()) == before + 1
          and "start=g_" in sent.await_args.args[0])
    cb = SimpleNamespace(data=f"giftlink_off:{code2}", answer=AsyncMock(), from_user=SimpleNamespace(id=1), bot=bot,
                         message=SimpleNamespace(edit_text=AsyncMock()))
    await admin.gift_link_off(cb)
    check("havola o'chirildi", not await gift_links.is_active(code2))
    cb = SimpleNamespace(data="giftlink_new", answer=AsyncMock(), from_user=SimpleNamespace(id=999), bot=bot,
                         message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()))
    before = len(await gift_links.links())
    await admin.gift_link_new(cb)
    check("admin bo'lmagan yarata olmaydi", len(await gift_links.links()) == before)


asyncio.run(main())
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
