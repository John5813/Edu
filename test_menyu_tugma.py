"""Mavzu so'ralganda boshqa menyu tugmasi bosilsa u mavzu bo'lib qolmaydi.

    python test_menyu_tugma.py
"""
import asyncio, datetime, os, sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.base import BaseSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import DeleteMessage, GetMe, SendMessage
from aiogram.types import Message, Update, User
from bot.handlers import premium_presentation as pp
from bot.keyboards import get_main_keyboard
from bot.middlewares import CommandResetMiddleware
from bot.states import PremiumPresentationStates as PS

sent = []
class FakeSession(BaseSession):
    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, SendMessage):
            sent.append(method.text)
            return Message.model_validate({"message_id": 50 + len(sent), "date": 0,
                                           "chat": {"id": 5, "type": "private"}, "text": method.text})
        if isinstance(method, GetMe):
            return User(id=123, is_bot=True, first_name="B", username="edufaylbot")
        return True
    async def stream_content(self, *a, **k):
        yield b""
    async def close(self): pass

class FakeDb:
    async def get_user(self, user_id): return None
    async def get_active_channels(self): return []

LABELS = {lang: [b.text for row in get_main_keyboard(lang).keyboard for b in row] for lang in ("uz", "ru", "en")}
OTHER = {lang: LABELS[lang][0] for lang in LABELS}        # "Boshqa professional xizmatlar"

handled = []
tail = Router()
@tail.message(F.text.in_(set(sum(LABELS.values(), []))))
async def menu(m): handled.append(("menu", m.text))
@tail.message()
async def catch(m): handled.append(("catch", m.text))

async def main():
    bot = Bot("123:abc", session=FakeSession())
    dp = Dispatcher(storage=MemoryStorage())
    async def inject(handler, event, data):
        data.update(user_lang="uz", db=FakeDb(), user=None); return await handler(event, data)
    dp.message.outer_middleware(CommandResetMiddleware())
    dp.message.middleware(inject)
    pp.router._parent_router = None
    dp.include_router(pp.router)
    dp.include_router(tail)
    state = FSMContext(storage=dp.storage, key=StorageKey(bot_id=123, chat_id=5, user_id=5))
    n = [0]
    async def send(text):
        n[0] += 1
        await dp.feed_update(bot, Update.model_validate({"update_id": n[0], "message": {
            "message_id": n[0], "date": int(datetime.datetime.now().timestamp()),
            "chat": {"id": 5, "type": "private"}, "from": {"id": 5, "is_bot": False, "first_name": "T"},
            "text": text}}))

    # Taqdimot tugmasi → mavzu so'raladi
    await send(LABELS["uz"][1] if "Taqdimot" in LABELS["uz"][1] else "🌟 Taqdimot")
    check("taqdimot mavzu so'raydi", await state.get_state() == PS.waiting_for_topic_text.state, await state.get_state())

    for lang in ("uz", "ru", "en"):
        for label in LABELS[lang]:
            if label in ("🌟 Taqdimot", "🌟 Presentation", "🌟 Презентация"):
                continue
            await state.set_state(PS.waiting_for_topic_text); await state.set_data({}); handled.clear()
            await send(label)
            ok = handled == [("menu", label)] and await state.get_state() is None and "topic" not in await state.get_data()
            check(f"[{lang}] «{label}» mavzu bo'lib qolmadi", ok, (handled, await state.get_state(), await state.get_data()))

    # Boshqa bosqichlarda ham (ism, tushuntirish)
    for st in (PS.waiting_for_client_name, PS.waiting_for_preferences):
        await state.set_state(st); handled.clear()
        await send(OTHER["uz"])
        check(f"{st.state.split(':')[1]} da ham menyu tugmasi ishlaydi",
              handled == [("menu", OTHER["uz"])] and await state.get_state() is None, handled)

    # Oddiy mavzu esa mavzu bo'lib qoladi
    await state.set_state(PS.waiting_for_topic_text); await state.set_data({}); handled.clear()
    await send("Kvadrat tenglama va funksiyalar")
    data = await state.get_data()
    check("oddiy matn mavzu sifatida qabul qilinadi", data.get("topic") == "Kvadrat tenglama va funksiyalar" and not handled, (data, handled))
    check("... va keyingi bosqichga o'tildi", await state.get_state() == PS.waiting_for_client_name.state, await state.get_state())
    await bot.session.close()

asyncio.run(main())
print("\nHAMMASI O'TDI" if not FAILS else f"\nXATOLAR: {FAILS}")
sys.exit(1 if FAILS else 0)
