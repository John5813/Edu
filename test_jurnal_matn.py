"""Jurnal uslubi (qog'oz, serif) — yaxlit matn: o'q bilan bog'langan teng qutilar (QADAMLAR) chiqmaydi.

Ketma-ketlik ham kitobdagidek bog'langan abzatslar bilan yoziladi: AI'ga oldindan aytiladi, baribir qutilar
yozsa — slayd qayta so'raladi, u ham chiqmasa — kod qutilarni abzatsga aylantiradi.

    python test_jurnal_matn.py
"""
import asyncio, os, sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services.premium_presentation import html_slides, themes

STEPS = ('<section class="slide"><div class="head"><h2 class="title">Yechimlarga qarab harakat</h2>'
         '<div class="rule"></div></div><div class="body"><p class="lead">Muammolar bosqichma-bosqich hal qilinadi.</p>'
         '<div class="steps">'
         '<div class="card"><div class="card-title">Xalqaro hamkorlik</div><div class="card-note">Davlatlar umumiy '
         'strategiya ishlab chiqadi.</div></div><div class="arrow">&#8594;</div>'
         '<div class="card"><div class="card-title">Innovatsiya</div><div class="card-note">Yashil texnologiyalar '
         'joriy etiladi.</div></div><div class="arrow">&#8594;</div>'
         '<div class="card"><div class="card-title">Barqarorlik</div><div class="card-note">O\'sish va ekologiya '
         'uyg\'unlashadi</div></div></div></div></section>')

print("1) Qaysi uslub")
jurnal = themes.for_deck("Falsafa tarixi", "jurnal", "kop")
toza = themes.for_deck("Falsafa tarixi", "toza", "kop")
check("jurnal — yaxlit matnli uslub", html_slides.prose_style(jurnal), (jurnal.style, jurnal.layout))
check("toza — qadamlar bloki qoladi", not html_slides.prose_style(toza))
check("jurnal promptida qadamlar taqiqlangan", "STYLE RULE" in html_slides.shell_rules(jurnal, "uz"))
check("toza promptida qoida yo'q", "STYLE RULE" not in html_slides.shell_rules(toza, "uz"))

print("2) Zaxira: qutilar → abzatslar")
out = html_slides.steps_to_prose(STEPS)
check("qadamlar bloki qolmadi", not html_slides.has_steps(out) and "arrow" not in out, out)
check("hamma qadam matnda saqlandi", all(w in out for w in ("Xalqaro hamkorlik", "Innovatsiya", "Barqarorlik",
                                                            "umumiy strategiya", "uyg'unlashadi.")), out)
check("abzatslar va sarlavha joyida", out.count('class="par"') == 2 and "Yechimlarga qarab harakat" in out
      and 'class="lead"' in out, out)
check("qadamsiz slayd o'zgarmaydi", html_slides.steps_to_prose("<section><p>Matn</p></section>")
      == "<section><p>Matn</p></section>")

print("3) Yozish: qutilar chiqsa qayta so'raladi")
PROSE = STEPS.split('<div class="steps">')[0] + '<div class="par-col"><p class="par">Avvalo hamkorlik, keyin ' \
        'innovatsiya.</p></div></div></section>'
asked = []

def fake_chunk(system, user, count):
    asked.append(user)
    if len(asked) == 1:
        return [STEPS] * count
    return [PROSE]

html_slides._write_chunk = fake_chunk
html_slides.plan_outline = lambda *a, **k: {"family": "", "slides": [
    {"title": f"S{i}", "brief": "b", "category": "jarayon"} for i in range(6)]}
html_slides.chart_data.ground = lambda o, *a, **k: o
html_slides.chart_data.ground_kpis = lambda o, *a, **k: o
html_slides.repair_deck = lambda s, ctx: s
html_slides.diversify = lambda s, *a, **k: s
html_slides.build_pages = lambda s, theme, language: s
html_slides._thin = lambda b: False
pages = html_slides._write_slides("Global muammolar", 4, jurnal, "uz", 2, "", "", "", None, None, None)
check("qayta so'rovda yaxlit matn talab qilindi", any(html_slides.PROSE_DEMAND in u for u in asked), len(asked))
check("tayyor taqdimotda qadamlar bloki yo'q", not any(html_slides.has_steps(p) for p in pages))

print()
print("HAMMASI O'TDI" if not FAILS else f"XATOLAR: {len(FAILS)} — {FAILS}")
sys.exit(1 if FAILS else 0)
