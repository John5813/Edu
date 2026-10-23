"""Zamonaviy taqdimot: har slaydga sahna (fon, sarlavha, blok varianti) — xilma-xillik ildizdan.

    python test_dizayn_sahna.py
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services.premium_presentation import deck_art, deck_style, html_slides, themes

def S(body, cls="slide", title="T"):
    return f'<section class="{cls}"><div class="head"><h2 class="title">{title}</h2><div class="rule"></div></div><div class="body">{body}</div></section>'

card = lambda t: f'<div class="card"><div class="card-title">{t}</div><div class="card-note">izoh {t}</div></div>'
CARDS = '<p class="lead">Bosh gap.</p><div class="cols cols-3">' + card("a") + card("b") + card("c") + "</div>"
LIST = '<p class="lead">Bosh gap.</p><div class="list">' + "".join(
    f'<div class="item"><span class="item-dot"></span><div class="item-text">band {i}</div></div>' for i in range(4)) + "</div>"
KPI = '<div class="cols cols-3">' + "".join(
    f'<div class="kpi"><div class="kpi-value">{v}</div><div class="kpi-label">l</div></div>' for v in ("9 m", "12%", "x3")) + "</div>"
STEPS = '<div class="steps">' + '<div class="arrow">&#8594;</div>'.join(card(f"q{i}") for i in range(4)) + "</div>"
cover = '<section class="slide dark"><div class="body"><h1 class="title big">M</h1></div></section>'
reja = S('<div class="cols cols-3">' + card("x") + card("y") + card("z") + "</div>", "slide reja")
deck = [cover, reja] + [S(CARDS, title=f"K{i}") for i in range(4)] + [S(LIST, title="L1"), S(KPI), S(STEPS), S(LIST, title="L2"),
                                                                   S(LIST, "slide dark", "Xulosa")]

print("1) Sahna tanlash")
scenes = deck_art.plan(deck)
check("muqovaga sahna berilmaydi", scenes[0] is None)
check("reja ham o'z variantini oladi", scenes[1] and scenes[1]["kind"] == "plan", scenes[1])
inner = [s for s in scenes if s]
check("ketma-ket ikki slayd bir xil fonda emas",
      all(a["canvas"] != b["canvas"] for a, b in zip(inner, inner[1:])), [s["canvas"] for s in inner])
cards = [s["variant"] for s in scenes if s and s["kind"] == "cards"]
check("ketma-ket 4 ta kartochkali slayd — 4 xil ko'rinish", len(set(cards)) == 4, cards)
check("yangi variantlar eski ko'rinishdan oldin ishlatiladi", cards[0] != deck_art.VARIANTS["cards"][0], cards)
check("xulosa to'q fonini saqlaydi", scenes[-1]["canvas"] == "dark", scenes[-1])
darks = [i for i, s in enumerate(scenes) if s and s["canvas"] == "dark"]
check("to'q fon kam (har 5 slaydga bittagacha) va yonma-yon emas",
      len(darks) <= len(deck) // 5 + 1 and all(b - a > 1 for a, b in zip(darks, darks[1:])), darks)
check("tanlov tasodifiy emas (qayta yig'ilganda o'zgarmaydi)", deck_art.plan(deck) == scenes)
check("halqa varianti uzun raqamga berilmaydi",
      not deck_art._fits("kpi", "ring", S(KPI.replace("9 m", "24-72 soat"))))
check("blok uslubida rangli sarlavha tasmasi tanlanmaydi (uslubning o'z tasmasi bor)",
      all(s is None or s["canvas"] != "top" for s in deck_art.plan(deck, "blok")))

print("\n2) Sinflar va bezaklar")
tagged = deck_art.direct(deck)
check("qaror faqat section sinflarida (manba HTML toza)",
      all(t.replace(re.search(r'class="[^"]*"', t).group(0), "", 1) == d.replace(re.search(r'class="[^"]*"', d).group(0), "", 1)
          for t, d in zip(tagged, deck)))
dressed = deck_art.dress(tagged[2])
check("bezak haqiqiy element bo'lib qo'yiladi (slayd raqami)", 'class="art-pg"' in dressed)
check("bezak ikki marta qo'yilmaydi", deck_art.dress(dressed) == dressed)
num = deck_art._tagged(S(CARDS), {"kind": "cards", "variant": "num", "canvas": "light", "head": "rule", "n": "03"})
check("raqamli kartochkaga 01, 02, 03 qo'yiladi", re.findall(r'art-cn">(\d+)<', deck_art.dress(num)) == ["01", "02", "03"])
rewritten = S(CARDS.replace("a", "A"))
check("tuzatishda AI sinfni tushirsa — sahna qaytariladi",
      deck_art._classes(deck_art.carry(num, rewritten)) == deck_art._classes(num), deck_art._classes(deck_art.carry(num, rewritten)))

again = deck_art.direct(tagged)
check("qayta sahnalashda natija o'zgarmaydi (sahna bergan to'q fon slaydning o'zi deb olinmaydi)", again == tagged)
one = deck_art.direct_one(tagged[:5] + [S(LIST, title="Yangi")] + tagged[6:], 5)
check("saytda bitta sahifa almashsa ham sahna oladi", "art-list-" in one, deck_art._classes(one))

print("\n3) Uslub va turlar")
modern = deck_style.stylesheet(themes.for_deck("Mavzu", "toza"))
info = deck_style.stylesheet(themes.for_deck("Mavzu", "", "kam"))
check("zamonaviy taqdimot CSS ida sahnalar bor", ".art-pg" in modern)
check("infografik taqdimotga tegilmaydi", ".art-pg" not in info)
check("qorong'u uslubida och tuslar to'q fonga moslanadi", "--tint:" in deck_style.stylesheet(themes.for_deck("Mavzu", "qorongu")))
pages = html_slides.build_pages(tagged, themes.for_deck("Mavzu", "toza"), "uz")
check("yig'ilgan sahifada bezak bor, manbada yo'q",
      'class="art-pg"' in pages[3] and 'art-pg' not in html_slides.source_of(pages[3]))

print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
