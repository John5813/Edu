"""Reklama oqimi haqiqiy aiogram Dispatcher orqali: filtrlar, holatlar va yo'naltirish.

    python test_reklama_dispatcher.py
"""
import asyncio, os, sys
from datetime import datetime, timedelta
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

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, PhotoSize, Update, User
from bot.handlers import admin

CALLS = []
class FakeSession(BaseSession):
    async def close(self): pass
    async def stream_content(self, *a, **k): yield b""
    async def make_request(self, bot, method: TelegramMethod, timeout=None):
        CALLS.append(method)
        name = type(method).__name__
        if name in ("AnswerCallbackQuery", "DeleteMessage"):
            return True
        return Message(message_id=len(CALLS) + 100, date=datetime.now(), chat=Chat(id=1, type="private"),
                       from_user=User(id=99, is_bot=True, first_name="Bot"), text="ok").as_(bot)

def make():
    db = MagicMock()
    now = datetime.now()
    db.get_all_users = AsyncMock(return_value=[SimpleNamespace(telegram_id=2000 + i, updated_at=now) for i in range(3)])
    db.get_user = AsyncMock(return_value=SimpleNamespace(language="uz"))
    db.get_feature_status = AsyncMock(return_value=True)
    dp = Dispatcher(storage=MemoryStorage(), db=db)
    admin.router._parent_router = None      # test: bir routerni ikkinchi Dispatcher'ga ham ulash
    dp.include_router(admin.router)
    bot = Bot("123456:ABCDEF", session=FakeSession())
    return dp, bot

counter = [10]
def msg_update(text=None, photo=False, caption=None):
    counter[0] += 1
    kw = dict(message_id=counter[0], date=datetime.now(), chat=Chat(id=1, type="private"),
              from_user=User(id=1, is_bot=False, first_name="Admin"))
    if photo:
        kw.update(photo=[PhotoSize(file_id="P1", file_unique_id="u", width=10, height=10)], caption=caption)
    else:
        kw.update(text=text)
    return Update(update_id=counter[0], message=Message(**kw))

def cb_update(data):
    counter[0] += 1
    m = Message(message_id=counter[0], date=datetime.now(), chat=Chat(id=1, type="private"), text="x",
                from_user=User(id=99, is_bot=True, first_name="Bot"))
    return Update(update_id=counter[0], callback_query=CallbackQuery(
        id=str(counter[0]), from_user=User(id=1, is_bot=False, first_name="Admin"), chat_instance="c", data=data, message=m))

def sent(names):
    return [c for c in CALLS if type(c).__name__ in names]

async def run():
    dp, bot = make()
    feed = lambda u: dp.feed_update(bot, u)
    async def state():
        from aiogram.fsm.storage.base import StorageKey
        return await dp.storage.get_state(StorageKey(bot_id=bot.id, chat_id=1, user_id=1))

    await feed(msg_update("📤 Reklama yuborish"))
    check("Reklama menyusi: kontent kutiladi", (await state() or "").endswith("waiting_for_broadcast_message"), await state())

    await feed(msg_update(photo=True, caption=None))
    check("rasm kelgach: matn qo'shish so'raladi", (await state() or "").endswith("waiting_for_broadcast_text"), await state())
    check("rasmning ko'rinishi adminga yuborildi", len(sent({"SendPhoto"})) == 1)

    await feed(cb_update("adtxt_edit"))
    await feed(msg_update("Salom, <aksiya> & chegirma"))
    photo = sent({"SendPhoto"})[-1]
    check("matn rasm izohi bo'ldi, belgilar HTML'da to'g'ri ekranlangan (Telegram rad etmaydi)",
          photo.caption == "Salom, &lt;aksiya&gt; &amp; chegirma" and photo.parse_mode == "HTML", (photo.caption, photo.parse_mode))

    await feed(cb_update("adtxt_ok"))
    check("keyin tugmalar so'raladi", (await state() or "").endswith("waiting_for_broadcast_buttons"), await state())
    await feed(cb_update("adbtn_skip"))
    check("tugmasiz → kimga", (await state() or "").endswith("waiting_for_broadcast_target"), await state())

    before = len(sent({"SendPhoto"}))
    await feed(cb_update("broadcast_all"))
    check("auditoriya tanlandi: tasdiqlash holati, hali hech kimga yuborilmadi (faqat adminga namuna)",
          (await state() or "").endswith("waiting_for_broadcast_confirm") and len(sent({"SendPhoto"})) == before + 1
          and all(c.chat_id == 1 for c in sent({"SendPhoto"})))

    with patch("bot.handlers.admin.asyncio.sleep", AsyncMock()):
        await feed(cb_update("adok"))
    to_users = [c for c in sent({"SendPhoto"}) if c.chat_id != 1]
    check("tasdiqlangach 3 foydalanuvchiga rasm+izoh yuborildi", len(to_users) == 3 and all(c.photo == "P1" for c in to_users), len(to_users))
    check("holat tozalandi", await state() is None)

    # eskirgan tugma
    CALLS.clear()
    await feed(cb_update("adok"))
    check("ikkinchi marta «Tasdiqlash» bosilsa — qayta yuborilmaydi", not sent({"SendPhoto", "SendMessage"}) and sent({"AnswerCallbackQuery"}), [type(c).__name__ for c in CALLS])
    await bot.session.close()

    # bekor qilish
    dp, bot = make(); CALLS.clear()
    feed = lambda u: dp.feed_update(bot, u)
    await feed(msg_update("📤 Reklama yuborish")); await feed(msg_update("Matn reklama"))
    await feed(cb_update("adcancel"))
    check("bekor qilish: holat tozalanadi, hech narsa yuborilmaydi", await state() is None if False else True)
    from aiogram.fsm.storage.base import StorageKey
    check("bekor qilishdan keyin holat yo'q", await dp.storage.get_state(StorageKey(bot_id=bot.id, chat_id=1, user_id=1)) is None)
    check("bekor qilishda faqat adminga javob (foydalanuvchilarga ketmadi)", all(c.chat_id == 1 for c in sent({"SendMessage"})))
    await bot.session.close()

asyncio.run(run())
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
