"""Zamonaviy taqdimot: narx oddiy taqdimot bilan bir xil; har 10 slaydda 3 ta rasmli slayd.

    python test_narx_rasm_kvota.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from config import PRESENTATION_PRICES
from bot.handlers import premium_presentation as pp
from services.premium_presentation import deck_logic, html_slides, html_images

print("1) Narx")
for count, price in PRESENTATION_PRICES.items():
    check(f"{count} slayd: zamonaviy narx oddiy taqdimot bilan bir xil ({price:,})", pp._get_price(count) == price, pp._get_price(count))
prices = {n: pp._get_price(n) for n in range(5, 31)}
check("narx slayd soni oshgani sari kamaymaydi", all(prices[n] <= prices[n + 1] for n in range(5, 30)), prices)
check("oraliq sonlar 500 ga yaxlitlanadi", all(p % 500 == 0 for p in prices.values()), prices)
check("12 slayd 10 va 15 orasida", 5000 < prices[12] < 7000, prices[12])
check("25 va 30 slayd 20 slayddan qimmat", prices[25] > prices[20] and prices[30] > prices[25], (prices[25], prices[30]))
check("eng arzon narx 3 000 dan past emas", min(prices.values()) >= pp.MIN_PRICE)
check("narx tugmalarida oddiy va zamonaviy bir xil (10/15/20)",
      all(dict(pp._count_options("jurnal"))[n] == dict(pp._count_options(pp.SIMPLE_STYLE))[n] for n in (10, 15, 20)))

print("\n2) Rasm kvotasi")
check("kvota: 10 → 4, 15 → 6, 20 → 8 (muqova va reja hisobsiz)",
      [deck_logic.photo_quota(n + 2) for n in (10, 15, 20)] == [4, 6, 8], [deck_logic.photo_quota(n + 2) for n in (10, 15, 20)])
check("kam matnli (infografik) kvota ham: 10 → 4, 20 → 8",
      [deck_logic.photo_quota(n + 2, "kam") for n in (10, 20)] == [4, 8])
check("kichik taqdimot ham rasm oladi (5 slayd — 2)", deck_logic.photo_quota(7) == 2)
check("rasm chegarasi kvotadan kam emas (30 slayd — 12, kam matnli ham 12)",
      html_images.photo_limit(30) >= deck_logic.photo_quota(32) == 12
      and html_images.photo_limit(30, "kam") >= deck_logic.photo_quota(32, "kam") == 12)

def outline(categories):
    items = [{"title": f"S{i}", "brief": f"mavzu {i}", "category": c} for i, c in enumerate(categories)]
    return items

for main in (10, 15, 20):
    cats = ["muqova", "reja"] + ["kartalar"] * main + ["yakun"]
    cats = cats[:2] + cats[2:-1][:main - 1] + ["yakun"]       # jami main + 2 ta
    result = html_slides.ensure_photos(outline(cats))
    photos = [i for i, item in enumerate(result) if item["category"] == "matn_rasm"]
    check(f"{main} slayd: {deck_logic.photo_quota(main + 2)} ta rasmli slayd belgilandi", len(photos) == deck_logic.photo_quota(len(result)), photos)
    check(f"{main} slayd: rasmli slaydlar ketma-ket emas", all(b - a > 1 for a, b in zip(photos, photos[1:])), photos)
    check(f"{main} slayd: muqova, reja, yakunga rasm tegmadi", all(result[i]["category"] == c for i, c in ((0, "muqova"), (1, "reja"), (len(result) - 1, "yakun"))))

planned = outline(["muqova", "reja", "matn_rasm", "kartalar", "matn_rasm", "kartalar", "matn_rasm", "kartalar", "kartalar", "matn_rasm", "kartalar", "yakun"])
check("reja o'zi yetarli rasm bergan bo'lsa tegilmaydi", [i["category"] for i in html_slides.ensure_photos([dict(x) for x in planned])] == [i["category"] for i in planned])
tough = outline(["muqova", "reja", "korsatkichlar", "diagramma", "iqtibos", "jadval", "vaqt_oqi", "formula", "misol", "kartalar", "yakun"])
res = html_slides.ensure_photos([dict(x) for x in tough])
check("rasmga yaroqsiz kategoriyalar (diagramma, formula...) rasmli qilinmaydi",
      [i for i, x in enumerate(res) if x["category"] == "matn_rasm"] == [9], [x["category"] for x in res])
# Bosqichlar va qiyos — AI tanlagan tuzilma (infografika): kvota to'lmasa ham rasmli matnga aylanmaydi.
shaped = outline(["muqova", "reja", "jarayon", "qiyoslash", "jarayon", "vaqt_oqi", "qiyoslash", "kartalar", "yakun"])
res = html_slides.ensure_photos([dict(x) for x in shaped], "kam")
check("jarayon va qiyoslash rasm kvotasi uchun buzilmaydi",
      [x["category"] for x in res] == [x["category"] for x in shaped[:7]] + ["matn_rasm", "yakun"],
      [x["category"] for x in res])

print("\n3) Prompt va tekshiruv")
import inspect
from services.premium_presentation import prompts as _prompts
# Prompt matni taqdimot tilidagi faylda (prompts/uz.py) — o'zbekcha nusxasi tekshiriladi.
src = inspect.getsource(html_slides.plan_outline) + str(_prompts.get("uz").PLAN)
check("rejada rasm nisbati ijobiy aytilgan (ikkala turda 4)",
      "10 ta slaydning taxminan ⟨photos⟩ tasi" in src and deck_logic.PHOTOS_PER_10 == {"kop": 4, "kam": 4})
check("'matn_rasm' takror chegarasidan mustasno", "'matn_rasm' bundan mustasno" in src or "bundan mustasno" in src)
with_photo = '<section class="slide"><div class="body"><div class="split"><div class="rasm" data-prompt="old city street"><p class="rasm-matn">x</p></div></div></div></section>'
without = '<section class="slide"><div class="body"><div class="list"><div class="item">x</div></div></div></section>'
check("has_photo: rasm bloki bor / yo'q", deck_logic.has_photo(with_photo) and not deck_logic.has_photo(without))
sig = ("list", "rasm", "split")
bodies = ["c", "r"] + [with_photo.replace("old city street", f"p{i}") if i % 2 == 0 else without.replace("x", f"y{i}") for i in range(8)] + ["z"]
flagged = html_slides.repeated_slides(bodies)
check("rasmli slaydlar bir-biriga tegmasa 'takror shakl' deb belgilanmaydi", all(not deck_logic.has_photo(bodies[i]) for i in flagged), flagged)

print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
