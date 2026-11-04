"""«Rahmat» personajini taqdimot SOZLAMALARIDA tanlash: savol → galereya → tanlash/o'tkazish → xulosa → orqaga.

- yozuv animatsiyasidan keyin savol chiqadi (admin o'chirmagan bo'lsa), 3D turlarda chiqmaydi;
- galereya: video namuna, ◀ ▶, tanlash; tanlov xulosada ko'rinadi va xulosadan almashtiriladi;
- «Kerak emas» — personajsiz davom etadi (majburiy emas);
- orqaga tugmasi qadamlar tartibiga mos; tayyor taqdimotga sahifa qo'shiladi.

    python test_rahmat_sozlama.py
"""
import asyncio
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        FAILS.append(name)


from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from pptx import Presentation

from bot.handlers import premium_presentation as pp
from bot.states import PremiumPresentationStates as PS
from aiogram.filters import CommandObject
import webapp
from services.thanks_anim import picker

webapp.WEBAPP_DOMAIN = "edufayl.uz"


class Chat:
    def __init__(self):
        self.next_id, self.sent, self.deleted, self.photos, self.edited = 100, [], [], [], []
        self.bot = SimpleNamespace(delete_message=self.delete, edit_message_text=self.edit_text)

    async def delete(self, chat_id, message_id):
        self.deleted.append(message_id)

    async def edit_text(self, text, chat_id=None, message_id=None, **kw):
        self.edited.append((message_id, text, kw.get("reply_markup")))

    def message(self):
        chat = self
        msg = MagicMock()
        msg.bot = self.bot
        msg.chat = SimpleNamespace(id=1)
        msg.message_id = 5

        async def answer(body, **kw):
            chat.next_id += 1
            chat.sent.append((chat.next_id, body, kw.get("reply_markup")))
            return SimpleNamespace(message_id=chat.next_id)

        async def answer_photo(photo, **kw):
            chat.next_id += 1
            chat.photos.append((chat.next_id, kw.get("caption"), kw.get("reply_markup")))
            chat.sent.append((chat.next_id, kw.get("caption"), kw.get("reply_markup")))
            return SimpleNamespace(message_id=chat.next_id, photo=[SimpleNamespace(file_id="P1")])
        msg.answer = answer
        msg.answer_photo = answer_photo
        msg.from_user = SimpleNamespace(id=1)
        msg.delete = AsyncMock()
        return msg

    def last(self):
        return self.sent[-1]


def buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]


def callback(chat, data, message_id=5):
    cb = MagicMock()
    cb.data = data
    cb.answer = AsyncMock()
    cb.message = chat.message()
    cb.message.message_id = message_id
    cb.bot = chat.bot
    cb.from_user = SimpleNamespace(id=1)
    return cb


db = MagicMock()
db.get_user = AsyncMock(return_value=SimpleNamespace(language="uz", first_name="Ali", balance=100000, id=1))

BASE = dict(kind="modern", topic="Ekologiya asoslari", presentation_language="uz", slide_count=12, style="toza",
            volume="kop", client_name="Ali")


async def flow():
    chat = Chat()
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=1, user_id=1))
    await state.update_data(**BASE, text_anim_offer=False)

    print("1) Yozuv animatsiyasidan keyin savol (rasm bilan)")
    pp._thanks_offer, real_offer = AsyncMock(return_value=True), pp._thanks_offer
    await pp._after_anim(chat.message(), state, "uz")
    check("savol chiqdi, holat — waiting_for_thanks", await state.get_state() == PS.waiting_for_thanks.state,
          await state.get_state())
    check("tugma ustida personajlar kollaji rasmi bor", len(chat.photos) == 1, chat.photos)
    text, markup = chat.last()[1], chat.last()[2]
    first = buttons(markup)[0]
    check("savolda mutlaqo tekin deyilgan", "mutlaqo tekin" in text, text)
    check("«Personaj tanlash» mini ilovani ochadi", first.web_app and "/anim?lang=uz" in first.web_app.url, first)
    check("«Kerak emas» va orqaga tugmalari", [b.callback_data for b in buttons(markup)[1:]] == ["prem_thx:skip",
                                                                                              "prem_ppt_prev"])
    check("thanks_offer saqlandi", (await state.get_data()).get("thanks_offer") is True)

    print("2) Mini ilova tanlovni /start thx_<kalit> bilan qaytaradi")
    msg = chat.message()
    await pp.premium_ppt_thanks_chosen(msg, CommandObject(command="start", args="thx_pingvin"), state, db)
    data = await state.get_data()
    check("tanlov saqlandi", data.get("thanks_key") == "pingvin", data.get("thanks_key"))
    check("«/start …» xabari o'chirildi", msg.delete.await_count == 1)
    check("xulosaga o'tdi", await state.get_state() == PS.waiting_for_slide_count.state, await state.get_state())
    stext, smarkup = chat.last()[1], chat.last()[2]
    check("xulosada personaj nomi ko'rinadi", picker.name_of("pingvin", "uz") in stext, stext)
    sb = [b for b in buttons(smarkup) if b.web_app]
    check("xulosada mini ilova tugmasi (almashtirish), nomi bilan", sb and "Pingvin" in sb[0].text
          and sb[0].web_app.url.endswith("sel=pingvin"), [b.text for b in buttons(smarkup)])

    print("3) Xulosadan almashtirish va olib tashlash")
    before = len(chat.sent)
    await pp.premium_ppt_thanks_chosen(chat.message(), CommandObject(command="start", args="thx_ayiqcha"), state, db)
    check("almashtirildi", (await state.get_data()).get("thanks_key") == "ayiqcha")
    check("xulosa joyida yangilandi (yangi xabar emas)", len(chat.sent) == before and chat.edited
          and "Ayiqcha" in chat.edited[-1][1], chat.edited[-1:])
    await pp.premium_ppt_thanks_chosen(chat.message(), CommandObject(command="start", args="thx_yoq"), state, db)
    check("noma'lum kalit — hech narsa o'zgarmaydi", (await state.get_data()).get("thanks_key") == "ayiqcha")
    await pp.premium_ppt_thanks_skip(callback(chat, "prem_thx:skip"), state, db)
    check("«Kerak emas» — personajsiz, xulosa yangilandi", (await state.get_data()).get("thanks_key") == ""
          and "yo'q" in chat.edited[-1][1])
    check("holat xulosada qoldi", await state.get_state() == PS.waiting_for_slide_count.state)

    print("4) Savoldan «Kerak emas» — tanlash majburiy emas")
    chat2 = Chat()
    state2 = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=2, user_id=2))
    await state2.update_data(**BASE, text_anim_offer=False)
    await pp._after_anim(chat2.message(), state2, "uz")
    await pp.premium_ppt_thanks_skip(callback(chat2, "prem_thx:skip"), state2, db)
    data2 = await state2.get_data()
    check("personajsiz xulosaga o'tdi", await state2.get_state() == PS.waiting_for_slide_count.state
          and not data2.get("thanks_key") and "yo'q" in chat2.last()[1])

    print("5) Muddati tugagan sozlamalar")
    chat3 = Chat()
    m3 = chat3.message()
    await pp.premium_ppt_thanks_stale(m3, db)
    check("holat yo'q bo'lsa — tushuntirish xabari", "muddati tugagan" in chat3.last()[1])

    print("6) Orqaga tartibi")
    d = {**BASE, "thanks_offer": True, "text_anim_offer": True, "step": "summary"}
    check("xulosa → personaj qadami", pp._previous_step(d) == "thanks")
    check("personaj qadami → yozuv animatsiyasi", pp._previous_step({**d, "step": "thanks"}) == "anim")
    check("yozuv animatsiyasi yo'q bo'lsa — rasm manbasi (zamonaviyda)", pp._previous_step(
        {**d, "step": "thanks", "text_anim_offer": False}) == "photos")
    check("personaj taklif qilinmasa xulosadan to'g'ridan orqaga", pp._previous_step(
        {**d, "thanks_offer": False}) == "anim")
    pp._thanks_offer = real_offer

    print("7) Qaysi turlarda taklif qilinadi")
    check("3D turlarda taklif yo'q", not await pp._thanks_offer({"kind": "pro3d"})
          and not await pp._thanks_offer({"kind": "med3d"}) and not await pp._thanks_offer({"kind": "kat3d"}))


asyncio.run(flow())

print("8) Tayyor taqdimotga qo'shiladi")
TMP = tempfile.mkdtemp()
prs = Presentation()
prs.slide_width, prs.slide_height = 12192000, 6858000
for _ in range(2):
    prs.slides.add_slide(prs.slide_layouts[6])
deck = os.path.join(TMP, "d.pptx")
prs.save(deck)
asyncio.run(pp._add_thanks_page(deck, {**BASE, "thanks_key": "pingvin"}, "uz", "Ali"))
check("oxiriga sahifa qo'shildi", len(Presentation(deck).slides) == 3)
shutil.copy(os.path.join(TMP, "d.pptx"), os.path.join(TMP, "e.pptx"))
shutil.rmtree(TMP, ignore_errors=True)

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
