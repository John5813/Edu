"""/start ikki marta tez bosilganda: mijoz bir marta yaratiladi, bonus bir marta, xato xabari chiqmaydi.

    python test_start_parallel.py
"""
import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        FAILS.append(name)


import database.database as dbmod

dbmod.DATABASE_FILE = os.path.join(tempfile.mkdtemp(), "test.db")

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from database.database import Database, init_db
from bot.handlers import start


class Msg:
    def __init__(self, uid):
        self.text = "/start"
        self.from_user = SimpleNamespace(id=uid, username=None, first_name="U")
        self.chat = SimpleNamespace(id=uid)
        self.bot = SimpleNamespace(send_message=self._send)
        self.out = []

    async def _send(self, *a, **kw):
        pass

    async def answer(self, text, **kw):
        self.out.append(text)


async def main():
    await init_db()
    db = Database()
    await db.set_feature_status("startup_bonus", True)
    real_get_user = Database.get_user
    seen = {"n": 0}

    async def slow_get_user(telegram_id):
        # Ikkala so'rov ham "mijoz yo'q" deb ko'rsin (haqiqiy poyga holati).
        seen["n"] += 1
        if seen["n"] <= 2:
            await asyncio.sleep(0.05)
            return None
        return await real_get_user(telegram_id)

    db.get_user = slow_get_user
    msgs = [Msg(555), Msg(555)]
    for m in msgs:
        state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=555, user_id=555))
        m.state = state
    await asyncio.gather(*(start.start_command(m, m.state, db) for m in msgs))
    user = await real_get_user(555)
    texts = [t for m in msgs for t in m.out]
    check("mijoz yaratildi", user is not None)
    check("start bonusi bir marta (5000)", user and user.balance == 5000, user and user.balance)
    check("xato xabari yo'q", not any("Xatolik" in t for t in texts), texts)
    check("ikkalasiga ham til tanlash ko'rsatildi", sum("Tilni tanlang" in t for t in texts) == 2, texts)


asyncio.run(main())
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
