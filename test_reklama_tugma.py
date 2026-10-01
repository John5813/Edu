"""Reklama ostidagi tugmalar: tahlil, yuborish, ichki tugma bosilganda bo'lim ochilishi.

    python test_reklama_tugma.py
"""
import asyncio, os, sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_IDS", "1")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from aiogram import Bot, Dispatcher, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from bot import ad_buttons
from bot.handlers import admin
from bot.states import AdminStates

# ── tahlil
buttons, errors = ad_buttons.parse(
    "Botga o'tish | @slaydtopbot\nSaytimiz | https://example.uz/x?a=1\nKanal | t.me/kanal\n"
    "Taqdimot yaratish | Taqdimot\nTezis | tezis\nBalans | hisob")
kinds = [(b["kind"], b["value"]) for b in buttons]
check("xatosiz yozuv: 6 ta tugma", len(buttons) == 6 and not errors, errors)
check("@nom, t.me va https havolalari URL tugma",
      kinds[:3] == [("url", "https://t.me/slaydtopbot"), ("url", "https://example.uz/x?a=1"), ("url", "https://t.me/kanal")], kinds)
check("bo'lim nomi ichki tugma, `tezis` tayyor os: tugmasi", kinds[3] == ("menu", "taqdimot") and kinds[4] == ("cb", "tezis") and kinds[5] == ("menu", "hisob"), kinds)
_, errs = ad_buttons.parse("Matn yo'q\nSayt | nimadir\n | https://a.uz\n" + "\n".join(f"T{i} | https://a.uz" for i in range(9)))
check("xatolar qator raqami bilan aytiladi", any("1-qator" in e for e in errs) and any("2-qator" in e for e in errs) and any("3-qator" in e for e in errs), errs)
check("8 tadan ko'p tugma rad etiladi", any("8 tadan oshmasin" in e for e in errs), errs)

markup = ad_buttons.markup(buttons)
flat = [b for row in markup.inline_keyboard for b in row]
check("URL tugma `url`, ichki tugma `ad:` / `os:` callback bilan",
      flat[0].url == "https://t.me/slaydtopbot" and flat[3].callback_data == "ad:taqdimot"
      and flat[4].callback_data == "os:tezis" and flat[5].callback_data == "ad:hisob", [(b.url, b.callback_data) for b in flat])
check("bo'sh ro'yxatda tugma yo'q", ad_buttons.markup([]) is None)
check("ichki tugma matni foydalanuvchi tilida", ad_buttons.menu_text("taqdimot", "uz") == "🌟 Taqdimot" and "Презентация" in ad_buttons.menu_text("taqdimot", "ru"))
check("callback_data 64 baytdan oshmaydi", all(len((b.callback_data or "").encode()) <= 64 for b in flat))

# ── yuborish: har tur reklama ostida tugma bilan ketadi
async def sending():
    bot = MagicMock()
    for name in ("send_message", "send_photo", "send_video", "send_document", "send_animation", "send_voice", "send_audio"):
        setattr(bot, name, AsyncMock())
    cases = {
        "text": {"message_type": "text", "message_text": "Salom"},
        "photo": {"message_type": "photo", "photo_id": "p", "caption": "c"},
        "video": {"message_type": "video", "video_id": "v", "caption": "c"},
        "document": {"message_type": "document", "document_id": "d", "caption": "c"},
        "animation": {"message_type": "animation", "animation_id": "a", "caption": "c"},
        "voice": {"message_type": "voice", "voice_id": "x", "caption": "c"},
        "audio": {"message_type": "audio", "audio_id": "u", "caption": "c"},
    }
    for kind, data in cases.items():
        await admin._send_ad(bot, 5, data, markup)
        method = getattr(bot, "send_message" if kind == "text" else f"send_{kind}")
        check(f"{kind} reklama tugma bilan yuboriladi", method.await_args.kwargs.get("reply_markup") is markup, method.await_args)
    await admin._send_ad(bot, 5, cases["text"])
    check("tugmasiz reklama avvalgidek (reply_markup=None)", bot.send_message.await_args.kwargs.get("reply_markup") is None)

asyncio.run(sending())

# ── admin oqimi
async def flow():
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=1, user_id=1))
    sent = []
    msg = MagicMock(); msg.from_user = SimpleNamespace(id=1); msg.chat = SimpleNamespace(id=1)
    msg.bot = MagicMock(); msg.bot.send_message = AsyncMock()
    async def answer(text, **kw): sent.append((text, kw.get("reply_markup")))
    msg.answer = answer

    msg.text = "Reklama matni"
    await admin.handle_broadcast_message(msg, state)
    check("kontent kiritilgach tugma so'raladi", await state.get_state() == AdminStates.waiting_for_broadcast_buttons.state)
    cbs = [b.callback_data for row in sent[-1][1].inline_keyboard for b in row]
    check("`Tugma qo'shish` va `Tugmasiz davom etish` tugmalari", cbs == ["adbtn_add", "adbtn_skip"], cbs)

    msg.text = "Noto'g'ri qator"
    await admin.handle_broadcast_buttons_text(msg, state)
    check("noto'g'ri yozuvda xato aytiladi va holat qoladi",
          "❌" in sent[-1][0] and await state.get_state() == AdminStates.waiting_for_broadcast_buttons.state, sent[-1][0])

    msg.text = "Taqdimot | taqdimot\nSayt | https://example.uz"
    await admin.handle_broadcast_buttons_text(msg, state)
    data = await state.get_data()
    check("to'g'ri yozuv: tugmalar saqlandi, preview yuborildi, auditoriya so'raladi",
          len(data["buttons"]) == 2 and msg.bot.send_message.await_count == 1
          and await state.get_state() == AdminStates.waiting_for_broadcast_target.state, data)
    check("preview'da tugmalar bor", msg.bot.send_message.await_args.kwargs["reply_markup"] is not None)

    # Telegram havolani rad etsa, auditoriyaga o'tilmaydi
    state2 = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=2, user_id=1))
    await state2.set_state(AdminStates.waiting_for_broadcast_buttons)
    await state2.update_data(message_type="text", message_text="x", buttons=[])
    msg.bot.send_message = AsyncMock(side_effect=RuntimeError("BUTTON_URL_INVALID"))
    msg.text = "Sayt | https://example.uz"
    await admin.handle_broadcast_buttons_text(msg, state2)
    check("Telegram rad etsa — xato aytiladi, foydalanuvchilarga yuborilmaydi",
          "BUTTON_URL_INVALID" in sent[-1][0] and await state2.get_state() == AdminStates.waiting_for_broadcast_buttons.state)

asyncio.run(flow())

# ── ichki tugma: haqiqiy Dispatcher orqali "🌟 Taqdimot" xabari sifatida qayta beriladi
async def pressed():
    got = []
    router = Router()
    @router.message(F.text == "🌟 Taqdimot")
    async def entry(message: Message):
        got.append((message.text, message.from_user.id, message.chat.id))
    dp = Dispatcher(storage=MemoryStorage()); dp.include_router(router)
    bot = Bot("123456:ABCDEF")

    user = User(id=77, is_bot=False, first_name="Ali")
    chat = Chat(id=77, type="private")
    original = Message(message_id=5, date=datetime.now(), chat=chat, from_user=User(id=1, is_bot=True, first_name="Bot"), text="Reklama")
    callback = CallbackQuery(id="1", from_user=user, chat_instance="x", data="ad:taqdimot", message=original).as_(bot)
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=77, user_id=77))
    await state.set_state(AdminStates.waiting_for_broadcast_buttons)
    db = MagicMock(); db.get_user = AsyncMock(return_value=SimpleNamespace(language="uz"))

    from unittest.mock import patch
    with patch.object(CallbackQuery, "answer", new=AsyncMock()):
        await admin.handle_ad_menu_button(callback, state, db, dp)
    check("ichki tugma bosilganda bo'lim kirish xabari foydalanuvchi nomidan keladi", got == [("🌟 Taqdimot", 77, 77)], got)
    check("eski holat tozalandi", await state.get_state() is None)
    await bot.session.close()

asyncio.run(pressed())

print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
