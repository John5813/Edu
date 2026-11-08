"""Taqdimot tili: o'zbekcha mavzu + «English» tanlansa taqdimot inglizcha bo'lsin (ilgari infografik o'zbekcha chiqardi).

Sabab: mavzu AI ga o'zbekcha borardi, reja sarlavhalari mavzu tilida yozilib, slaydlar ularni aynan ishlatardi;
inglizcha mavzu esa ko'pincha o'zbekcha deb aniqlanardi.

    python test_taqdimot_tili.py
"""
import asyncio, os, sys
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services.premium_presentation import html_slides, llm_client, pipeline, topic_language as tl

print("1) Mavzu tili")
cases = {"Climate change effects": "en", "Artificial intelligence in education": "en", "Inflation": "en",
         "Photosynthesis": "en", "Global warming": "en", "Iqlim o'zgarishi": "uz", "Ekologiya asoslari": "uz",
         "Falsafa: predmeti va muammolari": "uz", "Kompyuter tarmoqlari": "uz", "Covid-19 pandemiyasi": "uz",
         "Parlament tarixi": "uz", "Сельское хозяйство России": "ru", "Ўзбекистон тарихи": "uz"}
for topic, want in cases.items():
    check(f"{topic!r} → {want}", tl.detect(topic) == want, tl.detect(topic))
check("aniq bo'lmasa — None (bot o'zbekcha deb oladi)", tl.detect("Matematika") is None)

print("2) Mavzu taqdimot tiliga o'giriladi")
calls = []

def fake_ai(system, user, **kw):
    calls.append((system, user))
    return {"topic": "Climate change"}

with mock.patch.object(llm_client, "_call_openrouter", side_effect=fake_ai):
    out = tl.localize("Iqlim o'zgarishi", "en")
    check("o'zbekcha mavzu + English → inglizcha mavzu", out == "Climate change" and "English" in calls[-1][0], out)
    n = len(calls)
    check("mavzu allaqachon taqdimot tilida — AI chaqirilmaydi",
          tl.localize("Climate change effects", "en") == "Climate change effects"
          and tl.localize("Iqlim o'zgarishi", "uz") == "Iqlim o'zgarishi"
          and tl.localize("Iqlim o'zgarishi", "uz-cyrl") == "Iqlim o'zgarishi"
          and tl.localize("Iqlim o'zgarishi", "uz-yangi") == "Iqlim o'zgarishi" and len(calls) == n, len(calls) - n)
    tl.localize("Сельское хозяйство России", "uz")
    check("ruscha mavzu + o'zbekcha taqdimot — o'zbekchaga", "Uzbek" in calls[-1][0], calls[-1][0][:80])
with mock.patch.object(llm_client, "_call_openrouter", side_effect=RuntimeError("402")):
    check("AI ishlamasa — asl mavzu (taqdimot baribir yoziladi)", tl.localize("Iqlim o'zgarishi", "en") == "Iqlim o'zgarishi")
with mock.patch.object(llm_client, "_call_openrouter", return_value={"topic": "x" * 900}):
    check("g'alati uzun javob — asl mavzu", tl.localize("Iqlim o'zgarishi", "en") == "Iqlim o'zgarishi")

print("3) Generator AI ga tarjima qilingan mavzuni beradi")
seen = {}

def fake_write(topic, slide_count, theme, **kw):
    seen["topic"], seen["language"] = topic, kw.get("language")
    raise RuntimeError("to'xta")             # yozishning o'zi bu testda kerak emas

with mock.patch.object(llm_client, "_call_openrouter", side_effect=fake_ai), \
     mock.patch.object(html_slides, "write_slides", side_effect=fake_write):
    try:
        asyncio.run(pipeline.build_deck("Iqlim o'zgarishi", 8, language="en", volume="kam"))
    except RuntimeError:
        pass
check("infografik: slaydlar inglizcha mavzu bilan yoziladi", seen.get("topic") == "Climate change"
      and seen.get("language") == "en", seen)

import services.kat3d as kat3d
from services.kat3d import deck as k3deck, reja as k3reja, tadqiqot, yukla
got = {}

def fake_plan(topic, *a, **kw):
    got["topic"] = topic
    return {"slides": [{"layout": "muqova", "models": [], "notes": ""}], "style": "tungi"}

with mock.patch.object(llm_client, "_call_openrouter", side_effect=fake_ai), \
     mock.patch.object(yukla, "ensure", return_value=["m"]), mock.patch.object(tadqiqot, "enabled", return_value=False), \
     mock.patch.object(k3reja, "plan", side_effect=fake_plan), \
     mock.patch.object(k3deck, "build", side_effect=lambda plan, path: open(path, "wb").write(b"x") and path):
    asyncio.run(kat3d.build_deck("Iqlim o'zgarishi", 5, ["m"], language="en"))
check("3D taqdimot: reja inglizcha mavzu bilan", got.get("topic") == "Climate change", got)

print("4) Aniq fan: kod qo'shadigan sarlavhalar taqdimot tilida")
outline = [{"title": "M", "brief": "", "category": "muqova"}, {"title": "R", "brief": "", "category": "reja"},
           {"title": "", "brief": "", "category": "matn_rasm", "padded": True},
           {"title": "Kelajak prognozi 2030", "brief": "x", "category": "korsatkichlar"},
           {"title": "X", "brief": "", "category": "yakun"}]
en = html_slides.exact_rules([dict(o) for o in outline], "aniq", "Quadratic equations", "en")
uz = html_slides.exact_rules([dict(o) for o in outline], "aniq", "Kvadrat tenglamalar")
check("inglizcha: «Problem 1», «Applied problem 1»", [o["title"] for o in en][2:4] == ["Problem 1", "Applied problem 1"]
      and "Masala" not in str(en), [o["title"] for o in en])
check("o'zbekcha — avvalgidek", [o["title"] for o in uz][2:4] == ["Masala 1", "Amaliy masala 1"], [o["title"] for o in uz])

print("5) Bot: inglizcha mavzu inglizcha deb aniqlanadi")
from bot.handlers import premium_presentation as pp
check("«Climate change effects» → en (ilgari uz)", pp._detect_language("Climate change effects") == "en")
check("«Iqlim o'zgarishi» → uz", pp._detect_language("Iqlim o'zgarishi") == "uz")
check("aniq bo'lmagan mavzu → uz (avvalgidek)", pp._detect_language("Matematika") == "uz")

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta XATO")
sys.exit(1 if FAILS else 0)
