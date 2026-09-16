"""Ishni mavzusiga qarab fanga ajratadi.

Admin har nashrda kategoriya yozib o'tirmasligi uchun fan sarlavha,
tavsif va kalit so'zlardan aniqlanadi. Ro'yxat qat'iy: saytdagi filtrlar
shu nomlarga tayanadi, shuning uchun erkin yozilgan matn emas, shu
yerdagi nomlardan biri tanlanadi.
"""

import re
import unicodedata

# Fan → uni ajratib turadigan so'zlar. So'zlar o'zak ko'rinishida
# yoziladi (qo'shimchalar bilan kelsa ham topilsin): "iqtisod" →
# "iqtisodiyot", "iqtisodiy", "iqtisodchi".
TAXONOMY: dict[str, tuple[str, ...]] = {
    "iqtisodiyot": (
        "iqtisod", "bozor iqtisod", "makroiqtisod", "mikroiqtisod", "inflyatsiya",
        "talab va taklif", "yalpi ichki mahsulot", "yaim", "narx shakllanish",
        "эконом", "инфляц", "спрос и предложение", "economics", "econom",
    ),
    "moliya": (
        "moliya", "buxgalter", "soliq", "kredit", "bank", "investitsiya",
        "byudjet", "audit", "финанс", "бухгалтер", "налог", "банк",
        "finance", "accounting", "taxation",
    ),
    "menejment": (
        "menejment", "boshqaruv", "rahbar", "korxona boshqar", "strategik reja",
        "tadbirkorlik", "biznes reja", "менеджмент", "управлен",
        "предпринимат", "management", "entrepreneur",
    ),
    "marketing": (
        "marketing", "reklama", "brend", "sotuv strategiya", "iste'molchi xulq",
        "маркетинг", "реклам", "бренд", "advertising", "branding",
    ),
    "tarix": (
        "tarix", "mustaqillik", "amir temur", "sovet", "urush", "sulola",
        "xonlik", "arxeolog", "истор", "война", "history", "historical",
    ),
    "adabiyot": (
        "adabiyot", "she'r", "roman", "qissa", "doston", "navoiy",
        "shoir", "yozuvchi", "badiiy asar", "литератур", "поэз", "роман",
        "literature", "poetry", "novel",
    ),
    "tilshunoslik": (
        "tilshunos", "grammatika", "morfolog", "sintaksis", "fonetika",
        "leksikolog", "tarjima", "ingliz tili", "rus tili", "ona tili",
        "лингвист", "граммат", "перевод", "linguistic", "grammar", "translation",
    ),
    "matematika": (
        "matematik", "algebra", "geometriya", "trigonometr", "integral",
        "hosila", "tenglama", "ehtimol", "statistik", "математ", "алгебр",
        "геометр", "уравнен", "mathematic", "calculus", "algebra",
    ),
    "fizika": (
        "fizika", "mexanika", "termodinamik", "elektr maydon", "magnit maydon",
        "optika", "kvant", "yadro fizik", "физик", "механик", "квант",
        "physics", "thermodynamic",
    ),
    "kimyo": (
        "kimyo", "organik birikma", "anorganik", "molekula", "reaksiya",
        "kislota", "element davriy", "polimer", "хими", "реакц", "молекул",
        "chemistry", "chemical",
    ),
    "biologiya": (
        "biolog", "hujayra", "genetik", "anatomiya", "botanika", "zoolog",
        "evolyutsiya", "mikrobiolog", "биолог", "генетик", "клетк",
        "biology", "genetics",
    ),
    "tibbiyot": (
        "tibbiyot", "kasallik", "davolash", "shifokor", "diagnostik",
        "farmakolog", "jarrohlik", "медицин", "болезн", "лечен",
        "medicine", "medical", "clinical",
    ),
    "geografiya": (
        "geografi", "iqlim", "relyef", "materik", "aholi joylash", "kartograf",
        "geograf", "географ", "климат", "geography", "climate",
    ),
    "ekologiya": (
        "ekolog", "atrof-muhit", "atrof muhit", "chiqindi", "tabiatni muhofaza",
        "barqaror rivojlanish", "эколог", "окружающ сред", "ecology",
        "environment", "sustainab",
    ),
    "huquq": (
        "huquq", "qonun", "konstitutsiya", "jinoyat", "fuqarolik kodeks",
        # "прав" emas: u "направление" ichiga ham tushib, yolg'on moslik beradi.
        "sud", "yuridik", "право", "юридич", "закон", "конституц", "уголовн",
        "law", "legal", "constitution",
    ),
    "pedagogika": (
        "pedagog", "ta'lim", "talim", "dars", "o'qitish", "oqitish", "metodika",
        "o'quvchi", "oquvchi", "tarbiya", "педагог", "обучен", "воспитан",
        "pedagog", "teaching", "education",
    ),
    "psixologiya": (
        "psixolog", "shaxs xulq", "temperament", "stress", "motivatsiya",
        "психолог", "личност", "psycholog", "behaviour", "behavior",
    ),
    "sotsiologiya": (
        "sotsiolog", "jamiyat", "ijtimoiy tadqiqot", "demograf", "so'rovnoma",
        "социолог", "обществ", "sociolog", "social research",
    ),
    "falsafa": (
        "falsafa", "faylasuf", "ontolog", "etika", "mantiq ilmi",
        "философ", "этик", "philosoph", "ethics",
    ),
    "informatika": (
        "informatika", "dasturlash", "algoritm", "ma'lumotlar bazasi",
        "malumotlar bazasi", "kompyuter", "tarmoq", "sun'iy intellekt",
        "suniy intellekt", "python", "информатик", "программир", "компьютер",
        "algorithm", "programming", "software", "database",
    ),
    "texnika": (
        "muhandis", "mexanizm", "qurilish", "arxitektura", "energetika",
        "avtomobil", "stanok", "ishlab chiqarish texnolog", "инженер",
        "строительств", "engineering", "construction",
    ),
    "qishloq xo'jaligi": (
        "qishloq xo'jalig", "qishloq xojalig", "dehqonchilik", "chorvachilik",
        "agronom", "hosildorlik", "ekin", "сельск", "агроном",
        "agriculture", "farming",
    ),
    "san'at": (
        "san'at", "sanat", "musiqa", "rassom", "teatr", "kino", "dizayn",
        "haykaltarosh", "искусств", "музык", "art", "music", "design",
    ),
    "sport": (
        "sport", "jismoniy tarbiya", "musobaqa", "olimpiada o'yin", "futbol",
        "mashq", "спорт", "физкультур", "athletic", "fitness",
    ),
    "din": (
        "islom", "qur'on", "quron", "hadis", "shariat", "diniy",
        "ислам", "коран", "religio", "islamic",
    ),
}


def normalize(text: str) -> str:
    """Qidiruv uchun bir xil ko'rinishga keltiradi.

    O'zbek matnida bir tovush bir necha belgi bilan yoziladi (oʻ, o', o`),
    shuning uchun apostroflar olib tashlanadi — aks holda "o'zbek" va
    "ozbek" boshqa so'z bo'lib qolardi.
    """
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = re.sub(r"[ʻʼ‘’'`´]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def classify(*parts: str) -> str:
    """Matnga eng mos fan nomini qaytaradi, topilmasa bo'sh satr."""
    haystack = normalize(" ".join(p for p in parts if p))
    if not haystack:
        return ""

    best, best_score = "", 0
    for subject, needles in TAXONOMY.items():
        score = 0
        for needle in needles:
            key = normalize(needle)
            if key and key in haystack:
                # Uzunroq iboraning topilishi tasodif bo'lish ehtimoli kam,
                # shuning uchun u ko'proq ishonch beradi.
                score += 2 if " " in key else 1
        if score > best_score:
            best, best_score = subject, score
    return best


def subjects() -> list[str]:
    return list(TAXONOMY)
