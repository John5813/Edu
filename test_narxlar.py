"""«💵 Narxlar» tugmasi, «3D taqdimot Pro», yordamda narx yo'qligi, dizayn namunalari va 3D promokodsiz oqim.

    python test_narxlar.py
"""
import asyncio, os, re, sys
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import config
import services.kat3d as kat3d
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from bot import previews
from bot.handlers import premium_presentation as pp, prices
from bot.keyboards import get_main_keyboard
from bot.middlewares import CommandResetMiddleware
from bot.states import PremiumPresentationStates as PS
from services.med3d import auto as med3d_auto
from translations import get_text, kazakh_scope

print("1) Menyu: «Narxlar» Namunalar yonida, 3D tugmasida «Pro»")
for lang in ("uz", "ru", "en"):
    rows = [[b.text for b in row] for row in get_main_keyboard(lang).keyboard]
    pair = [get_text(lang, "main_menu.samples"), get_text(lang, "main_menu.prices")]
    check(f"{lang}: Namunalar va Narxlar bir qatorda", pair in rows, rows)
    check(f"{lang}: 3D tugmasida Pro", get_text(lang, "main_menu.presentation_3d").endswith(" Pro"))
with kazakh_scope(True):
    check("kk: Narxlar va 3D Pro", get_text("ru", "main_menu.prices") == "💵 Бағалар"
          and get_text("ru", "main_menu.presentation_3d").endswith(" Pro"))
off = [[b.text for b in row] for row in get_main_keyboard("uz", project_work_enabled=False).keyboard]
check("bitta xizmat o'chsa ham Namunalar va Narxlar yonma-yon", ["📁 Namunalar", "💵 Narxlar"] in off, off)
check("menyu tugmasi — boshqa bosqichdagi holat bekor qilinadi",
      {"💵 Narxlar", "💵 Цены", "💵 Prices"} <= CommandResetMiddleware.menu_labels())
check("Narxlar tugmasi barcha tillarda ushlanadi",
      {"💵 Narxlar", "💵 Цены", "💵 Prices", "💵 Бағалар"} <= set(prices.PRICES_TEXTS), prices.PRICES_TEXTS)
check("eski «🧊 3D taqdimot» tugmasi ham 3D bo'limini ochadi",
      "🧊 3D taqdimot" in pp.MED3D_ENTRY_TEXTS and get_text("uz", "main_menu.presentation_3d") in pp.MED3D_ENTRY_TEXTS)

print("2) Yordam: narxlar yo'q, aloqa bor")
for lang in ("uz", "ru", "en"):
    text = get_text(lang, "help_text")
    check(f"{lang}: yordamda narx yo'q", not re.search(r"\d[\d,]* ?(so'm|сум|som)", text), text[:200])
    check(f"{lang}: aloqa kanali qoldi", "https://t.me/Edufail" in text)
with kazakh_scope(True):
    text = get_text("ru", "help_text")
    check("kk: yordamda narx yo'q", not re.search(r"\d[\d,]* ?сум", text) and "https://t.me/Edufail" in text)

print("3) Narxlar matni — buyurtmadagi hisob bilan bir xil")
class Tags(HTMLParser):
    def __init__(self):
        super().__init__(); self.stack, self.bad = [], False
    def handle_starttag(self, tag, attrs): self.stack.append(tag)
    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag: self.bad = True
for lang in ("uz", "ru", "en", "kk"):
    text = prices.prices_text(lang)
    parser = Tags(); parser.feed(text)
    check(f"{lang}: Telegram chegarasiga sig'adi va HTML to'g'ri", len(text) < 4096 and not parser.bad
          and not parser.stack, (len(text), parser.stack))
text = prices.prices_text("uz")
som = prices._som
need = {
    "3D to'liq 10 slayd": som(kat3d.price_for(10)), "3D aralash 10 slayd": som(kat3d.price_for(10, "mix")),
    "3D Anatomiya 15": som(med3d_auto.price_for(15)), "taqdimot 20": som(pp._get_price(20)),
    "klassik 15": som(config.PRESENTATION_PRICES[15]), "mustaqil 25-30": som(config.DOCUMENT_PRICES["25_30"]),
    "kurs 50-60": som(config.COURSE_WORK_PRICES["50_60_3"]), "bitiruv 60-70": som(config.GRADUATION_WORK_PRICES["60_70_3"]),
    "dissertatsiya 90-100": som(config.DISSERTATION_PRICES["90_100_4"]), "maqola 7-10": som(config.ARTICLE_PRICES["7_10"]),
    "PDF 100+": som(config.PDF_CONVERT_PRICES["101_plus"]), "loyiha 30-40": som(config.PROJECT_WORK_SIZES["30_40"]["price"]),
}
for name, value in need.items():
    check(f"narxlarda bor: {name} — {value}", value in text)
for word in ("Toza", "Jurnal", "Qorong'u", "Tungi ko'k", "Rentgen", "Klassik", "Infografik", "Tezis", "Test yaratish"):
    check(f"narxlarda bor: {word}", word in text)

check("3D taqdimot Pro: varog'i 2 000 so'm, aralash 40% arzon",
      [kat3d.price_for(n) for n in (5, 10, 15)] == [10000, 20000, 30000] and kat3d.price_for(10, "mix") == 12000
      and "To'liq 3D: 5 slayd — 10 000 · 8 — 16 000 · 10 — 20 000" in text
      and "· 10 — 12 000 ·" in text.split("Aralash 3D")[1].split("\n")[0], text.split("\n")[6:9])

print("4) Narxlar tugmasi: matn va dizayn namunalari albomi")
for key in prices.ALBUM:
    check(f"namuna rasmi bor: {key}", previews.exists(key), previews.PATHS[key])

def photo_message(file_id):
    return SimpleNamespace(message_id=7, photo=[SimpleNamespace(file_id=file_id + "_kichik"),
                                                 SimpleNamespace(file_id=file_id)])

async def prices_button():
    previews._FILE_IDS.clear()
    message = MagicMock()
    message.answer = AsyncMock()
    message.answer_media_group = AsyncMock(return_value=[photo_message(f"id_{k}") for k in prices.ALBUM])
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=1, user_id=1))
    await state.set_state(PS.waiting_for_topic_text)
    await prices.prices_handler(message, state, "uz")
    check("tugma boshqa bosqichni bekor qiladi", await state.get_state() is None)
    sent = message.answer.call_args
    check("narxlar matni HTML bilan yuborildi", sent.kwargs.get("parse_mode") == "HTML" and "3D taqdimot Pro" in sent.args[0])
    album = message.answer_media_group.call_args.args[0]
    check("albomda 5 ta namuna, har biri ostida nomi", len(album) == 5 and all(m.caption for m in album),
          [m.caption for m in album])
    await prices.prices_handler(message, state, "uz")
    again = message.answer_media_group.call_args.args[0]
    check("ikkinchi marta rasmlar qayta yuklanmaydi (file_id)", [m.media for m in again]
          == [f"id_{k}" for k in prices.ALBUM], [m.media for m in again])
    previews._FILE_IDS.clear()
asyncio.run(prices_button())

print("5) Taqdimot turi va uslubini tanlashda namuna rasmi")
async def steps():
    previews._FILE_IDS.clear()
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=1, user_id=1))
    message = MagicMock()
    message.bot.delete_message = AsyncMock()
    message.chat.id = 1
    message.answer = AsyncMock(return_value=SimpleNamespace(message_id=5))
    message.answer_photo = AsyncMock(return_value=photo_message("turlar"))
    await pp._step_kind(message, state, "uz")
    call = message.answer_photo.call_args
    buttons = [b.callback_data for row in call.kwargs["reply_markup"].inline_keyboard for b in row]
    check("tur tanlash: rasm ostida savol va tugmalar", call and "Taqdimot turini" in call.kwargs["caption"]
          and "prem_ppt_kind:info" in buttons and not message.answer.called, buttons)
    check("tur tanlash: aynan turlar rasmi", call.args[0].path == previews.PATHS["turlar"])
    data = await state.get_data()
    check("tur so'rovi xabari eslab qolindi (keyin o'chiriladi)", data.get("prompt_mid") == 7
          and await state.get_state() == PS.waiting_for_kind.state, data)

    message.answer_photo = AsyncMock(return_value=photo_message("uslublar"))
    await pp._step_style(message, state, "uz")
    call = message.answer_photo.call_args
    check("uslub tanlash: 5 uslub rasmi va tugmalar", call.args[0].path == previews.PATHS["uslublar"]
          and len(call.kwargs["reply_markup"].inline_keyboard) == 6, call.kwargs["caption"])

    message.answer_photo = AsyncMock(side_effect=RuntimeError("tarmoq"))
    message.answer = AsyncMock(return_value=SimpleNamespace(message_id=9))
    await pp._step_kind(message, state, "uz")
    check("rasm ketmasa ham savol matn bo'lib chiqadi", message.answer.called
          and (await state.get_data()).get("prompt_mid") == 9)

    message.answer = AsyncMock(return_value=SimpleNamespace(message_id=11))
    message.answer_photo = AsyncMock(return_value=photo_message("x"))
    await state.update_data(topic="Juda uzun mavzu " * 80)
    await pp._step_kind(message, state, "uz")
    check("rasm ostiga sig'maydigan uzun matn — oddiy xabar", not message.answer_photo.called and message.answer.called)
    previews._FILE_IDS.clear()
asyncio.run(steps())

print("6) 3D promokod tizimi yo'q")
check("promokod holati yo'q", not hasattr(PS, "waiting_for_med3d_promocode"))
import inspect
from bot import keyboards
features = inspect.signature(keyboards.get_feature_management_keyboard).parameters
admin_buttons = [b for row in keyboards.get_feature_management_keyboard(
    **{n: True for n, p in features.items() if p.default is inspect.Parameter.empty}).inline_keyboard for b in row]
check("admin bo'limlarida 3D promokod tugmasi yo'q", admin_buttons
      and not any(b.callback_data == "med3d_promo_manage" for b in admin_buttons), [b.text for b in admin_buttons])
data = {"kind": pp.KIND_KAT3D, "standalone_med3d": True, "med3d_promo_percent": 50, "kat3d_mode": "full"}
check("eski buyurtmadagi chegirma narxga ta'sir qilmaydi", pp._price_of(data, 10) == kat3d.price_for(10))
check("promokod funksiyalari olib tashlangan",
      not any(hasattr(pp, n) for n in ("_step_med3d_promocode", "premium_med3d_promocode_input", "_reserve_med3d_promo")))

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta XATO")
sys.exit(1 if FAILS else 0)
