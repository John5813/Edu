"""Kitob tarjimasi: sayt orqali katta faylni yuklash, PDF ni joyida tarjima
qilish (rasmlar qoladi), to'lov va xato holatlari.

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
class FakeMsg:
    def __init__(self): self.chat = types.SimpleNamespace(id=7); self.bot = BOT
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

    # ── To'lov → tarjima (soxta tarjimon)
    async def fake_texts(texts, source, target, progress=None, translator=None):
        if progress: await progress(len(texts), len(texts))
        return [f"Tarjima {i}: oʻzbekcha matn" for i, _ in enumerate(texts)]
    bpt_real = bpt.translate_texts
    bpt.translate_texts = fake_texts
    charged = []
    class DB:
        async def update_user_balance(self, uid, delta): charged.append(delta)
    user = types.SimpleNamespace(telegram_id=7, balance=500000)
    cb = types.SimpleNamespace(message=FakeMsg(), bot=BOT, answer=lambda *a, **k: asyncio.sleep(0))
    await state.update_data(price=100000, target_lang="uz", page_from=None, page_to=None)
    sent.clear()
    await bt._translate_pdf_book(cb, state, "uz", DB(), user, await state.get_data(), 100000)
    docs = [s for s in sent if s[0] == "doc"]
    check("tarjima PDF yuborildi", docs and docs[0][1] == "Kitob 2-qism_uz.pdf", sent[-4:])
    check("pul faqat muvaffaqiyatdan keyin yechildi", charged == [-100000], charged)
    check("kiruvchi fayl o'chirildi", not os.path.exists(saved))
    data = await state.get_data()
    check("keyingi xizmatlar holati", await state.get_state() == BookTranslateStates.post_translation.state)
    text = bpt.read_text(data["translated_path"])
    check("tarjima matni o'qiladi", "Tarjima" in text, text[:80])
    os.remove(data["translated_path"])

    # ── Katta natija → saytdan yuklab olish havolasi
    import shutil
    shutil.copy(f"{SCR}/book40.pdf", f"{SCR}/book40_copy.pdf")
    await state.update_data(pdf_path=f"{SCR}/book40_copy.pdf", page_from=2, page_to=5)
    old_limit = bt.TELEGRAM_UPLOAD_LIMIT
    bt.TELEGRAM_UPLOAD_LIMIT = 600 * 1024
    sent.clear(); charged.clear()
    await bt._translate_pdf_book(cb, state, "uz", DB(), user, await state.get_data(), 30000)
    bt.TELEGRAM_UPLOAD_LIMIT = old_limit
    link_msgs = [s for s in sent if s[0] == "msg" and "48 soat" in s[1]]
    check("katta natija uchun yuklab olish havolasi", link_msgs and not [s for s in sent if s[0] == "doc"], sent)
    data = await state.get_data()
    check("oraliq tanlanganda faqat o'sha betlar", bpt.inspect_pdf(data["translated_path"]).total_pages == 4)
    check("havola berilgan fayl 'kerak emas'da o'chirilmaydi", data.get("translated_shared") is True)
    bt._drop_translated(data)
    check("... va haqiqatan qoldi", os.path.exists(data["translated_path"]))
    os.remove(data["translated_path"])

    # ── Mablag' tugasa: pul yechilmaydi
    async def no_credits(*a, **k):
        raise bpt.BookNoCredits("402")
    bpt.translate_texts = no_credits
    import bot.handlers.premium_presentation as pp
    warned = []
    async def warn(bot, detail): warned.append(detail)
    pp._warn_admins_no_credits = warn
    shutil.copy(f"{SCR}/book40.pdf", f"{SCR}/book40_copy.pdf")
    await state.update_data(pdf_path=f"{SCR}/book40_copy.pdf", page_from=1, page_to=2)
    sent.clear(); charged.clear()
    await bt._translate_pdf_book(cb, state, "uz", DB(), user, await state.get_data(), 30000)
    check("mablag' tugasa pul yechilmaydi va admin ogohlantiriladi",
          not charged and warned and any("vaqtincha" in s[1] for s in sent if s[0] == "msg"), sent)
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
import shutil
shutil.rmtree(SCR, ignore_errors=True)
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
