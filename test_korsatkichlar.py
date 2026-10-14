"""Raqamli kartochkalar ("korsatkichlar") — faqat haqiqiy raqamlar.

- reja bosqichida AI dan raqamlar manbasi bilan so'raladi; topilmasa slayd raqamsiz kartochkalar bo'ladi;
- topilsa yozuvchi modelga shu raqamlar beriladi va yozilgan slayddagi qiymatlar kod bilan almashtiriladi;
- kelajak yili, raqamsiz qiymat, manbasiz javob — qabul qilinmaydi.

    python test_korsatkichlar.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services import timeframe
from services.premium_presentation import chart_data

GOOD = {"ok": True, "items": [{"value": "46", "unit": "", "label": "Xromosomalar", "year": ""},
                              {"value": "37", "unit": "trln", "label": "Hujayralar soni", "year": ""}],
        "source": "Britannica, 2023", "approx": True}

print("1) Javobni tekshirish")
check("haqiqiy raqamlar qabul qilinadi", chart_data.validate_kpis(GOOD) is not None)
check("ok=false — rad", chart_data.validate_kpis({**GOOD, "ok": False}) is None)
check("manbasiz — rad", chart_data.validate_kpis({**GOOD, "source": ""}) is None)
future = {**GOOD, "items": GOOD["items"] + [{"value": "50", "unit": "%", "label": "O'sish",
                                              "year": str(timeframe.current_year() + 2)}]}
check("noaniq manba («Tadqiqotlar va ilmiy nashrlar») — rad",
      chart_data.validate_kpis({**GOOD, "source": "Tadqiqotlar va ilmiy nashrlar, 2026"}) is None)
check("aniq tashkilot manbasi — qabul", chart_data.validate_kpis({**GOOD, "source": "Human Genome Project"}) is not None)
check("kelajak yili (prognoz) — rad", chart_data.validate_kpis(future) is None)
words = {**GOOD, "items": [{"value": "ko'p", "label": "Tadqiqot"}, {"value": "100+", "label": "Nashr"}]}
check("raqamsiz qiymat tashlanadi, bitta qolsa — rad", chart_data.validate_kpis(words) is None)

print("\n2) Reja bosqichi")
outline = [{"title": "M", "brief": "", "category": "muqova"},
           {"title": "Hujayra raqamlarda", "brief": "Asosiy raqamlar.", "category": "korsatkichlar"},
           {"title": "Tadqiqotlar", "brief": "Yangi yo'nalishlar.", "category": "korsatkichlar"},
           {"title": "X", "brief": "", "category": "yakun"}]
answers = {"Hujayra raqamlarda": chart_data.validate_kpis(GOOD), "Tadqiqotlar": None}
out = chart_data.ground_kpis([dict(o) for o in outline], "Hujayra", "uz",
                             researcher=lambda topic, title, brief, lang: answers[title])
check("raqam topildi — slayd raqamli, yozuvchiga aniq raqamlar beriladi", out[1]["category"] == "korsatkichlar"
      and "46" in out[1]["chart_note"] and "Britannica" in out[1]["chart_note"], out[1])
check("raqam topilmadi — raqamsiz kartochkalar", out[2]["category"] == "kartalar" and "kpi" not in out[2]
      and "WITHOUT numbers" in out[2]["brief"], out[2])

print("\n3) Yozilgan slaydda raqamlar majburan almashadi")
kam = ('<section class="slide k k-raqamlar"><div class="k-text"><h2 class="title">Hujayra</h2><div class="k-row">'
       '<div class="k-kpi"><div class="k-num"><p class="k-v">100+</p><p class="k-u">ta</p></div><p class="k-l">Tadqiqot</p>'
       '<p class="k-d">izoh</p></div><div class="k-kpi"><div class="k-num"><p class="k-v">30+</p><p class="k-u">mlrd</p></div>'
       '<p class="k-l">Loyiha</p><p class="k-d">izoh</p></div></div><p class="k-src">Manba: tadqiqotlar</p></div></section>')
fixed = chart_data.enforce_kpis(kam, out[1], "uz")
check("kam matnli: qiymat, birlik, nom va manba AI bergan", '<p class="k-v">46</p>' in fixed and '<p class="k-v">37</p>' in fixed
      and '<p class="k-u">trln</p>' in fixed and "Xromosomalar" in fixed and "100+" not in fixed
      and "Britannica" in fixed and "taxminiy" in fixed, fixed)
kop = ('<section class="slide"><div class="body"><div class="cols"><div class="kpi"><div class="kpi-value">85%</div>'
       '<div class="kpi-label">Muhandislik</div></div><div class="kpi"><div class="kpi-value">70%</div>'
       '<div class="kpi-label">Iqtisod</div></div></div></div></section>')
fixed = chart_data.enforce_kpis(kop, out[1], "uz")
check("ko'p matnli: kpi-value va kpi-label almashadi", '<div class="kpi-value">46</div>' in fixed
      and '<div class="kpi-value">37 trln</div>' in fixed and "85%" not in fixed, fixed)
check("raqamsiz slaydga tegilmaydi", chart_data.enforce_kpis(kop, out[2], "uz") == kop)

print("\n4) Infografikaning diagramma qolipi ikki ustunga bo'linmaydi")
from services.premium_presentation import html_slides
k = ('<section class="slide k k-diagramma"><div class="k-text"><h2 class="title">T</h2><div class="chart"></div>'
     '<p class="k-p">izoh</p></div></section>')
m = '<section class="slide"><div class="body"><div class="chart"></div><p class="note">izoh</p></div></section>'
check("kam kompozitsiyaga tegilmaydi (matn tor ustunga siqilmaydi)", html_slides._chart_beside_text(k) == k)
check("zamonaviyda diagramma yonida izoh — avvalgidek", "split" in html_slides._chart_beside_text(m))

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
