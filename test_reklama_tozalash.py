"""Reklama tayyorlash: har bosqichda oldingi savol-javoblar o'chadi; ichki tugmalarda «Pul ishlab topish».

Soxta chat ekranda nima ko'rinib turganini sanaydi: bot yuborgan va admin yozgan har xabar ekranga
qo'shiladi, o'chirilgani olib tashlanadi. Har bosqichda ekranda faqat joriy bosqich xabarlari turishi kerak.

    python test_reklama_tozalash.py
"""
import asyncio, itertools, os, sys
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

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from bot import ad_buttons, keyboards
from bot.handlers import admin, payments
from bot.states import AdminStates

ADMIN_CHAT = 1
ids = itertools.count(100)
screen = {}            # message_id -> matn (adminning chatida ko'rinib turgan xabarlar)


def shown(text):
    mid = next(ids)
    screen[mid] = text
    return SimpleNamespace(message_id=mid, edit_text=AsyncMock(), edit_reply_markup=AsyncMock())


bot = MagicMock()


async def send(chat_id, *args, **kw):
    text = args[0] if args else kw.get("caption") or "[media]"
    return shown(text) if chat_id == ADMIN_CHAT else SimpleNamespace(message_id=0)
for name in ("send_message", "send_photo", "send_video", "send_document", "send_animation", "send_voice", "send_audio"):
    setattr(bot, name, AsyncMock(side_effect=send))


async def delete(chat_id, message_id):
    screen.pop(message_id, None)
    return True
bot.delete_message = AsyncMock(side_effect=delete)
bot.me = AsyncMock(return_value=SimpleNamespace(username="Edufayl_bot"))


async def answer(text, **kw):
    return shown(text)


def incoming(text=None, html=None, **media):
    """Admin yozgan xabar (u ham ekranda turadi)."""
    m = MagicMock()
    m.from_user = SimpleNamespace(id=1); m.chat = SimpleNamespace(id=ADMIN_CHAT); m.bot = bot; m.answer = answer
    m.text = text; m.html_text = html if html is not None else (text or "")
    for kind in ("photo", "video", "document", "animation", "voice", "audio"):
        setattr(m, kind, media.get(kind))
    m.message_id = shown(f"[admin] {text or 'media'}").message_id
    return m


def callback(data):
    cb = MagicMock(); cb.data = data; cb.answer = AsyncMock(); cb.from_user = SimpleNamespace(id=1)
    last = max(screen) if screen else 0
    cb.message = MagicMock(); cb.message.chat = SimpleNamespace(id=ADMIN_CHAT); cb.message.bot = bot
    cb.message.answer = answer; cb.message.message_id = last; cb.bot = bot
    return cb


def texts():
    return [screen[k] for k in sorted(screen)]


async def main():
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=ADMIN_CHAT, user_id=1))
    db = MagicMock(); db.get_all_users = AsyncMock(return_value=[SimpleNamespace(telegram_id=5000 + i,
                                                                                  updated_at=__import__("datetime").datetime.now())
                                                                  for i in range(3)])

    print("1) Har bosqichda ekranda faqat joriy savol")
    await admin.handle_broadcast_start(incoming("📤 Reklama yuborish"), state)
    check("boshlanish: tugma bosilgani va yo'riqnoma", len(screen) == 2, texts())

    await admin.handle_broadcast_message(incoming("Aksiya!", "<b>Aksiya!</b>"), state)
    check("matn bosqichi: faqat reklama ko'rinishi va «to'g'rimi?» (admin xabari va yo'riqnoma o'chdi)",
          len(screen) == 2 and texts()[0] == "<b>Aksiya!</b>" and "To'g'rimi" in texts()[1], texts())

    await admin.handle_ad_text_edit(callback("adtxt_edit"), state)
    check("tahrir: faqat «yangi matnni yuboring»", len(screen) == 1 and "Yangi matn" in texts()[0], texts())
    await admin.handle_ad_text_input(incoming("x" * 5000), state)
    check("xato javob: savol, admin javobi va xato ko'rinadi (tuzatish uchun)", len(screen) == 3 and "juda uzun" in texts()[-1], texts())
    await admin.handle_ad_text_input(incoming("Yangi aksiya"), state)
    check("to'g'ri javobdan keyin xato va eski javoblar o'chdi", len(screen) == 2 and texts()[0] == "Yangi aksiya", texts())

    await admin.handle_ad_text_ok(callback("adtxt_ok"), state, db)
    check("tugmalar savoli yolg'iz", len(screen) == 1 and "tugma qo'shasizmi" in texts()[0], texts())
    await admin.handle_broadcast_buttons_add(callback("adbtn_add"), state)
    check("tugma turi savoli yolg'iz", len(screen) == 1 and "nimaga olib borsin" in texts()[0], texts())

    print("2) Ichki tugma: «Pul ishlab topish»")
    await admin.handle_broadcast_button_menu_type(callback("adbtn_type_menu"), state)
    check("bo'limlar ro'yxati yolg'iz", len(screen) == 1, texts())
    sections = [b.callback_data for row in keyboards.get_broadcast_sections_keyboard().inline_keyboard for b in row]
    check("bo'limlar ro'yxatida «Pul ishlab topish» bor", "adbtn_pick:pul" in sections, sections)
    await admin.handle_broadcast_button_pick(callback("adbtn_pick:pul"), state)
    check("nom savoli yolg'iz", len(screen) == 1 and "nomni" in texts()[0], texts())
    await admin.handle_broadcast_button_defname(callback("adbtn_defname"), state)
    data = await state.get_data()
    check("tugma «💰 Pul ishlab topish» nomi bilan qo'shildi",
          data["buttons"] == [{"text": "💰 Pul ishlab topish", "kind": "menu", "value": "pul"}], data["buttons"])
    check("tugmalar ro'yxati yolg'iz, «qo'shildi» shu xabarning boshida",
          len(screen) == 1 and texts()[0].startswith("✅ Tugma qo'shildi."), texts())
    markup = ad_buttons.markup(data["buttons"])
    check("reklamadagi tugma `ad:pul`", markup.inline_keyboard[0][0].callback_data == "ad:pul")
    check("bosilganda «Pul ishlab topish» bo'limi ochiladi (har tilda)",
          ad_buttons.menu_text("pul", "uz") in payments.REFERRAL_TEXTS
          and ad_buttons.menu_text("pul", "ru") in payments.REFERRAL_TEXTS
          and ad_buttons.menu_text("pul", "kk") in payments.REFERRAL_TEXTS,
          [ad_buttons.menu_text("pul", l) for l in ("uz", "ru", "en", "kk")])

    print("3) Havola tugmasi: manzil va nom so'ralganda ham eski savollar o'chadi")
    await admin.handle_broadcast_buttons_add(callback("adbtn_add"), state)
    await admin.handle_broadcast_button_url_type(callback("adbtn_type_url"), state)
    await admin.handle_broadcast_button_url(incoming("nimadir"), state)
    check("noto'g'ri manzil: savol + javob + xato", len(screen) == 3, texts())
    await admin.handle_broadcast_button_url(incoming("https://edufayl.org"), state)
    check("nom savoli yolg'iz", len(screen) == 1 and "nomni" in texts()[0], texts())
    await admin.handle_broadcast_button_label(incoming("Saytga o'tish"), state)
    check("tugmalar ro'yxati yolg'iz (2 ta tugma)", len(screen) == 1 and "2." in texts()[0], texts())

    print("4) Kimga, tasdiq va yuborish")
    await admin.handle_broadcast_buttons_done(callback("adbtn_done"), state, db)
    check("«kimga?» yolg'iz", len(screen) == 1 and "Kimga" in texts()[0], texts())
    await admin.handle_broadcast_target(callback("broadcast_all"), state, db)
    check("tasdiq: reklama ko'rinishi va xulosa — boshqa hech narsa", len(screen) == 2 and "tasdiqlang" in texts()[1], texts())
    async def no_sleep(*a, **k): return None
    with patch("bot.handlers.admin.asyncio.sleep", no_sleep):
        await admin.handle_ad_confirmed(callback("adok"), state, db)
    check("yuborilgach ekranda faqat yakuniy natija", len(screen) == 1, texts())
    check("hammaga yuborildi (3 ta)", sum(1 for c in bot.send_message.await_args_list if c.args[0] != ADMIN_CHAT) == 3)

    print("5) Bekor qilish")
    state2 = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=ADMIN_CHAT, user_id=2))
    screen.clear()
    await admin.handle_broadcast_start(incoming("📤 Reklama yuborish"), state2)
    await admin.handle_broadcast_message(incoming("Matn"), state2)
    await admin.handle_ad_cancel(callback("adcancel"), state2)
    check("bekor qilinsa: faqat «bekor qilindi» xabari", len(screen) == 1 and "bekor" in texts()[0], texts())

asyncio.run(main())
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
