"""Kitob tarjimasi: sayt orqali katta faylni yuklash, kitob matnini fonda
qismma-qism tarjima qilish (natija — toza DOCX), to'lov va xato holatlari.

Tarmoq kerak emas: tarjimon soxta. Kitob ham sintetik — sinov uchun
yozilgan jumlalar, rasmlar va jadval.

    python test_kitob_tarjima.py
"""
import asyncio, os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")
import aiohttp
import io
import numpy as np
import pymupdf
from PIL import Image
from aiohttp.test_utils import TestServer, TestClient
from aiogram.fsm.storage.memory import MemoryStorage
import webapp
from webapp import book_upload
from webapp.server import create_web_app
from bot.handlers import book_translate as bt
from bot.states import BookTranslateStates
from services import book_pdf_translate as bpt

import tempfile
SCR = tempfile.mkdtemp(prefix="kitob_")
FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

sent = []
class FakeBot:
    id = 42
    async def send_message(self, chat_id, text, **kw):
        sent.append(("msg", text, kw.get("reply_markup"))); return FakeMsg()
    async def send_document(self, chat_id, document, caption=None, **kw):
        sent.append(("doc", document.filename, os.path.getsize(document.path))); return FakeMsg()
    async def edit_message_text(self, text, **kw): sent.append(("edit", text))
    async def delete_message(self, *a, **kw): pass
class FakeMsg:
    def __init__(self):
        self.chat = types.SimpleNamespace(id=7); self.bot = BOT; self.message_id = len(sent) + 1
    async def delete(self): pass
    async def edit_text(self, text, **kw): sent.append(("edit", text))
    async def answer(self, text, **kw): sent.append(("msg", text, kw.get("reply_markup"))); return FakeMsg()
BOT = FakeBot()

FONT = next((f for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
                  "/usr/share/fonts/dejavu/DejaVuSerif.ttf") if os.path.exists(f)), None)
PARA = ("Это тестовый абзац номер {n}. Он нужен только для проверки того, как "
        "программа переносит строки, сохраняет отступы и заменяет текст на странице. "
        "Здесь нет никакого настоящего содержания, только простые предложения.")

def photo(seed):
    rng = np.random.default_rng(seed)
    base = np.linspace(0, 255, 1800)[None, :, None] * np.ones((1200, 1, 3))
    noise = rng.normal(0, 25, (1200, 1800, 3))
    arr = np.clip(base + noise, 0, 255).astype("uint8")
    buf = io.BytesIO(); Image.fromarray(arr).save(buf, format="JPEG", quality=95)
    return buf.getvalue()

def build(path, pages):
    doc = pymupdf.open()
    for n in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_font(fontname="dv", fontfile=FONT)
        page.insert_text((297, 40), f"Глава {n//5+1}. Проверочный раздел", fontname="dv", fontsize=8)
        page.insert_textbox(pymupdf.Rect(60, 60, 535, 90), f"{n+1}.1. Заголовок проверочной страницы", fontname="dv", fontsize=14)
        y = 95
        for k in range(2):
            page.insert_textbox(pymupdf.Rect(60, y, 535, y + 75), PARA.format(n=k+1), fontname="dv", fontsize=10.5, align=3)
            y += 80
        if n % 2 == 0:
            page.insert_image(pymupdf.Rect(90, 270, 505, 540), stream=photo(n))
            page.insert_textbox(pymupdf.Rect(90, 545, 505, 560), f"Рис. {n+1}. Подпись к проверочному рисунку.", fontname="dv", fontsize=9, align=1)
        else:
            # jadval: chiziqlar + kataklar
            for r in range(4):
                page.draw_line((60, 280 + r*30), (535, 280 + r*30))
            for c in range(3):
                page.draw_line((60 + c*237.5, 280), (60 + c*237.5, 370))
            for r, row in enumerate([("Показатель", "Значение"), ("Глубина кармана", "до 3 мм"), ("Кровоточивость", "нет")]):
                for c, cell in enumerate(row):
                    page.insert_textbox(pymupdf.Rect(64 + c*237.5, 284 + r*30, 293 + c*237.5, 306 + r*30), cell, fontname="dv", fontsize=10)
        page.insert_textbox(pymupdf.Rect(60, 580, 535, 700), "• Первый пункт списка.\n• Второй пункт списка чуть длиннее первого.\n• Третий пункт.", fontname="dv", fontsize=10.5)
        page.insert_text((290, 815), str(n + 1), fontname="dv", fontsize=9)
    doc.save(path)


async def main():
    build(f"{SCR}/book40.pdf", 12)
    webapp.BOT = BOT
    webapp.DISPATCHER = types.SimpleNamespace(storage=MemoryStorage())
    webapp.WEBAPP_DOMAIN = "edufayl.org"
    delivered = []
    async def capture(record, path, name):
        delivered.append((record, path, name))
    book_upload.ON_UPLOAD = capture

    client = TestClient(TestServer(create_web_app()))
    await client.start_server()
    try:
        url = book_upload.new_upload_link(7, 7, "uz")
        path = "/" + url.split("/", 3)[3]
        check("havola https va /book/upload", url.startswith("https://edufayl.org/book/upload/"), url)
        page = await client.get(path)
        body = await page.text()
        check("yuklash sahifasi ochiladi", page.status == 200 and 'id="file"' in body, page.status)

        data = aiohttp.FormData()
        data.add_field("file", b"hello", filename="x.txt")
        r = await client.post(path, data=data)
        check("noto'g'ri tur rad etiladi", r.status == 415, r.status)

        data = aiohttp.FormData()
        data.add_field("file", b"not a pdf at all", filename="fake.pdf")
        r = await client.post(path, data=data)
        check("PDF bo'lmagan .pdf rad etiladi", r.status == 415, r.status)

        old = book_upload.BOOK_MAX_UPLOAD_MB
        book_upload.BOOK_MAX_UPLOAD_MB = 1
        data = aiohttp.FormData()
        data.add_field("file", open(f"{SCR}/book40.pdf", "rb"), filename="kitob.pdf")
        r = await client.post(path, data=data)
        check("chegaradan katta fayl rad etiladi", r.status == 413, r.status)
        book_upload.BOOK_MAX_UPLOAD_MB = old

        data = aiohttp.FormData()
        data.add_field("file", open(f"{SCR}/book40.pdf", "rb"), filename="Kitob 2-qism.pdf")
        r = await client.post(path, data=data)
        await asyncio.sleep(0.1)
        check("32 MB kitob qabul qilinadi", r.status == 200 and delivered, (r.status, await r.text()))
        saved = delivered[0][1] if delivered else ""
        check("fayl to'liq yozildi", saved and os.path.getsize(saved) == os.path.getsize(f"{SCR}/book40.pdf"))
        r = await client.post(path, data=aiohttp.FormData([("file", b"x")]))
        check("havola bir martalik", r.status == 410, r.status)

        # ── Bo'laklab yuklash: uzilsa to'xtagan joyidan davom etadi
        url2 = book_upload.new_upload_link(8, 8, "uz")
        base = "/" + url2.split("/", 3)[3]
        blob = open(f"{SCR}/book40.pdf", "rb").read()
        size, step = len(blob), 700 * 1024
        r = await client.post(f"{base}/chunk?offset=0&size={size}", data=blob[:step])
        check("birinchi bo'lak qabul qilindi", r.status == 200 and (await r.json())["received"] == step)
        r = await client.post(f"{base}/chunk?offset=0&size={size}", data=blob[:step])
        check("takror bo'lakda qayerdan davom etish aytiladi",
              r.status == 409 and (await r.json())["received"] == step, r.status)
        r = await client.get(f"{base}/status")
        check("holat so'rovi", (await r.json())["received"] == step)
        r = await client.post(f"{base}/finish", json={"name": "k.pdf"})
        check("chala faylni yakunlab bo'lmaydi", r.status == 400, r.status)
        offset = step
        while offset < size:
            r = await client.post(f"{base}/chunk?offset={offset}&size={size}",
                                  data=blob[offset:offset + step])
            offset = (await r.json())["received"]
        before = len(delivered)
        r = await client.post(f"{base}/finish", json={"name": "Kitob bo'laklab.pdf"})
        await asyncio.sleep(0.1)
        ok = (r.status == 200 and len(delivered) == before + 1
              and open(delivered[-1][1], "rb").read() == blob)
        check("bo'laklab yuklangan fayl aynan asliday", ok, r.status)
        if len(delivered) > before:
            os.remove(delivered.pop()[1])
        url3 = book_upload.new_upload_link(9, 9, "uz")
        base3 = "/" + url3.split("/", 3)[3]
        await client.post(f"{base3}/chunk?offset=0&size=9", data=b"not a pdf")
        r = await client.post(f"{base3}/finish", json={"name": "x.pdf"})
        check("bo'laklab yuklangan soxta PDF rad etiladi", r.status == 415, r.status)
        r = await client.post(f"{base3}/chunk?offset=0&size={999 * 1024 * 1024}", data=b"%PDF")
        check("e'lon qilingan hajm chegaradan katta — rad", r.status == 413, r.status)

        link = book_upload.new_download_link(saved, "Kitob_uz.pdf")
        r = await client.get("/" + link.split("/", 3)[3])
        blob = await r.read()
        check("tayyor faylni saytdan yuklab olish", r.status == 200 and blob[:4] == b"%PDF"
              and "attachment" in r.headers.get("Content-Disposition", ""), r.status)
    finally:
        await client.close()

    # ── Bot oqimi: saytdan kelgan fayl → varoq oralig'i so'raladi
    sent.clear()
    record, saved, name = delivered[0]
    await bt._on_web_upload(record, saved, name)
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    state = FSMContext(storage=webapp.DISPATCHER.storage, key=StorageKey(bot_id=42, chat_id=7, user_id=7))
    st = await state.get_state(); data = await state.get_data()
    check("saytdan kelgan kitob bot oqimiga ulandi", st == BookTranslateStates.waiting_for_line_range.state, st)
    check("kitob tahlil qilindi (12 bet, ruscha)", data.get("total_pages") == 12 and data.get("source_lang") == "ru", data)

    # ── To'lov → fonda qismma-qism tarjima → bitta DOCX
    from services import book_jobs
    import database.database as dbm
    from docx import Document as Docx
    async def fake_texts(texts, source, target, progress=None, translator=None):
        return [f"Tarjima {i}: oʻzbekcha matn" for i, _ in enumerate(texts)]
    bpt_real = bpt.translate_texts
    bpt.translate_texts = fake_texts
    balance = {"v": 500000}
    async def upd(uid, delta): balance["v"] += delta
    dbm.Database.update_user_balance = staticmethod(upd)
    class DB:
        async def update_user_balance(self, uid, delta): balance["v"] += delta
    old_part = book_jobs.BOOK_PART_PAGES
    book_jobs.BOOK_PART_PAGES = 5
    user = types.SimpleNamespace(telegram_id=7, balance=500000)
    cb = types.SimpleNamespace(message=FakeMsg(), bot=BOT, answer=lambda *a, **k: asyncio.sleep(0))
    await state.update_data(price=100000, target_lang="uz", page_from=None, page_to=None)
    sent.clear()
    await bt._translate_pdf_book(cb, state, "uz", DB(), user, await state.get_data(), 100000)
    check("mijoz darhol bo'shatildi (kutish holati yo'q)", await state.get_state() is None)
    check("pul buyurtmada yechildi", balance["v"] == 400000, balance)
    await asyncio.gather(*list(book_jobs._tasks))
    docs = [s for s in sent if s[0] == "doc"]
    check("bitta DOCX yuborildi", len(docs) == 1 and docs[0][1] == "Kitob 2-qism_uz.docx", sent[-6:])
    check("kiruvchi fayl o'chirildi", not os.path.exists(saved))
    check("holat foizi ko'rsatildi", any(s[0] in ("msg", "edit") and "%" in s[1] for s in sent))
    data = await state.get_data()
    check("keyingi xizmatlar taklif qilindi", await state.get_state() == BookTranslateStates.post_translation.state)
    paras = [p.text for p in Docx(data["translated_path"]).paragraphs if p.text.strip()]
    check("DOCX da tarjima bor, rasm yo'q", paras and all("Tarjima" in p or not any("а" <= c <= "я" for c in p) for p in paras)
          and not Docx(data["translated_path"]).inline_shapes, paras[:3])
    check("sahifa raqamlari va kolontitul tushib qoldi",
          not any(p.strip().isdigit() for p in paras) and not any("Проверочный раздел" in p for p in paras), paras[:5])
    os.remove(data["translated_path"])

    # ── Bet chegarasida uzilgan abzats ulanadi, sarlavha ajratiladi
    items = bpt.join_page_breaks([
        {"text": "Birinchi betdagi gap davom", "page": 0, "heading": False, "translate": True},
        {"text": "etadi va shu yerda tugaydi.", "page": 1, "heading": False, "translate": True},
        {"text": "2-bob", "page": 1, "heading": True, "translate": True}])
    check("bet chegarasidagi abzats ulandi", len(items) == 2 and items[0]["text"].endswith("tugaydi."), items)

    # ── Bot qayta ishga tushsa, to'xtagan qismidan davom etadi
    import shutil
    sent.clear(); balance["v"] = 500000
    build(f"{SCR}/resume.pdf", 12)
    job = book_jobs.create_job(user_id=8, chat_id=8, lang="uz", pdf_path=f"{SCR}/resume.pdf",
        file_name="K2.pdf", target_lang="uz", source_lang="ru", start=0, stop=12, price=60000, charged=60000)
    first = await book_jobs._translate_part(BOT, job, 0, 5)
    job.update(next=5, parts=[first["path"]], status="running"); book_jobs._save(job)
    seen = []
    real_part = book_jobs._translate_part
    async def spy(bot, job, a, b):
        seen.append((a, b)); return await real_part(bot, job, a, b)
    book_jobs._translate_part = spy
    await book_jobs.resume_all(BOT)
    await asyncio.gather(*list(book_jobs._tasks))
    book_jobs._translate_part = real_part
    check("qayta ishga tushgach 6-betdan davom etdi", seen == [(5, 10), (10, 12)], seen)
    check("mijozga davom etayotgani aytildi", any("6-betdan" in s[1] for s in sent if s[0] == "msg"))
    check("natija yuborildi", [s[1] for s in sent if s[0] == "doc"] == ["K2_uz.docx"])

    # ── Mablag' tugasa: tayyor qism yuboriladi, qolgani uchun pul qaytadi
    calls = {"n": 0}
    async def credits_run_out(texts, source, target, progress=None, translator=None):
        calls["n"] += 1
        if calls["n"] > 1:
            raise bpt.BookNoCredits("402")
        return [f"Tarjima {i}" for i in range(len(texts))]
    bpt.translate_texts = credits_run_out
    import bot.handlers.premium_presentation as pp
    warned = []
    async def warn(bot, detail): warned.append(detail)
    pp._warn_admins_no_credits = warn
    old_tries = book_jobs.CREDIT_TRIES
    book_jobs.CREDIT_TRIES = 1
    build(f"{SCR}/credits.pdf", 10)
    sent.clear(); balance["v"] = 0
    job = book_jobs.create_job(user_id=9, chat_id=9, lang="uz", pdf_path=f"{SCR}/credits.pdf",
        file_name="K3.pdf", target_lang="uz", source_lang="ru", start=0, stop=10, price=50000, charged=50000)
    await book_jobs.run(BOT, job)
    book_jobs.CREDIT_TRIES = old_tries
    check("mablag' tugasa tayyor qism yuboriladi", [s[1] for s in sent if s[0] == "doc"] == ["K3_uz_1-5.docx"], sent)
    check("qolgan betlar uchun pul qaytdi va admin ogohlantirildi", balance["v"] == 25000 and warned, (balance, warned))
    check("ish papkasi tozalandi", not os.path.exists(book_jobs._job_dir(job["id"])))
    book_jobs.BOOK_PART_PAGES = old_part
    bpt.translate_texts = bpt_real

asyncio.run(main())

# ── Tarjima mijozi: 402, uzilgan javob, kirill javob
class Resp:
    def __init__(self, content, finish="stop"):
        self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=content), finish_reason=finish)]
class Err(Exception):
    def __init__(self, code): super().__init__(f"HTTP {code}"); self.status_code = code

async def client_tests():
    calls = []
    class Completions:
        async def create(self, model, messages, **kw):
            items = [l for l in messages[1]["content"].split("\n") if l.startswith("[[")]
            calls.append((model, len(items)))
            ids = [int(l[2:l.index("]]")]) for l in items]
            if mode == "402": raise Err(402)
            if mode == "cut" and len(items) > 2:
                return Resp(f"[[{ids[0]}]] birinchi", "length")
            if mode == "cyr" and model == bpt._models()[0]:
                return Resp("\n".join(f"[[{i}]] Это кириллица" for i in ids))
            return Resp("\n".join(f"[[{i}]] tarjima {i}" for i in ids))
    fake = types.SimpleNamespace(chat=types.SimpleNamespace(completions=Completions()), close=lambda: asyncio.sleep(0))
    bpt._client = lambda: fake
    global mode
    texts = [f"Абзац {i} с русским текстом." for i in range(6)]
    mode = "ok"
    out = await bpt.translate_texts(texts, "ru", "uz")
    check("hamma bo'lak tarjima qilindi", out == [f"tarjima {i}" for i in range(6)], out)
    mode = "cut"; calls.clear()
    out = await bpt.translate_texts(texts, "ru", "uz")
    check("uzilgan javobda bo'lak ikkiga bo'linadi", all(out), (out, calls))
    mode = "cyr"; calls.clear()
    out = await bpt.translate_texts(texts, "ru", "uz")
    check("kirill harfli 'o'zbekcha' javob rad etilib, keyingi model ishlaydi",
          all(o and "кир" not in o for o in out) and len({m for m, _ in calls}) > 1, (out, calls))
    mode = "402"
    try:
        await bpt.translate_texts(texts, "ru", "uz"); ok = False
    except bpt.BookNoCredits:
        ok = True
    check("402 da darhol to'xtaydi", ok)
asyncio.run(client_tests())
# ── Buyruq va menyu tugmasi kutish holatidan chiqaradi
import datetime
print("\nHolatlar:")
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.session.base import BaseSession
from aiogram.filters import Command, StateFilter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.context import FSMContext
from aiogram.types import Update, Message
from aiogram.methods import SendMessage
from bot.handlers import book_translate
from bot.middlewares import CommandResetMiddleware
from bot.states import BookTranslateStates, StorePublishStates

replies = []
class FakeSession(BaseSession):
    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, SendMessage):
            replies.append(method.text)
            return Message.model_validate({"message_id": 1, "date": 0, "chat": {"id": 5, "type": "private"}, "text": method.text})
        from aiogram.methods import GetMe
        from aiogram.types import User
        if isinstance(method, GetMe):
            return User(id=123, is_bot=True, first_name="B", username="edufaylbot")
        return True
    async def stream_content(self, *a, **k):
        yield b""
    async def close(self): pass

handled = []
tail = Router()
@tail.message(Command("admin"))
async def admin(m): handled.append("admin")
@tail.message(Command("bekor"), StateFilter(StorePublishStates))
async def bekor(m): handled.append("bekor")
@tail.message(F.text == "📄 Referat")
async def menu(m): handled.append("menu")
@tail.message()
async def catch(m): handled.append("catch")

async def state_main():
    bot = Bot("123:abc", session=FakeSession())
    dp = Dispatcher(storage=MemoryStorage())
    async def inject(handler, event, data):
        data.update(user_lang="uz", db=None, user=None); return await handler(event, data)
    dp.message.outer_middleware(CommandResetMiddleware())
    dp.message.middleware(inject)
    dp.include_router(book_translate.router)
    dp.include_router(tail)
    state = FSMContext(storage=dp.storage, key=StorageKey(bot_id=123, chat_id=5, user_id=5))
    n = [0]
    async def send(**msg):
        n[0] += 1
        base = {"message_id": n[0], "date": int(datetime.datetime.now().timestamp()),
                "chat": {"id": 5, "type": "private"}, "from": {"id": 5, "is_bot": False, "first_name": "T"}}
        base.update(msg)
        await dp.feed_update(bot, Update.model_validate({"update_id": n[0], "message": base}))
    ok = True
    def check(name, cond, detail=""):
        nonlocal ok
        if not cond: FAILS.append(name)
        print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
        ok &= bool(cond)

    for cmd in ("/admin", "/admin@edufaylbot"):
        await state.set_state(BookTranslateStates.waiting_for_file); replies.clear(); handled.clear()
        await send(text=cmd, entities=[{"type": "bot_command", "offset": 0, "length": len(cmd)}])
        check(f"{cmd} fayl kutilayotganda ham ishlaydi", handled == ["admin"] and not replies, (handled, replies))
        check("... va kutish bekor bo'ldi", await state.get_state() is None)

    await state.set_state(BookTranslateStates.waiting_for_line_range); handled.clear()
    await send(text="/admin", entities=[{"type": "bot_command", "offset": 0, "length": 6}])
    check("/admin varoq oralig'i kutilayotganda ham ishlaydi", handled == ["admin"], handled)

    await state.set_state(BookTranslateStates.waiting_for_file); replies.clear(); handled.clear()
    await send(text="📄 Referat")
    check("menyu tugmasi o'z ishini qiladi", handled == ["menu"] and not replies, (handled, replies))
    check("... kutish bekor bo'ldi", await state.get_state() is None)

    await state.set_state(BookTranslateStates.waiting_for_line_range); replies.clear(); handled.clear()
    await send(text="📄 Referat")
    check("varoq oralig'i kutilayotganda ham menyu tugmasi ishlaydi",
          handled == ["menu"] and not replies and await state.get_state() is None, (handled, replies))

    await state.set_state(BookTranslateStates.waiting_for_file); replies.clear(); handled.clear()
    await send(photo=[{"file_id": "x", "file_unique_id": "y", "width": 10, "height": 10}])
    check("rasm yuborilsa fayl turi haqida aytiladi, kutish qoladi",
          replies and "fayl turi" in replies[0].lower() and await state.get_state() == BookTranslateStates.waiting_for_file.state,
          (replies, await state.get_state()))

    await state.set_state(StorePublishStates.waiting_for_file) if hasattr(StorePublishStates, "waiting_for_file") else await state.set_state(list(StorePublishStates.__states__)[0])
    handled.clear()
    await send(text="/bekor", entities=[{"type": "bot_command", "offset": 0, "length": 6}])
    check("/bekor do'kon holatida ishlaydi (holat saqlanadi)", handled == ["bekor"], handled)
    await bot.session.close()
asyncio.run(state_main())

import shutil
shutil.rmtree(SCR, ignore_errors=True)
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
