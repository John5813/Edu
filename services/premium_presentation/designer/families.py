"""Mavzu oilasi va obrazi bo'yicha uslub og'irliklari.

Tanlovchi uslubni tasodifiy tanlaydi, lekin tasodif mavzuga bog'langan:
- OILA — reja tuzilganda aniqlangan fan oilasi (`deck_shape`: tarix, aniq, tabiiy, ijtimoiy ...);
- OBRAZ — mavzu nomidagi so'zlardan: tabiat, texnika, biznes, ta'lim, tibbiyot, madaniyat, sayohat.

Har biri uslubga ko'paytuvchi beradi: 1 — oddiy, 2-3 — ko'proq chiqsin, 0 — umuman chiqmasin
(masalan, moliya mavzusida barglar, adabiyotda tishli g'ildiraklar). Oila va obraz ko'paytuvchilari
ko'paytiriladi. Agar hamma mos uslub taqiqlanib qolsa, tanlovchi ko'paytuvchilarsiz tanlaydi.
"""
from typing import Dict, List

FAMILY: Dict[str, Dict[str, float]] = {
    "tarix": {"arcs": 2, "fan": 2, "swirl": 1.5, "tree": 1.5, "gears": 0, "leaves": 0.3, "cross": 0.6,
              "cover_x": 1.5},
    "aniq": {"gears": 2.5, "arrows": 2, "cross": 1.5, "diamond": 1.5, "pencil": 1.5, "leaves": 0, "tree": 0.4,
             "cover_hex": 1.5},
    "tabiiy": {"leaves": 2.5, "tree": 2.5, "swirl": 1.5, "fan": 1.3, "gears": 0.4, "cross": 0.6},
    "ijtimoiy": {"pie": 2, "arcs": 2, "diamond": 1.5, "arrows": 1.5, "leaves": 0.3, "tree": 0.6},
    "gumanitar": {"pencil": 2, "fan": 2, "swirl": 1.5, "tree": 1.3, "gears": 0, "cross": 0.6},
    "amaliy": {"tree": 1.5, "pencil": 1.5, "cross": 1.5, "arrows": 1.5, "plan_wave": 1.5},
    "hisob": {"pie": 2, "arcs": 2, "arrows": 1.5, "diamond": 1.5, "leaves": 0, "tree": 0.3, "cover_hex": 1.5},
    "umumiy": {},
}

# Obraz: (kalit so'zlar, ko'paytuvchilar). Mavzu nomida birinchi topilgani olinadi.
MOODS: List[tuple] = [
    ("tabiat", ("ekolog", "tabiat", "o'simlik", "o‘simlik", "hayvon", "o'rmon", "suv ", "iqlim", "bog'", "qishloq xo",
                "agro", "biolog", "atrof-muhit", "эколог", "природ", "растен", "лес", "климат", "ecolog", "nature",
                "plant", "forest", "climate", "environment", "табиғат", "экология"),
     {"leaves": 3, "tree": 3, "fan": 1.5, "swirl": 1.3, "gears": 0, "cross": 0.5, "pencil": 0.5}),
    ("texnika", ("texnolog", "raqamli", "dastur", "kompyuter", "internet", "sun'iy intellekt", "muhandis", "sanoat",
                 "robot", "axborot", "kiber", "технолог", "цифров", "программ", "компьютер", "инженер", "промышлен",
                 "technolog", "digital", "software", "computer", "engineer", "industr", "технология"),
     {"gears": 3, "arrows": 2, "cross": 1.8, "diamond": 1.5, "leaves": 0, "tree": 0.4, "cover_hex": 2}),
    ("biznes", ("iqtisod", "moliya", "biznes", "marketing", "bank", "investitsiya", "savdo", "tadbirkor", "soliq",
                "budjet", "byudjet", "menejment", "эконом", "финанс", "бизнес", "маркетинг", "банк", "инвест",
                "econom", "financ", "business", "marketing", "invest", "бизнес", "қаржы"),
     {"pie": 2.5, "arcs": 2, "diamond": 2, "arrows": 2, "gears": 1.5, "leaves": 0, "tree": 0.4, "pencil": 0.6}),
    ("talim", ("ta'lim", "ta’lim", "pedagog", "maktab", "o'qitish", "o‘qitish", "talaba", "o'quvchi", "dars",
               "metodika", "tarbiya", "образован", "педагог", "школ", "обучен", "education", "teaching", "school",
               "pedagog", "білім", "мектеп"),
     {"pencil": 3, "tree": 1.5, "plan_wave": 2, "arrows": 1.3, "leaves": 0.5, "gears": 0.6}),
    ("tibbiyot", ("tibbiyot", "sog'liq", "sog‘liq", "kasallik", "shifo", "salomatlik", "psixolog", "gigiyena",
                  "медицин", "здоров", "болезн", "психолог", "medic", "health", "disease", "psycholog", "денсаулық"),
     {"swirl": 2, "cross": 2, "diamond": 1.5, "arrows": 1.3, "gears": 0.4, "pencil": 0.6}),
    ("madaniyat", ("tarix", "madaniyat", "meros", "adabiyot", "san'at", "san’at", "she'r", "falsafa", "musiqa", " din ",
                   "истори", "культур", "литератур", "искусств", "философ", "history", "culture", "literature", "artist",
                   "philosoph", "тарих", "мәдениет", "әдебиет"),
     {"arcs": 2, "swirl": 2, "fan": 2, "tree": 1.5, "pencil": 1.3, "gears": 0, "cross": 0.5, "cover_x": 1.5}),
    ("sayohat", ("turizm", "sayohat", "sayyoh", "mehmonxona", "туризм", "путешеств", "tourism", "travel", "саяхат"),
     {"fan": 2, "swirl": 2, "arcs": 2, "arrows": 1.5, "gears": 0.3, "cover_x": 1.5}),
]


def mood_of(topic: str) -> str:
    text = " " + (topic or "").lower() + " "
    for name, words, _ in MOODS:
        if any(word.lower() in text for word in words):
            return name
    return ""


def multipliers(family: str, topic: str) -> Dict[str, float]:
    """Uslub nomi → ko'paytuvchi (oila × obraz)."""
    out: Dict[str, float] = dict(FAMILY.get(family or "", {}))
    mood = mood_of(topic)
    for name, _, weights in MOODS:
        if name == mood:
            for style, value in weights.items():
                out[style] = out.get(style, 1.0) * value
    return out
