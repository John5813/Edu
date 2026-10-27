"""«Funksiyalar boshqaruvi»: tayyor fayllarni do'konga chiqarish tugmasi va panelni yopish.

- tugma holati, yoqish/o'chirish va o'chiq bo'lsa `schedule_publish` nashr qilmaydi;
- «❌ Yopish» xabarni o'chiradi, o'chirib bo'lmasa tugmalarni olib tashlaydi.

    python test_dokon_nashr.py
"""
import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "test.db")
config.ADMIN_IDS = [1]


def datas(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


async def main():
    from database.database import Database, init_db
    from bot.handlers import admin
    from services import store_publisher as sp

    await init_db()
    db = Database()

    print("1) Tugmalar")
    kb = await admin._feature_keyboard(db)
    check("sukut — yoqilgan, o'chirish tugmasi bor", "toggle_store_publish_off" in datas(kb), datas(kb))
    check("oxirida «❌ Yopish»", kb.inline_keyboard[-1][0].callback_data == "features_close"
          and "Yopish" in kb.inline_keyboard[-1][0].text)

    print("2) O'chirish")
    cb = SimpleNamespace(data="toggle_store_publish_off", answer=AsyncMock(), from_user=SimpleNamespace(id=1),
                         message=SimpleNamespace(edit_text=AsyncMock()))
    await admin.toggle_store_publish(cb, db)
    check("holat o'chdi", not await db.get_feature_status(sp.FEATURE))
    check("panel yangilandi", "toggle_store_publish_on" in datas(cb.message.edit_text.await_args.kwargs["reply_markup"]))

    print("3) O'chiq bo'lsa nashr qilinmaydi")
    src = os.path.join(TMP, "ish.docx")
    open(src, "wb").write(b"x")
    with patch.object(config, "STORE_AUTO_PUBLISH", True), patch.object(sp, "STORE_VAULT_CHAT_ID", -100), \
            patch.object(sp, "TEMP_DIR", TMP), patch.object(sp, "publish_work", AsyncMock()) as pw:
        sp.schedule_publish(None, src, "Mavzu", "referat")
        await asyncio.sleep(0.2)
        check("o'chiq: publish_work chaqirilmadi", not pw.await_count)
        await db.set_feature_status(sp.FEATURE, True)
        sp.schedule_publish(None, src, "Mavzu", "referat")
        await asyncio.sleep(0.2)
        check("yoqiq: publish_work chaqirildi", pw.await_count == 1)
    check("vaqtinchalik nusxalar o'chirildi", sorted(os.listdir(TMP)) == ["ish.docx", "test.db"], os.listdir(TMP))

    print("4) Yopish")
    msg = SimpleNamespace(delete=AsyncMock(), edit_reply_markup=AsyncMock())
    await admin.close_feature_management(SimpleNamespace(answer=AsyncMock(), message=msg))
    check("xabar o'chirildi", msg.delete.await_count == 1)
    msg = SimpleNamespace(delete=AsyncMock(side_effect=Exception("eski")), edit_reply_markup=AsyncMock())
    await admin.close_feature_management(SimpleNamespace(answer=AsyncMock(), message=msg))
    check("o'chmasa tugmalar olib tashlandi", msg.edit_reply_markup.await_args.kwargs == {"reply_markup": None})


asyncio.run(main())
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
