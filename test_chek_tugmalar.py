"""«To'lov chekini yuborish» va «Orqaga» tugmalari haqiqiy dispetcher orqali ishlaydi.

Ilgari ular bosilganda bot "Bu bosqichda boshqa javob kutilmoqda" der edi (o'z tugmasini tanimasdi).

    python test_chek_tugmalar.py
"""
import asyncio, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "123:abc")

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import GetMe, SendMessage
from aiogram.types import Message, Update, User

from bot.handlers import payments, start
from bot.states import PaymentStates

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

calls = []
def _msg(text=""):
    return Message.model_validate({"message_id": len(calls) + 1, "date": 0,
                                   "chat": {"id": 5, "type": "private"}, "text": text or "x"})
class FakeSession(BaseSession):
    async def make_request(self, bot, method, timeout=None):
        calls.append(method)
        if isinstance(method, GetMe):
            return User(id=123, is_bot=True, first_name="B", username="edufaylbot")
        if isinstance(method, SendMessage):
            return _msg(method.text).as_(bot)
        return True
    async def stream_content(self, *a, **k):
        yield b""
    async def close(self): pass

class FakeUser:
    telegram_id = 5; id = 1; language = "uz"; kazakh = False; username = "t"; balance = 0
class FakeDB:
    async def get_user(self, uid): return FakeUser()

async def main():
    bot = Bot("123:abc", session=FakeSession())
    dp = Dispatcher(storage=MemoryStorage())
    async def inject(handler, event, data):
        data.update(user_lang="uz", db=FakeDB(), user=FakeUser())
        return await handler(event, data)
    dp.message.middleware(inject)
    for router in (payments.router, start.router):          # asosiy dasturdagi tartib: payments avval, start oxirida
        dp.include_router(router)
    state = FSMContext(storage=dp.storage, key=StorageKey(bot_id=123, chat_id=5, user_id=5))
    n = [0]
    async def say(text):
        n[0] += 1
        calls.clear()
        await dp.feed_update(bot, Update.model_validate({"update_id": n[0], "message": {
            "message_id": n[0], "date": 0, "chat": {"id": 5, "type": "private"},
            "from": {"id": 5, "is_bot": False, "first_name": "T"}, "text": text}}))
        return [c.text for c in calls if isinstance(c, SendMessage)]

    await state.set_state(PaymentStates.waiting_for_screenshot)
    await state.update_data(payment_amount=10000)
    for button in ("📤 To'lov chekini yuborish", "📤 Отправить чек", "📤 Upload receipt"):
        await state.set_state(PaymentStates.waiting_for_screenshot)
        out = await say(button)
        check(f"«{button}» → chek so'raladi", out and "Chekni yuboring" in out[0] and "boshqa javob" not in out[0], out)
        check("   holat saqlanadi", await state.get_state() == PaymentStates.waiting_for_screenshot.state)
    await state.set_state(PaymentStates.waiting_for_screenshot)
    out = await say("🔙 Orqaga qaytish")
    check("«Orqaga» → bekor, menyu va summa tanlash", len(out) == 2 and "boshqa javob" not in " ".join(out) and "miqdorini tanlang" in out[1], out)
    check("   holat tozalandi", await state.get_state() is None)
    await state.set_state(PaymentStates.waiting_for_screenshot)
    out = await say("tasodifiy matn")
    check("boshqa matnga avvalgidek tushuntirish", out and "boshqa javob" in out[0], out)

asyncio.run(main())
print("\nXATO:" if FAILS else "\nHAMMASI YAXSHI", FAILS or "")
sys.exit(1 if FAILS else 0)
