"""O'zbekcha taqdimot: lotin va kirill yozuvi aralashmaydi.

    python test_yozuv_lotin_kirill.py
"""
import asyncio, datetime, os, re, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services import uz_script as u

print("1) O'girish")
pairs = {
    "Tahlil jadvali": "Таҳлил жадвали",
    "E'tiboringiz uchun rahmat!": "Эътиборингиз учун раҳмат!",
    "O'zbekiston Respublikasi": "Ўзбекистон Республикаси",
    "yo'q, yaxshi, Yevropa": "йўқ, яхши, Европа",
    "Sun'iy intellekt va ta'lim": "Сунъий интеллект ва таълим",
    "Ijtimoiy-siyosiy kontekst": "Ижтимоий-сиёсий контекст",
    "Jahon adabiyoti, Mutafakkirlar": "Жаҳон адабиёти, Мутафаккирлар",
}
for latin, cyrillic in pairs.items():
    check(f"lotin → kirill: {latin}", u.to_cyrillic(latin) == cyrillic, u.to_cyrillic(latin))
back = {
    "Таҳлилнинг асосий йўналишлари": "Tahlilning asosiy yo'nalishlari",
    "Эътиборингиз учун раҳмат!": "E'tiboringiz uchun rahmat!",
    "Европа, ёш, ҳаёт": "Yevropa, yosh, hayot",
    "ҚИЁСИЙ-ТИПОЛОГИК МЕТОД": "QIYOSIY-TIPOLOGIK METOD",
    "Адабиёт ва фалсафа уйғунлиги": "Adabiyot va falsafa uyg'unligi",
}
for cyrillic, latin in back.items():
    check(f"kirill → lotin: {cyrillic}", u.to_latin(cyrillic) == latin, u.to_latin(cyrillic))
keep = "AI va PDF, x = 3, $x^2$ &amp; mg, edu.uz, info@mail.ru, https://t.me/Edufayl_bot"
out = u.to_cyrillic(keep)
check("formula, qisqartma, birlik, havola tegilmaydi",
      all(part in out for part in ("AI", "PDF", "x = 3", "$x^2$", "&amp;", "mg", "edu.uz", "info@mail.ru", "https://t.me/Edufayl_bot")), out)
check("oddiy so'z (va) o'giriladi", " ва " in out, out)
check("lotin matnga tegilmaydi (lotinga)", u.to_latin("Tahlil jadvali") == "Tahlil jadvali")
check("kirill matnga tegilmaydi (kirillga)", u.to_cyrillic("Таҳлил") == "Таҳлил")

print("\n2) Tayyor fayl")
from pptx import Presentation
from pptx.util import Inches
prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[6])
box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
box.text_frame.text = "Режа"
para = box.text_frame.add_paragraph(); para.text = "1. Mutafakkirlar ta'limoti nazariyasi"
table = slide.shapes.add_table(2, 2, Inches(1), Inches(3), Inches(6), Inches(1)).table
table.cell(0, 0).text = "Tahlil jadvali"; table.cell(0, 1).text = "Таҳлил натижалари"
table.cell(1, 0).text = "E'tiboringiz uchun rahmat!"; table.cell(1, 1).text = "2020"
def texts(path):
    p = Presentation(path); out = []
    for s in p.slides:
        for sh in s.shapes:
            if sh.has_text_frame: out.append(sh.text_frame.text)
            if getattr(sh, "has_table", False) and sh.has_table:
                out += [c.text for r in sh.table.rows for c in r.cells]
    return " ".join(out)
for script, bad in (("latin", re.compile(r"[Ѐ-ӿ]")), ("cyrillic", re.compile(r"\b[A-Za-z]{3,}\b"))):
    path = tempfile.mktemp(suffix=".pptx"); prs.save(path)
    changed = u.normalize_pptx(path, script)
    result = texts(path)
    check(f"{script}: faylda boshqa yozuv qolmadi", not bad.search(result) and changed > 0, result)
    check(f"{script}: raqam saqlandi", "2020" in result)

print("\n3) Premium slayd HTML")
from services.premium_presentation import html_slides, themes
body = ('<section class="slide"><div class="head"><h2 class="title">Tahlil jadvali</h2></div><div class="body">'
        '<div class="chart" data-kind="bar" data-labels="Savdo,Xizmat" data-series="Ulush: 40,30" data-unit="mln so\'m"></div>'
        '<div class="rasm" data-prompt="documentary photo of a hospital"><p class="rasm-matn">Ta\'limning ahamiyati.</p></div>'
        '<div class="formula"><div class="formula-body">$x^2 = 4$</div></div></div></section>')
theme = themes.get("ko'k")
page_cyr = html_slides.build_pages([body], theme, "uz-cyrl")[0]
visible = re.sub(r"<style.*?</style>|<script.*?</script>|<!--.*?-->|<svg.*?</svg>", " ", page_cyr, flags=re.S)
check("kirill sahifa: sarlavha kirillda", "Таҳлил жадвали" in page_cyr)
check("kirill sahifa: diagramma yorlig'i kirillda", "Савдо" in page_cyr and "Хизмат" in page_cyr)
check("kirill sahifa: rasm tavsifi ingliz tilida qoldi", "documentary photo of a hospital" in page_cyr)
check("kirill sahifa: formula o'zgarmadi", "x" in page_cyr and "Tahlil" not in visible)
page_lat = html_slides.build_pages([body.replace("Tahlil jadvali", "Таҳлил жадвали")], theme, "uz")[0]
check("lotin sahifa: kirill qolmadi", "Tahlil jadvali" in page_lat and "Таҳлил" not in re.sub(r"<!--.*?-->", "", page_lat, flags=re.S))
rule = html_slides.shell_rules(theme, "uz-cyrl")
check("model kirillda yozishi so'raladi", "KIRILL" in rule)
check("lotin uchun kirillsiz yozish so'raladi", "lotin" in html_slides.shell_rules(theme, "uz").lower())

print("\n4) Model so'rovi")
msgs = [{"role": "user", "content": "Write slides"}]
check("yozuv belgilanmasa so'rov o'zgarmaydi", u.with_rule(msgs) == msgs)
token = u.use("cyrillic")
sent = u.with_rule(msgs)
u.reset(token)
check("kirill tanlansa qoida so'rovga qo'shiladi", "CYRILLIC" in sent[-1]["content"] and sent[-1]["content"].startswith("Write slides"))
check("asl ro'yxat o'zgarmadi", msgs == [{"role": "user", "content": "Write slides"}])
check("reset qilingach qoida qolmaydi", u.with_rule(msgs) == msgs)

print("\n5) Bot: yozuvni so'rash")
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import GetMe, SendMessage
from aiogram.types import Message, Update, User
from bot.handlers import premium_presentation as pp
from bot.states import PremiumPresentationStates as PS

sent_texts = []
class FakeSession(BaseSession):
    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, SendMessage):
            sent_texts.append((method.text, method.reply_markup))
            return Message.model_validate({"message_id": 50 + len(sent_texts), "date": 0,
                                           "chat": {"id": 5, "type": "private"}, "text": method.text})
        if isinstance(method, GetMe):
            return User(id=123, is_bot=True, first_name="B", username="edufaylbot")
        return True
    async def stream_content(self, *a, **k):
        yield b""
    async def close(self): pass

class FakeDb:
    async def get_user(self, user_id): return None

async def main():
    bot = Bot("123:abc", session=FakeSession())
    dp = Dispatcher(storage=MemoryStorage())
    async def inject(handler, event, data):
        data.update(user_lang="uz", db=FakeDb(), user=None); return await handler(event, data)
    dp.message.middleware(inject); dp.callback_query.middleware(inject)
    pp.router._parent_router = None
    dp.include_router(pp.router)
    state = FSMContext(storage=dp.storage, key=StorageKey(bot_id=123, chat_id=5, user_id=5))
    n = [0]
    base = lambda: {"date": int(datetime.datetime.now().timestamp()), "chat": {"id": 5, "type": "private"},
                    "from": {"id": 5, "is_bot": False, "first_name": "T"}}
    async def say(text):
        n[0] += 1
        await dp.feed_update(bot, Update.model_validate({"update_id": n[0], "message": {"message_id": n[0], **base(), "text": text}}))
    async def press(data):
        n[0] += 1
        await dp.feed_update(bot, Update.model_validate({"update_id": n[0], "callback_query": {
            "id": str(n[0]), "chat_instance": "x", "data": data, "from": base()["from"],
            "message": {"message_id": 99, **base(), "text": "x"}}}))

    async def start(topic):
        await state.clear(); await state.set_state(PS.waiting_for_topic_text); await state.set_data({})
        sent_texts.clear(); await say(topic)

    await start("Мутафаккирлар таълимоти ва ўзбек адабиёти")
    check("kirillcha o'zbek mavzu: yozuv so'raladi", await state.get_state() == PS.waiting_for_script.state, await state.get_state())
    buttons = [b.callback_data for row in sent_texts[-1][1].inline_keyboard for b in row]
    check("... lotin va kirill tugmalari bor", "prem_ppt_script:latin" in buttons and "prem_ppt_script:cyrillic" in buttons, buttons)

    await press("prem_ppt_script:cyrillic")
    data = await state.get_data()
    check("kirill tanlandi: til uz-cyrl, mavzu o'zgarmadi",
          data.get("presentation_language") == "uz-cyrl" and data["topic"].startswith("Мутафаккирлар"), data)
    check("... keyingi savol — ism", await state.get_state() == PS.waiting_for_client_name.state, await state.get_state())

    await start("Мутафаккирлар таълимоти ва ўзбек адабиёти")
    await press("prem_ppt_script:latin")
    data = await state.get_data()
    check("lotin tanlandi: mavzu lotinga o'tdi, til uz",
          data.get("presentation_language") == "uz" and data["topic"] == "Mutafakkirlar ta'limoti va o'zbek adabiyoti", data)

    await start("Mutafakkirlar ta'limoti va o'zbek adabiyoti")
    check("lotin mavzu: yozuv so'ralmaydi", await state.get_state() == PS.waiting_for_client_name.state, await state.get_state())
    await start("История развития русской литературы")
    check("ruscha mavzu: yozuv so'ralmaydi", await state.get_state() == PS.waiting_for_client_name.state
          and (await state.get_data()).get("presentation_language") == "ru")

    # Xulosa: 4 ta til/yozuv tugmasi
    text, markup = pp._summary({"topic": "Mavzu", "presentation_language": "uz-cyrl", "slide_count": 10, "style": "toza"}, "uz")
    codes = [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data.startswith("prem_ppt_lang:")]
    check("xulosada lotin/kirill/rus/ingliz/qozoq tugmalari", codes == ["prem_ppt_lang:uz", "prem_ppt_lang:uz-cyrl", "prem_ppt_lang:ru", "prem_ppt_lang:en", "prem_ppt_lang:kk"], codes)
    check("tasdiq oynasida tanlangan til belgisi (✓) bor",
          any(b.text.startswith("✓") and b.callback_data == "prem_ppt_lang:uz-cyrl" for row in markup.inline_keyboard for b in row))
    summary = pp._order_summary({"topic": "Mavzu", "presentation_language": "uz-cyrl", "slide_count": 10}, "uz")
    check("buyurtma tafsilotida yozuv ko'rsatilgan", "UZ (кирилл)" in summary, summary)

    # Orqaga: ism → yozuv → mavzu
    await start("Мутафаккирлар таълимоти ва ўзбек адабиёти"); await press("prem_ppt_script:cyrillic")
    await press("prem_ppt_prev")
    check("ismdan orqaga — yozuv tanlovi", await state.get_state() == PS.waiting_for_script.state, await state.get_state())
    await press("prem_ppt_prev")
    check("yozuvdan orqaga — mavzu", await state.get_state() == PS.waiting_for_topic_text.state, await state.get_state())
    await bot.session.close()

asyncio.run(main())
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
