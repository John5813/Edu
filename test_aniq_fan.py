"""Aniq fanlar va arzon model himoyalari (25/20 slaydli jonli sinovlarda topilgan nuqsonlar).

- mavzu oilasi: model "umumiy" desa ham matematika/fizika mavzusi "aniq" bo'ladi;
- aniq fanda masala/mashq slaydi — ishlangan misol; rasmlar soni kamaytirilmaydi;
- rejadagi misol/formula bloki slaydda bo'lmasa — qayta so'raladi;
- 1-slayd muqova bo'lmasa (oddiy slayd yoki reja yozilgan) — muqova kod bilan yig'iladi;
- aniq fanda formulali/grafikli rasmlar ruxsat, slayd skrinshotlari esa yo'q;
- to'qima iqtibos ("mutaxassislar") oddiy gapga aylanadi.

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

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
