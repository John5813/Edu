"""Bitta "Taqdimot" tugmasi: mavzu → ism → AI ga tushuntirish → manba → uslub → (rang) → hajm.
Hajm bosqichida narxlar tanlangan uslubga qarab va mijoz balansi bilan ko'rsatiladi.

Zamonaviy uslublarda keyin rang, "Chiroyli orqa fonlar" tanlansa hozirgi
oddiy oqim ishlaydi. Har so'rov javob olingach oynadan o'chadi.

    python test_taqdimot_oqimi.py
"""
import asyncio, os, sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from bot.handlers import premium_presentation as pp
from bot.states import DocumentStates, PremiumPresentationStates as PS


class Chat:
    """Soxta suhbat: yuborilgan va o'chirilgan xabarlarni yodda tutadi."""
    def __init__(self):
        self.next_id, self.sent, self.deleted = 100, [], []
        self.bot = SimpleNamespace(delete_message=self.delete)

    async def delete(self, chat_id, message_id):
        self.deleted.append(message_id)

    def message(self, text=None):
        chat = self
        msg = MagicMock()
        msg.text = text
        msg.bot = self.bot
        msg.chat = SimpleNamespace(id=1)
        msg.from_user = SimpleNamespace(id=1, first_name="Ali")

        async def answer(body, **kw):
            chat.next_id += 1
            chat.sent.append((chat.next_id, body, kw.get("reply_markup")))
            return SimpleNamespace(message_id=chat.next_id)
        msg.answer = answer
        msg.edit_text = AsyncMock()
        msg.delete = AsyncMock()
        return msg

    def last(self):
        return self.sent[-1]


def buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]

def callback(chat, data):
    cb = MagicMock(); cb.data = data; cb.answer = AsyncMock()
    cb.message = chat.message(); cb.bot = chat.bot
    cb.from_user = SimpleNamespace(id=1)
    return cb

def make_db(balance=100000):
    db = MagicMock()
    user = SimpleNamespace(language="uz", first_name="Ali", balance=balance, id=1)
    db.get_user = AsyncMock(return_value=user)
    db.get_active_channels = AsyncMock(return_value=[])
    return db

async def new_state():
    return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=1, user_id=1))


async def full_flow():
    chat, db, state = Chat(), make_db(), await new_state()

    # 1. Mavzu
    await pp.premium_presentation_start(chat.message("🌟 Taqdimot"), state, db)
    check("1-qadam: mavzu so'raladi", await state.get_state() == PS.waiting_for_topic_text.state)
    topic_prompt = (await state.get_data())["prompt_mid"]
    check("1-qadam: so'rovda matn bor", "mavzu" in chat.last()[1].lower())

    await pp.premium_ppt_got_topic(chat.message("Falsafa: predmeti va muammolari"), state, db)
    data = await state.get_data()
    check("mavzu saqlandi, til mavzudan aniqlandi", data["topic"].startswith("Falsafa") and data["presentation_language"] == "uz", data)
    check("mavzu so'rovi javobdan keyin o'chdi", topic_prompt in chat.deleted, chat.deleted)

    # 2. Ism (matn bilan)
    check("2-qadam: ism so'raladi", await state.get_state() == PS.waiting_for_client_name.state)
    skip_btn = [b.callback_data for b in buttons(chat.last()[2])]
    check("ism: 'o'tkazib yuborish' tugmasi bor", "prem_ppt_skip_name" in skip_btn, skip_btn)
    name_prompt = (await state.get_data())["prompt_mid"]
    await pp.premium_ppt_got_name(chat.message("Aliyev Jasur"), state, db)
    check("ism yozilgach so'rov matni o'chdi", name_prompt in chat.deleted)
    check("ism saqlandi", (await state.get_data())["client_name"] == "Aliyev Jasur")

    # 3. AI ga tushuntirish (o'tkazib yuborish bilan)
    check("3-qadam: istaklar so'raladi", await state.get_state() == PS.waiting_for_preferences.state)
    prefs_prompt = (await state.get_data())["prompt_mid"]
    await pp.premium_ppt_skip_preferences(callback(chat, "prem_ppt_skip_preferences"), state, db)
    check("o'tkazib yuborilgach so'rov matni o'chdi", prefs_prompt in chat.deleted)
    check("istak bo'sh saqlandi", (await state.get_data())["preferences"] == "")

    # 4. Manba
    check("4-qadam: manba so'raladi", await state.get_state() == PS.waiting_for_source_kind.state)
    cbs = [b.callback_data for b in buttons(chat.last()[2])]
    check("manba: AI/matn/fayl/sayt tugmalari", all(f"prem_ppt_source:{k}" in cbs for k in ("ai", "text", "file", "url")), cbs)
    await pp.premium_ppt_chose_source(callback(chat, "prem_ppt_source:ai"), state, db)

    # 5. Uslub (hajmdan oldin)
    check("5-qadam: uslub so'raladi", await state.get_state() == PS.waiting_for_style.state)
    text, markup = chat.last()[1], chat.last()[2]
    style_cbs = [b.callback_data for b in buttons(markup) if b.callback_data and b.callback_data.startswith("ppt_style:")]
    check("6 ta uslub tugmasi (5 zamonaviy + chiroyli orqa fonlar)",
          style_cbs == ["ppt_style:toza", "ppt_style:jurnal", "ppt_style:blok", "ppt_style:kontur",
                        "ppt_style:qorongu", "ppt_style:fon"], style_cbs)
    check("tugmalar chiroyli nomlangan", any("Chiroyli orqa fonlar" in b.text for b in buttons(markup))
          and any("Qorong'u" in b.text for b in buttons(markup)))
    check("uslub oynasida narx yo'q (u hajm bilan ko'rsatiladi)", "so'm" not in text.split("keyingi qadamda")[0])

    # 5a. Zamonaviy uslub -> rang -> hajm (narx + balans) -> xulosa
    await pp.premium_ppt_style_selected(callback(chat, "ppt_style:jurnal"), state, db)
    check("zamonaviy uslub: rang so'raladi", await state.get_state() == PS.waiting_for_theme.state)
    check("uslub saqlandi", (await state.get_data())["style"] == "jurnal")
    await pp.premium_ppt_got_theme(callback(chat, "prem_ppt_theme:qizil"), state, db)
    check("6-qadam: hajm so'raladi", await state.get_state() == PS.waiting_for_count.state)
    text, markup = chat.last()[1], chat.last()[2]
    count_btns = [b for b in buttons(markup) if b.callback_data.startswith("prem_ppt_count:")]
    check("zamonaviy hajm: har tugmada narx", all("so'm" in b.text for b in count_btns)
          and any(b.callback_data == "prem_ppt_count:12" and "8,000" in b.text for b in count_btns),
          [b.text for b in count_btns])
    check("hajm oynasida mijoz balansi ko'rinadi", "Balansingiz" in text and "100,000" in text, text)
    check("hajm oynasida tanlangan uslub nomi", "Jurnal" in text, text)
    await pp.premium_ppt_got_count(callback(chat, "prem_ppt_count:12"), state, db)
    data = await state.get_data()
    check("xulosa: holat va narx", await state.get_state() == PS.waiting_for_slide_count.state and data["price"] == 8000, data.get("price"))
    summary = chat.last()[1]
    check("xulosada mavzu, ism, uslub, slayd soni", all(w in summary for w in ("Falsafa", "Aliyev Jasur", "Jurnal", "12")), summary)
    langs = [b.callback_data for b in buttons(chat.last()[2]) if b.callback_data.startswith("prem_ppt_lang:")]
    check("xulosada tilni o'zgartirish tugmalari (o'zbek lotin va kirill alohida)", langs == ["prem_ppt_lang:uz", "prem_ppt_lang:uz-cyrl", "prem_ppt_lang:ru", "prem_ppt_lang:en", "prem_ppt_lang:kk"], langs)
    await pp.premium_ppt_change_language(callback(chat, "prem_ppt_lang:en"), state, db)
    check("til almashtirildi", (await state.get_data())["presentation_language"] == "en")

    # Orqaga: xulosa -> hajm -> rang -> uslub
    for expect in (PS.waiting_for_count, PS.waiting_for_theme, PS.waiting_for_style):
        await pp.premium_ppt_previous(callback(chat, "prem_ppt_prev"), state, db)
        check(f"orqaga: {expect.state.split(':')[1]}", await state.get_state() == expect.state, await state.get_state())

    # 5b. "Chiroyli orqa fonlar" -> hajm faqat 10/15/20, narxlar va balans bilan
    await pp.premium_ppt_style_selected(callback(chat, "ppt_style:fon"), state, db)
    check("orqa fonlar: rang emas, hajm so'raladi", await state.get_state() == PS.waiting_for_count.state, await state.get_state())
    fon_btns = [b for b in buttons(chat.last()[2]) if b.callback_data.startswith("ppt_fon:")]
    check("orqa fonlar: faqat 10/15/20", [b.callback_data for b in fon_btns] == ["ppt_fon:10", "ppt_fon:15", "ppt_fon:20"], fon_btns)
    check("orqa fonlar: oddiy narxlar (5 000 / 7 000 / 10 000)",
          [("5,000" in fon_btns[0].text), ("7,000" in fon_btns[1].text), ("10,000" in fon_btns[2].text)] == [True] * 3,
          [b.text for b in fon_btns])
    check("orqa fonlar: balans va uslub nomi ko'rinadi",
          "Balansingiz" in chat.last()[1] and "Chiroyli orqa fonlar" in chat.last()[1], chat.last()[1])
    await pp.premium_ppt_previous(callback(chat, "prem_ppt_prev"), state, db)
    check("orqa fonlar hajmidan orqaga: uslub (rang emas)", await state.get_state() == PS.waiting_for_style.state, await state.get_state())
    await pp.premium_ppt_style_selected(callback(chat, "ppt_style:fon"), state, db)
    await pp.premium_ppt_fon_count(callback(chat, "ppt_fon:15"), state, db)
    data = await state.get_data()
    check("oddiy oqim: to'lov bosqichiga o'tildi", await state.get_state() == DocumentStates.waiting_for_payment.state, await state.get_state())
    check("oddiy oqim ma'lumotlari: turi, til, mavzu, ism, hajm, narx",
          data.get("document_type") == "presentation" and data.get("doc_language") == "en"
          and data.get("topic", "").startswith("Falsafa") and data.get("author_name") == "Aliyev Jasur"
          and data.get("slide_count") == 15 and data.get("price") == 7000, data)
    check("oddiy oqim: to'lovdan keyin shablonlar bosqichi", data.get("doc_next_step") == "presentation_template")
    check("oddiy oqim: premium ma'lumotlari qolmadi", "style" not in data and "prompt_mid" not in data, data.keys())

    # 5c. Kam balans ham ko'rinadi
    chat2, state2 = Chat(), await new_state()
    low_db = make_db(balance=1500)
    await pp.premium_presentation_start(chat2.message("🌟 Taqdimot"), state2, low_db)
    await pp.premium_ppt_got_topic(chat2.message("Сельское хозяйство России"), state2, low_db)
    check("ruscha mavzu: til aniqlandi", (await state2.get_data())["presentation_language"] == "ru")
    await pp.premium_ppt_skip_name(callback(chat2, "prem_ppt_skip_name"), state2, low_db)
    await pp.premium_ppt_got_preferences(chat2.message("Qisqa va vizual"), state2, low_db)
    await pp.premium_ppt_chose_source(callback(chat2, "prem_ppt_source:ai"), state2, low_db)
    await pp.premium_ppt_style_selected(callback(chat2, "ppt_style:fon"), state2, low_db)
    check("kam balans hajm oynasida ko'rinadi", "1,500" in chat2.last()[1], chat2.last()[1])
    await pp.premium_ppt_fon_count(callback(chat2, "ppt_fon:10"), state2, low_db)
    data2 = await state2.get_data()
    check("10 slayd: oddiy oqimga o'tadi",
          await state2.get_state() == DocumentStates.waiting_for_payment.state and data2.get("price") == 5000, data2)
    check("o'tkazib yuborilgan ism o'rniga foydalanuvchi ismi", data2.get("author_name") == "Ali", data2.get("author_name"))
    check("AI ga tushuntirish oddiy oqimga o'tdi", data2.get("book_context") == "Qisqa va vizual", data2.get("book_context"))
    check("hamma so'rovlar o'chdi (suhbat toza)", len(chat2.deleted) >= 6, chat2.deleted)

    # Inglizcha mavzu
    chat3, state3 = Chat(), await new_state()
    await pp.premium_presentation_start(chat3.message("🌟 Taqdimot"), state3, db)
    await pp.premium_ppt_got_topic(chat3.message("The impact of climate change on agriculture"), state3, db)
    check("inglizcha mavzu: til aniqlandi", (await state3.get_data())["presentation_language"] == "en")

    # Qisqa mavzu rad etiladi, so'rov o'chmaydi
    chat4, state4 = Chat(), await new_state()
    await pp.premium_presentation_start(chat4.message("🌟 Taqdimot"), state4, db)
    before = list(chat4.deleted)
    await pp.premium_ppt_got_topic(chat4.message("ab"), state4, db)
    check("qisqa mavzu: so'rov qoladi va xato aytiladi",
          chat4.deleted == before and "juda qisqa" in chat4.last()[1] and await state4.get_state() == PS.waiting_for_topic_text.state)

    # Manba: fayl so'raladi va so'rov qaytish tugmasi bilan keladi
    chat5, state5 = Chat(), await new_state()
    await pp.premium_presentation_start(chat5.message("🌟 Taqdimot"), state5, db)
    await pp.premium_ppt_got_topic(chat5.message("Ekologiya asoslari"), state5, db)
    await pp.premium_ppt_skip_name(callback(chat5, "prem_ppt_skip_name"), state5, db)
    await pp.premium_ppt_skip_preferences(callback(chat5, "prem_ppt_skip_preferences"), state5, db)
    await pp.premium_ppt_chose_source(callback(chat5, "prem_ppt_source:file"), state5, db)
    check("fayl manbasi: fayl kutiladi", await state5.get_state() == PS.waiting_for_source_file.state)
    await pp.premium_ppt_previous(callback(chat5, "prem_ppt_prev"), state5, db)
    check("fayl so'rovidan orqaga: manba tanlovi", await state5.get_state() == PS.waiting_for_source_kind.state)

asyncio.run(full_flow())

print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
