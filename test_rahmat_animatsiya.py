""""Rahmat" animatsiyasi: taqdimot yuborilgach mijoz oxiriga harakatlanuvchi personajli sahifa qo'shadi.

- katalogdagi har animatsiyaning fayllari bor (manba, namuna video, muqova);
- sahifa qo'shiladi: GIF personaj panel rangida (chegara ko'rinmaydi), ovoz — "audio" aloqasi bilan,
  slayd ochilganda o'zi boshlanadi, yozuvlar navbat bilan paydo bo'ladi;
- funksiya sukut bo'yicha YOQILGAN, admin "🎛 Funksiyalar boshqaruvi" dan o'chira oladi;
- personaj taqdimot SOZLAMALARIDA tanlanadi (galereya: ◀ ▶, tanlash yoki «Kerak emas»), tayyor taqdimotga
  `picker.apply` sahifani qo'shadi.

    python test_rahmat_animatsiya.py
"""
import asyncio
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        FAILS.append(name)


from PIL import Image
from pptx import Presentation
from pptx.oxml.ns import qn

from services.premium_presentation import themes
from services.thanks_anim import catalog
from services.thanks_anim import slide as thanks_slide

TMP = tempfile.mkdtemp()
theme = themes.for_deck("Moliyaviy savodxonlik", "toza", "kam")

print("1) Katalog")
keys = [a.key for a in catalog.ANIMATIONS]
check("nomlar takrorlanmaydi", len(keys) == len(set(keys)))
missing = [a.key for a in catalog.ANIMATIONS if not a.ready]
check("har animatsiyaning fayllari bor", not missing, missing)
check("muqova rasmlari bor", all(os.path.exists(a.path("poster.jpg")) for a in catalog.ANIMATIONS))
check("noma'lum nom — None", catalog.get("yoq") is None and catalog.get("../x") is None)
check("nom tilga qarab", catalog.get("pul_mushuk").name("ru") == "Кот считает деньги")

print("2) Sahifa qo'shiladi")
prs = Presentation()
prs.slide_width, prs.slide_height = 12192000, 6858000
for _ in range(3):
    prs.slides.add_slide(prs.slide_layouts[6])
base = os.path.join(TMP, "base.pptx")
prs.save(base)
anim = catalog.get("anime_qiz")
out = thanks_slide.add_thanks_slide(base, os.path.join(TMP, "out.pptx"), anim, theme, "uz", "Javlonbek")
deck = Presentation(out)
check("bitta sahifa qo'shildi", len(deck.slides) == 4)
last = deck.slides[-1]
texts = " ".join(sh.text_frame.text for sh in last.shapes if sh.has_text_frame)
check("rahmat yozuvi va muallif", "E'tiboringiz uchun rahmat!" in texts and "Javlonbek" in texts, texts)
pics = [sh for sh in last.shapes if sh.shape_type == 13]
gif = [p for p in pics if p.image.content_type == "image/gif"]
check("personaj — GIF", len(gif) == 1)
audio = [p for p in pics if p._element.find(".//" + qn("a:audioFile")) is not None]
check("ovoz bor va slayddan tashqarida", len(audio) == 1 and audio[0].left < 0)
check("GIF slayd ichida", gif and gif[0].left > 0 and gif[0].top >= 0
      and gif[0].left + gif[0].width <= deck.slide_width and gif[0].top + gif[0].height <= deck.slide_height)

# GIF foni panel rangi bilan aynan bir xil — chegara ko'rinmaydi
import io
with Image.open(io.BytesIO(gif[0].image.blob)) as im:
    frames = im.n_frames
    bg = max(im.convert("RGB").getcolors(1 << 16))[1]
panels = [sh for sh in last.shapes if sh.shape_type == 1 and sh.fill.type == 1
          and abs(sh.width - deck.slide_width * 860 / 1920) < 20000]
panel_rgb = tuple(panels[0].fill.fore_color.rgb) if panels else None
check("GIF harakatlanadi (ko'p kadr)", frames > 20, frames)
check("GIF foni = panel rangi", panel_rgb == bg, (panel_rgb, bg))

timing = last._element.find(qn("p:timing"))
xml = timing is not None and __import__("lxml.etree", fromlist=["x"]).tostring(timing).decode()
check("slayd ochilganda o'zi boshlanadi", xml and 'evt="onBegin"' in xml and 'nodeType="clickEffect"' not in xml)
check("ovoz o'zi boshlanadi", xml and 'cmd="playFrom(0.0)"' in xml and "<p:audio>" in xml)
check("yozuvlar navbat bilan paydo bo'ladi", xml and xml.count('presetClass="entr"') == 5 and xml.count("<p:bldP") == 5,
      xml and xml.count('presetClass="entr"'))
import zipfile
with zipfile.ZipFile(out) as z:
    rels = z.read("ppt/slides/_rels/slide4.xml.rels").decode()
    first = z.read("ppt/slides/_rels/slide1.xml.rels").decode()
check("ovoz aloqasi — audio (video emas)", "relationships/audio" in rels and "relationships/video" not in rels)
check("boshqa sahifalarga tegilmadi", "audio" not in first)

print("3) Tillar")
check("rus", thanks_slide.texts("ru")[1] == "Спасибо за внимание!")
check("kirill", thanks_slide.texts("uz-cyrl")[1].startswith("Эътиборингиз"))
check("noma'lum til — ingliz", thanks_slide.texts("de")[1].startswith("Thank you"))
out_ru = thanks_slide.add_thanks_slide(base, os.path.join(TMP, "ru.pptx"), catalog.get("pul_mushuk"), theme, "ru", "")
ru_texts = " ".join(sh.text_frame.text for sh in Presentation(out_ru).slides[-1].shapes if sh.has_text_frame)
check("muallifsiz ham chiziladi", "Спасибо" in ru_texts and "Автор" not in ru_texts, ru_texts)

print("3b) Fonli personajlar: har birining o'z dizayni, fon chegarasi ko'rinmaydi")
import io

import numpy as np

from services.thanks_anim import solid_slide

solid = [a for a in catalog.ANIMATIONS if a.solid]
check("9 ta fonli personaj qo'shilgan", len(solid) == 9, len(solid))
check("har birining dizayni boshqa", len({a.design for a in solid}) == len(solid))
check("dizaynlar chizuvchisi bor", all(a.design in solid_slide.DESIGNS for a in solid))
check("nomlar uch tilda", all(a.name("ru") != a.name("uz") or a.key == "ayiqcha" for a in solid))
for i, a in enumerate(solid):
    lang = ("uz", "ru", "en")[i % 3]
    deck_path = thanks_slide.add_thanks_slide(base, os.path.join(TMP, f"s_{a.key}.pptx"), a, theme, lang, "Javlonbek")
    deck = Presentation(deck_path)
    last = deck.slides[-1]
    W_, H_ = deck.slide_width, deck.slide_height
    pics = [sh for sh in last.shapes if sh.shape_type == 13]
    gifs = [p for p in pics if p.image.content_type == "image/gif"]
    bgs = [p for p in pics if p.image.content_type == "image/png" and p.width == W_ and p.left == 0]
    ok = len(deck.slides) == 4 and len(gifs) == 1 and len(bgs) == 1
    check(f"{a.key}: sahifa, GIF va fon bor", ok)
    if not ok:
        continue
    g = gifs[0]
    check(f"{a.key}: personaj sahifa balandligicha, ichkarida",
          g.top == 0 and abs(g.height - H_) < 2000 and g.left >= 0 and g.left + g.width <= W_ + 2000)
    texts_ = [sh for sh in last.shapes if sh.has_text_frame and sh.text_frame.text.strip()]
    inside = all(sh.left >= 0 and sh.top >= 0 and sh.left + sh.width <= W_ and sh.top + sh.height <= H_ for sh in texts_)
    clear = all(sh.left + sh.width <= g.left or sh.left >= g.left + g.width for sh in texts_)
    check(f"{a.key}: yozuvlar sahifada va personajga tegmaydi", inside and clear and len(texts_) >= 3)
    with Image.open(io.BytesIO(g.image.blob)) as im:
        check(f"{a.key}: GIF harakatlanadi", im.n_frames > 40, im.n_frames)
        gcol = np.asarray(im.convert("RGB")).astype(int)
    edge = np.concatenate([gcol[:, :2], gcol[:, -2:]], 1).mean(1)                     # (balandlik, 3)
    with Image.open(io.BytesIO(bgs[0].image.blob)) as im:
        bgcol = np.asarray(im.convert("RGB")).astype(int)[:, 5]                      # qator ranglari (1080, 3)
    ys = np.linspace(0, len(bgcol) - 1, len(edge))
    bg_rows = np.stack([np.interp(ys, np.arange(len(bgcol)), bgcol[:, c]) for c in range(3)], 1)
    diff = np.abs(edge - bg_rows).max(1)
    check(f"{a.key}: GIF cheti = sahifa foni (tikuv ko'rinmaydi)", diff.mean() < 2.5 and np.percentile(diff, 95) < 8,
          (round(float(diff.mean()), 2), round(float(np.percentile(diff, 95)), 1)))
    t_xml = last._element.find(qn("p:timing"))
    check(f"{a.key}: ovoz va yozuv animatsiyasi", t_xml is not None and b"playFrom" in __import__("lxml.etree", fromlist=["x"]).tostring(t_xml))

print("4) Funksiya sukut bo'yicha YOQILGAN, admin o'chira oladi")
import database.database as dbmod
from database.database import Database, init_db

dbmod.DATABASE_FILE = os.path.join(TMP, "t.db")
from services import thanks_anim
from services.thanks_anim import picker


async def db_part():
    await init_db()
    db = Database()
    default_on = await db.get_feature_status(thanks_anim.FEATURE, default=True)
    offered_default = await picker.offered(db)
    from bot.handlers.admin import _feature_keyboard

    kb = await _feature_keyboard(db)
    row = [b for r in kb.inline_keyboard for b in r if "Rahmat animatsiyasi" in b.text]
    await db.set_feature_status(thanks_anim.FEATURE, False)
    offered_off = await picker.offered(db)
    kb2 = await _feature_keyboard(db)
    row2 = [b for r in kb2.inline_keyboard for b in r if "Rahmat animatsiyasi" in b.text]
    await db.set_feature_status(thanks_anim.FEATURE, True)
    return default_on, offered_default, row, offered_off, row2


default_on, offered_default, row, offered_off, row2 = asyncio.run(db_part())
check("sukut — yoqilgan, taklif chiqadi", default_on is True and offered_default is True)
check("admin panelida tugma: yoqilgan", row and "Yoqilgan" in row[0].text and row[0].callback_data == "toggle_thanks_anim_off",
      row and row[0].text)
check("admin o'chirsa — taklif chiqmaydi", offered_off is False and row2 and "O'chirilgan" in row2[0].text
      and row2[0].callback_data == "toggle_thanks_anim_on")

print("5) Tanlash oynasi (picker)")
lst = picker.items()
check("galereyada barcha 24 personaj", len(lst) == len(catalog.ANIMATIONS) == 24, len(lst))
pm = picker.pager_markup(0, "uz")
cbs = [b.callback_data for r in pm.inline_keyboard for b in r]
check("◀ birinchidan oxirgisiga o'tadi, ▶ keyingisiga", f"prem_thx:go:{len(lst) - 1}" in cbs and "prem_thx:go:1" in cbs, cbs)
check("tanlash tugmasi personaj kalitini beradi", f"prem_thx:pick:{lst[0].key}" in cbs and "prem_thx:skip" in cbs
      and "prem_thx:close" in cbs)
check("callback_data 64 baytdan oshmaydi", all(len(c.encode()) <= 64 for k in range(len(lst))
                                              for r in picker.pager_markup(k, "ru").inline_keyboard
                                              for c in [b.callback_data for b in r]))
check("ro'yxat oxirida aylanadi", f"prem_thx:go:0" in [b.callback_data for r in picker.pager_markup(len(lst) - 1, "en").inline_keyboard for b in r])
q = picker.question_markup("uz", "", [])
qc = [b.callback_data for r in q.inline_keyboard for b in r]
check("savolda «tanlash» va «kerak emas» bor (tanlash majburiy emas)", qc[:2] == ["prem_thx:open", "prem_thx:skip"], qc)
check("«mutlaqo tekin» deyilgan", "mutlaqo tekin" in picker.question_text("uz") and "бесплатно" in picker.question_text("ru"))
check("tanlangan personaj savolda ko'rinadi", "Paxmoq" in picker.question_text("uz", "paxmoq"))
check("nom tilga qarab, qozoqcha — ruscha", picker.name_of("paxmoq", "ru") == "Пушистик" and picker.name_of("paxmoq", "kk") == "Пушистик")
check("start indeks: tanlangan personajdan", lst[picker.start_index("pingvin")].key == "pingvin"
      and picker.start_index("") == 0 and picker.start_index("yoq") == 0)

# taqdimotga qo'shish: tanlangan personaj oxirgi sahifaga tushadi, boshqa sahifalar o'zgarmaydi
deck_path = os.path.join(TMP, "apply.pptx")
shutil.copy(base, deck_path)
res = picker.apply(deck_path, "pingvin", topic="Moliya", style="toza", volume="kam", theme_key="", language="ru",
                   author="Ali")
applied = Presentation(deck_path)
check("apply: sahifa qo'shildi (joyida)", res == deck_path and len(applied.slides) == 4)
t_ = " ".join(sh.text_frame.text for sh in applied.slides[-1].shapes if sh.has_text_frame)
check("apply: tanlangan tilda va muallif bilan", "Спасибо" in t_ and "Ali" in t_, t_)
shutil.copy(base, deck_path)
check("apply: noma'lum personaj — o'zgarishsiz (None)", picker.apply(deck_path, "yoq", topic="T", style="", volume="",
                                                                      theme_key="", language="uz", author="") is None
      and len(Presentation(deck_path).slides) == 3)

print("6) Admin/xulosa: eski «tugagandan keyin» taklifi yo'q")

pp_src = open(os.path.join(HERE, "bot", "handlers", "premium_presentation.py"), encoding="utf-8").read()
check("tugagandan keyingi taklif olib tashlangan", "_offer_thanks_anim" not in pp_src and "tanim_no" not in pp_src)
check("mini oyna yo'li yo'q", not os.path.exists(os.path.join(HERE, "webapp", "thanks_anim.py")))

shutil.rmtree(TMP, ignore_errors=True)
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
