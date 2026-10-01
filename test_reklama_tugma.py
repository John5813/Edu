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

# ── manzil va tugmalar
check("sayt manzili o'zgarishsiz", ad_buttons.normalize_link("https://example.uz/x?a=1") == "https://example.uz/x?a=1")
check("t.me kanal va @nom to'liq URL bo'ladi",
      ad_buttons.normalize_link("t.me/kanal") == "https://t.me/kanal" and ad_buttons.normalize_link("@MeningBotim") == "https://t.me/MeningBotim")
check("yaroqsiz manzil rad etiladi", all(ad_buttons.normalize_link(x) is None for x in ("nimadir", "javascript:alert(1)", "@ab", "")))
check("hamma bo'lim nomi menyudagi nom bilan ko'rinadi", ad_buttons.target_name("taqdimot") == "🌟 Taqdimot" and ad_buttons.target_name("tezis") == "📝 Tezis")

buttons = [
    {"text": "Saytga o'tish", "kind": "url", "value": "https://example.uz"},
    {"text": "Taqdimot yaratish", "kind": "menu", "value": "taqdimot"},
    {"text": "Tezis", "kind": "cb", "value": "tezis"},
]
markup = ad_buttons.markup(buttons)
flat = [b for row in markup.inline_keyboard for b in row]
check("URL tugma `url`, ichki tugma `ad:` / `os:` callback bilan; matn admin yozganicha",
      [b.text for b in flat] == ["Saytga o'tish", "Taqdimot yaratish", "Tezis"] and flat[0].url == "https://example.uz"
      and flat[1].callback_data == "ad:taqdimot" and flat[2].callback_data == "os:tezis", [(b.text, b.url, b.callback_data) for b in flat])
check("bo'sh ro'yxatda tugma yo'q", ad_buttons.markup([]) is None)
check("ichki tugma matni foydalanuvchi tilida", ad_buttons.menu_text("taqdimot", "uz") == "🌟 Taqdimot" and "Презентация" in ad_buttons.menu_text("taqdimot", "ru"))
check("callback_data 64 baytdan oshmaydi", all(len((b.callback_data or "").encode()) <= 64 for b in flat))
from bot import keyboards
sections = [b.callback_data for row in keyboards.get_broadcast_sections_keyboard().inline_keyboard for b in row]
check("bo'limlar ro'yxati: hamma ichki bo'lim tanlash tugmasi bilan", [c for c in sections if c.startswith("adbtn_pick:")] == [f"adbtn_pick:{k}" for k in ad_buttons.TARGETS], sections)

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

# ── admin oqimi (tugmalar bilan, matn sintaksisisiz)
async def flow():
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=1, user_id=1))
    sent = []
    msg = MagicMock(); msg.from_user = SimpleNamespace(id=1); msg.chat = SimpleNamespace(id=1)
    msg.bot = MagicMock(); msg.bot.send_message = AsyncMock()
    msg.bot.me = AsyncMock(return_value=SimpleNamespace(username="Edufayl_bot"))
    async def answer(text, **kw): sent.append((text, kw.get("reply_markup"))); 
    msg.answer = answer

    def callback(data):
        cb = MagicMock(); cb.data = data; cb.answer = AsyncMock(); cb.from_user = msg.from_user
        cb.message = msg; cb.bot = msg.bot
        return cb
    cbs = lambda i=-1: [b.callback_data for row in sent[i][1].inline_keyboard for b in row]

    msg.text = "Reklama matni"
    await admin.handle_broadcast_message(msg, state)
    check("kontent kiritilgach tugma so'raladi", await state.get_state() == AdminStates.waiting_for_broadcast_buttons.state)
    check("`Tugma qo'shish` va `Tugmasiz davom etish`", cbs() == ["adbtn_add", "adbtn_skip"], cbs())

    await admin.handle_broadcast_buttons_add(callback("adbtn_add"), state)
    check("tugma turi so'raladi: havola yoki ichki bo'lim", cbs() == ["adbtn_type_url", "adbtn_type_menu", "adbtn_back"], cbs())

    # 1) Havola: manzil -> nom
    await admin.handle_broadcast_button_url_type(callback("adbtn_type_url"), state)
    check("manzil so'raladi va misolda ADMINNING o'z boti ko'rsatiladi", "@Edufayl_bot" in sent[-1][0] and "slaydtop" not in sent[-1][0].lower(), sent[-1][0])
    msg.text = "nimadir"
    await admin.handle_broadcast_button_url(msg, state)
    check("yaroqsiz manzilda xato aytiladi", "❌" in sent[-1][0] and await state.get_state() == AdminStates.waiting_for_ad_button_url.state)
    msg.text = "https://example.uz/aksiya"
    await admin.handle_broadcast_button_url(msg, state)
    check("manzildan keyin tugma nomi so'raladi", await state.get_state() == AdminStates.waiting_for_ad_button_label.state and "nom" in sent[-1][0])
    msg.text = "Aksiyani ko'rish"
    await admin.handle_broadcast_button_label(msg, state)
    buttons = (await state.get_data())["buttons"]
    check("havola tugma admin yozgan nom bilan saqlandi (manzil ko'rinmaydi)",
          buttons == [{"text": "Aksiyani ko'rish", "kind": "url", "value": "https://example.uz/aksiya"}], buttons)
    check("tugma qo'shilgach: yana / o'chirish / tayyor", cbs() == ["adbtn_add", "adbtn_undo", "adbtn_done"], cbs())
    check("ro'yxatda manzil adminga ko'rinadi", "https://example.uz/aksiya" in sent[-1][0] and "Aksiyani ko'rish" in sent[-1][0], sent[-1][0])

    # 2) Ichki bo'lim: ro'yxatdan tanlash -> nom
    await admin.handle_broadcast_buttons_add(callback("adbtn_add"), state)
    await admin.handle_broadcast_button_menu_type(callback("adbtn_type_menu"), state)
    check("ichki bo'limlar ro'yxati chiqadi", "adbtn_pick:taqdimot" in cbs() and "adbtn_pick:tezis" in cbs(), cbs())
    await admin.handle_broadcast_button_pick(callback("adbtn_pick:taqdimot"), state)
    check("bo'lim tanlangach nom so'raladi, standart nom taklif qilinadi", cbs() == ["adbtn_defname"] and await state.get_state() == AdminStates.waiting_for_ad_button_label.state, cbs())
    await admin.handle_broadcast_button_defname(callback("adbtn_defname"), state)
    check("standart nom: bo'lim nomi", (await state.get_data())["buttons"][-1] == {"text": "🌟 Taqdimot", "kind": "menu", "value": "taqdimot"}, (await state.get_data())["buttons"])

    await admin.handle_broadcast_buttons_add(callback("adbtn_add"), state)
    await admin.handle_broadcast_button_menu_type(callback("adbtn_type_menu"), state)
    await admin.handle_broadcast_button_pick(callback("adbtn_pick:tezis"), state)
    msg.text = "Tezisni arzonga yozdiring"
    await admin.handle_broadcast_button_label(msg, state)
    last = (await state.get_data())["buttons"][-1]
    check("`Boshqa xizmatlar` bo'limi (tezis) o'z nomi bilan", last == {"text": "Tezisni arzonga yozdiring", "kind": "cb", "value": "tezis"}, last)

    await admin.handle_broadcast_button_undo(callback("adbtn_undo"), state)
    check("oxirgi tugmani o'chirish", len((await state.get_data())["buttons"]) == 2)

    # 3) Tayyor -> preview -> auditoriya
    await admin.handle_broadcast_buttons_done(callback("adbtn_done"), state)
    check("tayyor: reklama ko'rinishi tugmalar bilan yuborildi, auditoriya so'raladi",
          msg.bot.send_message.await_args.kwargs["reply_markup"] is not None
          and await state.get_state() == AdminStates.waiting_for_broadcast_target.state)

    # Telegram havolani rad etsa, auditoriyaga o'tilmaydi
    state2 = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=2, user_id=1))
    await state2.set_state(AdminStates.waiting_for_broadcast_buttons)
    await state2.update_data(message_type="text", message_text="x", buttons=[{"text": "A", "kind": "url", "value": "https://a.uz"}])
    msg.bot.send_message = AsyncMock(side_effect=RuntimeError("BUTTON_URL_INVALID"))
    await admin.handle_broadcast_buttons_done(callback("adbtn_done"), state2)
    check("Telegram rad etsa — xato aytiladi, foydalanuvchilarga yuborilmaydi",
          "BUTTON_URL_INVALID" in sent[-1][0] and await state2.get_state() == AdminStates.waiting_for_broadcast_buttons.state)

    # Tugmasiz davom etish
    state3 = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=3, user_id=1))
    await state3.set_state(AdminStates.waiting_for_broadcast_buttons)
    await state3.update_data(message_type="text", message_text="x", buttons=[])
    await admin.handle_broadcast_buttons_skip(callback("adbtn_skip"), state3)
    check("tugmasiz davom etish: to'g'ridan-to'g'ri auditoriya", await state3.get_state() == AdminStates.waiting_for_broadcast_target.state)

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
