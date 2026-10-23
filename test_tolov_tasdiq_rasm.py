"""Admin to'lovni chek SURATI kartochkasidan tasdiqlaydi/rad etadi.

Ilgari: "there is no text in the message to edit" — pul tushardi, lekin admin "Xatolik" ko'rardi,
tugmalar qolardi. Endi kartochka izohi (caption) yangilanadi.

    python test_tolov_tasdiq_rasm.py
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


import config
import database.database as dbmod

dbmod.DATABASE_FILE = os.path.join(tempfile.mkdtemp(), "test.db")
from database.database import Database, init_db
from bot.handlers import admin


class PhotoCard:
    """Chek surati bilan kelgan admin kartochkasi: matni yo'q, izohi bor."""

    def __init__(self):
        self.text = None
        self.photo = [object()]
        self.document = None
        self.caption = "To'lov #? — chek"
        self.chat = SimpleNamespace(id=config.ADMIN_IDS[0])
        self.message_id = 10
        self.edits = []

    async def edit_text(self, *a, **kw):
        raise RuntimeError("Telegram server says - Bad Request: there is no text in the message to edit")

    async def edit_caption(self, caption=None, **kw):
        self.edits.append(("caption", caption, kw.get("reply_markup", "-")))

    async def edit_reply_markup(self, **kw):
        pass


class Bot:
    async def send_message(self, *a, **kw):
        pass


class Callback:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=config.ADMIN_IDS[0], username="admin", full_name="Admin")
        self.message = PhotoCard()
        self.bot = Bot()
        self.answers = []

    async def answer(self, text=None, **kw):
        self.answers.append(text)


async def main():
    await init_db()
    db = Database()
    user = await Database.create_user(77, "u77", "U", "uz")
    pid = await Database.create_payment(user.id, 10000, "file_id", "")
    cb = Callback(f"approve_payment_{pid}")
    await admin.approve_payment(cb, db)
    fresh = await Database.get_user(77)
    check("balansga tushdi", fresh.balance - user.balance == 10000, (user.balance, fresh.balance))
    check("admin 'Xatolik' ko'rmadi", "❌ Xatolik yuz berdi." not in cb.answers, cb.answers)
    check("rasm izohi yangilandi va tugmalar olindi",
          cb.message.edits and "tasdiqlandi" in cb.message.edits[0][1] and cb.message.edits[0][2] is None,
          cb.message.edits)

    pid2 = await Database.create_payment(user.id, 5000, "file_id", "")
    cb = Callback(f"reject_payment_{pid2}")
    await admin.reject_payment(cb, db)
    check("rad etish ham izohni yangiladi", cb.message.edits and "rad etildi" in cb.message.edits[0][1]
          and "❌ Xatolik yuz berdi." not in cb.answers, (cb.message.edits, cb.answers))


asyncio.run(main())
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
