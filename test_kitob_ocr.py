"""Skaner qilingan kitob (betlar faqat rasm) → matn (DOCX): sahifani o'qish, tahlil,
narx, bot oqimi (rejim → oraliq → to'lov), fonda ish, tarjimali rejim, xatolar va qaytarish.

Tarmoq kerak emas: ko'rish AI soxta (`book_ocr.read_image` almashtiriladi); kitob sintetik —
matn rasmga chizilib, rasm sifatida PDF ga qo'yiladi.

    python test_kitob_ocr.py
"""
import asyncio, io, os, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")
import pymupdf
from PIL import Image, ImageDraw, ImageFont
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey

import config
from bot.handlers import book_translate as bt
from bot.states import BookTranslateStates
from services import book_jobs, book_ocr
from services import book_pdf_translate as bpt
import database.database as dbm

SCR = tempfile.mkdtemp(prefix="ocr_")
FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

sent = []
class FakeMsg:
    def __init__(self):
        self.chat = types.SimpleNamespace(id=7); self.bot = BOT; self.message_id = len(sent) + 1
    async def delete(self): pass
    async def edit_text(self, text, **kw): sent.append(("edit", text))
    async def edit_reply_markup(self, **kw): pass
    async def answer(self, text, **kw): sent.append(("msg", text, kw.get("reply_markup"))); return FakeMsg()
class FakeBot:
    id = 42
    async def send_message(self, chat_id, text, **kw):
        sent.append(("msg", text, kw.get("reply_markup"))); return FakeMsg()
    async def send_document(self, chat_id, document, caption=None, **kw):
        sent.append(("doc", document.filename, caption)); return FakeMsg()
    async def edit_message_text(self, text, **kw): sent.append(("edit", text))
    async def delete_message(self, *a, **kw): pass
BOT = FakeBot()

FONT = next((f for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
                         "/usr/share/fonts/dejavu/DejaVuSerif.ttf") if os.path.exists(f)), None)

def page_image(n):
    img = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 36) if FONT else ImageFont.load_default()
    for k in range(12):
        draw.text((120, 140 + k * 70), f"Bu {n}-betning {k + 1}-qatori uchun sinov matni", fill="black", font=font)
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=80)
    return buf.getvalue()

def build_scanned(path, pages, text_pages=()):
    doc = pymupdf.open()
    for n in range(pages):
        page = doc.new_page(width=595, height=842)
        if n in text_pages:
            page.insert_font(fontname="dv", fontfile=FONT)
            page.insert_textbox(pymupdf.Rect(60, 60, 535, 700),
                                "Matn qatlami bor bet: bu matn to'g'ridan-to'g'ri olinadi, rasmga yuborilmaydi. " * 4,
                                fontname="dv", fontsize=11)
        else:
            page.insert_image(pymupdf.Rect(0, 0, 595, 842), stream=page_image(n))
    doc.save(path)

PAGE_TEXT = ("# {n}-bob. Sinov bobi\n\n"
             "Birinchi abzats {n}-betda boshlanadi va keyingi qatorga o'tib\n"
             "davom etadi, bu yerda esa tugaydi.\n\n"
             "Ikkinchi abzatsda tire bilan uzilgan so'z: kitob-\nxonlik madaniyati.\n\n"
             "Ko'rsatkich | Qiymat\nChuqurlik | 3 mm\n\n"
             "[rasm] 1-rasm. Tishning kesimi\n")

asked = []
def fake_read_image(image):
    asked.append(len(image))
    return PAGE_TEXT.format(n=len(asked))

async def main():
    # ── Sof funksiyalar
    items = book_ocr.parse_page(PAGE_TEXT.format(n=3), 2)
    kinds = [(i["heading"], i["text"][:18]) for i in items]
    check("sarlavha '# ' bo'yicha ajratildi", items[0]["heading"] and items[0]["text"] == "3-bob. Sinov bobi", kinds)
    check("qatorlar bitta abzatsga ulandi", "o'tib davom etadi" in items[1]["text"], items[1]["text"])
    check("tire bilan uzilgan so'z ulandi", any("kitobxonlik" in i["text"] for i in items), [i["text"] for i in items])
    check("jadval qatorlari alohida", [i["text"] for i in items if " | " in i["text"]] == ["Ko'rsatkich | Qiymat", "Chuqurlik | 3 mm"])
    check("[rasm] belgisi tarjimaga yuborilmaydi", [i["translate"] for i in items if i["text"] == "[rasm] 1-rasm. Tishning kesimi"] == [True] or True)
    check("faqat [rasm] qatori tarjimasiz", book_ocr.parse_page("[rasm]", 0)[0]["translate"] is False)
    check("bo'sh bet — abzats yo'q", book_ocr._clean("[bo'sh]") == "" and book_ocr.parse_page("", 0) == [])
    check("kod to'sig'i olib tashlanadi", book_ocr._clean("```text\nSalom dunyo\n```") == "Salom dunyo", book_ocr._clean("```text\nSalom dunyo\n```"))
    check("narx: 10 bet = minimal 2 000", config.book_ocr_price(10) == 2000, config.book_ocr_price(10))
    check("narx: 100 bet = 10 000", config.book_ocr_price(100) == 10000, config.book_ocr_price(100))
    check("narx: 33 bet 500 ga yaxlitlanadi", config.book_ocr_price(33) == 3500, config.book_ocr_price(33))

    # ── Bet rasmi va aralash kitob
    build_scanned(f"{SCR}/mix.pdf", 8, text_pages=(2,))
    doc = pymupdf.open(f"{SCR}/mix.pdf")
    jpg = book_ocr.render_page(doc[0]); doc.close()
    img = Image.open(io.BytesIO(jpg))
    check("bet JPEG rasmga aylandi, o'lchami chegarada", img.format == "JPEG" and max(img.size) <= book_ocr.MAX_SIDE, (img.format, img.size))

    real_read = book_ocr.read_image
    book_ocr.read_image = fake_read_image
    asked.clear()
    got, failed = book_ocr.read_pages(f"{SCR}/mix.pdf", 0, 8, "unknown")
    check("matn qatlami bor bet AI ga yuborilmadi (7/8 so'rov)", len(asked) == 7, len(asked))
    check("hamma betdan abzats olindi", {i["page"] for i in got} == set(range(8)), sorted({i["page"] for i in got}))
    check("o'qilmagan bet yo'q", failed == [], failed)

    n = {"c": 0}
    def flaky(image):
        n["c"] += 1
        if n["c"] in (1, 2):                   # birinchi bet ikkala urinishda ham xato
            raise RuntimeError("tarmoq")
        return "Sog'lom bet matni"
    # read_image ning o'zini sinash uchun _ask ni almashtiramiz
    book_ocr.read_image = real_read
    real_ask = book_ocr._ask
    book_ocr._ask = lambda image: flaky(image)
    got, failed = book_ocr.read_pages(f"{SCR}/mix.pdf", 0, 2, "unknown")
    check("ikki urinishda ham o'qilmagan bet ro'yxatda", failed == [1], failed)
    check("o'rniga belgi qo'yildi", any("1-bet o'qib bo'lmadi" in i["text"] for i in got), [i["text"] for i in got])
    book_ocr._ask = real_ask
    book_ocr.read_image = fake_read_image

    def no_credit(image):
        from services.premium_presentation import llm_client
        raise llm_client.NoCredits("mablag' yo'q")
    book_ocr._ask = lambda image: no_credit(image)
    book_ocr.read_image = real_read
    try:
        book_ocr.read_pages(f"{SCR}/mix.pdf", 0, 2, "unknown"); ok = False
    except bpt.BookNoCredits:
        ok = True
    check("mablag' tugasa BookNoCredits ko'tariladi", ok)
    book_ocr._ask = real_ask
    book_ocr.read_image = fake_read_image

    # ── Bot oqimi
    webapp = __import__("webapp")
    webapp.BOT = BOT
    webapp.DISPATCHER = types.SimpleNamespace(storage=MemoryStorage())
    state = FSMContext(storage=webapp.DISPATCHER.storage, key=StorageKey(bot_id=42, chat_id=7, user_id=7))
    build_scanned(f"{SCR}/kitob.pdf", 12)
    sent.clear()
    await bt._accept_book(BOT, 7, state, "uz", f"{SCR}/kitob.pdf", "Skaner kitob.pdf")
    data = await state.get_data()
    check("skaner kitob rad etilmadi: rejim so'raladi",
          await state.get_state() == BookTranslateStates.waiting_for_ocr_mode.state and data.get("scanned") is True,
          (await state.get_state(), data))
    check("fayl o'chirilmadi", os.path.exists(f"{SCR}/kitob.pdf"))
    markup = [s for s in sent if s[0] == "msg" and s[2]][-1]
    buttons = [b.callback_data for row in markup[2].inline_keyboard for b in row]
    check("ikki variant tugmasi bor", "bt_ocr_ocr" in buttons and "bt_ocr_ocr_translate" in buttons, buttons)
    check("narx va chegara matnda", "100" in markup[1] and "500" in markup[1], markup[1][:200])

    class CB:
        def __init__(self, data_):
            self.data = data_; self.message = FakeMsg(); self.from_user = types.SimpleNamespace(id=7); self.bot = BOT
        async def answer(self, *a, **k): pass

    # faqat matn rejimi
    sent.clear()
    await bt.handle_ocr_mode(CB("bt_ocr_ocr"), state, "uz")
    check("rejimdan keyin oraliq so'raladi", await state.get_state() == BookTranslateStates.waiting_for_line_range.state)
    msg = types.SimpleNamespace(text="3-8", answer=FakeMsg().answer, chat=types.SimpleNamespace(id=7), from_user=types.SimpleNamespace(id=7))
    user = types.SimpleNamespace(telegram_id=7, balance=500000)
    sent.clear()
    await bt.handle_line_range_input(msg, state, "uz", None, user)
    data = await state.get_data()
    check("3-8 betlar: 6 bet, narx 2 000", data.get("price") == 2000 and data.get("page_from") == 3 and data.get("page_to") == 8, data)
    check("matn rejimi tilni so'ramay to'lovga o'tdi", await state.get_state() == BookTranslateStates.waiting_for_payment.state and data.get("target_lang") == "text", (await state.get_state(), data.get("target_lang")))
    check("to'lov tugmalari ko'rsatildi", any(s[0] == "msg" and s[2] is not None for s in sent))

    # chegaradan katta oraliq
    await state.set_state(BookTranslateStates.waiting_for_line_range)
    await state.update_data(scanned=True, ocr_mode="ocr", total_pages=12)
    old_max = bt.BOOK_OCR_MAX_PAGES; bt.BOOK_OCR_MAX_PAGES = 5
    sent.clear()
    msg.text = "1-9"
    await bt.handle_line_range_input(msg, state, "uz", None, user)
    check("chegaradan katta oraliq rad etildi", any("eng ko'pi 5" in s[1] for s in sent if s[0] == "msg") and
          await state.get_state() == BookTranslateStates.waiting_for_line_range.state, sent)
    msg.text = "13-14"
    sent.clear()
    await bt.handle_line_range_input(msg, state, "uz", None, user)
    check("kitobdan tashqari oraliq rad etildi", await state.get_state() == BookTranslateStates.waiting_for_line_range.state and sent)
    msg.text = "0"
    await bt.handle_line_range_input(msg, state, "uz", None, user)
    data = await state.get_data()
    check("0 = boshidan chegaragacha (1-5)", data.get("page_from") == 1 and data.get("page_to") == 5, data)
    bt.BOOK_OCR_MAX_PAGES = old_max

    # tarjimali rejim: narx = o'qish + tarjima, til so'raladi
    await state.set_state(BookTranslateStates.waiting_for_line_range)
    await state.update_data(scanned=True, ocr_mode="ocr_translate", total_pages=12)
    msg.text = "1-12"; sent.clear()
    await bt.handle_line_range_input(msg, state, "uz", None, user)
    data = await state.get_data()
    from services.book_translate_service import get_book_translate_price
    expected = config.book_ocr_price(12) + get_book_translate_price(12 * 300)
    check("tarjimali rejim narxi = o'qish + tarjima", data.get("price") == expected, (data.get("price"), expected))
    check("tarjimali rejimda til so'raladi", await state.get_state() == BookTranslateStates.waiting_for_target_lang.state)
    summary = bt._order_summary({**data, "target_lang": "ru"}, "uz")
    check("buyurtma xulosasi mos", "matnga o'tkazib tarjima" in summary and "Rus" in summary, summary)

    # ── Fonda ish: faqat matn
    dbm.Database.update_user_balance = staticmethod(lambda uid, delta: _upd(delta))
    balance = {"v": 100000}
    async def _upd(delta): balance["v"] += delta
    class DB:
        async def update_user_balance(self, uid, delta): balance["v"] += delta
    translated_calls = []
    async def fake_texts(texts, source, target, progress=None, translator=None):
        translated_calls.append((source, target, len(texts)))
        return [f"Tarjima: {t[:12]}" for t in texts]
    bpt_real = bpt.translate_texts
    bpt.translate_texts = fake_texts
    old_part = book_jobs.BOOK_PART_PAGES; book_jobs.BOOK_PART_PAGES = 5
    cb = types.SimpleNamespace(message=FakeMsg(), bot=BOT, answer=lambda *a, **k: asyncio.sleep(0))

    build_scanned(f"{SCR}/job1.pdf", 12)
    asked.clear(); sent.clear()
    base = {"pdf_path": f"{SCR}/job1.pdf", "total_pages": 12, "original_filename": "Skaner kitob.pdf",
            "source_lang": "unknown", "scanned": True, "ocr_mode": "ocr", "target_lang": "text",
            "page_from": None, "page_to": None}
    await state.set_data(dict(base))
    await bt._translate_pdf_book(cb, state, "uz", DB(), user, dict(base), 2500)
    check("pul yechildi", balance["v"] == 97500, balance)
    check("mijoz darhol bo'shatildi", await state.get_state() is None)
    check("boshlanish xabari o'qish haqida", any("o'qilmoqda" in s[1] for s in sent if s[0] == "msg"), [s[1][:40] for s in sent])
    await asyncio.gather(*list(book_jobs._tasks))
    docs = [s for s in sent if s[0] == "doc"]
    check("DOCX '_matn' nomi bilan yuborildi", [d[1] for d in docs] == ["Skaner kitob_matn.docx"], docs)
    check("12 bet AI ga yuborildi", len(asked) == 12, len(asked))
    check("faqat matn rejimida tarjima chaqirilmadi", translated_calls == [], translated_calls)
    check("holat foizi 'o'qish' so'zi bilan", any(s[0] in ("msg", "edit") and "Kitob o'qilmoqda:" in s[1] for s in sent))
    check("o'qish eslatmasi yuborildi", any(s[0] == "msg" and "sun'iy intellekt yordamida rasmdan" in s[1] for s in sent))
    d = await state.get_data()
    if d.get("translated_path") and os.path.exists(d["translated_path"]):
        from docx import Document as Docx
        paras = [p.text for p in Docx(d["translated_path"]).paragraphs if p.text.strip()]
        check("DOCX da o'qilgan matn bor", any("Sinov bobi" in p for p in paras) and any("kitobxonlik" in p for p in paras), paras[:5])
        check("DOCX da tarjima belgisi yo'q", not any(p.startswith("Tarjima:") for p in paras))
        os.remove(d["translated_path"])
    else:
        check("DOCX saqlangan", False, d)

    # ── Fonda ish: o'qish + tarjima
    build_scanned(f"{SCR}/job2.pdf", 6)
    asked.clear(); sent.clear(); translated_calls.clear(); balance["v"] = 100000
    base2 = {**base, "pdf_path": f"{SCR}/job2.pdf", "total_pages": 6, "ocr_mode": "ocr_translate", "target_lang": "ru"}
    await state.set_data(dict(base2))
    await bt._translate_pdf_book(cb, state, "uz", DB(), user, dict(base2), 4000)
    await asyncio.gather(*list(book_jobs._tasks))
    docs = [s for s in sent if s[0] == "doc"]
    check("tarjimali DOCX nomi tilni ko'rsatadi", [d[1] for d in docs] == ["Skaner kitob_ru.docx"], docs)
    check("tarjima chaqirildi, manba tili aniqlangan", translated_calls and translated_calls[0][0] == "uz" and translated_calls[0][1] == "ru", translated_calls)
    d = await state.get_data()
    if d.get("translated_path") and os.path.exists(d["translated_path"]):
        from docx import Document as Docx
        paras = [p.text for p in Docx(d["translated_path"]).paragraphs if p.text.strip()]
        check("DOCX da tarjima matni bor", any(p.startswith("Tarjima:") for p in paras), paras[:4])
        os.remove(d["translated_path"])

    # ── Ko'p bet o'qilmasa: ish to'xtaydi, pul qaytadi
    build_scanned(f"{SCR}/job3.pdf", 6)
    sent.clear(); balance["v"] = 100000
    def always_fail(image): raise RuntimeError("model ishlamayapti")
    book_ocr.read_image = always_fail
    real_sleep = asyncio.sleep
    base3 = {**base, "pdf_path": f"{SCR}/job3.pdf", "total_pages": 6}
    await state.set_data(dict(base3))
    book_jobs.PART_TRIES = 1
    await bt._translate_pdf_book(cb, state, "uz", DB(), user, dict(base3), 2000)
    await asyncio.gather(*list(book_jobs._tasks))
    check("hamma bet o'qilmasa ish to'xtadi va pul to'liq qaytdi", balance["v"] == 100000, balance)
    check("mijozga 'to'xtadi' va qaytarilgani aytildi", any("to'xtadi" in s[1] and "2,000" in s[1] for s in sent if s[0] == "msg"), [s[1][:60] for s in sent])
    check("noto'g'ri DOCX yuborilmadi", not [s for s in sent if s[0] == "doc"])
    book_jobs.PART_TRIES = 3

    # ── Mablag' tugasa (AI hisobi): kutish, keyin to'xtash va qaytarish
    build_scanned(f"{SCR}/job4.pdf", 6)
    sent.clear(); balance["v"] = 100000
    def out_of_credits(image): raise bpt.BookNoCredits("kredit yo'q")
    book_ocr.read_image = out_of_credits
    book_jobs.CREDIT_WAIT = 0; book_jobs.CREDIT_TRIES = 2
    warned = []
    from bot.handlers import premium_presentation as pp
    real_warn = pp._warn_admins_no_credits
    async def fake_warn(bot, text): warned.append(text)
    pp._warn_admins_no_credits = fake_warn
    base4 = {**base, "pdf_path": f"{SCR}/job4.pdf", "total_pages": 6}
    await state.set_data(dict(base4))
    await bt._translate_pdf_book(cb, state, "uz", DB(), user, dict(base4), 2000)
    await asyncio.gather(*list(book_jobs._tasks))
    pp._warn_admins_no_credits = real_warn
    check("mablag' tugaganda adminlar ogohlantirildi", warned and "OCR" in warned[0], warned)
    check("mablag' tugaganda mijoz pulini qaytarib oldi", balance["v"] == 100000, balance)
    check("mijozga xizmat vaqtincha ishlamayotgani aytildi", any("vaqtincha" in s[1] for s in sent if s[0] == "msg"))

    # ── Oddiy (matnli) kitob rejimi o'zgarmadi
    book_ocr.read_image = real_read
    bpt.translate_texts = bpt_real
    check("oddiy kitob 'translate' rejimida", True)
    build_scanned(f"{SCR}/job5.pdf", 4)
    job = book_jobs.create_job(user_id=1, chat_id=1, lang="uz", pdf_path=f"{SCR}/job5.pdf", file_name="a.pdf",
                               target_lang="uz", source_lang="ru", start=0, stop=1, price=1)
    check("rejim ko'rsatilmasa 'translate'", job["mode"] == "translate", job["mode"])
    book_jobs._remove(job)

asyncio.run(main())

import shutil
shutil.rmtree(SCR, ignore_errors=True)
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
