"""Reklama ostidagi tugmalar: tahlil, yuborish, ichki tugma bosilganda bo'lim ochilishi.

    python test_reklama_tugma.py
"""
import asyncio, os, sys
from datetime import datetime
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

# ── admin oqimi: kontent → matn → tugmalar → kimga → tasdiqlash → yuborish
from datetime import datetime, timedelta
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage

def users(n, old=0):
    now = datetime.now()
    return [SimpleNamespace(telegram_id=1000 + i, updated_at=now - timedelta(days=60 if i < old else 1)) for i in range(n)]

def make_db(n=5, old=2):
    db = MagicMock(); db.get_all_users = AsyncMock(return_value=users(n, old)); return db

async def flow():
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=1, user_id=1))
    sent = []
    msg = MagicMock(); msg.from_user = SimpleNamespace(id=1); msg.chat = SimpleNamespace(id=1)
    msg.bot = MagicMock()
    for name in ("send_message", "send_photo", "send_video", "send_document", "send_animation", "send_voice", "send_audio"):
        setattr(msg.bot, name, AsyncMock())
    msg.bot.me = AsyncMock(return_value=SimpleNamespace(username="Edufayl_bot"))
    async def answer(text, **kw):
        sent.append((text, kw.get("reply_markup")))
        return SimpleNamespace(edit_text=AsyncMock())
    msg.answer = answer
    db = make_db()

    def callback(data):
        cb = MagicMock(); cb.data = data; cb.answer = AsyncMock(); cb.from_user = msg.from_user
        cb.message = msg; cb.bot = msg.bot
        cb.message.edit_reply_markup = AsyncMock(); cb.message.edit_text = AsyncMock()
        return cb
    cbs = lambda i=-1: [b.callback_data for row in sent[i][1].inline_keyboard for b in row]
    st = lambda: state.get_state()

    # 0) admin menyusi tugmasi reklama matni bo'lib qolmaydi
    msg.text = "📤 Reklama yuborish"; msg.html_text = "📤 Reklama yuborish"
    await state.set_state(AdminStates.waiting_for_broadcast_message)
    await admin.handle_broadcast_message(msg, state)
    check("admin menyusi tugmasi reklama bo'lmaydi", "admin menyusi" in sent[-1][0] and await st() == AdminStates.waiting_for_broadcast_message.state, sent[-1][0])

    # 1) matn reklama: ko'rinish + "to'g'rimi?"
    msg.text = "Reklama matni"; msg.html_text = "<b>Reklama</b> matni"; msg.photo = None
    await admin.handle_broadcast_message(msg, state)
    check("matn: holat — matnni tekshirish", await st() == AdminStates.waiting_for_broadcast_text.state)
    check("matn: reklama ko'rinishi adminga yuborildi (HTML formatlash saqlangan)",
          msg.bot.send_message.await_args.args[1] == "<b>Reklama</b> matni" and msg.bot.send_message.await_args.kwargs["parse_mode"] == "HTML")
    check("matn: to'g'ri / tahrirlash / bekor (matnsiz tugmasi yo'q)", cbs() == ["adtxt_ok", "adtxt_edit", "adcancel"], cbs())

    # 2) tahrirlash
    await admin.handle_ad_text_edit(callback("adtxt_edit"), state)
    check("tahrirlashda yangi matn so'raladi", "Yangi matn" in sent[-1][0] and "adtxt_back" in cbs(), sent[-1][0])
    msg.text = "x" * 5000; msg.html_text = "x" * 5000
    await admin.handle_ad_text_input(msg, state)
    check("juda uzun matn rad etiladi, eskisi qoladi", "juda uzun" in sent[-1][0] and (await state.get_data())["message_text"] == "<b>Reklama</b> matni", sent[-1][0])
    msg.text = "Yangi matn"; msg.html_text = "Yangi <i>matn</i>"
    await admin.handle_ad_text_input(msg, state)
    check("yangi matn saqlandi va qayta ko'rsatildi", (await state.get_data())["message_text"] == "Yangi <i>matn</i>"
          and msg.bot.send_message.await_args.args[1] == "Yangi <i>matn</i>" and cbs() == ["adtxt_ok", "adtxt_edit", "adcancel"])
    msg.text = None; msg.html_text = ""
    await admin.handle_ad_text_input(msg, state)
    check("matn o'rniga rasm yuborilsa — xato", "Matn yuboring" in sent[-1][0])

    # 3) tasdiqlangach tugma so'raladi
    await admin.handle_ad_text_ok(callback("adtxt_ok"), state, db)
    check("matn to'g'ri: tugma so'raladi", await st() == AdminStates.waiting_for_broadcast_buttons.state and cbs() == ["adbtn_add", "adbtn_skip", "adcancel"], cbs())

    # 4) tugma qo'shish (havola)
    await admin.handle_broadcast_buttons_add(callback("adbtn_add"), state)
    check("tugma turi so'raladi", cbs() == ["adbtn_type_url", "adbtn_type_menu", "adbtn_back"], cbs())
    await admin.handle_broadcast_button_url_type(callback("adbtn_type_url"), state)
    check("manzil so'raladi va misolda adminning o'z boti", "@Edufayl_bot" in sent[-1][0] and "slaydtop" not in sent[-1][0].lower(), sent[-1][0])
    msg.text = "nimadir"
    await admin.handle_broadcast_button_url(msg, state)
    check("yaroqsiz manzilda xato", "❌" in sent[-1][0] and await st() == AdminStates.waiting_for_ad_button_url.state)
    msg.text = "https://example.uz/aksiya"
    await admin.handle_broadcast_button_url(msg, state)
    msg.text = "Aksiyani ko'rish"
    await admin.handle_broadcast_button_label(msg, state)
    buttons = (await state.get_data())["buttons"]
    check("havola tugma admin yozgan nom bilan saqlandi", buttons == [{"text": "Aksiyani ko'rish", "kind": "url", "value": "https://example.uz/aksiya"}], buttons)
    check("tugma qo'shilgach: yana / o'chirish / tayyor / bekor", cbs() == ["adbtn_add", "adbtn_undo", "adbtn_done", "adcancel"], cbs())

    # 5) ichki bo'lim tugmasi
    await admin.handle_broadcast_buttons_add(callback("adbtn_add"), state)
    await admin.handle_broadcast_button_menu_type(callback("adbtn_type_menu"), state)
    await admin.handle_broadcast_button_pick(callback("adbtn_pick:taqdimot"), state)
    await admin.handle_broadcast_button_defname(callback("adbtn_defname"), state)
    check("ichki bo'lim tugmasi standart nom bilan", (await state.get_data())["buttons"][-1] == {"text": "🌟 Taqdimot", "kind": "menu", "value": "taqdimot"})
    await admin.handle_broadcast_button_undo(callback("adbtn_undo"), state)
    check("oxirgi tugmani o'chirish", len((await state.get_data())["buttons"]) == 1)

    # 6) tayyor → kimga so'raladi (hali yuborilmaydi)
    msg.bot.send_message.reset_mock()
    await admin.handle_broadcast_buttons_done(callback("adbtn_done"), state, db)
    check("tugmalar tayyor: auditoriya so'raladi, hech narsa yuborilmadi",
          await st() == AdminStates.waiting_for_broadcast_target.state and not msg.bot.send_message.await_count)
    check("auditoriya tugmalarida bekor qilish bor", "adcancel" in cbs() and "broadcast_all" in cbs(), cbs())

    # 7) auditoriya tanlandi → YUBORILMAYDI, tasdiqlash so'raladi
    await admin.handle_broadcast_target(callback("broadcast_active"), state, db)
    check("auditoriya tanlangach tasdiqlash holati", await st() == AdminStates.waiting_for_broadcast_confirm.state)
    check("tasdiqlashda yakuniy ko'rinish (tugmalar bilan) adminning o'ziga yuborildi, 1 ta xabar",
          msg.bot.send_message.await_count == 1 and msg.bot.send_message.await_args.args[0] == 1 and msg.bot.send_message.await_args.kwargs["reply_markup"] is not None)
    summary = sent[-1][0]
    check("xulosada tur, tugma soni va faol foydalanuvchilar soni (3 ta)", "Matn" in summary and "1 ta" in summary and "<b>3</b>" in summary, summary)
    check("tasdiqlash tugmalari", cbs() == ["adok", "adedit_text", "adedit_btn", "adedit_aud", "adcancel"], cbs())

    # 8) tasdiqlashdan tahrirlash → qaytib tasdiqlashga keladi
    await admin.handle_ad_edit_text(callback("adedit_text"), state)
    check("tasdiqlashdan matn tahriri", await st() == AdminStates.waiting_for_broadcast_text.state)
    msg.text = "Yakuniy matn"; msg.html_text = "Yakuniy matn"
    await admin.handle_ad_text_input(msg, state)
    await admin.handle_ad_text_ok(callback("adtxt_ok"), state, db)
    check("tahrirdan keyin to'g'ridan-to'g'ri tasdiqlashga qaytdi (tugma/auditoriya qayta so'ralmadi)",
          await st() == AdminStates.waiting_for_broadcast_confirm.state and "Yakuniy matn" in str(msg.bot.send_message.await_args.args[1]))
    await admin.handle_ad_edit_audience(callback("adedit_aud"), state)
    await admin.handle_broadcast_target(callback("broadcast_all"), state, db)
    check("auditoriya o'zgartirildi: hammasi (5 ta)", "<b>5</b>" in sent[-1][0], sent[-1][0])

    # 9) tasdiqlandi → yuboriladi, holat darhol tozalanadi
    msg.bot.send_message.reset_mock()
    async def fake_sleep(*a, **k): return None
    with patch("bot.handlers.admin.asyncio.sleep", fake_sleep):
        await admin.handle_ad_confirmed(callback("adok"), state, db)
    check("tasdiqlangach 5 ta foydalanuvchiga yuborildi", msg.bot.send_message.await_count == 5, msg.bot.send_message.await_count)
    check("tugma bilan yuborildi", all(c.kwargs["reply_markup"] is not None for c in msg.bot.send_message.await_args_list))
    check("holat tozalandi (ikkinchi bosish qayta yubormaydi)", await st() is None)

    # 10) bekor qilish
    state2 = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=2, user_id=1))
    await state2.set_state(AdminStates.waiting_for_broadcast_confirm); await state2.update_data(message_type="text", message_text="x")
    msg.bot.send_message.reset_mock()
    await admin.handle_ad_cancel(callback("adcancel"), state2)
    check("bekor qilish: hech kimga yuborilmaydi, holat tozalanadi", not msg.bot.send_message.await_count and await state2.get_state() is None and "bekor" in sent[-1][0])

    # 11) Telegram havolani rad etsa — tasdiqlashgacha bilinadi
    state3 = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=3, user_id=1))
    await state3.set_state(AdminStates.waiting_for_broadcast_target)
    await state3.update_data(message_type="text", message_text="x", target="all", buttons=[{"text": "A", "kind": "url", "value": "https://a.uz"}])
    msg.bot.send_message = AsyncMock(side_effect=RuntimeError("BUTTON_URL_INVALID"))
    await admin.handle_broadcast_target(callback("broadcast_all"), state3, db)
    check("Telegram rad etsa — xato aytiladi, tugmalar bosqichiga qaytadi, tasdiqlash ko'rsatilmaydi",
          "BUTTON_URL_INVALID" in sent[-1][0] and await state3.get_state() == AdminStates.waiting_for_broadcast_buttons.state)
    msg.bot.send_message = AsyncMock()

    # 12) tugmasiz → to'g'ridan-to'g'ri kimga
    state4 = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=4, user_id=1))
    await state4.set_state(AdminStates.waiting_for_broadcast_buttons); await state4.update_data(message_type="text", message_text="x", buttons=[])
    await admin.handle_broadcast_buttons_skip(callback("adbtn_skip"), state4, db)
    check("tugmasiz davom etish: auditoriya so'raladi", await state4.get_state() == AdminStates.waiting_for_broadcast_target.state)

    # 13) RASM: izohsiz → "matn qo'shasizmi?"; izoh qo'shiladi; izohli → tuzatish
    state5 = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=5, user_id=1))
    await state5.set_state(AdminStates.waiting_for_broadcast_message)
    m = MagicMock(); m.from_user = msg.from_user; m.chat = msg.chat; m.bot = msg.bot; m.answer = answer
    m.text = None; m.photo = [SimpleNamespace(file_id="small"), SimpleNamespace(file_id="BIG")]; m.html_text = ""
    await admin.handle_broadcast_message(m, state5)
    d = await state5.get_data()
    check("rasm saqlandi (eng katta o'lcham), izoh bo'sh", d["message_type"] == "photo" and d["photo_id"] == "BIG" and d["caption"] == "", d)
    check("rasm ostiga matn qo'shasizmi? — qo'shish / matnsiz", "matn qo'shasizmi" in sent[-1][0] and cbs() == ["adtxt_edit", "adtxt_ok", "adcancel"], (sent[-1][0], cbs()))
    await admin.handle_ad_text_edit(callback("adtxt_edit"), state5)
    m.text = "Rasm tagidagi matn"; m.html_text = "Rasm tagidagi <b>matn</b>"
    await admin.handle_ad_text_input(m, state5)
    check("rasm izohi saqlandi va rasm shu izoh bilan ko'rsatildi",
          (await state5.get_data())["caption"] == "Rasm tagidagi <b>matn</b>" and msg.bot.send_photo.await_args.kwargs["caption"] == "Rasm tagidagi <b>matn</b>" and msg.bot.send_photo.await_args.kwargs["parse_mode"] == "HTML")
    check("izohli rasm: to'g'ri / tahrirlash / matnsiz", cbs() == ["adtxt_ok", "adtxt_edit", "adtxt_none", "adcancel"], cbs())
    m.text = "x" * 1100; m.html_text = "x" * 1100
    await admin.handle_ad_text_input(m, state5)
    check("izoh 1024 belgidan oshsa rad etiladi", "juda uzun" in sent[-1][0] and "1024" in sent[-1][0])
    await admin.handle_ad_text_ok(callback("adtxt_none"), state5, db)
    check("«Matnsiz yuborish»: izoh tozalanadi va tugmalarga o'tiladi", (await state5.get_data())["caption"] == "" and await state5.get_state() == AdminStates.waiting_for_broadcast_buttons.state)

    # 14) VIDEO / FAYL izoh bilan keladi
    for attr, kind, ident in (("video", "video", "video_id"), ("document", "document", "document_id")):
        stx = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=6, user_id=1))
        mm = MagicMock(); mm.from_user = msg.from_user; mm.chat = msg.chat; mm.bot = msg.bot; mm.answer = answer
        mm.text = None; mm.photo = None; mm.video = None; mm.document = None
        setattr(mm, attr, SimpleNamespace(file_id="F1")); mm.html_text = "Izoh bor"
        await admin.handle_broadcast_message(mm, stx)
        dd = await stx.get_data()
        check(f"{kind}: fayl va izoh saqlandi, matnni tekshirish so'raladi", dd[ident] == "F1" and dd["caption"] == "Izoh bor" and "adtxt_none" in cbs(), dd)

    # 15) _deliver: to'sib qo'ygan / xato / flood alohida sanaladi
    class Blocked(TelegramForbiddenError):
        def __init__(self): pass
    class Flood(TelegramRetryAfter):
        def __init__(self): self.retry_after = 0
    calls = {"n": 0}
    async def flaky(chat_id, *a, **k):
        calls["n"] += 1
        if chat_id == 1000: raise Blocked()
        if chat_id == 1001: raise RuntimeError("boom")
        if chat_id == 1002 and calls.get("flood") is None:
            calls["flood"] = 1; raise Flood()
        return None
    bot = MagicMock(); bot.send_message = flaky
    with patch("bot.handlers.admin.asyncio.sleep", fake_sleep):
        res = await admin._deliver(bot, users(4), {"message_type": "text", "message_text": "x"})
    check("_deliver: yuborildi 2 (flooddan keyin qayta urinish bilan), to'sgan 1, xato 1", res == (2, 1, 1), res)

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
