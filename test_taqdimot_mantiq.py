"""Taqdimot mantig'i: reja haqiqiy sarlavhalardan, takror, jadval, diagramma, muqova rasmi.

    python test_taqdimot_mantiq.py
"""
import asyncio, base64, io, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services.premium_presentation import (deck_charts, deck_logic, html_extract, html_images,
                                           html_render, html_slides, llm_client, themes)
THEME = themes.get("ko'k")

def slide(title, body_html, dark=False):
    return (f'<section class="slide{" dark" if dark else ""}"><div class="head"><h2 class="title">{title}</h2>'
            f'<div class="rule"></div></div><div class="body">{body_html}</div></section>')

def cards(*names):
    return '<div class="cols cols-3">' + "".join(
        f'<div class="card"><div class="card-title">{n}</div><div class="card-note">{n} haqida to\'liq izoh matni.</div></div>'
        for n in names) + "</div>"

print("1) Sarlavha va takror aniqlash")
check("bir xil sarlavha takror", deck_logic.similar_titles("Mustaqillik deklaratsiyasining e'lon qilinishi",
                                                           "Mustaqillik deklaratsiyasining e’lon qilinishi"))
check("o'xshash sarlavha takror", deck_logic.similar_titles("Davlat ramzlari", "Davlat ramzlari qabul qilinishi"))
check("boshqa sarlavha takror emas", not deck_logic.similar_titles("Davlat ramzlari", "Milliy armiya va chegaralar"))
check("reja sarlavhasi taniladi", all(deck_logic.is_plan_title(t) for t in
      ("Taqdimot rejasi", "Reja", "План презентации", "Содержание", "Agenda", "Тақдимот режаси")))
check("oddiy sarlavha reja emas", not deck_logic.is_plan_title("Rejalashtirish usullari"))

a = slide("Davlat ramzlari", cards("Bayroq", "Gerb", "Madhiya"))
b = slide("Milliy armiya", cards("Qurolli Kuchlar", "Chegara", "Harbiy doktrina"))
dup = slide("Davlat ramzlari qabul qilinishi", cards("Bayroq", "Gerb", "Madhiya"))
plan2 = slide("Taqdimot rejasi", cards("Bayroq", "Armiya", "Valyuta"))
cover = slide("Mavzu", "", dark=True)
end = slide("Xulosa", "<p class=\"lead\">Yakuniy fikr.</p>")
deck = [cover, slide("Reja", ""), a, b, dup, plan2, end]
check("takrorlangan slayd topildi", deck_logic.duplicates(deck) == {4: 2}, str(deck_logic.duplicates(deck)))
check("o'rtadagi reja slaydi topildi", deck_logic.stray_plans(deck) == [5], str(deck_logic.stray_plans(deck)))

print("\n2) Jadval")
small = '<table><tr><th>Tur</th><th>Xususiyat</th></tr><tr><td>A</td><td>Tez</td></tr></table>'
big = ('<table>' + "<tr>" + "".join(f"<th>Ustun {i}</th>" for i in range(4)) + "</tr>"
       + "".join("<tr>" + "".join(f"<td>{'so`z ' * 12}</td>" for _ in range(4)) + "</tr>" for _ in range(5)) + "</table>")
check("qisqa jadval ruxsat", not deck_logic.oversized_table(slide("T", small)))
check("zich jadval aniqlandi", deck_logic.oversized_table(slide("T", big)))

print("\n3) Diagramma kvotasi")
check("kvota: 5 slaydda 0, 8 da 1, 12 da 2, 20 da 3",
      [deck_logic.chart_quota(n) for n in (5, 8, 12, 20)] == [0, 1, 2, 3])
outline = [{"title": f"S{i}", "brief": "mavzu jihati", "category": "kartalar"} for i in range(12)]
outline[0]["category"], outline[1]["category"], outline[-1]["category"] = "muqova", "reja", "yakun"
filled = html_slides.ensure_charts([dict(o) for o in outline], "uz")
charts = [i for i, o in enumerate(filled) if o["category"] == "diagramma"]
check("model diagramma bermasa 2 ta belgilandi", len(charts) == 2, str(charts))
check("muqova, reja va yakun tegilmadi", all(i not in charts for i in (0, 1, 11)), str(charts))
check("biri halqa", any(o.get("chart_kind") == "halqa" for o in filled), str([o.get("chart_kind") for o in filled]))
check("shartli misol eslatilgan", all("Shartli misol" in filled[i]["brief"] for i in charts))
check("allaqachon yetarli bo'lsa o'zgarmaydi", html_slides.ensure_charts(
      [dict(o, category="diagramma") if 3 <= i <= 5 else dict(o) for i, o in enumerate(outline)], "uz")
      == [dict(o, category="diagramma") if 3 <= i <= 5 else dict(o) for i, o in enumerate(outline)])
check("ulush so'zi → halqa, yil so'zi → chiziqli",
      deck_logic.chart_kind_for("tarkib ulushi") == "halqa" and deck_logic.chart_kind_for("yillar dinamikasi") == "chiziqli")

print("\n4) Kichik qiymatli diagramma yorliqlari")
check("0,004 va 0,002 nolga yaxlitlanmaydi", deck_charts._fmt(0.004) == "0,004" and deck_charts._fmt(0.002) == "0,002")
check("oddiy qiymatlar avvalgidek", [deck_charts._fmt(v) for v in (0, 12, 2.5, 0.29, 12.34)] == ["0", "12", "2,5", "0,29", "12,3"])

print("\n5) Reja slaydi haqiqiy sarlavhalardan")
items = [("Davlat ramzlari: bayroq, gerb, madhiya", "Bayroq va gerb qabul qilindi. Keyingi gap."),
         ("Milliy armiya", "Qurolli Kuchlar tashkil etildi"), ("Valyuta tizimi", "")]
plan = deck_logic.plan_slide(items, "uz")
check("reja sarlavhasi", ">Taqdimot rejasi<" in plan)
check("sarlavhalar qisqartirilgan (ikki nuqtadan keyin tashlandi)", "Davlat ramzlari<" in plan and "bayroq, gerb" not in plan.split("card-title")[1])
check("raqamlangan kartalar faqat rejada", plan.count("card-num") == 3)
many = deck_logic.plan_slide([(f"Mavzu {i}", "") for i in range(1, 18)], "uz")
check("17 sarlavhadan 8 tasi tanlanadi", many.count("card-title") == 8)
check("kartochka raqami reja bo'lmagan slaydda olib tashlanadi",
      "card-num" not in deck_logic.strip_numbering('<section class="slide"><div class="cols"><div class="card"><div class="card-num">01</div><div class="card-title">A</div></div></div></section>')
      and "card-num" in deck_logic.strip_numbering(plan))

print("\n6) repair_deck (soxta model bilan)")
def fake_slide(title, text):
    return slide(title, f'<p class="lead">{text}</p>' + cards(title + " a", title + " b", title + " v"))
written = [
    cover, slide("Reja", ""),
    fake_slide("Davlat ramzlari", "Davlat ramzlari milliy o'zlikni ifodalaydi."),
    fake_slide("Milliy armiya", "Qurolli Kuchlar suverenitetni himoya qiladi."),
    slide("Davlat ramzlari qabul qilinishi", cards("Bayroq", "Gerb", "Madhiya")),   # takror
    slide("Taqdimot rejasi", small),                                                  # o'rtada reja
    slide("Valyuta tizimi", "<p class=\"lead\">So'm iqtisodiy mustaqillik belgisi.</p>" + big),   # zich jadval
    slide("Aholi tarkibi", cards("Bir", "Ikki", "Uch")),                              # diagramma kutilgan
    end]
outline = [{"title": t, "brief": f"{t} jihati", "category": c} for t, c in (
    ("Mavzu", "muqova"), ("Taqdimot rejasi", "reja"), ("Davlat ramzlari", "kartalar"), ("Milliy armiya", "kartalar"),
    ("Mustaqil fikr", "kartalar"), ("Siyosiy tizim", "kartalar"), ("Valyuta tizimi", "kartalar"),
    ("Aholi tarkibi", "diagramma"), ("Xulosa", "yakun"))]
outline[7]["chart_kind"] = "halqa"
prompts = []
def rewriter(system, user, count):
    prompts.append(user)
    if "TAQDIMOT REJASINI" in user:
        return [fake_slide("Siyosiy tizim", "Siyosiy tizim davlat boshqaruvini belgilaydi.")]
    if "TAKRORLAYAPTI" in user:
        return [fake_slide("Mustaqil fikr", "Mustaqil fikr yangi masalani ochadi.")]
    if "ZICH JADVAL" in user:
        return [fake_slide("Valyuta tizimi", "So'm iqtisodiy mustaqillik belgisi bo'ldi.")]
    if "DIAGRAMMALI" in user:
        return [slide("Aholi tarkibi", '<div class="chart" data-kind="donut" data-labels="A,B" data-series="Ulush: 60,40"></div>'
                      '<p class="note">Shartli misol.</p>')]
    return []
saved = (html_slides._write_chunk, llm_client._call_openrouter)
html_slides._write_chunk = rewriter
llm_client._call_openrouter = lambda *a, **k: {"leads": [{"n": 8, "lead": "Aholi tarkibi turli guruhlar ulushidan iborat bo'ladi."}]}
try:
    ctx = html_slides._Deck("Mustaqillik", 9, outline, "umumiy", "sys", THEME, "uz", 2, "", "", "")
    fixed = html_slides.repair_deck(written, ctx)
finally:
    html_slides._write_chunk, llm_client._call_openrouter = saved
titles = [deck_logic.title_of(b) for b in fixed]
check("slaydlar soni saqlandi", len(fixed) == len(written), str(len(fixed)))
check("takror slayd boshqa mavzu bilan almashdi", titles[4] == "Mustaqil fikr", str(titles))
check("o'rtadagi reja slaydi mazmunli slaydga almashdi", titles[5] == "Siyosiy tizim", str(titles))
check("zich jadval jadvalsiz qayta yozildi", not deck_logic.oversized_table(fixed[6]) and "<table" not in fixed[6])
check("diagramma kutilgan slaydda diagramma bor", deck_logic.has_chart(fixed[7]))
check("2-slayd — yozilgan haqiqiy sarlavhalardan reja",
      "Taqdimot rejasi" in fixed[1] and all(t in fixed[1] for t in ("Davlat ramzlari", "Milliy armiya", "Valyuta tizimi", "Aholi tarkibi")),
      deck_logic.plain(fixed[1]))
check("rejada takror ham, olib tashlangan sarlavha ham yo'q", fixed[1].count("Taqdimot rejasi") == 1
      and "qabul qilinishi" not in fixed[1])
check("umumlashtiruvchi gap qo'shildi (yo'q slaydga)", "Aholi tarkibi turli guruhlar" in deck_logic.plain(fixed[7]) or deck_logic.has_chart(fixed[7]))
check("so'rovda qayta yozish sababi aytilgan", any("TAKRORLAYAPTI" in p for p in prompts) and any("ZICH JADVAL" in p for p in prompts))
check("muqova va xulosa tegilmadi", fixed[0] == cover and fixed[-1] == end)

print("\n7) Muqova rasmi")
from PIL import Image
buf = io.BytesIO(); Image.new("RGB", (800, 600), (40, 120, 90)).save(buf, "PNG")
uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
cover_body = ('<section class="slide dark"><div class="body"><h1 class="title big">Dorivor o\'simliklar va ularning xususiyatlari</h1>'
              '<div class="rule"></div><p class="lead">Tabiiy dori vositalari haqida.</p><p class="note">Tayyorladi: Ali Valiyev</p></div></section>')
page = html_slides.build_pages([cover_body, slide("A", cards("x", "y", "z"))], THEME, "uz")[0]
rich = html_images.with_cover_photo(page, uri)
check("muqova rasmli sinfga o'tdi", "cover-photo" in rich and "cover-split" in rich and "cover-text" in rich)
check("rasm muqovada turibdi", rich.count(uri) == 1)
check("matn o'zgarmagan", "Dorivor o&#x27;simliklar" in rich or "Dorivor o'simliklar" in rich)
fake_path = os.path.join("temp", "muqova_sinov.png"); os.makedirs("temp", exist_ok=True)
Image.new("RGB", (800, 600), (40, 120, 90)).save(fake_path)

async def fake_generate(subject):
    return fake_path
pages, done = asyncio.run(html_images.fill_cover([page, page], "Dorivor o'simliklar", generate=fake_generate))
check("fill_cover rasm qo'ydi", done and html_images._HAS_COVER_PHOTO.search(pages[0])
      and not html_images._HAS_COVER_PHOTO.search(pages[1]))
async def broken(subject):
    raise RuntimeError("tarmoq yo'q")
pages2, done2 = asyncio.run(html_images.fill_cover([page], "Mavzu", generate=broken))
check("rasm chiqmasa muqova o'zgarmaydi (xato ko'tarilmaydi)", not done2 and pages2 == [page])

if html_render.available():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = html_render._launch(pw)
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        handle = ctx.new_page()
        handle.set_content(rich, wait_until="load")
        layout = html_extract.read_layout(handle)
        kinds = [b["kind"] for b in layout["blocks"]]
        texts = [b["text"] for b in layout["blocks"] if b["kind"] == "text"]
        check("PPTX uchun rasm bloki topildi", "image" in kinds, str(kinds))
        check("sarlavha o'qiladi", any("Dorivor" in t for t in texts), str(texts))
        images = [b for b in layout["blocks"] if b["kind"] == "image"]
        check("rasm chap tomonda", images and images[0]["x"] < 50 and images[0]["w"] < 1000, str(images[:1]))
        out = os.environ.get("MUQOVA_OUT")
        if out:
            handle.screenshot(path=out)
        browser.close()
else:
    check("brauzer mavjud", False, "chromium topilmadi")

print("\n8) Promptlar: taqiq diagrammani butunlay o'chirib yubormaydi")
seen = {}
def catch(system, user, temperature=0.7, max_tokens=16000):
    seen["plan"] = user
    return {"fan": "gumanitar", "slides": []}
orig = llm_client._call_openrouter
llm_client._call_openrouter = catch
try:
    html_slides.plan_outline("Alisher Navoiy ijodi", 12, "uz")
finally:
    llm_client._call_openrouter = orig
from services.premium_presentation import deck_shape
everything = "\n".join([html_slides.shell_rules(THEME, "uz"), seen.get("plan", "")]
                      + [deck_shape.guidance(k) for k in deck_shape.FAMILY_KEYS]
                      + [html_slides._user_prompt("Mavzu", 1, 3, 12, [{"title": "A", "brief": "b", "category": "kartalar"}],
                                                  [], 2, "", "", "", f) for f in deck_shape.FAMILY_KEYS])
low = everything.lower()
suppressing = ("diagramma bo'lmasligi", "statistika kategoriyalarini umuman", "diagramma yozmang",
               "statistika bu yerda kerak emas", "diagramma va statistika yozmang",
               "diagramma o'rniga matn", "umuman ishlatmang", "diagrammasiz taqdimot")
check("diagrammani butunlay chetlab o'tishga undaydigan ibora yo'q",
      not [p for p in suppressing if p in low], str([p for p in suppressing if p in low]))
check("reja so'rovi kamida bitta diagramma talab qiladi (12 slaydda 2 ta)", "kamida 2 ta slayd 'diagramma'" in seen["plan"])
check("reja so'rovi halqani eslatadi", "halqa" in seen["plan"])
check("qoidalarda diagramma soni va turi aytilgan",
      "Diagramma soni" in everything and "ulush → halqa" in everything)
check("jadval faqat qisqa bo'lsin deyilgan", "QISQA bo'lsa" in everything and "tahlil jadvali" in everything.lower())
check("umumlashtiruvchi gap talabi bor", "UMUMLASHTIRUVCHI GAP" in everything)
check("raqamlash cheklangan", "RAQAMLASH FAQAT KERAK JOYDA" in everything)

print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
