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
from services.thanks_anim import picker


class Chat:
    def __init__(self):
        self.next_id, self.sent, self.deleted, self.videos, self.edited = 100, [], [], [], []
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

        async def answer_video(video, **kw):
            chat.next_id += 1
            chat.videos.append((chat.next_id, kw.get("caption"), kw.get("reply_markup")))
            return SimpleNamespace(message_id=chat.next_id, video=SimpleNamespace(file_id=f"F{chat.next_id}"))
        msg.answer = answer
        msg.answer_video = answer_video
        msg.edit_media = AsyncMock(return_value=SimpleNamespace(video=SimpleNamespace(file_id="FX")))
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

    print("1) Yozuv animatsiyasidan keyin savol")
    pp._thanks_offer, real_offer = AsyncMock(return_value=True), pp._thanks_offer
    await pp._after_anim(chat.message(), state, "uz")
    check("savol chiqdi, holat — waiting_for_thanks", await state.get_state() == PS.waiting_for_thanks.state,
          await state.get_state())
    text, markup = chat.last()[1], chat.last()[2]
    cbs = [b.callback_data for b in buttons(markup)]
    check("savolda mutlaqo tekin deyilgan", "mutlaqo tekin" in text, text)
    check("tanlash, kerak emas va orqaga tugmalari", cbs == ["prem_thx:open", "prem_thx:skip", "prem_ppt_prev"], cbs)
    check("thanks_offer saqlandi", (await state.get_data()).get("thanks_offer") is True)

    print("2) Galereya")
    await pp.premium_ppt_thanks_open(callback(chat, "prem_thx:open"), state, db)
    check("video namuna yuborildi (1/24)", len(chat.videos) == 1 and "(1/24)" in chat.videos[0][1], chat.videos)
    pager_mid = (await state.get_data())["thx_mid"]
    check("galereya xabari eslab qolindi", pager_mid == chat.videos[0][0])
    pager_cbs = [b.callback_data for b in buttons(chat.videos[0][2])]
    check("◀ ▶ tanlash, kerak emas, orqaga", "prem_thx:go:1" in pager_cbs and "prem_thx:go:23" in pager_cbs
          and any(c.startswith("prem_thx:pick:") for c in pager_cbs) and "prem_thx:skip" in pager_cbs
          and "prem_thx:close" in pager_cbs, pager_cbs)
    nav = callback(chat, "prem_thx:go:4", pager_mid)
    await pp.premium_ppt_thanks_go(nav, state, db)
    check("▶ — xabar joyida yangilandi (edit_media)", nav.message.edit_media.await_count == 1)
    media = nav.message.edit_media.await_args.args[0]
    check("yangi kadr: 5/24 sarlavha", "(5/24)" in media.caption, media.caption)

    print("3) Tanlash → xulosa")
    pick = picker.items()[4].key
    cb = callback(chat, f"prem_thx:pick:{pick}", pager_mid)
    await pp.premium_ppt_thanks_pick(cb, state, db)
    data = await state.get_data()
    check("tanlov saqlandi", data.get("thanks_key") == pick, data.get("thanks_key"))
    check("galereya xabari o'chdi", cb.message.delete.await_count == 1)
    check("xulosaga o'tdi", await state.get_state() == PS.waiting_for_slide_count.state, await state.get_state())
    stext, smarkup = chat.last()[1], chat.last()[2]
    check("xulosada personaj nomi ko'rinadi", picker.name_of(pick, "uz") in stext, stext)
    sb = [b for b in buttons(smarkup) if b.callback_data == "prem_thx:open"]
    check("xulosada «almashtirish» tugmasi, nomi bilan", sb and picker.name_of(pick, "uz") in sb[0].text,
          [b.text for b in buttons(smarkup)])

    print("4) Xulosadan almashtirish va olib tashlash")
    await pp.premium_ppt_thanks_open(callback(chat, "prem_thx:open"), state, db)
    check("galereya tanlangan personajdan ochiladi", f"({picker.start_index(pick) + 1}/24)" in chat.videos[-1][1],
          chat.videos[-1][1])
    skip = callback(chat, "prem_thx:skip", chat.videos[-1][0])
    await pp.premium_ppt_thanks_skip(skip, state, db)
    data = await state.get_data()
    check("«Kerak emas» — personajsiz", data.get("thanks_key") == "")
    check("xulosa joyida yangilandi: «yo'q»", chat.edited and "yo'q" in chat.edited[-1][1], chat.edited[-1:] )
    check("holat xulosada qoldi", await state.get_state() == PS.waiting_for_slide_count.state)

    print("5) Savoldan «Kerak emas» — tanlash majburiy emas")
    chat2 = Chat()
    state2 = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=2, user_id=2))
    await state2.update_data(**BASE, text_anim_offer=False)
    await pp._after_anim(chat2.message(), state2, "uz")
    await pp.premium_ppt_thanks_skip(callback(chat2, "prem_thx:skip"), state2, db)
    data2 = await state2.get_data()
    check("personajsiz xulosaga o'tdi", await state2.get_state() == PS.waiting_for_slide_count.state
          and not data2.get("thanks_key") and "yo'q" in chat2.last()[1])

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
