"""Mablag' yetmasa buyurtma saqlanib, to'lovdan keyin davom etadi — hamma xizmatda.

Haqiqiy aiogram dispetcheri orqali sinaladi (Telegram soxta):
  mablag' yetmaydi → to'lov tugmalari (berk ko'cha emas) → mijoz balansni
  to'ldirishga o'tadi (FSM tozalanadi) → bot o'zi eslatadi → «Davom etish»
  → xizmat bajariladi va pul yechiladi.

    python test_tolov_kutish.py
"""
import asyncio, datetime, os, shutil, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "123:abc")

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import (GetMe, SendDocument, SendInvoice, SendMessage, EditMessageText)
from aiogram.types import Message, Update, User

from bot import checkout as pay
from bot.states import BookTranslateStates, ConverterStates, DocumentStates, TestStates

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
        if isinstance(method, (SendMessage, EditMessageText)):
            return _msg(method.text).as_(bot)
        if isinstance(method, (SendDocument, SendInvoice)):
            return _msg().as_(bot)
        return True
    async def stream_content(self, *a, **k):
        yield b""
    async def close(self): pass

balance = {"v": 0}
class FakeUser:
    telegram_id = 5
    language = "uz"
    @property
    def balance(self): return balance["v"]
class FakeDB:
    async def get_user(self, uid): return FakeUser()
    async def update_user_balance(self, uid, delta): balance["v"] += delta

def buttons(method):
    markup = getattr(method, "reply_markup", None)
    return [b.callback_data for row in (markup.inline_keyboard if markup else []) for b in row]

async def main():
    import database.database as dbm
    dbm.Database.get_user = staticmethod(FakeDB().get_user)
    dbm.Database.update_user_balance = staticmethod(FakeDB().update_user_balance)
    from bot.handlers import converter, book_translate, documents
    from bot.handlers import test as test_handler

    bot = Bot("123:abc", session=FakeSession())
    dp = Dispatcher(storage=MemoryStorage())
    async def inject(handler, event, data):
        data.update(user_lang="uz", db=FakeDB(), user=FakeUser())
        return await handler(event, data)
    dp.message.middleware(inject); dp.callback_query.middleware(inject)
    for r in (converter.router, book_translate.router, test_handler.router, documents.router):
        dp.include_router(r)
    state = FSMContext(storage=dp.storage, key=StorageKey(bot_id=123, chat_id=5, user_id=5))
    n = [0]
    async def press(data):
        n[0] += 1
        await dp.feed_update(bot, Update.model_validate({"update_id": n[0], "callback_query": {
            "id": str(n[0]), "chat_instance": "c", "data": data,
            "from": {"id": 5, "is_bot": False, "first_name": "T"},
            "message": {"message_id": 1, "date": 0, "chat": {"id": 5, "type": "private"}, "text": "x"}}}))

    tmp = tempfile.mkdtemp()
    import pymupdf
    pdf = pymupdf.open(); pdf.new_page().insert_text((72, 72), "Test sahifa"); pdf.save(f"{tmp}/a.pdf")

    async def scenario(name, service, setup, pay_button, run_check):
        print(f"\n{name}")
        calls.clear(); balance["v"] = 1000
        await setup()
        await press(pay_button)
        short = [c for c in calls if isinstance(c, SendMessage) and "yetarli emas" in c.text]
        kb = buttons(short[0]) if short else []
        check("mablag' yetmasa to'lov tugmalari chiqadi",
              short and "pay_card_start" in kb and f"{service}_stars" in kb and f"{service}_recheck" in kb,
              [str(getattr(c, "text", None) or type(c).__name__)[:60] for c in calls])
        check("buyurtma saqlandi", pay.pending(5).get("service") == service, pay.pending(5))
        # Stars: buyurtma narxicha to'ldirish hisob-fakturasi
        calls.clear()
        await press(f"{service}_stars")
        inv = [c for c in calls if isinstance(c, SendInvoice)]
        check("Stars tugmasi hisob-faktura yuboradi", inv and (inv[0].payload.startswith("topup_")
              or inv[0].payload.startswith(f"{service}:")), [type(c).__name__ for c in calls])
        # Mijoz balansni to'ldirishga o'tdi — FSM tozalanadi
        await state.clear()
        balance["v"] = 100000
        calls.clear()
        sent = await pay.offer_continue(bot, 5, balance["v"], "uz")
        ready = [c for c in calls if isinstance(c, SendMessage)]
        check("balans to'lgach bot o'zi eslatadi", sent and ready and f"{service}_recheck" in buttons(ready[0]),
              [str(getattr(c, "text", None) or type(c).__name__)[:60] for c in calls])
        calls.clear()
        await press(f"{service}_recheck")
        await run_check()
        check("buyurtma navbatdan olindi", not pay.pending(5))

    # ── PDF → Word
    async def conv(path):
        out = path.replace(".pdf", ".docx"); open(out, "wb").write(b"PK"); return out
    converter.convert_pdf_to_docx = conv
    async def setup_pdf():
        shutil.copy(f"{tmp}/a.pdf", f"{tmp}/in.pdf")
        await state.set_state(ConverterStates.waiting_for_payment)
        await state.set_data(pay.start({"pdf_file_path": f"{tmp}/in.pdf", "pdf_filename": "a.pdf",
                                        "pdf_pages": 1, "price": 5000}))
    async def check_pdf():
        docs = [c for c in calls if isinstance(c, SendDocument)]
        check("konvertatsiya bajarildi va pul yechildi", docs and balance["v"] == 95000, (balance, calls))
    await scenario("PDF → Word", "pdf", setup_pdf, "pdf_pay", check_pdf)

    # Kutayotgan buyurtma fayli temp tozalanishidan himoyalangan
    shutil.copy(f"{tmp}/a.pdf", f"{tmp}/keep.pdf")
    pay.remember(5, "pdf", pay.start({"pdf_file_path": f"{tmp}/keep.pdf", "price": 1}))
    check("\nkutayotgan buyurtma fayli himoyalangan", os.path.abspath(f"{tmp}/keep.pdf") in pay.protected_paths())
    pay.forget(5)

    # ── Test
    async def fake_questions(topic, count, lang):
        return [{"question": "Savol?", "options": ["a", "b", "c", "d"], "correct_index": 0}] * count
    test_handler.generate_test_questions = fake_questions
    async def setup_test():
        await state.set_state(TestStates.waiting_for_format)
        await state.set_data({"test_topic": "Sinov mavzusi", "test_count": 10, "test_price": 5000,
                              "test_source": "ai"})
    async def check_test():
        docs = [c for c in calls if isinstance(c, SendDocument)]
        check("test yaratildi va pul yechildi", docs and balance["v"] == 95000, (balance, [type(c).__name__ for c in calls]))
    await scenario("Test", "test", setup_test, "test_format_file", check_test)

    # ── Kitob tarjimasi
    from services import book_jobs
    started = []
    book_jobs.start = lambda b, job: started.append(job)
    async def setup_book():
        shutil.copy(f"{tmp}/a.pdf", f"{tmp}/book.pdf")
        await state.set_state(BookTranslateStates.waiting_for_payment)
        await state.set_data(pay.start({"pdf_path": f"{tmp}/book.pdf", "original_filename": "k.pdf",
                                        "total_pages": 1, "source_lang": "ru", "target_lang": "uz",
                                        "price": 30000}))
    async def check_book():
        check("tarjima boshlandi va pul yechildi", started and balance["v"] == 70000, (balance, started))
        for job in started:
            book_jobs._remove(job)
    await scenario("Kitob tarjimasi", "book", setup_book, "book_pay", check_book)

    # ── Hujjat: Stars tugmasi endi ishlaydi (ilgari handleri yo'q edi)
    print("\nHujjat")
    calls.clear()
    await state.set_state(DocumentStates.waiting_for_payment)
    await state.set_data({"price": 12000, "doc_next_step": "tezis_gen", "topic": "Mavzu"})
    await press("doc_stars")
    inv = [c for c in calls if isinstance(c, SendInvoice)]
    check("hujjatdagi Stars tugmasi hisob-faktura yuboradi", inv and inv[0].payload.startswith("topup_"),
          [type(c).__name__ for c in calls])

    shutil.rmtree(tmp, ignore_errors=True)
    await bot.session.close()

asyncio.run(main())
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
