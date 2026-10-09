"""Kam matnli taqdimotning vektor dizayneri (`services/premium_presentation/designer`).

- har uslub punktlar soni chegarasida (va rasmsiz ham) xatosiz chiziladi, slaydda haqiqiy shakllar bor;
- ranglar temadan: boshqa tema — boshqa rang;
- sahifa (HTML kompozitsiya) mazmuni to'g'ri o'qiladi: muqova, reja, rasmli, kartalar, bosqichlar, raqamlar,
  qiyos, iqtibos, xulosa; diagramma va formula — o'qilmaydi (HTML dan chiziladi);
- tanlovchi: ketma-ket bir xil uslub yo'q, eski kompozitsiyalar ham aralashadi, "fon rasm + oq karta"
  (rasm_fon) va 4 tadan ko'p punktli eski kartalar hech qachon eski ko'rinishda chiqmaydi, urug' bir xil
  bo'lsa tanlov ham bir xil;
- `rasm_fon` modelga taklif qilinmaydi.

    python test_vektor_dizayn.py
"""
import base64
import io
import os
import sys

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

from services.premium_presentation import deck_compose, deck_logic, deck_style, themes
from services.premium_presentation.designer import OLD, Designer, kit, parse, styles


def jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (180, 120, 70)).save(buf, "JPEG")
    return buf.getvalue()


def uri() -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg()).decode()


def deck():
    prs = Presentation()
    prs.slide_width, prs.slide_height = 12192000, 6858000
    return prs


def items(n, value=False):
    out = [{"title": f"Yo'nalish {i + 1}", "note": f"Qisqa izoh matni {i + 1}"} for i in range(n)]
    if value:
        for i, it in enumerate(out):
            it["value"] = f"{i + 1}0%"
    return out


theme = themes.for_deck("Turizm", "", "kam")

print("1) Har uslub chiziladi (punktlar soni chegarasida, rasm bilan va rasmsiz)")
bad = []
for style in styles.STYLES:
    for n in sorted({style.min_items, style.max_items} - {0, 99}) or [0]:
        for with_photo in (True, False):
            prs = deck()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            pic = kit.Photo(jpeg()) if with_photo else None
            ctx = styles.Ctx(slide=slide, pal=styles.Palette.of(theme), rng=__import__("random").Random(1),
                             cover=pic, topic_icon="globe")
            spec = {"title": "Sarlavha", "lead": "Bosh gap", "text": "Matn", "photo_obj": pic,
                    "items": items(max(n, 1), value=True), "credit": "Muallif",
                    "sides": [{"name": "A", "items": ["bir", "ikki", "uch"]}, {"name": "B", "items": ["to'rt", "besh"]}],
                    "points": ["birinchi", "ikkinchi"]}
            try:
                style.draw(ctx, spec)
                if len(slide.shapes) < 4:
                    bad.append((style.name, n, with_photo, "shakl kam"))
            except Exception as exc:
                bad.append((style.name, n, with_photo, repr(exc)))
            if pic:
                pic.cleanup()
check("hamma uslub xatosiz chizildi", not bad, bad)
check("16 ta yangi uslub + xulosa ro'yxatda", len(styles.STYLES) == 19 and "finale" in styles.BY_NAME,
      [s.name for s in styles.STYLES])

print("2) Ranglar temadan")
blue, green = styles.Palette.of(themes.get("ko'k")), styles.Palette.of(themes.get("yashil"))
check("palitra temaga qarab o'zgaradi", blue.accent != green.accent and blue.dark != green.dark)
ramp = blue.ramp(5)
check("ramp: och → to'q, 5 ta", len(ramp) == 5 and kit.luminance(ramp[0]) > kit.luminance(ramp[-1]), ramp)
check("jurnal uslubida sarlavha serif", styles.Palette.of(themes.for_deck("Tarix", "jurnal", "kam")).head_font == kit.SERIF)

print("3) Sahifa mazmunini o'qish")
P = lambda body: deck_style.wrap_all(theme, [body])[0]
photo_div = f'<div class="rasm photo-in"><img class="photo" src="{uri()}" alt=""></div>'
cover = P('<section class="slide dark cover-photo"><div class="body cover-split"><div class="rasm photo-in cover-img">'
          f'<img class="photo" src="{uri()}" alt=""></div><div class="cover-text"><h1 class="title big">Mavzu nomi</h1>'
          '<p class="lead">Izoh</p><p class="note">Muallif: Ali</p></div></div></section>')
spec = parse.spec_of(cover, 0, 10)
check("muqova: sarlavha, izoh, muallif, rasm", spec and spec["kind"] == "cover" and spec["title"] == "Mavzu nomi"
      and spec["lead"] == "Izoh" and "Ali" in spec["credit"] and spec["photo"], spec and {k: v for k, v in spec.items() if k != "photo"})
plan = P(deck_logic.plan_slide([("Birinchi bo'lim", ""), ("Ikkinchi bo'lim", ""), ("Uchinchi bo'lim", "")], "uz"))
spec = parse.spec_of(plan, 1, 10)
check("reja: bo'limlar", spec and spec["kind"] == "plan" and [i["title"] for i in spec["items"]] ==
      ["Birinchi bo'lim", "Ikkinchi bo'lim", "Uchinchi bo'lim"], spec)
body = (f'<section class="slide k k-rasm-chap">{photo_div}<div class="k-text"><h2 class="title">Tarix</h2>'
        '<p class="lead">Bosh fikr.</p><p class="k-p">Abzats.</p></div></section>')
spec = parse.spec_of(P(body), 3, 10)
check("rasmli sahifa", spec and spec["kind"] == "photo" and spec["lead"] == "Bosh fikr." and spec["photo"], spec and spec.get("kind"))
cards = "".join(f'<div class="k-card"><p class="k-h">K{i}</p><p class="k-d">D{i}</p></div>' for i in range(4))
spec = parse.spec_of(P(f'<section class="slide k k-kartalar"><div class="k-text"><h2 class="title">T</h2><p class="lead">L</p>'
                       f'<div class="k-row">{cards}</div></div></section>'), 4, 10)
check("kartalar → guruh, 4 punkt", spec and spec["kind"] == "group" and len(spec["items"]) == 4
      and spec["items"][0] == {"title": "K0", "note": "D0"}, spec)
kpi = ('<section class="slide k k-raqamlar"><div class="k-text"><h2 class="title">R</h2><div class="k-row">'
       '<div class="k-kpi"><div class="k-num"><p class="k-v">8,2</p><p class="k-u">mln</p></div><p class="k-l">Sayyoh</p>'
       '<p class="k-d">Izoh</p></div><div class="k-kpi"><div class="k-num"><p class="k-v">45</p><p class="k-u">%</p></div>'
       '<p class="k-l">O\'sish</p><p class="k-d">Izoh</p></div></div><p class="k-src">Manba</p></div></section>')
spec = parse.spec_of(P(kpi), 5, 10)
check("raqamlar: qiymat va birlik", spec and spec["kind"] == "numbers" and spec["items"][0]["value"] == "8,2 mln", spec)
qiyos = ('<section class="slide k k-qiyos"><h2 class="title">Q</h2>' + "".join(
    f'<div class="k-half {c}"><p class="k-q">?</p><p class="k-h2">{n}</p><div class="k-items">'
    + "".join(f'<p class="k-li"><i></i><span>{n}{j}</span></p>' for j in range(3)) + "</div></div>"
    for c, n in (("a", "Bir"), ("b", "Ikki"))) + "</section>")
spec = parse.spec_of(P(qiyos), 6, 10)
check("qiyos: ikki tomon", spec and spec["kind"] == "compare" and spec["sides"][1]["name"] == "Ikki"
      and spec["sides"][0]["items"] == ["Bir0", "Bir1", "Bir2"], spec)
quote = (f'<section class="slide k k-iqtibos">{photo_div}<div class="k-text"><h2 class="title">So\'z</h2>'
         '<p class="quote">Iqtibos</p><p class="quote-by">— Muallif</p><p class="k-p">Nega muhim.</p></div></section>')
spec = parse.spec_of(P(quote), 7, 10)
check("iqtibos → rasmli varaq", spec and spec["kind"] == "photo" and spec["quote"] == "Iqtibos" and spec["by"] == "Muallif", spec and spec.get("kind"))
fin = ('<section class="slide k k-yakun"><div class="k-text"><h2 class="title">Xulosa</h2><p class="lead">Asosiy</p>'
       '<p class="k-ln"><i></i><span>Bir</span></p></div></section>')
spec = parse.spec_of(P(fin), 9, 10)
check("xulosa", spec and spec["kind"] == "finale" and spec["points"] == ["Bir"], spec)
chart = ('<section class="slide k k-diagramma"><div class="k-text"><h2 class="title">D</h2><div class="chart" '
         'data-kind="bar" data-labels="a,b" data-series="X: 1,2"></div></div></section>')
check("diagramma o'qilmaydi (HTML dan chiziladi)", parse.spec_of(P(chart), 5, 10) is None)

print("4) Aqlli tanlovchi")
group = {"kind": "group", "items": items(4)}
d = Designer(theme, "Turizm", seed=5)
picks = [d.choose(dict(group)) for _ in range(40)]
check("ketma-ket bir xil uslub yo'q", all(a != b for a, b in zip(picks, picks[1:])), picks)
check("eski kompozitsiya ham aralashadi", OLD in picks, picks)
check("yangi uslublar ko'p xil", len(set(picks) - {OLD}) >= 6, set(picks))
d = Designer(theme, "Turizm", seed=5)
check("urug' bir xil — tanlov bir xil", [d.choose(dict(group)) for _ in range(40)] == picks)
d = Designer(theme, "Turizm", seed=3)
fon = [d.choose({"kind": "photo", "old_ok": False}) for _ in range(30)]
check("rasm_fon hech qachon eski ko'rinishda emas", OLD not in fon and set(fon) <= {"band_right", "band_left", "band_chevron"}, fon)
d = Designer(theme, "Turizm", seed=3)
six = [d.choose({"kind": "group", "items": items(6), "old_ok": False}) for _ in range(30)]
check("6 punktga mos uslublargina", OLD not in six and all(styles.BY_NAME[s].max_items >= 6 for s in six), six)
d = Designer(theme, "Turizm", seed=9)
covers = {d.choose({"kind": "cover"}) for _ in range(20)}
plans = {d.choose({"kind": "plan", "items": items(5)}) for _ in range(20)}
check("muqova faqat yangi muqova uslublarida", covers == {"cover_x", "cover_hex"}, covers)
check("reja faqat yangi reja uslublarida", plans == {"plan_glass", "plan_wave"}, plans)

print("5) Sahifa → slayd (Designer.draw)")
prs = deck()
d = Designer(theme, "Turizm", seed=1)
drawn = d.draw(prs, cover, 0, 10)
check("muqova vektor uslubda chizildi", drawn and len(prs.slides) == 1 and d.chosen[-1] in ("cover_x", "cover_hex"))
check("diagramma sahifasi HTML ga qoldi", d.draw(prs, P(chart), 5, 10) is False and len(prs.slides) == 1)
d.close()

print("6) Eski 'fon rasm + oq karta' modelga taklif qilinmaydi")
check("rasm_fon katalogda yo'q", "[rasm_fon]" not in deck_compose.catalogue("uz"))
check("rasmli kompozitsiyalar: chap, o'ng, tepa", deck_compose.PHOTO_LAYOUTS == ("rasm_chap", "rasm_ong", "rasm_tepa"))

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
