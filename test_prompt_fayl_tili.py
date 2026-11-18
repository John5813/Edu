"""Saytdagi tayyor AI ko'rsatmalari FAYL tilida (mijoz taqdimot uchun tanlagan tilda), sayt tilida emas.

«AI ga taqdimot qanday bo'lishini tushuntiring» namunalari va «AI bilan o'zgartirish» tugmalari har bir
taqdimot tili uchun bor, ruscha/inglizcha/qozoqcha ro'yxatda o'zbekcha so'z yo'q, taqdimot ko'rinishi
(`web_decks.public`) tilni brauzerga beradi.

    python test_prompt_fayl_tili.py
"""
import os
import re
import sys

os.environ.setdefault("BOT_TOKEN", "1:x")

from webapp import api  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  XATO ") + name + ("" if ok else f" — {detail}"))
    if not ok:
        FAILS.append(name)


UZ_WORDS = re.compile(r"[ʻ‘']|\b(?:qilib|ber|uchun|bilan|ko'proq|sahifa|va)\b", re.IGNORECASE)
LANGS = ("uz", "uz-cyrl", "uz-yangi", "ru", "en", "kk")

rewrite, prefs = api.REWRITE_PROMPTS_BY_LANG, api.PREF_EXAMPLES_BY_LANG
check("har bir taqdimot tili uchun «AI bilan o'zgartirish» tugmalari bor", all(k in rewrite for k in LANGS),
      sorted(set(LANGS) - set(rewrite)))
check("har bir taqdimot tili uchun namunalar bor", all(k in prefs for k in LANGS), sorted(set(LANGS) - set(prefs)))
check("tugmalar soni va belgilari hamma tilda bir xil",
      all([p["icon"] for p in rewrite[k]] == [p["icon"] for p in api.REWRITE_PROMPTS] for k in LANGS))
for lang in ("ru", "en", "kk"):
    texts = [p["text"] for p in rewrite[lang]] + prefs[lang]
    bad = [t for t in texts if UZ_WORDS.search(t.replace("'", ""))] if lang != "en" else \
        [t for t in texts if re.search(r"\b(?:qilib|uchun|bilan|sahifa)\b", t)]
    check(f"{lang}: o'zbekcha so'z qolmagan", not bad, bad)
cyr = [p["text"] for p in rewrite["uz-cyrl"]] + prefs["uz-cyrl"]
check("kirill o'zbekchada lotin harfi yo'q", not [t for t in cyr if re.search(r"[A-Za-z]", t)], cyr[:3])

import inspect  # noqa: E402
from services import web_decks  # noqa: E402
check("taqdimot ko'rinishi tilni beradi (tugmalar shu tilda chiqadi)", '"language"' in inspect.getsource(web_decks.public))

print("\n✅ hammasi o'tdi" if not FAILS else f"\n❌ {len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
