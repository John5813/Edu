"""O'zbekistonga oid mavzularni ajratadi va ularga maxsus qoida qo'yadi.

O'zbekistonda topshiriladigan kurs va diplom ishlarida yozilmagan bir
tartib bor: mavzu mamlakat iqtisodi yoki siyosatiga tegishli bo'lsa,
kirish Prezidentning shu sohadagi so'zlaridan boshlanadi va o'sha
so'zlarga snoska qo'yiladi, adabiyotlar ro'yxatining boshida esa
Prezident asari va Konstitutsiya turadi. Shu modul o'sha tartibni bir
joyda saqlaydi — har bir hujjat turi uni o'zicha qilmasin.
"""

import re

from services import timeframe

# Mavzu shu so'zlardan biri bilan boshlansa — bu O'zbekiston haqidagi ish.
_OPENERS = (
    "ozbekiston", "ozbekistonda", "ozbekistonning", "ozbekiston respublikasi",
    "uzbekistan", "узбекистан", "узбекистана", "узбекистане",
    "республика узбекистан",
)

# Mavzu ichida mamlakat nomi uchrasa, uni soha so'zi bilan birga qaraymiz:
# "Jahon iqtisodiyoti va O'zbekiston" ham shu tartibga kiradi.
_COUNTRY = ("ozbekiston", "uzbekistan", "узбекистан")

_FIELD_WORDS = (
    # iqtisod
    "iqtisod", "iqtisodiy", "moliya", "budjet", "byudjet", "soliq", "bank",
    "investitsiya", "eksport", "import", "savdo", "bozor", "tadbirkorlik",
    "sanoat", "qishloq xojaligi", "turizm", "inflyatsiya", "yalpi ichki",
    "milliy boylik", "aholi daromadi", "bandlik", "ish haqi",
    "эконом", "финанс", "бюджет", "налог", "банк", "инвестиц", "экспорт",
    "импорт", "торговл", "рынок", "предпринимат", "промышленн", "туризм",
    "economy", "economic", "finance", "budget", "tax", "investment",
    "export", "import", "trade", "market", "industry", "tourism",
    # siyosat va davlat
    "siyosat", "siyosiy", "davlat", "hukumat", "islohot", "konstitutsiya",
    "qonun", "huquq", "parlament", "oliy majlis", "diplomatiya", "tashqi siyosat",
    "mahalliy boshqaruv", "strategiya", "taraqqiyot",
    "полити", "государств", "правительств", "реформ", "конституц", "закон",
    "прав", "парламент", "дипломат", "стратеги", "развити",
    "politic", "state", "government", "reform", "constitution", "law",
    "parliament", "diplomacy", "strategy", "development",
)


def _flatten(text: str) -> str:
    """Apostrof va tinish belgilarisiz kichik harfli ko'rinish.

    O'zbek tilida mamlakat nomi "O'zbekiston", "Oʻzbekiston", "Ozbekiston"
    va "Uzbekistan" shaklida yoziladi — solishtirish uchun hammasini bir
    xil qilamiz.
    """
    text = (text or "").lower()
    text = re.sub(r"[‘’ʻʼ′'`´]", "", text)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]+", " ", text)).strip()


def is_uzbek_topic(topic: str) -> bool:
    """Mavzu O'zbekiston iqtisodi yoki siyosatiga tegishlimi.

    Ikki yo'l bilan: mavzu mamlakat nomi bilan boshlansa — shartsiz;
    nomi mavzu ichida bo'lsa — soha so'zi ham bo'lishi kerak, aks holda
    "O'zbekiston adabiyoti" ham shu tartibga tushib qolardi.
    """
    flat = _flatten(topic)
    if not flat:
        return False
    if any(flat.startswith(opener) for opener in _OPENERS):
        return True
    if any(name in flat for name in _COUNTRY):
        return any(word in flat for word in _FIELD_WORDS)
    return False


def opening_rule(topic: str, language: str = "uz") -> str:
    """Kirishning birinchi abzasi uchun prompt qoidasi."""
    year = timeframe.current_year()
    if language == "ru":
        return (
            f'Тема "{topic}" относится к Узбекистану, поэтому ВВЕДЕНИЕ '
            "начинается с отдельного первого абзаца (110-150 слов, примерно "
            "треть страницы) о том, что Президент Республики Узбекистан "
            "Шавкат Мирзиёев говорил именно об этой сфере: из Послания Олий "
            "Мажлису, выступления или книги. Абзац должен быть связан "
            "непосредственно с темой, а не быть общими словами о реформах. "
            f"Ссылайтесь на выступления последних лет (до {year} года)."
        )
    if language == "en":
        return (
            f'The topic "{topic}" concerns Uzbekistan, so the INTRODUCTION '
            "opens with a separate first paragraph (110-150 words, about a "
            "third of a page) on what the President of the Republic of "
            "Uzbekistan, Shavkat Mirziyoyev, has said about this very field "
            "— from an Address to the Oliy Majlis, a speech or a book. The "
            "paragraph must bear directly on the topic, not be general talk "
            f"about reforms. Use addresses of recent years (up to {year})."
        )
    return (
        f'"{topic}" mavzusi O\'zbekistonga tegishli, shuning uchun KIRISH '
        "alohida birinchi abzatsdan boshlanadi (110-150 so'z, taxminan "
        "varaqning uchdan bir qismi): O'zbekiston Respublikasi Prezidenti "
        "Shavkat Mirziyoyev aynan shu soha haqida nima deganini yozing — "
        "Oliy Majlisga Murojaatnomasidan, ma'ruzasidan yoki asaridan. "
        "Abzats bevosita mavzuga bog'lansin, islohotlar haqidagi umumiy "
        f"gap bo'lmasin. So'nggi yillardagi ({year}-yilgacha) chiqishlarga "
        "tayaning."
    )


def chapter_arc(topic: str, language: str = "uz") -> str:
    """Uch bobning mantiqiy ketma-ketligi — prompt qoidasi.

    O'zbekistonga oid kurs ishlari shu tartibda yoziladi: avval
    tushuncha va nazariya, keyin mamlakatdagi bugungi holat, oxirida
    istiqbollar. Bu tartibsiz boblar bir-birini takrorlab, ish
    mantiqiy izchillikni yo'qotardi.
    """
    if language == "ru":
        return (
            "СТРУКТУРА ГЛАВ (строго в этом порядке):\n"
            "- I глава — концептуальная: понятие, сущность, теоретические "
            "основы и мировой опыт по теме.\n"
            "- II глава — нынешнее положение в Узбекистане: действующая "
            "практика, данные, достигнутые результаты и проблемы.\n"
            "- III глава — перспективы: пути совершенствования, прогноз и "
            "предложения.\n"
            "Главы не должны повторять друг друга: каждая продолжает "
            "предыдущую."
        )
    if language == "en":
        return (
            "CHAPTER STRUCTURE (strictly in this order):\n"
            "- Chapter I — conceptual: the notion, its essence, the "
            "theoretical foundations and international experience.\n"
            "- Chapter II — the present state in Uzbekistan: current "
            "practice, figures, results achieved and problems.\n"
            "- Chapter III — prospects: ways to improve, forecast and "
            "proposals.\n"
            "The chapters must not repeat one another: each continues the "
            "previous one."
        )
    return (
        "BOBLAR TUZILISHI (aynan shu tartibda):\n"
        "- I bob — konseptual: mavzuning tushunchasi, mohiyati, nazariy "
        "asoslari va jahon tajribasi.\n"
        "- II bob — O'zbekistondagi bugungi holat: amaldagi tartib, "
        "raqamlar, erishilgan natijalar va muammolar.\n"
        "- III bob — istiqbollar: takomillashtirish yo'llari, prognoz va "
        "takliflar.\n"
        "Boblar bir-birini takrorlamasin: har biri oldingisining davomi "
        "bo'lsin."
    )


def constitution_source(language: str = "uz") -> str:
    """Adabiyotlar ro'yxatida ikkinchi bo'lib turadigan yozuv."""
    if language == "ru":
        return ("Конституция Республики Узбекистан. — Ташкент: "
                "«Узбекистан», 2023. — 76 с.")
    if language == "en":
        return ("The Constitution of the Republic of Uzbekistan. — Tashkent: "
                "“O‘zbekiston”, 2023. — 76 p.")
    return ("O'zbekiston Respublikasining Konstitutsiyasi. — Toshkent: "
            "«O'zbekiston», 2023. — 76 b.")


def default_president_source(language: str = "uz") -> str:
    """Prezident manbasi topilmasa ishlatiladigan zaxira yozuv."""
    if language == "ru":
        return ("Мирзиёев Ш.М. Стратегия Нового Узбекистана. — Ташкент: "
                "«Узбекистан», 2022. — 464 с.")
    if language == "en":
        return ("Mirziyoyev Sh.M. The Strategy of New Uzbekistan. — Tashkent: "
                "“O‘zbekiston”, 2022. — 464 p.")
    return ("Mirziyoyev Sh.M. Yangi O'zbekiston strategiyasi. — Toshkent: "
            "«O'zbekiston», 2022. — 464 b.")


def _is_president(text: str) -> bool:
    flat = _flatten(text)
    return any(word in flat for word in (
        "mirziyoyev", "мирзиёев", "mirziyoev",
        "prezidenti", "президент", "president",
        "murojaatnoma", "послание", "address to the oliy majlis",
    ))


def _is_constitution(text: str) -> bool:
    flat = _flatten(text)
    return any(word in flat for word in ("konstitutsiya", "конституц", "constitution"))


def _year_of(text: str) -> int:
    """Yozuvdagi eng katta yilni qaytaradi — saralash uchun."""
    years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", str(text))]
    return max(years) if years else 0


def order_references(references: list, language: str = "uz",
                     president_source: str = "") -> list:
    """Adabiyotlarni O'zbekiston ishlari uchun talab qilingan tartibga soladi.

    Birinchi — Prezident asari yoki nutqi, ikkinchi — Konstitutsiya,
    qolganlari esa eng yangi yildan eskisiga qarab. Ro'yxatda Prezident
    yoki Konstitutsiya bo'lmasa, ular qo'shiladi: bu ikkisi shunday
    ishlarda doim birinchi o'rinlarda turadi.
    """
    items = [str(r).strip() for r in (references or []) if str(r).strip()]
    # Raqamlash qayta qo'yiladi, shuning uchun eskisi olib tashlanadi.
    items = [re.sub(r"^\s*\d+[\.\)]\s*", "", item) for item in items]

    president = next((i for i in items if _is_president(i)), "")
    constitution = next((i for i in items if _is_constitution(i)), "")
    rest = [i for i in items if i not in (president, constitution)]

    if not president:
        president = (president_source or "").strip() or default_president_source(language)
    if not constitution:
        constitution = constitution_source(language)

    rest.sort(key=_year_of, reverse=True)
    return [president, constitution] + rest
