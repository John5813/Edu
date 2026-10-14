"""Aniq fanlar va arzon model himoyalari (25/20 slaydli jonli sinovlarda topilgan nuqsonlar).

- mavzu oilasi: model "umumiy" desa ham matematika/fizika mavzusi "aniq" bo'ladi;
- aniq fanda masala/mashq slaydi — ishlangan misol; rasmlar soni kamaytirilmaydi;
- rejadagi misol/formula bloki slaydda bo'lmasa — qayta so'raladi;
- 1-slayd muqova bo'lmasa (oddiy slayd yoki reja yozilgan) — muqova kod bilan yig'iladi;
- aniq fanda formulali/grafikli rasmlar ruxsat, slayd skrinshotlari esa yo'q;
- to'qima iqtibos ("mutaxassislar") oddiy gapga aylanadi;
- formulada «$D < 0$» xom qolmaydi, «b^2» daraja bo'ladi;
- aniq fanda «(2026)» ko'rsatkich/prognoz slaydi o'rniga amaliy masala; takror slayd — masala.

    python test_aniq_fan.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services import photo_search
from services.premium_presentation import deck_shape, html_slides

print("1) Mavzu oilasi")
for topic, hint, want in [("Kvadrat tenglamalar va ularni yechish usullari", "umumiy", "aniq"),
                          ("Nyutonning harakat qonunlari", "", "aniq"),
                          ("Trigonometrik funksiyalar", "umumiy", "aniq"),
                          ("Kvadrat tenglamalar va ularni yechish usullari", "hisob", "aniq"),
                          ("Amir Temur saltanati", "tarix", "tarix")]:
    got = deck_shape.of(topic, hint)
    check(f"«{topic}» → {want}", got == want, got)

print("\n2) Aniq fan rejasi: masala slaydi — misol, rasmlar kamaymaydi")
outline = ([{"title": "M", "brief": "", "category": "muqova"}, {"title": "R", "brief": "", "category": "reja"}]
           + [{"title": t, "brief": "b", "category": c} for t, c in
              [("Kvadrat tenglama ta'rifi", "matn_rasm"), ("Testlar va mashqlar", "kartalar"),
               ("Amaliy masalalar yechish", "matn_rasm"), ("Grafik usul", "matn_rasm")]]
           + [{"title": "X", "brief": "", "category": "yakun"}])
out = html_slides.exact_rules([dict(o) for o in outline], "aniq")
cats = [o["category"] for o in out]
check("masala/mashq slaydlari misol bo'ldi", cats[3] == "misol" and cats[4] == "misol", cats)
check("qolgan rasmli slaydlar o'z holicha (rasm kamaymaydi)", cats[2] == "matn_rasm" and cats[5] == "matn_rasm", cats)
check("boshqa fanlarda tegilmaydi", [o["category"] for o in html_slides.exact_rules([dict(o) for o in outline], "tarix")]
      == [o["category"] for o in outline])

print("\n3) Rejadagi blok slaydda bo'lishi shart")
check("misol slaydida misol yo'q — qayta so'raladi",
      "misol" in html_slides._missing_block('<div class="rasm"></div>', {"category": "misol"}))
check("misol bor — so'ralmaydi", html_slides._missing_block('<div class="misol">', {"category": "misol"}) == "")
check("formula slaydida formula yo'q — qayta so'raladi",
      "formula" in html_slides._missing_block('<p>matn</p>', {"category": "formula"}))
check("boshqa kategoriyalarda talab yo'q", html_slides._missing_block("<p>x</p>", {"category": "kartalar"}) == "")

print("\n4) 1-slayd har doim muqova")
plain = ('<section class="slide"><div class="head"><h2 class="title">Kvadrat tenglamalar</h2></div>'
         '<div class="body"><p class="lead">Umumiy ma\'lumot.</p></div></section>')
plan = ('<section class="slide"><div class="head"><h2 class="title">Taqdimot rejasi</h2></div>'
        '<div class="body"><p class="lead">Quyidagi masalalar ko\'rib chiqiladi.</p><div class="list"></div></div></section>')
fixed = html_slides._ensure_cover(plain, "Kvadrat tenglamalar", {"brief": "Tenglamalarni yechish usullari."})
check("oddiy slayd → muqova (dark, katta sarlavha, izoh)", 'class="slide dark"' in fixed and 'title big' in fixed
      and "Tenglamalarni yechish usullari." in fixed, fixed)
fixed = html_slides._ensure_cover(plan, "O'zbekiston eksporti", {"brief": "01. Kirish\n02. Tarkib"})
check("reja yozilgan bo'lsa → muqova, reja matni olinmaydi", "title big" in fixed and "rejasi" not in fixed
      and "Quyidagi masalalar" not in fixed, fixed)
good = '<section class="slide dark"><div class="body"><h1 class="title big">X</h1></div></section>'
check("to'g'ri muqova o'zgarmaydi", html_slides._ensure_cover(good, "X") == good)

print("\n5) Aniq fanda formulali rasm ruxsat, slayd yo'q")
def res(i, title, source="example.org"):
    return {"title": title, "source": source, "url": f"https://{source}/p{i}",
            "properties": {"url": f"https://{source}/i{i}.jpg", "width": 1200, "height": 800}}
raw = [res(1, "Quadratic formula diagram"), res(2, "Parabola graph of quadratic function"),
       res(3, "Quadratic equations - PowerPoint presentation"), res(4, "Lecture 5 slides"),
       res(5, "Discriminant chart", source="slideplayer.com")]
strict = [c["url"].rsplit("/", 1)[1] for c in photo_search.usable(raw)]
loose = [c["url"].rsplit("/", 1)[1] for c in photo_search.usable(raw, formulas=True)]
check("oddiy rejim: diagramma/grafik ham tashlanadi", strict == [], strict)
check("aniq fan: formula va grafik qoladi, slayd/ma'ruza/slayd sayti yo'q", loose == ["i1.jpg", "i2.jpg"], loose)
check("aniq fan: vision tekshiruvi formulani ruxsat etadi",
      "WELCOME" in photo_search._TEXT_CHECK_FORMULAS and "slide" in photo_search._TEXT_CHECK_FORMULAS)
check("aniq fan: tanlovchiga formulali rasm ruxsati aytiladi",
      photo_search._PICK_FORMULAS in photo_search._pick_prompt("t", ["s"], [], formulas=True)
      and photo_search._PICK_FORMULAS not in photo_search._pick_prompt("t", ["s"], []))

import asyncio
from services.premium_presentation import html_images
page = '<section class="slide"><div class="body"><div class="rasm" data-prompt="parabola graph"></div></div></section>'
async def _found(topic, slots, **kw):
    return ["/nonexistent.jpg"] * len(slots)
with __import__("unittest.mock").mock.patch.object(html_images, "_take_uri", lambda p: "data:image/jpeg;base64,AA"):
    got, n = asyncio.run(html_images.fill_photos([page], topic="Kvadrat tenglama", find=_found, formulas=True))
    plain_got, _ = asyncio.run(html_images.fill_photos([page], topic="Tarix", find=_found))
check("aniq fanda rasm kesilmaydi (fit), boshqa fanda — kesib to'ldiriladi",
      n == 1 and 'class="photo fit"' in got[0] and 'class="photo"' in plain_got[0], (got, plain_got))

print("\n6) To'qima iqtibos")
fake = ('<div class="body"><div><div class="quote-mark">&#8220;</div><p class="quote">Kelajakda markaz bo\'ladi.</p>'
        '<p class="quote-by">— Turizm sohasi mutaxassislari</p></div></div>')
check("«mutaxassislar» iqtibosi oddiy gapga aylandi", 'class="quote"' not in html_slides.guard_quote_sources(fake)
      and "Kelajakda markaz" in html_slides.guard_quote_sources(fake))
real = fake.replace("Turizm sohasi mutaxassislari", "Amir Temur")
check("haqiqiy iqtibos o'zgarmaydi", html_slides.guard_quote_sources(real) == real)

print("\n7) Qisqa reja: ikkinchi «reja» va ikki xulosa yo'q")
raw = [{"title": "M"}, {"title": "R"}, {"title": "A"}, {"title": "B"},
       {"title": "Xulosa", "brief": "Asosiy xulosalar", "category": "yakun"}]
stretched = html_slides._stretch(raw, 8)
check("xulosa oxirida, bo'sh o'rinlar undan oldin", [x.get("title", "") for x in stretched] == ["M", "R", "A", "B", "", "", "", "Xulosa"],
      stretched)
check("xulosasiz qisqa reja o'zgarmaydi", html_slides._stretch(raw[:-1], 6) == raw[:-1])
check("zaxira turlarda «reja» yo'q", "reja" not in html_slides._SAFE_CATEGORIES)
out = html_slides.exact_rules([{"title": "M", "brief": "", "category": "muqova"}, {"title": "R", "brief": "", "category": "reja"},
                               {"title": "Amaliy ahamiyati", "brief": "Qo'llanish sohalari.", "category": "matn_rasm"},
                               {"title": "Y", "brief": "", "category": "yakun"}], "aniq")
check("misolga o'tganda izohga masala talabi qo'shiladi", "masala" in out[2]["brief"] and out[2]["category"] == "misol", out)

padded = [{"title": "M", "brief": "", "category": "muqova"}, {"title": "R", "brief": "", "category": "reja"},
          {"title": "Kvadrat tenglamalar", "brief": "x", "category": "kartalar", "padded": True},
          {"title": "Y", "brief": "", "category": "yakun"}]
out = html_slides.exact_rules(padded, "aniq", "Kvadrat tenglamalar")
check("aniq fanda to'ldiruvchi slayd — qo'shimcha masala", out[2]["category"] == "misol" and out[2]["title"] == "Masala 1"
      and "masala" in out[2]["brief"], out[2])

print("\n8) Abzats ichidagi <ul> ro'yxati")
bad = ('<section class="slide"><div class="body"><p class="note">Jarayon:<ul><li>Birinchi.</li><li>Ikkinchi.</li></ul>'
       'Agar D=0 bo\'lsa, bitta ildiz.</p></div></section>')
fixed = html_slides._fix_html_lists(bad)
check("ro'yxat botning .list blokiga aylandi", fixed.count('class="item"') == 2 and "<ul" not in fixed and "<li" not in fixed, fixed)
check("ro'yxatdan keyingi matn o'z abzatsida (tegsiz qolmaydi)",
      '<p class="note">Agar D=0' in fixed, fixed)
plain = '<section class="slide"><div class="body"><p class="lead">L</p></div></section>'
check("ro'yxatsiz slaydga tegilmaydi", html_slides._fix_html_lists(plain) == plain)

print("\n9) Formulalar: matndagi «<» va $ siz daraja")
from services.premium_presentation import deck_math
got = deck_math.render("<p>Agar $D < 0$ bo'lsa, ildiz yo'q.</p>")
check("«$D < 0$» xom qolmaydi", "$" not in got and "D < 0" in got, got)
got = deck_math.render('<div class="formula-body">D = b^2 - 4ac</div>')
check("«b^2» → b²", "b² - 4ac" in got and "^" not in got, got)
check("teglar buzilmaydi", deck_math.render('<p class="x">a < b</p>') == '<p class="x">a < b</p>')

print("\n10) Aniq fanda to'qima statistika va prognoz yo'q")
out = html_slides.exact_rules([{"title": "M", "brief": "", "category": "muqova"}, {"title": "R", "brief": "", "category": "reja"},
                               {"title": "Qo'llanilish sohalari (2026)", "brief": "x", "category": "korsatkichlar"},
                               {"title": "Kelajak prognozi (2026-2028)", "brief": "x", "category": "ikki_ustun"},
                               {"title": "Diskriminant formulasi", "brief": "x", "category": "formula"},
                               {"title": "Y", "brief": "", "category": "yakun"}], "aniq", "Kvadrat tenglamalar")
check("ko'rsatkich va prognoz — amaliy masala", [o["category"] for o in out[2:4]] == ["misol", "misol"]
      and out[2]["title"].startswith("Amaliy masala") and "O'YLAB TOPILMASIN" in out[3]["brief"], out[2:4])
out2 = html_slides.exact_rules([{"title": "M", "brief": "", "category": "muqova"}, {"title": "R", "brief": "", "category": "reja"},
                                {"title": "Mashhur matematiklar fikri", "brief": "x", "category": "kartalar"},
                                {"title": "Y", "brief": "", "category": "yakun"}], "aniq", "Kvadrat tenglamalar")
check("«mashhur matematiklar fikri» (to'qima iqtibos) — amaliy masala", out2[2]["category"] == "misol", out2[2])
check("formula slaydiga tegilmaydi", out[4]["category"] == "formula" and out[4]["title"] == "Diskriminant formulasi")
out = html_slides.exact_rules([{"title": "M", "brief": "", "category": "muqova"}, {"title": "R", "brief": "", "category": "reja"},
                               {"title": "Viet teoremasi", "brief": "x", "category": "iqtibos"},
                               {"title": "Qiziqarli jihatlar", "brief": "x", "category": "iqtibos"},
                               {"title": "Y", "brief": "", "category": "yakun"}], "aniq")
check("aniq fanda to'qima iqtibos yo'q (teorema — formula)", [o["category"] for o in out[2:4]] == ["formula", "kartalar"], out)
fixed = html_slides._retitle('<section class="slide"><div class="head"><h2 class="title">Eski</h2></div></section>', "Masala: X")
check("takror slayd sarlavhasi almashadi", '<h2 class="title">Masala: X</h2>' in fixed, fixed)

print("\n11) Bir xil masala ikki slaydda")
from services.premium_presentation import deck_logic
def ms(title, task, extra=""):
    return (f'<section class="slide"><div class="head"><h2 class="title">{title}</h2></div><div class="body">'
            f'<p class="lead">{extra}</p><div class="misol"><div class="misol-task">{task}</div></div></div></section>')
viet = ms("Misol: Viet teoremasi", "Berilgan tenglama: x² - 7x + 10 = 0. Ildizlarini toping.", "Tez aniqlash.")
viet2 = ms("Viet bo'yicha mashq", "Tenglama x² − 7x + 10 = 0 ning ildizlarini Viet teoremasi bilan toping.", "Boshqa izoh matni.")
other = ms("Misol: Diskriminant", "2x² + 5x - 3 = 0 ni yeching.")
check("bir xil tenglama — takror", deck_logic.same_task(viet, viet2))
check("boshqa tenglama — takror emas", not deck_logic.same_task(viet, other))
theory = ('<section class="slide"><div class="head"><h2 class="title">Viet teoremasi</h2></div><div class="body">'
          '<p class="lead">Ildizlar yig\'indisi va ko\'paytmasi koeffitsientlar bilan bog\'liq.</p></div></section>')
deck = ["<section></section>", "<section></section>", theory, viet, other, viet2, "<section></section>"]
check("nazariya + shu mavzudagi misol takror emas; bir xil masala — takror", deck_logic.duplicates(deck) == {5: 3},
      deck_logic.duplicates(deck))

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
