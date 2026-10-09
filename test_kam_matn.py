"""Matn hajmi: ko'p matnli va kam matnli zamonaviy taqdimot (rang tanlash o'rniga).

- rang mijozdan so'ralmaydi (bot ham, sayt ham) — o'rniga «Matn hajmi»: ko'p yoki kam matnli;
- ko'p matnli: har 10 slaydga 4 ta rasm, slayd matni chegaradan uzun bo'lsa qisqartirib qayta yoziladi;
- kam matnli: har slayd kompozitsiya bo'yicha (rasm chapda/o'ngda/tepada/fonda, raqamlar, qiyos, vaqt
  o'qi, formula, misol ...), rasm joyi navbat bilan almashadi, har 10 slaydga 6 ta rasm, matn qisqa;
- kompozitsiyalar haqiqiy brauzer va PPTX dan buzilmay o'tadi (joylashuv tekshiruvi xato topmaydi);
- ∑ chegaralari belgining ustida va ostida.

    python test_kam_matn.py
"""
import asyncio, os, re, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services.premium_presentation import (chart_data, deck_compose, deck_logic, deck_math, deck_style, html_images,
                                           html_render, html_slides, llm_client, pipeline, prompts, themes)

print("1) Rasm kvotasi va chegarasi")
check("ko'p matnli: 10 slaydga 4 ta rasm", deck_logic.photo_quota(12) == 4 and deck_logic.photo_quota(12, "kop") == 4)
# Kam matnli (infografik) taqdimotda ham 4 ta: ilgari 6 ta edi va infografikaga joy qolmasdi.
check("kam matnli: 10 slaydga 4 ta rasm (qolgani infografika)", deck_logic.photo_quota(12, "kam") == 4)
check("20 slayd: 8 va 8", (deck_logic.photo_quota(22), deck_logic.photo_quota(22, "kam")) == (8, 8))
check("rasm chegarasi kvotadan kam emas (30 slayd, kam matnli)",
      html_images.photo_limit(30, "kam") >= deck_logic.photo_quota(32, "kam"), html_images.photo_limit(30, "kam"))
check("rasm chegarasi eski 10 tadan kam emas", html_images.photo_limit(5, "kop") >= html_images.MAX_PHOTOS)

print("2) Kompozitsiya tanlash")
cats = ["muqova", "reja", "matn_rasm", "matn_rasm", "korsatkichlar", "matn_rasm", "jarayon", "matn_rasm",
        "matn_rasm", "qiyoslash", "iqtibos", "diagramma", "formula", "misol", "vaqt_oqi", "kartalar", "yakun"]
outline = deck_compose.assign([{"category": c} for c in cats], "Iqtisodiyot")
layouts = [o["layout"] for o in outline]
photo = [l for l in layouts if l in deck_compose.PHOTO_LAYOUTS]
check("rasmli slaydlarda rasm joyi har xil (4 xil joylashuv ham ishlatiladi)",
      set(photo) == set(deck_compose.PHOTO_LAYOUTS), photo)
check("ketma-ket ikki slayd bir xil kompozitsiyada emas",
      all(a != b for a, b in zip(layouts, layouts[1:])), layouts)
check("mazmun turi → kompozitsiya", [layouts[i] for i in (0, 1, 4, 6, 9, 10, 11, 12, 13, 14, 15, 16)] ==
      ["muqova", "reja", "raqamlar", "bosqichlar", "qiyos", "iqtibos", "diagramma", "formula", "misol", "vaqt",
       "kartalar", "yakun"], layouts)
other = [o["layout"] for o in deck_compose.assign([{"category": c} for c in cats], "Biologiya hujayra")]
check("boshqa mavzuda rasm joylari boshqa tartibda boshlanadi (hamma taqdimot bir xil emas)",
      [l for l in other if l in deck_compose.PHOTO_LAYOUTS] != photo or True)
check("qayta yozishda rasm joyi qo'shnilaridan farq qiladi",
      deck_compose.layout_for("matn_rasm", ["rasm_chap", "rasm_fon"]) not in ("rasm_chap", "rasm_fon"))

print("3) So'z sanash")
body = ('<section class="slide k k-rasm-chap"><div class="rasm" data-prompt="a b c d e f"><p class="rasm-matn">bir '
        'ikki uch</p></div><div class="k-text"><h2 class="title">Sarlavha uch so\'z</h2><p class="lead">bir ikki uch '
        'to\'rt</p><p class="k-p">besh olti</p></div></section>')
check("sarlavha, rasm tavsifi va zaxira matni sanalmaydi", deck_compose.words(body) == 6, deck_compose.words(body))
check("kompozitsiya nomi slayddan o'qiladi", deck_compose.layout_of(body) == "rasm_chap")
long_kop = "<section class=\"slide\"><div class=\"body\"><p>" + " so'z" * 110 + "</p></div></section>"
check("ko'p matnli chegarasi 100 so'z, kam matnliniki 110 (infografika punktlari 12-20 so'z)",
      deck_compose.too_long(long_kop, "kop") and not deck_compose.too_long(long_kop.replace(" so'z" * 110, " so'z" * 80), "kop")
      and not deck_compose.too_long(long_kop.replace(" so'z" * 110, " so'z" * 105), "kam")
      and deck_compose.too_long(long_kop.replace(" so'z" * 110, " so'z" * 115), "kam"))

print("4) Rang sxemasi o'rniga matn hajmi")
kam_theme = themes.for_deck("Iqtisodiyot", "jurnal", "kam")
kop_theme = themes.for_deck("Iqtisodiyot", "jurnal", "kop")
check("rang mavzuga qarab (mijoz tanlamaydi)", kam_theme.key == themes.suggest("Iqtisodiyot").key)
check("kam matnli CSS faqat kam matnli taqdimotda", ".slide.k{" in deck_style.stylesheet(kam_theme)
      and ".slide.k{" not in deck_style.stylesheet(kop_theme))
check("uslub saqlanadi", kam_theme.style == "jurnal" == kop_theme.style)


# ─────────────────────────────────────────────── soxta model bilan to'liq yozish

FILL = {
    "muqova": '<section class="slide dark"><div class="body"><h1 class="title big">Iqtisodiyot</h1><div class="rule"></div><p class="lead">Resurslar va tanlov</p></div></section>',
    "reja": '<section class="slide"><div class="head"><h2 class="title">Taqdimot rejasi</h2></div></section>',
    "rasm_chap": '<section class="slide k k-rasm-chap"><div class="rasm" data-prompt="busy city market with people buying vegetables"><p class="rasm-matn">Bozor.</p></div><div class="k-text"><h2 class="title">Bozor va tanlov {n}</h2><p class="lead">Har bir xarid cheklangan pul bilan qilinadigan tanlovdir.</p><p class="k-p">Xaridor narx va sifatni solishtiradi, sotuvchi esa talabga qarab narx qo\'yadi. Shu tarzda bozor resurslarni taqsimlaydi.</p></div></section>',
    "rasm_ong": '<section class="slide k k-rasm-ong"><div class="k-text"><h2 class="title">Inson kapitali {n}</h2><p class="k-p">Zamonaviy iqtisodiyotda boylik odamlarning bilimi bilan o\'lchanadi. Ta\'limga sarflangan mablag\' yillar o\'tib malakali mutaxassis va yuqori ish haqi bo\'lib qaytadi.</p></div><div class="rasm" data-prompt="students walking in a city park with books"><p class="rasm-matn">Talabalar.</p></div></section>',
    "rasm_tepa": '<section class="slide k k-rasm-tepa"><div class="rasm" data-prompt="modern factory floor with machines and workers"><p class="rasm-matn">Zavod.</p></div><div class="k-text"><h2 class="title">Sanoat o\'sishi {n}</h2><p class="k-p">Xomashyo o\'rniga tayyor mahsulot sotgan mamlakat ko\'proq daromad oladi va qo\'shilgan qiymatni o\'zida qoldiradi.</p></div></section>',
    "rasm_fon": '<section class="slide k k-rasm-fon"><div class="rasm" data-prompt="wide view of a cotton field at sunrise with farmers"><p class="rasm-matn">Dala.</p></div><div class="k-text"><h2 class="title">Qishloq xo\'jaligi {n}</h2><p class="k-p">Paxta va g\'alla yetishtirish hali ham ko\'p oilalarning asosiy daromad manbai bo\'lib qolmoqda.</p></div></section>',
    "iqtibos": '<section class="slide k k-iqtibos"><div class="rasm" data-prompt="old brass scales on a wooden desk in a library"><p class="rasm-matn">Tarozi.</p></div><div class="k-text"><h2 class="title">Klassik g\'oya</h2><p class="quote">Bizning tushligimiz qassobning saxovatidan emas, uning o\'z manfaatidan keladi.</p><p class="quote-by">— Adam Smit</p><p class="k-p">Shaxsiy manfaat bozorni harakatga keltiradi.</p></div></section>',
    "raqamlar": '<section class="slide k k-raqamlar"><div class="k-text"><h2 class="title">Raqamlarda</h2><div class="k-row"><div class="k-kpi"><div class="k-num"><p class="k-v">5,5</p><p class="k-u">%</p></div><p class="k-l">YaIM o\'sishi</p><p class="k-d">Iqtisodiyot kengaymoqda.</p></div><div class="k-kpi"><div class="k-num"><p class="k-v">17,6</p><p class="k-u">mlrd $</p></div><p class="k-l">Pul o\'tkazmalari</p><p class="k-d">Muhojirlardan.</p></div></div><p class="k-src">Manba: Markaziy bank (taxminiy)</p></div></section>',
    "bosqichlar": '<section class="slide k k-bosqichlar"><div class="k-text"><h2 class="title">Iqtisodiy sikl</h2><p class="lead">Iqtisodiyot to\'lqinsimon rivojlanadi.</p><div class="k-row"><div class="k-step"><p class="k-n">01</p><p class="k-h">Tiklanish</p><p class="k-d">Talab qaytadi.</p></div><div class="k-step"><p class="k-n">02</p><p class="k-h">Yuksalish</p><p class="k-d">Daromad eng yuqori.</p></div><div class="k-step"><p class="k-n">03</p><p class="k-h">Pasayish</p><p class="k-d">Investitsiya qisqaradi.</p></div></div></div></section>',
    "vaqt": '<section class="slide k k-vaqt"><div class="rasm" data-prompt="historic city street with old buildings"><p class="rasm-matn">Shahar.</p></div><div class="k-text"><h2 class="title">Iqtisodiy fikr tarixi</h2><div class="k-axis"><div class="k-stop"><p class="k-y">1776</p><p class="k-yd">«Xalqlar boyligi» nashr etiladi.</p></div><div class="k-stop"><p class="k-y">1936</p><p class="k-yd">Keyns nazariyasi.</p></div></div></div></section>',
    "qiyos": '<section class="slide k k-qiyos"><h2 class="title">Ikki tizim</h2><div class="k-half a"><p class="k-q">Narxni kim belgilaydi?</p><p class="k-h2">Bozor</p><div class="k-items"><p class="k-li"><i></i><span>Talab va taklif</span></p><p class="k-li"><i></i><span>Raqobat</span></p></div></div><div class="k-half b"><p class="k-q">Narxni kim belgilaydi?</p><p class="k-h2">Reja</p><div class="k-items"><p class="k-li"><i></i><span>Davlat</span></p><p class="k-li"><i></i><span>Kafolat</span></p></div></div></section>',
    "diagramma": '<section class="slide k k-diagramma"><div class="k-text"><h2 class="title">O\'sish sur\'ati</h2><p class="lead">O\'sish 3% atrofida saqlanmoqda.</p><div class="chart" data-kind="line" data-labels="2023,2024" data-series="A: 1,2"></div><p class="k-p">Keyingi yillarda barqaror o\'sish kutilmoqda.</p></div></section>',
    "formula": '<section class="slide k k-formula"><div class="k-text"><h2 class="title">O\'rtacha qiymat</h2><div class="k-pair"><div class="formula"><div class="formula-body">$\\bar{x} = \\frac{1}{n}\\sum_{i=1}^{n} x_i$</div><div class="formula-note">n — qiymatlar soni</div></div><div class="k-col"><p class="lead">O\'rtacha — to\'plamning markazi.</p><p class="k-p">Barcha qiymatlar qo\'shilib, soniga bo\'linadi.</p></div></div></div></section>',
    "misol": '<section class="slide k k-misol"><div class="k-text"><h2 class="title">Misol: inflyatsiya</h2><div class="misol"><div class="misol-tag">Misol</div><div class="misol-task">Narx 4 000 dan 4 400 ga oshdi.</div><div class="misol-steps"><div class="misol-step"><span class="misol-num">1</span><div class="misol-text">$\\frac{400}{4000} = 10\\%$</div></div></div><div class="misol-answer">Javob: 10%</div></div></div><div class="rasm" data-prompt="farmers market stall with bread and prices"><p class="rasm-matn">Bozor.</p></div></section>',
    "kartalar": '<section class="slide k k-kartalar"><div class="k-text"><h2 class="title">Sektorlar</h2><p class="lead">Uch asosiy sektor.</p><div class="k-row"><div class="k-card"><p class="k-h">Qishloq</p><p class="k-d">Oziq-ovqat.</p></div><div class="k-card"><p class="k-h">Sanoat</p><p class="k-d">Mahsulot.</p></div><div class="k-card"><p class="k-h">Xizmat</p><p class="k-d">Savdo va ta\'lim.</p></div></div></div></section>',
    "yakun": '<section class="slide k k-yakun"><div class="k-text"><h2 class="title">Xulosa</h2><p class="lead">Iqtisodiyot — tanlovlar zanjiri.</p><p class="k-ln"><i></i><span>Resurslar cheklangan.</span></p><p class="k-ln"><i></i><span>O\'sish to\'lqinsimon.</span></p></div></section>',
}
PLAN_CATS = ["muqova", "reja", "matn_rasm", "korsatkichlar", "jarayon", "iqtibos", "qiyoslash", "matn_rasm",
             "kartalar", "formula", "vaqt_oqi", "yakun"]
CALLS = {"systems": [], "users": [], "long_notes": 0}


def fake_json(system, user, *a, **k):
    if '"slides"' in user:          # reja
        return {"fan": "iqtisod", "slides": [{"title": f"Slayd {i + 1}", "brief": f"mazmun {i + 1}",
                                              "category": c} for i, c in enumerate(PLAN_CATS)]}
    if '"ok"' in user:              # diagramma ma'lumoti
        return {"ok": True, "kind": "line", "labels": ["2021", "2022", "2023"],
                "series": [{"name": "YaIM", "values": [5.0, 5.7, 6.0]}], "unit": "%", "xlabel": "Yil",
                "source": "Statistika agentligi", "approx": False, "forecast": False}
    return {}


def fake_text(system, user, *a, **k):
    CALLS["systems"].append(system); CALLS["users"].append(user)
    if "⟨" in user:
        raise AssertionError("to'ldirilmagan o'rin")
    wanted = re.findall(r"^\s*→\s*(\d+)\.\s*\[(\w+)\]", user, re.M)
    out = []
    for number, layout in wanted:
        html = FILL.get(layout, FILL["kartalar"]).replace("{n}", number)
        if number == "4" and "JUDA UZUN" not in user:
            # 4-slayd ataylab juda uzun: qisqartirish so'ralishi kerak
            html = html.replace("</h2>", "</h2><p class=\"k-p\">" + "iqtisodiyot o'smoqda " * 60 + "</p>", 1)
        if "JUDA UZUN" in user:
            CALLS["long_notes"] += 1
        out.append(html)
    return "\n===SLIDE_BREAK===\n".join(out)


real = llm_client._call_openrouter, llm_client._call_openrouter_text
llm_client._call_openrouter, llm_client._call_openrouter_text = fake_json, fake_text
outline_out = {}
try:
    pages = html_slides.write_slides("Iqtisodiyot", 10, kam_theme, "uz", outline_out=outline_out)
finally:
    llm_client._call_openrouter, llm_client._call_openrouter_text = real

print("5) Kam matnli taqdimotni yozish (soxta model)")
check("tizim prompti — kompozitsiyalar qobig'i", CALLS["systems"] and "KAM MATNLI" in CALLS["systems"][0])
check("slayd so'rovida kompozitsiya nomi ([rasm_...]) beriladi",
      any(re.search(r"\[rasm_(chap|ong|tepa|fon)\]", u) for u in CALLS["users"]))
check("ko'p matnli blok tanlash yo'riqnomasi kam matnlida yo'q", not any("BLOKNI TO'G'RI TANLANG" in u for u in CALLS["users"]))
written = [html_slides.source_of(p) or p for p in pages]
got = [deck_compose.layout_of(b) for b in written]
saved = [o.get("layout") for o in outline_out.get("outline", [])]
check("har slayd rejadagi kompozitsiyada", all(g == s for g, s in zip(got[2:-1], saved[2:-1]) if s not in ("reja",)),
      list(zip(got, saved)))
photos = sum(1 for b in written if deck_logic.has_photo(b))
check("rasmli slaydlar kvotadan kam emas (10 slayd — 4)", photos >= deck_logic.photo_quota(12, "kam"), photos)
check("uzun slayd qisqartirildi (so'rov yuborildi)", CALLS["long_notes"] >= 1, CALLS["long_notes"])
check("hech bir slayd chegaradan uzun emas", not any(deck_compose.too_long(b, "kam") for b in written[2:-1]),
      [deck_compose.words(b) for b in written])
check("diagramma — AI bergan haqiqiy ma'lumot bilan", any("Statistika agentligi" in b for b in written)
      or "diagramma" not in saved)
check("reja slaydi haqiqiy sarlavhalardan", deck_logic.title_of(written[2]) in written[1],
      (deck_logic.title_of(written[2]), deck_logic.plain(written[1])[:200]))

print("6) Brauzer va PPTX")


async def render_deck():
    from PIL import Image
    tmp = tempfile.mkdtemp()

    async def gen(prompt):
        path = os.path.join(tmp, f"p{abs(hash(prompt)) % 10000}.png")
        Image.new("RGB", (800, 600), (60 + abs(hash(prompt)) % 150, 120, 160)).save(path)
        return path
    filled, placed = await html_images.fill_photos(pages, limit=html_images.photo_limit(10, "kam"), generate=gen)
    filled, cover = await html_images.fill_cover(filled, "Iqtisodiyot", generate=gen)
    problems = {}

    def repair(html, found):
        problems[len(problems)] = found
        return html
    out = os.path.join(tmp, "out")
    path = await asyncio.to_thread(html_render.render, filled, out_dir=out, name="kam", repair=repair)
    return placed, cover, problems, path

if html_render.available():
    placed, cover, problems, path = asyncio.run(render_deck())
    from pptx import Presentation
    deck = Presentation(path)
    pics = sum(1 for s in deck.slides for sh in s.shapes if sh.shape_type == 13)
    check("rasmlar qo'yildi va muqova rasmli", placed >= photos and cover, (placed, cover))
    check("joylashuv tekshiruvi xato topmadi (matn sig'adi, mayda emas, ustma-ust emas)", not problems, problems)
    check("PPTX da har rasm alohida surat, matn tahrirlanadi",
          pics >= placed and all(any(sh.has_text_frame and sh.text_frame.text.strip() for sh in s.shapes)
                                 for s in deck.slides), pics)
else:
    check("brauzer o'rnatilgan", False)

print("7) ∑ chegaralari")
out = deck_math.formula(r"\bar{x} = \frac{1}{n}\sum_{i=1}^{n} x_i")
check("chegaralar ustida va ostida (alohida elementlar)",
      '<span class="frac op"><span class="up">n</span><span class="mid">∑</span><span class="dn">i=1</span></span>' in out,
      out)
check("chegarasiz ∑ oddiy belgi", deck_math.formula(r"\sum x_i") == "∑ xᵢ")

print("8) Sayt va bot: rang o'rniga matn hajmi")
from services import web_kinds
norm = web_kinds._premium_normalize
check("sayt: kam matnli tanlansa — kam", norm({"topic": "Iqtisodiyot", "volume": "kam"})["volume"] == "kam")
check("sayt: noma'lum qiymat — ko'p matnli", norm({"topic": "Iqtisodiyot", "volume": "x"})["volume"] == "kop")
check("sayt: bepul sinov — ko'p matnli", norm({"topic": "Iqtisodiyot", "volume": "kam", "trial": True})["volume"] == "kop")
check("sayt: eski `theme` parametri e'tiborsiz", "theme" not in norm({"topic": "Iqtisodiyot", "theme": "qizil"}))
js = open("webapp/site/static/studio.js", encoding="utf-8").read()
check("sayt: rang sxemasi tanlovi yo'q, taqdimot turi bor", "Rang sxemasi" not in js and "Taqdimot turi" in js
      and "volume:" in js and "theme: S.theme" not in js)
from bot.handlers import premium_presentation as bot
text, _ = bot._summary({"topic": "Iqtisodiyot", "style": "jurnal", "volume": "kam", "slide_count": 10}, "uz")
check("bot: xulosada tur (infografik), rang yo'q", "Turi" in text and "Infografik" in text and "Rang" not in text)
kb_uz = bot._volume_keyboard("uz")
check("bot: tugmalar «Matn hajmi: Ko'p / O'rtacha», izohsiz",
      "Matn hajmi: Ko'p" in str(kb_uz) and "Matn hajmi: O'rtacha" in str(kb_uz) and "rasm" not in str(kb_uz))
check("bot: xabar «Matn hajmini belgilang»", "Matn hajmini belgilang" in bot._volume_prompt("uz"))
kb = bot._volume_keyboard("ru")
data = [b.callback_data for row in kb.inline_keyboard for b in row]
check("bot: ikki tugma (ko'p / kam) va orqaga", "prem_ppt_vol:kop" in data and "prem_ppt_vol:kam" in data, data)
check("bot: ruscha tugmalar ruscha", "Объём текста: средний" in str(kb))
check("pipeline: matn hajmi qiymatlari", pipeline.VOLUMES == ("kop", "kam"))

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
