"""Admin: namunalarni bir nechtalab qo'shish (nom so'ralmaydi).

    python test_namuna_ommaviy.py
"""
import asyncio, datetime, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import EditMessageText, GetMe, SendMessage
from aiogram.types import Message, Update, User
from bot.handlers import samples
from bot.middlewares import CommandResetMiddleware

sent, edits = [], []
class FakeSession(BaseSession):
    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, SendMessage):
            sent.append(method.text)
            return Message.model_validate({"message_id": 100 + len(sent), "date": 0,
                                           "chat": {"id": 5, "type": "private"}, "text": method.text})
        if isinstance(method, EditMessageText):
            edits.append(method.text)
            return Message.model_validate({"message_id": 1, "date": 0, "chat": {"id": 5, "type": "private"}, "text": method.text})
        if isinstance(method, GetMe):
            return User(id=123, is_bot=True, first_name="B", username="edufaylbot")
        return True
    async def stream_content(self, *a, **k):
        yield b""
    async def close(self): pass

saved = []
class FakeDb:
    async def add_sample_file(self, title, description, file_id, file_type):
        saved.append((title, description, file_id, file_type)); return True

async def main():
    samples.ADMIN_IDS = [5]
    bot = Bot("123:abc", session=FakeSession())
    dp = Dispatcher(storage=MemoryStorage())
    async def inject(handler, event, data):
        data.update(user_lang="uz", db=FakeDb(), user=None); return await handler(event, data)
    dp.message.outer_middleware(CommandResetMiddleware())
    dp.message.middleware(inject); dp.callback_query.middleware(inject)
    samples.router._parent_router = None
    dp.include_router(samples.router)
    state = FSMContext(storage=dp.storage, key=StorageKey(bot_id=123, chat_id=5, user_id=5))
    n = [0]
    def base(user=5):
        return {"date": int(datetime.datetime.now().timestamp()), "chat": {"id": 5, "type": "private"},
                "from": {"id": user, "is_bot": False, "first_name": "A"}}
    async def send(user=5, **fields):
        n[0] += 1
        await dp.feed_update(bot, Update.model_validate({"update_id": n[0], "message": {"message_id": n[0], **base(user), **fields}}))
    async def press(data, user=5):
        n[0] += 1
        await dp.feed_update(bot, Update.model_validate({"update_id": n[0], "callback_query": {
            "id": str(n[0]), "chat_instance": "x", "data": data, "from": base(user)["from"],
            "message": {"message_id": 99, **base(user), "text": "x"}}}))
    doc = lambda name, fid: {"document": {"file_id": fid, "file_unique_id": fid, "file_name": name}}

    await press("add_sample")
    check("namuna qo'shish: fayl kutiladi", await state.get_state() == samples.SampleStates.waiting_for_file.state)

    await send(**doc("Mustaqil_ish_iqtisod.docx", "d1"))
    await send(**doc("Referat namunasi.pdf", "d2"), media_group_id="g1")
    await send(**doc("Taqdimot.pptx", "d3"), media_group_id="g1")
    await send(photo=[{"file_id": "p0", "file_unique_id": "a", "width": 10, "height": 10},
                      {"file_id": "p1", "file_unique_id": "b", "width": 100, "height": 100}], caption="Kurs ishi muqovasi\nIkkinchi qator")
    await send(video={"file_id": "v1", "file_unique_id": "v", "width": 10, "height": 10, "duration": 3})
    check("5 ta fayl saqlandi", len(saved) == 5, saved)
    check("nom so'ralmadi: holat fayl kutishda qoldi", await state.get_state() == samples.SampleStates.waiting_for_file.state)
    titles = [s[0] for s in saved]
    check("hujjat nomi: kengaytmasiz, pastki chiziqsiz", titles[:3] == ["Mustaqil ish iqtisod", "Referat namunasi", "Taqdimot"], titles)
    check("rasm: izohning birinchi qatori nom", titles[3] == "Kurs ishi muqovasi", titles)
    check("nomsiz video: «Namuna»", titles[4] == "Namuna", titles)
    check("fayl turlari va id to'g'ri", [(s[2], s[3]) for s in saved] == [("d1", "document"), ("d2", "document"), ("d3", "document"), ("p1", "photo"), ("v1", "video")], saved)
    check("tavsif bo'sh (so'ralmaydi)", all(s[1] == "" for s in saved))
    check("har fayl uchun alohida xabar emas: holat xabari bitta", len([t for t in sent if t.startswith("✅ Qo'shildi")]) == 1, sent)

    sent.clear()
    await press("sample_batch_done")
    check("«Tayyor»: holat tozalandi", await state.get_state() is None)
    check("yakuniy son aytildi", any("5 ta namuna" in t for t in edits + sent), (edits, sent))

    # admin bo'lmagan fayl yubora olmaydi
    saved.clear()
    await state.set_state(samples.SampleStates.waiting_for_file)
    await send(user=77, **doc("a.pdf", "x"))
    check("admin bo'lmagan foydalanuvchi fayli saqlanmaydi", not saved)

    # boshqa admin tugmasi kutishni bekor qiladi
    await state.set_state(samples.SampleStates.waiting_for_file)
    await send(text="📊 Statistika")
    check("admin menyusi tugmasi namuna kutishini bekor qiladi", await state.get_state() is None, await state.get_state())
    await bot.session.close()

asyncio.run(main())
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
