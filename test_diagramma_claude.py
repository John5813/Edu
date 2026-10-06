"""Diagramma ma'lumotlari FAQAT Claude'dan va haqiqiy: boshqa model to'qimaydi.

    python test_diagramma_claude.py
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services import timeframe
from services.premium_presentation import chart_data, config, deck_charts, deck_logic, html_slides, llm_client, themes

THEME = themes.get("zumrad")
YEAR = timeframe.current_year()
GOOD = {"ok": True, "kind": "line", "labels": [str(YEAR - 4 + i) for i in range(4)],
        "series": [{"name": "YaIM o'sishi (%)", "values": [5.2, 6.0, 5.7, 6.5]}],
        "unit": "%", "xlabel": "Yil", "source": "Jahon banki", "approx": False, "forecast": False}

print("1) Model faqat Claude")
check("diagramma ro'yxati faqat Anthropic", config.OPENROUTER_CHART_MODELS
      and all(m.startswith("anthropic/") for m in config.OPENROUTER_CHART_MODELS), config.OPENROUTER_CHART_MODELS)
llm_client.set_text_model("google/gemini-2.5-pro")          # admin boshqa model tanladi
chain = llm_client._models("chart")
check("admin tanlagan boshqa model diagramma uchun ishlatilmaydi",
      chain and all(m.startswith("anthropic/") for m in chain), chain)
check("matn uchun admin tanlovi saqlanadi", llm_client._models("text")[0] == "google/gemini-2.5-pro")
llm_client._preferred.pop("text", None); llm_client._WORKING.pop("text", None)

print("2) Tekshiruv (validate)")
v = chart_data.validate(GOOD, "uz")
check("yaxshi javob qabul qilindi", v and v["kind"] == "line" and v["series"][0][1] == [5.2, 6.0, 5.7, 6.5], v)
check("manba belgisi tilga mos", v["label"] == "Manba:" and chart_data.validate(GOOD, "ru")["label"] == "Источник:")
bad = {
    "ok false": {**GOOD, "ok": False},
    "manba yo'q": {**GOOD, "source": ""},
    "qiymat soni yorliqqa mos emas": {**GOOD, "series": [{"name": "A", "values": [1, 2]}]},
    "raqam emas": {**GOOD, "series": [{"name": "A", "values": [1, "ko'p", 3, 4]}]},
    "bitta yorliq": {**GOOD, "labels": ["2024"], "series": [{"name": "A", "values": [1]}]},
    "kelajak yili prognozsiz": {**GOOD, "labels": [str(YEAR + 1 + i) for i in range(4)]},
    "halqa yig'indisi 100 emas": {**GOOD, "kind": "donut", "labels": ["A", "B"], "series": [{"name": "U", "values": [10, 20]}]},
    "hammasi nol": {**GOOD, "series": [{"name": "A", "values": [0, 0, 0, 0]}]},
}
for name, raw in bad.items():
    check(f"rad etiladi: {name}", chart_data.validate(raw, "uz") is None)
check("prognoz belgilangan bo'lsa kelajak yili qabul", chart_data.validate(
    {**GOOD, "labels": [str(YEAR + i) for i in range(4)], "forecast": True}, "uz") is not None)
donut = chart_data.validate({**GOOD, "kind": "donut", "labels": ["A", "B", "C"],
                             "series": [{"name": "Ulush", "values": [50, 30, 20]}]}, "uz")
check("halqa yig'indisi 100 bo'lsa qabul", donut and donut["kind"] == "donut")

print("3) Claude'ga so'rov (kind='chart')")
seen = {}
orig = llm_client._call_openrouter
def fake_call(system, user, temperature=0.7, max_tokens=16000, kind="text"):
    seen["kind"], seen["user"] = kind, user
    return GOOD
llm_client._call_openrouter = fake_call
try:
    got = chart_data.research("Iqtisodiyot", "YaIM o'sishi", "Yillik o'sish", "chiziqli", "uz")
finally:
    llm_client._call_openrouter = orig
check("so'rov 'chart' turi bilan ketdi", seen.get("kind") == "chart", seen.get("kind"))
check("so'rov haqiqiy raqam, manba va yangi yillarni talab qiladi",
      "rasmiy" in seen["user"] and "manba" in seen["user"].lower() and "YANGI yillar" in seen["user"]
      and str(YEAR) in seen["user"], "")
check("ishonchli ma'lumot bo'lmasa chiqish yo'li berilgan", "`ok` ni false" in seen["user"])
check("natija tekshirilgan ma'lumot", got and got["source"] == "Jahon banki")
def boom(*a, **k): raise RuntimeError("tarmoq")
llm_client._call_openrouter = boom
try:
    check("xatoda None (boshqa modelga o'tilmaydi)", chart_data.research("a", "b", "c", "bar", "uz") is None)
finally:
    llm_client._call_openrouter = orig

print("4) Rejani asoslash (ground)")
outline = [{"title": "Mavzu", "brief": "m", "category": "muqova"},
           {"title": "Reja", "brief": "r", "category": "reja"},
           {"title": "YaIM", "brief": "iqtisodiy o'sish", "category": "diagramma", "was": "kartalar", "chart_kind": "chiziqli"},
           {"title": "Hudud", "brief": "hudud tuzilmasi", "category": "diagramma", "was": "ikki_ustun"},
           {"title": "Xulosa", "brief": "x", "category": "yakun"}]
def researcher(topic, title, brief, kind, language):
    return chart_data.validate(GOOD, language) if title == "YaIM" else None
out = chart_data.ground([dict(o) for o in outline], "Iqtisodiyot", "uz", 2, researcher=researcher)
check("ma'lumot topilgan slaydda diagramma qoldi", out[2]["category"] == "diagramma" and out[2]["chart"]["source"] == "Jahon banki")
check("yozuvchiga tayyor blok va manba beriladi", "TAYYOR DIAGRAMMA" in out[2]["chart_note"] and 'class="chart"' in out[2]["chart_note"]
      and "Manba: Jahon banki" in out[2]["chart_note"])
check("ma'lumot topilmagan slayd diagrammasiz kategoriyaga qaytdi", out[3]["category"] == "ikki_ustun" and "chart" not in out[3], out[3])

print("5) Slaydga majburlash (enforce)")
invented = ('<section class="slide"><div class="body"><div class="chart" data-kind="bar" data-labels="a,b" '
            'data-series="X: 1,2"></div><div class="chart" data-kind="bar" data-labels="a,b" data-series="Y: 3,4"></div>'
            '<p class="note">Izoh.</p></div></section>')
fixed = chart_data.enforce(invented, out[2])
check("model to'qigan raqamlar tayyor ma'lumotga almashdi, ortiqcha diagramma tushdi",
      fixed.count('class="chart"') == 1 and "5.2,6,5.7,6.5" in fixed and "X: 1,2" not in fixed, fixed)
check("rejada ma'lumot yo'q slaydda to'qima diagramma olib tashlandi",
      "chart" not in chart_data.enforce(invented, out[3]) and "Izoh." in chart_data.enforce(invented, out[3]))
calc = '<div class="calc" data-kind="line" data-series="a: t"></div>'
check("hisob (calc) bloki tegilmaydi", chart_data.enforce(calc, None) == calc)

print("6) Diagramma chizilganda manba ko'rinadi")
svg = deck_charts.draw(chart_data.block(out[2]["chart"]), THEME)
check("manba yozuvi diagrammada", "Manba: Jahon banki" in svg and svg.count("<svg") == 1)
check("raqamlar Claude bergan qiymatlar", all(f">{x}<" in svg.replace(",", ".") or f">{str(x).replace('.', ',')}<" in svg for x in ("5.2",)) or "5,2" in svg)

print("7) To'liq oqim: write_slides")
body = lambda title, extra: (f'<section class="slide"><div class="head"><h2 class="title">{title}</h2></div>'
                             f'<div class="body"><p class="lead">{title} haqida bosh fikr.</p>{extra}</div></section>')
cover = '<section class="slide dark"><div class="body"><h1 class="title big">Mavzu</h1></div></section>'
chart_fake = '<div class="chart" data-kind="bar" data-labels="a,b,c" data-series="To\'qima: 11,22,33"></div>'
card = '<div class="cols cols-2"><div class="card"><div class="card-title">Bir</div><div class="card-note">Izoh bir.</div></div><div class="card"><div class="card-title">Ikki</div><div class="card-note">Izoh ikki.</div></div></div>'
slides_fake = [cover, body("Reja", ""), body("YaIM o'sishi", chart_fake + '<p class="note">Bu diagramma o\'sishni ko\'rsatadi.</p>'),
               body("Hudud", chart_fake + '<p class="note">Hududlar.</p>'), body("Qo'shimcha", card),
               body("Yana", card), body("Xulosa", '<p class="note">Xulosa matni bu yerda yoziladi.</p>')]
saved = (html_slides.plan_outline, html_slides._write_chunk, html_slides._thicken, chart_data.research)
try:
    html_slides.plan_outline = lambda *a, **k: {"family": "umumiy", "slides": [
        {"title": "Mavzu", "brief": "m", "category": "muqova"},
        {"title": "Taqdimot rejasi", "brief": "r", "category": "reja"},
        {"title": "YaIM o'sishi", "brief": "o'sish", "category": "diagramma", "was": "kartalar", "chart_kind": "chiziqli"},
        {"title": "Hudud", "brief": "hudud", "category": "diagramma", "was": "ikki_ustun"},
        {"title": "Qo'shimcha", "brief": "q", "category": "kartalar"},
        {"title": "Yana", "brief": "y", "category": "kartalar"},
        {"title": "Xulosa", "brief": "Xulosa: asosiy fikrlar", "category": "yakun"}]}
    prompts = []
    def chunk(system, user, count):
        prompts.append(user)
        start = int(re.search(r"(\d+)-slayddan boshlab", user).group(1)) if "-slayddan boshlab" in user else 1
        return slides_fake[start - 1:start - 1 + count]
    html_slides._write_chunk = chunk
    html_slides._thicken = lambda b, s, t: b
    chart_data.research = lambda topic, title, brief, kind, language: (
        chart_data.validate(GOOD, language) if title == "YaIM o'sishi" else None)
    pages = html_slides.write_slides("Iqtisodiyot", 5, THEME)
finally:
    html_slides.plan_outline, html_slides._write_chunk, html_slides._thicken, chart_data.research = saved
joined = "\n".join(pages)
check("yozuvchi so'rovida tayyor diagramma ma'lumoti bor", any("TAYYOR DIAGRAMMA" in p for p in prompts))
check("to'qima raqamlar sahifada yo'q", "To'qima" not in joined and ">33<" not in joined)
check("Claude bergan raqam va manba sahifada bor", "Manba: Jahon banki" in joined and ">6,5<" in joined or "6.5" in joined)
check("ma'lumot topilmagan slaydda diagramma yo'q (diagramma soni 1)", joined.count('class="chart"') == 1, joined.count('class="chart"'))

print("\nXATO:" if FAILS else "\nHAMMASI YAXSHI", FAILS or "")
sys.exit(1 if FAILS else 0)
