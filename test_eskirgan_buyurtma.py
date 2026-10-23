"""Hujjat sahifalari tanlanganda jarayon ma'lumoti yo'q bo'lsa (KeyError: 'document_type'): bot yiqilmaydi,
mijozga "qaytadan boshlang" deyiladi va holat tozalanadi.

    python test_eskirgan_buyurtma.py
"""
import asyncio
import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from bot.handlers import documents
from bot.states import DocumentStates

out = []


class Msg:
    async def answer(self, text, **kw):
        out.append(text)


class Callback:
    data = "pages_10_15"
    message = Msg()

    async def answer(self, *a, **kw):
        pass


async def main():
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=1, user_id=1))
    await state.set_state(DocumentStates.waiting_for_page_count)
    await documents.handle_page_count(Callback(), state, None, "uz", SimpleNamespace(balance=0))
    ok = len(out) == 1 and "eskirgan" in out[0] and await state.get_state() is None
    print(("  ok   " if ok else "  XATO ") + "ma'lumot yo'q — xabar va holat tozalandi", out)
    return ok


ok = asyncio.run(main())
print("\nNATIJA:", "HAMMASI O'TDI" if ok else "XATO")
sys.exit(0 if ok else 1)
