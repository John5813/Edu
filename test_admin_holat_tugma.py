"""Admin kiritish kutayotgan holatda admin menyusi tugmasi o'z ishini qiladi.

Ilgari admin biror dialogni (reklama matni, mijozga xabar, promokod ...) tugatmay
"🔄 Botni yangilash" ni bossa, tugma o'sha dialogga javob bo'lib tushardi: promokod
yaratilar, mijozga xabar ketar yoki xabar jimgina o'chirilardi — yangilash ochilmasdi.

- har bir AdminStates holatida admin tugmasi kutishni bekor qiladi va o'z handleriga boradi;
- admin tugmasi bo'lmagan matn (summa, kod) avvalgidek dialogga tushadi;
- asosiy menyu tugmasi (reklama tugmasi nomi bo'lishi mumkin) AdminStates ni bekor qilmaydi.

    python test_admin_holat_tugma.py
"""
import asyncio, datetime, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")
os.chdir(tempfile.mkdtemp())      # vaqtinchalik baza shu papkada yaratiladi

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import GetMe
from aiogram.types import Message, Update, User

from bot.handlers import admin
from bot.middlewares import CommandResetMiddleware, DatabaseMiddleware
from bot.states import AdminStates
from services import self_update

ADMIN = 777
sent = []


class FakeSession(BaseSession):
    async def make_request(self, bot, method, timeout=None):
        sent.append((type(method).__name__, getattr(method, "text", None)))
        if isinstance(method, GetMe):
            return User(id=123, is_bot=True, first_name="B", username="b")
        if "Message" in str(method.__returning__):
            return Message.model_validate({"message_id": 1, "date": 0, "chat": {"id": ADMIN, "type": "private"},
                                           "text": getattr(method, "text", None) or "x"}).as_(bot)
        return True

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        pass


async def main():
    from database.database import init_db

    await init_db()
    admin.ADMIN_IDS = [ADMIN]
    self_update.status = lambda: {"ok": True, "branch": "main", "current": "abc", "incoming": [],
                                  "local_only": [], "dirty": []}
    bot = Bot("123:abc", session=FakeSession())
    dp = Dispatcher(storage=MemoryStorage())

    async def inject(handler, event, data):
        data.update(user_lang="uz")
        return await handler(event, data)

    dp.message.outer_middleware(CommandResetMiddleware())
    dp.message.middleware(DatabaseMiddleware())
    dp.message.middleware(inject)
    admin.router._parent_router = None
    dp.include_router(admin.router)
    key = StorageKey(bot_id=123, chat_id=ADMIN, user_id=ADMIN)
    n = [0]

    async def send(text, state):
        n[0] += 1
        sent.clear()
        await dp.storage.set_state(key, state)
        await dp.storage.set_data(key, {})
        try:
            await dp.feed_update(bot, Update.model_validate({"update_id": n[0], "message": {
                "message_id": n[0], "date": int(datetime.datetime.now().timestamp()),
                "chat": {"id": ADMIN, "type": "private"}, "from": {"id": ADMIN, "is_bot": False, "first_name": "A"},
                "text": text}}))
        except Exception as exc:       # dialog handleri tugmani o'z kiritishi deb yiqildi
            sent.append(("xato", repr(exc)[:80]))
        return list(sent), await dp.storage.get_state(key)

    print("1) Har bir admin holatida «🔄 Botni yangilash»")
    broken = []
    for state in AdminStates.__all_states__:
        replies, after = await send("🔄 Botni yangilash", state.state)
        if not any("GitHub" in str(text) for _, text in replies) or after is not None:
            broken.append((state.state, replies[:2], after))
    check(f"{len(AdminStates.__all_states__)} ta holatning hammasida yangilash ochiladi, kutish bekor bo'ladi",
          not broken, broken)

    print("2) Boshqa admin tugmasi ham")
    replies, after = await send("📊 Statistika", AdminStates.waiting_for_promocode.state)
    check("promokod kutilayotganda «📊 Statistika» promokod bo'lib qolmaydi",
          after is None and not any("Promokod yaratildi" in str(t) for _, t in replies), replies)

    print("3) Oddiy kiritish avvalgidek")
    replies, after = await send("abc", AdminStates.waiting_for_payment_amount.state)
    check("summa kutilganda oddiy matn dialogga tushadi", any("raqam" in str(t) for _, t in replies), replies)
    replies, after = await send("📞 Yordam", AdminStates.waiting_for_ad_button_label.state)
    check("asosiy menyu yozuvi (reklama tugmasi nomi) AdminStates ni bekor qilmaydi",
          not any("GitHub" in str(t) for _, t in replies) and after is not None, (replies, after))
    await bot.session.close()


asyncio.run(main())
print()
if FAILS:
    print(f"XATOLAR: {len(FAILS)}"); sys.exit(1)
print("Hammasi joyida")
