"""Rasm manbasi — mijoz tanlovi: internetdan / AI chizadi / aralash.

- "web": avval internet qidiruvi; topilmagan joyni AI chizadi (rasm bloki bo'sh qolmaydi — mijozga shunday aytiladi);
- "ai": internetga qaralmaydi, hammasini AI chizadi;
- "mix" (sukut): avval internet, topilmaganini AI chizadi;
- rasm manbasi alohida qadamda tanlanadi (uchta tugma), xulosada yoziladi; 3D Pro'da tanlov yo'q;
- rang: «🎨 Rang» tugmasi ranglar ro'yxatini ochadi (faqat to'q ranglar va «Avto»).

    python test_rasm_manbasi.py
"""
import asyncio, os, sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services.premium_presentation import html_images

PAGE = '<section class="slide"><div class="body"><div class="rasm" data-prompt="{p}"></div></div></section>'
COVER = '<section class="slide dark"><div class="body"><h1 class="title big">Mavzu</h1></div></section>'


def run(source, found):
    """found — internet natijasi har slot uchun (None — topilmadi). (qo'yilgan, qidirildimi, chizilganlar)"""
    calls = {"find": 0, "drawn": []}

    async def find(topic, slots, **kw):
        calls["find"] += 1
        return list(found)[:len(slots)]

    async def generate(prompt):
        calls["drawn"].append(prompt)
        return "/ai.png"

    pages = [PAGE.format(p="bir"), PAGE.format(p="ikki")]
    with patch.object(html_images, "_take_uri", lambda path: "data:image/png;base64,AA" if path else None), \
            patch.object(html_images, "_together_generate", lambda aspect="4:3": generate):
        _, placed = asyncio.run(html_images.fill_photos(pages, topic="Mavzu", source=source,
                                                        find=find if source != "ai" else None))
    return placed, calls


print("1) Slayd rasmlari")
placed, calls = run("web", ["/web1.jpg", None])
check("internetdan: qidiriladi, topilmaganini AI chizadi (bo'sh qolmaydi)", calls["find"] == 1
      and len(calls["drawn"]) == 1 and placed == 2, (placed, calls))
placed, calls = run("ai", ["/web1.jpg", "/web2.jpg"])
check("AI: internetga qaralmaydi, ikkalasini chizadi", calls["find"] == 0 and len(calls["drawn"]) == 2
      and placed == 2, (placed, calls))
placed, calls = run("mix", ["/web1.jpg", None])
check("aralash: internetdan topilgani, qolganini AI", calls["find"] == 1 and len(calls["drawn"]) == 1
      and placed == 2, (placed, calls))
placed, calls = run("noma'lum", ["/web1.jpg", None])
check("noma'lum qiymat — aralash", placed == 2 and len(calls["drawn"]) == 1, (placed, calls))

print("\n2) Muqova rasmi")
async def cover(source, found):
    calls = {"find": 0}
    async def find(topic, slots, **kw):
        calls["find"] += 1
        return [found]
    async def generate(subject):
        calls["drawn"] = True
        return "/ai.png"
    with patch.object(html_images, "_take_uri", lambda path: "data:image/png;base64,AA" if path else None):
        _, done = await html_images.fill_cover([COVER], "Mavzu", generate=generate, find=find, source=source)
    return done, calls
done, calls = asyncio.run(cover("web", None))
check("internetdan: muqova topilmasa AI chizadi", done and calls["find"] == 1 and calls.get("drawn"), calls)
done, calls = asyncio.run(cover("ai", "/web.jpg"))
check("AI: muqova internetdan qidirilmaydi, chiziladi", done and calls["find"] == 0 and calls.get("drawn"), calls)
done, calls = asyncio.run(cover("mix", None))
check("aralash: muqova topilmasa AI chizadi", done and calls["find"] == 1 and calls.get("drawn"), calls)

print("\n3) Bot: rasm manbasi qadami va xulosa")
from bot.handlers import premium_presentation as h
data = {"topic": "Plombalar", "slide_count": 10, "presentation_language": "ru"}


async def photo_step():
    shown = {}

    async def prompt(message, state, text, markup, key, new_state):
        shown.update(text=text, markup=markup)
    with patch.object(h, "_prompt", prompt):
        from aiogram.fsm.context import FSMContext
        from aiogram.fsm.storage.base import StorageKey
        from aiogram.fsm.storage.memory import MemoryStorage
        state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=4, user_id=4))
        await state.update_data(**data)
        await h._step_photos(SimpleNamespace(), state, "uz")
    return shown
shown = asyncio.run(photo_step())
buttons = [b for row in shown["markup"].inline_keyboard for b in row if b.callback_data.startswith("prem_ppt_img:")]
check("alohida qadamda uchta tugma (aralash birinchi — tavsiya)", [b.callback_data for b in buttons] ==
      ["prem_ppt_img:mix", "prem_ppt_img:web", "prem_ppt_img:ai"], buttons)
check("internet rejimida AI to'ldirishi mijozga aytilgan (va'da xatti-harakatga mos)",
      "AI chizadi" in shown["text"] and "o'rniga matn" not in shown["text"], shown["text"])
text, markup = h._summary(data, "uz")
check("xulosada rasm manbasi yozilgan", "🖼 Rasmlar" in text and "avval internetdan" in text, text)
text, markup = h._summary({**data, "photo_source": "web"}, "uz")
check("internet tanlangani xulosada", "haqiqiy fotosuratlar" in text, text)
pro = {**data, "kind": h.KIND_PRO3D}
text, markup = h._summary(pro, "uz")
check("3D Pro'da tanlov yo'q", h._photo_source(pro) is None and "prem_ppt_img:" not in str(markup)
      and "🖼 Rasmlar" not in text)

stored = {}
async def tap(value):
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=5, user_id=5))
    await state.update_data(**data)
    shown = []

    async def prompt(message, state, text, markup, key, new_state=None, photo=""):
        shown.append(key)
    cb = SimpleNamespace(data=f"prem_ppt_img:{value}", answer=AsyncMock(), from_user=SimpleNamespace(id=5),
                         message=SimpleNamespace())
    with patch.object(h, "_lang_of", AsyncMock(return_value="uz")), patch.object(h, "_prompt", prompt), \
            patch.object(h, "_anim_offer", AsyncMock(return_value=False)):
        await h.premium_ppt_photo_source(cb, state, None)
    stored.update(await state.get_data())
    return shown
shown = asyncio.run(tap("ai"))
check("tugma bosilsa tanlov saqlanadi va keyingi qadam (xulosa) ko'rsatiladi", stored.get("photo_source") == "ai"
      and shown == ["summary"], (stored.get("photo_source"), shown))
shown = asyncio.run(tap("xyz"))
check("noto'g'ri qiymat e'tiborsiz", shown == [], shown)

print("\n4) Rang tanlash")
info = {**data, "kind": h.KIND_INFO}
text, markup = h._summary(info, "uz")
check("xulosada «🎨 Rang: Avto» tugmasi", any(b.callback_data == "prem_ppt_color" and "Avto" in b.text
      for row in markup.inline_keyboard for b in row) and "🎨 Rang" in text, text)
check("3D Pro'da rang tanlovi yo'q", h._color(pro) is None and "prem_ppt_color" not in str(h._summary(pro, "uz")[1]))
check("taklif qilinadigan ranglarda sariq va qizil yo'q", "to'q sariq" not in h.COLOR_KEYS and "qizil" not in h.COLOR_KEYS)
from services.premium_presentation import themes
import re as _re
from services.premium_presentation import deck_style as _ds
bad = {k: _re.findall(r"#(?:TONE|TINT|DEEP)\d", _ds.stylesheet(themes.get(k))) for k in themes.THEME_KEYS}
check("har bir rangda kartochka tuslari to'liq (#TONE3 kabi almashtirilmagan qolmaydi)",
      not any(bad.values()), {k: v for k, v in bad.items() if v})
check("har bir rang kaliti mavjud sxema", all(themes.get(k).key == k for k in h.COLOR_KEYS if k != "auto"))

async def pick(index):
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=6, user_id=6))
    await state.update_data(**info)
    menu = AsyncMock()
    cb = SimpleNamespace(data="prem_ppt_color", answer=AsyncMock(), from_user=SimpleNamespace(id=6),
                         message=SimpleNamespace(edit_text=menu))
    with patch.object(h, "_lang_of", AsyncMock(return_value="uz")):
        await h.premium_ppt_color_menu(cb, state, None)
        cb.data = f"prem_ppt_clr:{index}"
        edit = AsyncMock(); cb.message = SimpleNamespace(edit_text=edit)
        await h.premium_ppt_color_chosen(cb, state, None)
    return menu, edit, await state.get_data()
menu, edit, got = asyncio.run(pick(h.COLOR_KEYS.index("yashil")))
colors = [b.callback_data for row in menu.await_args.kwargs["reply_markup"].inline_keyboard for b in row]
check("ranglar ro'yxati ochiladi (7 ta)", len(colors) == 7, colors)
check("yashil tanlandi va xulosa yangilandi", got.get("theme_key") == "yashil" and edit.await_count == 1
      and "Yashil" in edit.await_args.args[0], got)
menu, edit, got = asyncio.run(pick(0))
check("«Avto» — kalit bo'sh (mavzuga qarab)", got.get("theme_key") == "")

print("\n5) Zamonaviy: xira fon rasmi va katta rasm")
CSS = "<style>.rasm.photo-in{} .backdrop{}</style>"
def pg(body, dark=False):
    return f'<html><head>{CSS}</head><body><section class="slide{" dark" if dark else ""}">{body}</section></body></html>'
photo = '<div class="split"><div class="par-col"></div><div class="rasm photo-in"><img class="photo" src="data:image/jpeg;base64,QQ" alt=""></div></div>'
formula = photo.replace('class="photo"', 'class="photo fit"').replace("QQ", "Rg")
text = '<div class="body"><p class="lead">Matn</p><div class="list"></div></div>'
icon = '<div class="body"><img class="ikon" src="data:image/png;base64,SQ"></div>'
pages = [pg(""), pg(photo), pg(text), pg(text), pg(text, dark=True), pg(icon), pg(text), pg(text), pg(text)]
check("sukut: xira fon o'chirilgan — taqdimotdagi rasm boshqa varaqda takrorlanmaydi",
      html_images.add_backdrops(pages) == pages)
with patch.object(html_images, "BACKDROP_LIMIT", 3):     # yoqilsa — qoidalar avvalgidek
    out = html_images.add_backdrops(pages)
    only_formula = html_images.add_backdrops([pg(""), pg(formula), pg(text), pg(text), pg(text)])
marked = [i for i, p in enumerate(out) if 'class="backdrop"' in p]
check("(yoqilsa) rasmsiz och matnli varaqlarning bir qismiga xira fon", marked and all(i in (2, 3, 6, 7, 8) for i in marked),
      marked)
check("(yoqilsa) to'q, ikonkali va rasmli varaqqa qo'yilmaydi", not any(i in marked for i in (0, 1, 4, 5)), marked)
check("(yoqilsa) CSS ichidagi «photo-in» so'zi varaqni rad etmaydi", bool(marked))
check("formulali rasm fon bo'lmaydi", not any('class="backdrop"' in p for p in only_formula))
from services.premium_presentation import deck_style, html_render
css = deck_style.stylesheet(themes.get("ko'k"))
check("rasm varaqning butun bo'yi bo'ylab (absolute, 44%)", "rasm.photo-in{position:absolute;top:0;bottom:0;width:44%" in css)
check("sig'ish o'lchovi chetdagi rasmni hisobga olmaydi", 'closest(".rasm.photo-in")' in html_render._MEASURE)

print("\n6) Infografika: rasm topilmasa bo'sh blok yo'q, formula rasmi kesilmaydi")
from services.premium_presentation.designer import Designer, kit
import io as _io
from PIL import Image as _Image
buf = _io.BytesIO(); _Image.new("RGB", (400, 100), (200, 0, 0)).save(buf, "JPEG")
cut = _Image.open(kit.Photo(buf.getvalue(), fit=True).crop(200, 200))
check("fit: keng rasm kvadratga kesilmay, oq hoshiya bilan", cut.size[0] == cut.size[1] == 400
      and cut.getpixel((200, 10))[0] > 240 and cut.getpixel((200, 200))[0] > 150, cut.size)
from pptx import Presentation as _Prs
nophoto = ('<html><body><section class="slide k k-rasm-chap"><div class="rasm" data-prompt="cell">'
           '<p class="rasm-matn">Hujayra mikroskopda.</p></div><div class="k-text"><h2 class="title">Hujayra</h2>'
           '<p class="lead">Hayotning birligi</p><p class="k-p">Har bir tirik organizm hujayralardan tashkil topgan.</p>'
           '</div></section></body></html>')
chosen = set()
for seed in range(12):
    designer = Designer(themes.for_deck("Hujayra", "", "kam"), "Hujayra", seed=seed)
    designer.draw(_Prs(), nophoto, 3, 10)
    chosen.update(designer.chosen)
check("rasmsiz rasmli sahifaga eski HTML qolip (bo'sh ko'k blok) tanlanmaydi", chosen and "html" not in chosen, chosen)

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
