"""«🟩 Boshqa professional xizmatlar» → «🎬 Personaj qo'shish» (bepul, faqat botda).

Tugma mini ilovani darhol ochadi (`/anim?mode=add`), tanlov `/start thxadd_<kalit>` bilan qaytadi, bot .pptx faylni
so'raydi va oxiriga «Rahmat» sahifasini qo'shib qaytaradi. 4:3 va boshqa o'lchamdagi taqdimotga ham sahifa
moslashadi, pul yechilmaydi.

    python test_personaj_qoshish.py
"""
import asyncio
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        FAILS.append(name)


import webapp  # noqa: E402
from aiogram.fsm.context import FSMContext  # noqa: E402
from aiogram.fsm.storage.base import StorageKey  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from pptx import Presentation  # noqa: E402
from pptx.util import Inches  # noqa: E402

from bot.handlers import thanks_service as ts  # noqa: E402
from bot.keyboards import get_other_services_keyboard  # noqa: E402
from bot.states import ThanksAddStates  # noqa: E402
from services.thanks_anim import catalog, picker  # noqa: E402

webapp.WEBAPP_DOMAIN = "edufayl.org"
TMP = tempfile.mkdtemp()
KEY = catalog.available()[0].key


def deck(path, w, h, n=2):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(w), Inches(h)
    for i in range(n):
        prs.slides.add_slide(prs.slide_layouts[1]).shapes.title.text = f"Slayd {i + 1}"
    prs.save(path)
    return path


class Bot:
    def __init__(self, src): self.src = src
    async def download(self, doc, destination):
        import shutil
        shutil.copyfile(self.src, destination)


class Msg:
    def __init__(self, bot, doc=None, text=None):
        self.bot, self.document, self.text = bot, doc, text
        self.from_user = types.SimpleNamespace(id=501)
        self.answers, self.docs = [], []
    async def answer(self, text, **kw):
        self.answers.append((text, kw))
        async def _del(): pass
        return types.SimpleNamespace(delete=_del)
    async def answer_document(self, document, caption=None, **kw):
        out = os.path.join(TMP, "got_" + document.filename)
        import shutil
        shutil.copyfile(document.path, out)
        self.docs.append((out, caption))
    async def delete(self): pass


def state():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=501, user_id=501))


async def main():
    print("1) Tugma — mini ilova darhol ochiladi")
    kb = get_other_services_keyboard("uz", thanks_url=picker.add_service_url("uz"))
    btn = [b for row in kb.inline_keyboard for b in row if b.text == "🎬 Personaj qo'shish"]
    check("«🎬 Personaj qo'shish» — mini ilova tugmasi (mode=add)", btn and btn[0].web_app and "mode=add" in btn[0].web_app.url
          and "/anim?" in btn[0].web_app.url, btn)
    kb_off = get_other_services_keyboard("uz")
    check("funksiya o'chiq bo'lsa tugma yo'q", not any(b.text.startswith("🎬") for row in kb_off.inline_keyboard for b in row))
    page = open("webapp/thanks_anim.html", encoding="utf8").read()
    check("mini ilova: mode=add bo'lsa tanlov thxadd_ bilan qaytadi (taqdimot buyurtmasi buzilmaydi)",
          "'thxadd_'" in page and "'thx_'" in page)

    print("2) Personaj tanlandi — fayl so'raladi")
    st = state()
    m = Msg(None)
    await ts.thanks_chosen(m, types.SimpleNamespace(args="thxadd_" + KEY), st, "uz")
    check("holat: fayl kutilmoqda, personaj eslab qolindi", await st.get_state() == ThanksAddStates.waiting_for_file.state
          and (await st.get_data())["thanks_key"] == KEY)
    check("xabar: tanlangan personaj, .pptx yuboring, bepul", ".pptx" in m.answers[-1][0] and "bepul" in m.answers[-1][0]
          and picker.name_of(KEY, "uz") in m.answers[-1][0], m.answers)
    st2 = state(); m2 = Msg(None)
    await ts.thanks_chosen(m2, types.SimpleNamespace(args="thxadd_none"), st2, "ru")
    check("mini ilovada «Kerak emas» — bekor qilindi (ruscha)", await st2.get_state() is None and "Отменено" in m2.answers[-1][0])

    print("3) Fayl")
    bad = Msg(Bot(""), doc=types.SimpleNamespace(file_name="ish.docx", file_size=1000))
    await ts.thanks_file(bad, st, "uz")
    check("pptx emas — rad, holat qoladi", ".pptx" in bad.answers[-1][0] and await st.get_state() == ThanksAddStates.waiting_for_file.state)
    big = Msg(Bot(""), doc=types.SimpleNamespace(file_name="katta.pptx", file_size=25 * 1024 * 1024))
    await ts.thanks_file(big, st, "uz")
    check("20 MB dan katta — tushuntirish", "20 MB" in big.answers[-1][0], big.answers)
    for label, w, h in (("4:3", 10, 7.5), ("16:9", 13.333, 7.5)):
        st3 = state()
        await st3.set_state(ThanksAddStates.waiting_for_file); await st3.update_data(thanks_key=KEY)
        src = deck(os.path.join(TMP, f"in_{w}.pptx"), w, h)
        m3 = Msg(Bot(src), doc=types.SimpleNamespace(file_name=f"Mening ishim {label.replace(':', 'x')}.pptx", file_size=os.path.getsize(src)))
        await ts.thanks_file(m3, st3, "uz")
        ok = bool(m3.docs)
        prs = Presentation(m3.docs[0][0]) if ok else None
        check(f"{label}: fayl qaytdi, nomi o'sha, oxiriga 1 sahifa qo'shildi", ok and len(prs.slides) == 3
              and os.path.basename(m3.docs[0][0]) == f"got_Mening ishim {label.replace(':', 'x')}.pptx", m3.answers)
        if ok:
            W, H = prs.slide_width, prs.slide_height
            last = prs.slides[-1]
            inside = [sh for sh in last.shapes if sh.shape_type != 16 and sh.width and sh.height < H * 3]
            out = [sh.name for sh in inside if sh.left + sh.width > W * 1.02 or sh.top + sh.height > H * 1.02
                   and not sh.name.startswith("Media")]
            pics = [sh for sh in last.shapes if sh.shape_type == 13]
            check(f"{label}: sahifa o'lchamiga moslashgan (fon butun sahifada, chetdan chiqqan narsa yo'q)",
                  pics and pics[0].width == W and not [n for n in out if not n.startswith(("Media", "Rectangle"))], out[:5])
            check(f"{label}: tayyor xabari, holat tozalandi", "Tayyor" in (m3.docs[0][1] or "")
                  and await st3.get_state() is None, m3.docs[0][1])
    # Ichida «Rahmat» sahifasi (ovozli) bor taqdimot — ilgari «ochib bo'lmadi» bo'lardi; endi eski sahifa
    # yangi personaj bilan almashtiriladi (ikkinchi sahifa qo'shilmaydi). Eski fayllarda belgi yo'q — matndan topiladi.
    from services.thanks_anim import slide as thx_slide
    others = [KEY] + [a.key for a in catalog.available() if a.key != KEY][:1]
    for i, (other, legacy) in enumerate([(k, lg) for k in others for lg in (False, True)]):
        st5 = state(); await st5.set_state(ThanksAddStates.waiting_for_file); await st5.update_data(thanks_key=other)
        src = deck(os.path.join(TMP, f"ovozli_{i}.pptx"), 13.333, 7.5)
        picker.apply(src, KEY, topic="x", style="", volume="kop", theme_key="", language="ru", author="")
        if legacy:                                  # belgisiz (oldingi versiyada yaratilgan) fayl
            p0 = Presentation(src); p0.slides[-1]._element.cSld.attrib.pop("name", None); p0.save(src)
        m5 = Msg(Bot(src), doc=types.SimpleNamespace(file_name=f"Ovozli {i}.pptx", file_size=os.path.getsize(src)))
        await ts.thanks_file(m5, st5, "uz")
        got = Presentation(m5.docs[0][0]) if m5.docs else None
        marks = [sl for sl in got.slides if thx_slide._is_thanks(sl)] if got else []
        check(f"«Rahmat» bor taqdimot: almashtirildi ({'o\'sha' if other == KEY else 'boshqa'} personaj"
              f"{', eski fayl' if legacy else ''})",
              got is not None and len(got.slides) == 3 and len(marks) == 1 and thx_slide._is_thanks(got.slides[-1])
              and "rahmat" in " ".join(sh.text_frame.text for sh in got.slides[-1].shapes if sh.has_text_frame).lower(),
              m5.answers)
    st4 = state(); await st4.set_state(ThanksAddStates.waiting_for_file); await st4.update_data(thanks_key=KEY)
    broken = os.path.join(TMP, "buzuq.pptx"); open(broken, "wb").write(b"PK\x03\x04 buzuq")
    m4 = Msg(Bot(broken), doc=types.SimpleNamespace(file_name="buzuq.pptx", file_size=20))
    await ts.thanks_file(m4, st4, "uz")
    check("buzuq fayl — tushunarli xato, holat qoladi (boshqa faylni yuborishi mumkin)",
          "ochib bo'lmadi" in m4.answers[-1][0] and await st4.get_state() == ThanksAddStates.waiting_for_file.state, m4.answers)

    import inspect
    src_code = inspect.getsource(ts)
    check("bepul: balans/to'lov kodi yo'q", "balance" not in src_code and "price" not in src_code)

    print("\n✅ hammasi o'tdi" if not FAILS else f"\n❌ {len(FAILS)} ta xato: {FAILS}")
    sys.exit(1 if FAILS else 0)


asyncio.run(main())
