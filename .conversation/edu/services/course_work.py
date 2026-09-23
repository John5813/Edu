"""Kurs ishining ikki usuli va kirish qismining qat'iy tartibi.

Ustoz tekshirgan ishdagi qizil tuzatishlar shu yerda qoida bo'lib
yozilgan:

- Kirish "Mavzuning dolzarbligi." dan boshlanadi.
- "Ushbu kurs ishi ... bag'ishlangan" deb yozilmaydi.
- Kurs ishida TADQIQOT qilinmaydi: "tadqiqotning ilmiy ahamiyati",
  "tadqiqot natijalari" kabi iboralar ishlatilmaydi.
- "Mavzuning o'rganilganlik darajasi" bandi umuman bo'lmaydi.
- Vazifalar "Kurs ishining vazifalari:" deb emas, "Kurs ishining
  maqsadidan kelib chiqib quyidagi vazifalar belgilab olindi:" deb
  beriladi va raqamlanmaydi — tire bilan yoziladi.
- Tarkib bandida rejaning HAQIQIY soni yoziladi va u "xulosa va
  foydalanilgan adabiyotlar ro'yxatidan iborat" deb tugaydi. Ilgari
  matnda "uchta bo'lim" deb yozilar, hujjatda esa to'rtta chiqardi.

Ikki usul:

  `oddiy`    — reja savollardan iborat (mustaqil ishga o'xshaydi):
               Kirish, 1-4 savol, Xulosa, Adabiyotlar.
  `murakkab` — reja boblardan va ularning ichidagi mavzulardan iborat.
"""

import re
from typing import Dict, List

SIMPLE = "oddiy"
COMPLEX = "murakkab"
STYLES = (SIMPLE, COMPLEX)


def normalize(style: str) -> str:
    value = (style or "").strip().lower()
    return value if value in STYLES else COMPLEX


# ─────────────────────────────────────────────── kirish bandlari

_LEAD = {
    "uz": {
        "relevance": "Mavzuning dolzarbligi.",
        "subject": "Kurs ishining predmeti.",
        "object": "Kurs ishining obyekti.",
        "goal": "Kurs ishining maqsadi.",
        "tasks": "Kurs ishining maqsadidan kelib chiqib quyidagi vazifalar "
                 "belgilab olindi:",
        "structure": "Kurs ishining tarkibi.",
    },
    "ru": {
        "relevance": "Актуальность темы.",
        "subject": "Предмет курсовой работы.",
        "object": "Объект курсовой работы.",
        "goal": "Цель курсовой работы.",
        "tasks": "Исходя из цели курсовой работы определены следующие задачи:",
        "structure": "Структура курсовой работы.",
    },
    "en": {
        "relevance": "Relevance of the topic.",
        "subject": "Subject of the course work.",
        "object": "Object of the course work.",
        "goal": "Aim of the course work.",
        "tasks": "The following tasks were set to achieve this aim:",
        "structure": "Structure of the course work.",
    },
}

# Qaysi usulda qaysi band bo'ladi. "o'rganilganlik darajasi" hech
# qaysisida yo'q — ustoz uni butunlay chizib tashlagan.
_ORDER = {
    SIMPLE: ("goal", "tasks", "structure"),
    COMPLEX: ("subject", "object", "goal", "tasks", "structure"),
}


def lead(language: str, key: str) -> str:
    return _LEAD.get(language, _LEAD["uz"]).get(key, "")


def point_keys(style: str) -> tuple:
    """Kirishdagi bandlar ketma-ketligi — raqamsiz."""
    return _ORDER[normalize(style)]


def point_labels(language: str, style: str) -> List[str]:
    """Bandlarning sarlavhalari, hujjatda yoziladigan ko'rinishda."""
    return [lead(language, key) for key in point_keys(style)]


_UZ_NUMBERS = ("bitta", "ikkita", "uchta", "to'rtta", "beshta", "oltita",
               "yettita", "sakkizta", "to'qqizta", "o'nta")
_EN_NUMBERS = ("one", "two", "three", "four", "five", "six", "seven",
               "eight", "nine", "ten")


def _number_word(count: int, language: str) -> str:
    """Sonni so'z bilan: "beshta savol" — akademik matnda shunday yoziladi."""
    if language == "ru":
        return str(count)
    words = _EN_NUMBERS if language == "en" else _UZ_NUMBERS
    if 1 <= count <= len(words):
        return words[count - 1]
    return str(count) if language == "en" else f"{count} ta"


def structure_sentence(language: str, style: str, count: int) -> str:
    """Tarkib bandining matni — reja soni haqiqatga mos bo'lsin.

    Ilgari bu jumla AI tomonidan yozilar va "uchta bo'lim" deb chiqar,
    hujjatda esa to'rtta bo'lardi. Endi son kod tomonidan qo'yiladi.

    Jumla bitta qatordan iborat bo'lsa varaqda juda quruq ko'rinardi,
    shuning uchun ishning qaysi qismida nima yoritilgani ham qisqacha
    aytib o'tiladi. Rejaning o'zi bu yerda takrorlanmaydi — u
    mundarijada turibdi.
    """
    count = max(1, int(count or 1))
    number = _number_word(count, language)

    if normalize(style) == SIMPLE:
        if language == "ru":
            return (f"Курсовая работа состоит из введения, {number} вопросов, "
                    "заключения с предложениями и списка использованной "
                    "литературы. Во введении раскрыты актуальность темы, её "
                    "цель и вытекающие из неё задачи. В вопросах тема "
                    "рассматривается последовательно, теоретические подходы "
                    "сопоставляются с практическими данными, приводятся "
                    "статистические показатели и примеры. В заключении "
                    "обобщены результаты работы и даны практические "
                    "рекомендации.")
        if language == "en":
            return (f"The course work consists of an introduction, {number} "
                    "questions, a conclusion with proposals and a list of "
                    "references. The introduction sets out the relevance of "
                    "the topic, its aim and the tasks that follow from it. "
                    "The questions examine the topic step by step, comparing "
                    "theoretical approaches with practical data, statistics "
                    "and examples. The conclusion summarises the results of "
                    "the work and offers practical recommendations.")
        return (f"Kurs ishi kirish, {number} savol, xulosa va takliflar hamda "
                "foydalanilgan adabiyotlar ro'yxatidan iborat. Kirish "
                "qismida mavzuning dolzarbligi, maqsadi va shu maqsaddan "
                "kelib chiqadigan vazifalar yoritilgan. Savollarda mavzu "
                "bosqichma-bosqich tahlil qilinib, nazariy qarashlar amaliy "
                "ma'lumotlar, statistik ko'rsatkichlar va misollar bilan "
                "solishtirilgan. Xulosa va takliflar qismida ish natijalari "
                "umumlashtirilib, amaliy tavsiyalar berilgan.")

    if language == "ru":
        return (f"Курсовая работа состоит из введения, {number} глав, "
                "заключения и списка использованной литературы. Во введении "
                "раскрыты актуальность темы, её цель и вытекающие из неё "
                "задачи. Главы разделены на подразделы: тема раскрывается "
                "последовательно — от теоретических основ к практическому "
                "анализу и предложениям. В заключении обобщены результаты "
                "работы и даны практические рекомендации.")
    if language == "en":
        return (f"The course work consists of an introduction, {number} "
                "chapters, a conclusion and a list of references. The "
                "introduction sets out the relevance of the topic, its aim "
                "and the tasks that follow from it. The chapters are divided "
                "into subsections and develop the topic step by step, from "
                "its theoretical foundations to practical analysis and "
                "proposals. The conclusion summarises the results of the "
                "work and offers practical recommendations.")
    return (f"Kurs ishi kirish, {number} bob, xulosa va foydalanilgan "
            "adabiyotlar ro'yxatidan iborat. Kirish qismida mavzuning "
            "dolzarbligi, maqsadi va shu maqsaddan kelib chiqadigan "
            "vazifalar yoritilgan. Boblar o'z mavzulariga bo'lingan bo'lib, "
            "ularda mavzu nazariy asoslardan amaliy tahlilga qarab "
            "bosqichma-bosqich ochib berilgan. Xulosa qismida ish natijalari "
            "umumlashtirilib, amaliy takliflar berilgan.")


# ─────────────────────────────────────────── promptga qo'yiladigan qoida

def intro_rule(language: str, style: str) -> str:
    """Kirish matni uchun qat'iy qoida — ustoz tuzatishlaridan."""
    if language == "ru":
        return (
            "ПРАВИЛА ВВЕДЕНИЯ (строго):\n"
            "- Не пишите «данная курсовая работа посвящена…».\n"
            "- В курсовой работе НЕ проводится исследование: не пишите "
            "«научная значимость исследования», «результаты исследования», "
            "«объект исследования».\n"
            "- Не пишите о степени изученности темы.\n"
            "- Текст — сплошное изложение актуальности темы, без "
            "заголовков и без нумерации."
        )
    if language == "en":
        return (
            "INTRODUCTION RULES (strict):\n"
            "- Do not write \"this course work is devoted to…\".\n"
            "- A course work carries out NO research: never write "
            "\"scientific significance of the research\", \"research "
            "results\" or \"object of the research\".\n"
            "- Do not write about how well the topic has been studied.\n"
            "- Continuous prose on why the topic matters, no headings, "
            "no numbering."
        )
    return (
        "KIRISH QOIDALARI (qat'iy):\n"
        "- \"Ushbu kurs ishi ... bag'ishlangan\" deb YOZMANG.\n"
        "- Kurs ishida TADQIQOT qilinmaydi: \"tadqiqotning ilmiy "
        "ahamiyati\", \"tadqiqot natijalari\", \"tadqiqot obyekti\" kabi "
        "iboralarni ISHLATMANG.\n"
        "- Mavzuning o'rganilganlik darajasi haqida yozmang.\n"
        "- Matn mavzu nega dolzarbligi haqida yaxlit bayon bo'lsin — "
        "sarlavhasiz va raqamlashsiz."
    )


def points_rule(language: str, style: str) -> str:
    """Kirish bandlari uchun qoida — qaysi band nima yozishini aytadi."""
    keys = point_keys(style)
    lines = []
    for key in keys:
        if key == "goal":
            lines.append("goal — kurs ishining maqsadi, bitta-ikkita jumla")
        elif key == "tasks":
            lines.append("tasks — maqsaddan kelib chiqadigan 3-4 vazifa, "
                         "har biri alohida qator, RAQAMSIZ")
        elif key == "subject":
            lines.append("subject — kurs ishining predmeti, bitta jumla")
        elif key == "object":
            lines.append("object — kurs ishining obyekti, bitta jumla")
    lines.append("structure — YOZMANG, uni kod o'zi qo'yadi")

    head = {
        "ru": "Пункты введения (только содержание, без заголовков):",
        "en": "Introduction points (content only, no headings):",
    }.get(language, "Kirish bandlari (faqat mazmun, sarlavhasiz):")
    return head + "\n- " + "\n- ".join(lines)


# ──────────────────────────────────────────────── Prezident snoskasi

def _flat(text: str) -> str:
    """Solishtirish uchun: kichik harf, apostrofsiz, bitta bo'shliq."""
    value = re.sub(r"[\u2018\u2019\u02bb\u02bc\u2032'`\u00b4]", "", str(text or "").lower())
    return re.sub(r"[^\w\s]+", " ", value)


def strip_echo(text: str, language: str, key: str) -> str:
    """Band matnidan uning o'z sarlavhasini olib tashlaydi.

    Sarlavhani hujjatga kod yozadi ("Kurs ishining predmeti."), AI esa
    matnni ko'pincha o'sha ibora bilan boshlaydi. Natijada varaqda
    "Kurs ishining predmeti. Kurs ishining predmeti O'zbekistonda..."
    bo'lib chiqar — ustoz aynan shu takrorni chizib tashlagan.
    """
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return ""

    label = lead(language, key)
    # Nuqtasiz variant ham kerak: AI sarlavhani gapga qo'shib yuboradi —
    # "Kurs ishining predmeti O'zbekistonda ... jarayonidir."
    variants = sorted({label, label.rstrip(".:")}, key=len, reverse=True)
    flat_value = _flat(value)
    for variant in variants:
        flat_variant = _flat(variant).strip()
        if flat_variant and flat_value.startswith(flat_variant):
            words = len(flat_variant.split())
            value = " ".join(value.split()[words:]).lstrip(" \u2014\u2013-:.,")
            break

    return value[:1].upper() + value[1:] if value else ""


# AI javobi ro'yxat bo'lib kelib, matnga aylantirilganda qoladigan iz:
# "['Birinchi vazifa.', 'Ikkinchi vazifa.']". Varaqda aynan shu
# ko'rinishda — qavs va qo'shtirnoqlari bilan, bitta qatorda — chiqib
# qolgan edi.
_LIST_REPR = re.compile(r"^\[\s*['\"].*['\"]\s*\]$", re.S)


def clean_tasks(text) -> list:
    """Vazifalar ro'yxati — har biri alohida qatorda, raqamsiz.

    Ustoz vazifalarni raqamlamaslikni va ularni bir-birining ostiga
    yozishni talab qilgan. AI esa ularni uch xil ko'rinishda beradi:
    ro'yxat sifatida, qatorma-qator matn sifatida yoki hammasini
    bitta qatorga "1. ... 2. ..." qilib. Uchalasi ham shu yerda bir
    ko'rinishga keltiriladi.
    """
    if isinstance(text, (list, tuple)):
        items = [str(item) for item in text]
    else:
        value = str(text or "").strip()
        if _LIST_REPR.match(value):
            # Ro'yxat matnga aylantirilgan bo'lsa — qaytarib ajratamiz.
            try:
                import ast
                parsed = ast.literal_eval(value)
                items = [str(item) for item in parsed]
            except (ValueError, SyntaxError):
                items = [value]
        else:
            items = [value]

    lines = []
    for chunk in items:
        value = str(chunk or "").replace(";", "\n")
        # AI ba'zan hammasini bitta qatorga yozadi: "1. ... 2. ... 3. ...".
        # Shunda raqamlarning o'zi ajratuvchi bo'ladi.
        if "\n" not in value.strip():
            value = re.sub(r"\s+(?=\d+\s*[.)]\s)", "\n", value)

        for raw in value.splitlines():
            item = raw.strip().lstrip("-\u2014\u2013\u2022 ").strip("'\"")
            item = re.sub(r"^\d+\s*[.)]\s*", "", item).strip(" .;")
            if item:
                lines.append(item)
    return lines


def president_footnote(source: str, language: str = "uz") -> str:
    """Prezident so'zlariga snoska — to'liq ko'rinishda.

    Ustoz qisqa yozilgan snoskani to'g'rilab, to'liq ism, murojaat
    qilingan palata, sana va manba havolasini talab qilgan.
    """
    value = (source or "").strip()
    if value and len(value) > 60 and any(ch.isdigit() for ch in value):
        return value

    if language == "ru":
        return ("Мирзиёев Ш.М. Послание Президента Республики Узбекистан "
                "Олий Мажлису. — Ташкент, 2025 г. — www.president.uz")
    if language == "en":
        return ("Mirziyoyev Sh.M. Address of the President of the Republic "
                "of Uzbekistan to the Oliy Majlis. — Tashkent, 2025. — "
                "www.president.uz")
    return ("Mirziyoyev Sh.M. O'zbekiston Respublikasi Prezidentining Oliy "
            "Majlis Qonunchilik palatasi va Senatiga Murojaatnomasi. — "
            "Toshkent, 2025-yil. — www.president.uz")


def footnote_rule(language: str = "uz") -> str:
    """Snoska qanday yozilishi — promptga qo'yiladi."""
    if language == "ru":
        return ("Ссылка пишется полностью: фамилия и инициалы Президента, "
                "название послания, палата, город, год и адрес сайта.")
    if language == "en":
        return ("The citation must be complete: the President's surname and "
                "initials, the title of the address, the chamber, city, year "
                "and the web address.")
    return ("Snoska to'liq yozilsin: Prezidentning familiyasi va bosh "
            "harflari, murojaatnoma nomi, qaysi palataga qilingani, shahar, "
            "yil va sayt manzili.")
