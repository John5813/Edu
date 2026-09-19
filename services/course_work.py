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


def structure_sentence(language: str, style: str, count: int) -> str:
    """Tarkib bandining matni — reja soni haqiqatga mos bo'lsin.

    Ilgari bu jumla AI tomonidan yozilar va "uchta bo'lim" deb chiqar,
    hujjatda esa to'rtta bo'lardi. Endi son kod tomonidan qo'yiladi.
    """
    count = max(1, int(count or 1))
    if normalize(style) == SIMPLE:
        if language == "ru":
            return (f"Введение, {count} вопроса, заключение и предложения, "
                    "а также список использованной литературы.")
        if language == "en":
            return (f"An introduction, {count} questions, conclusions and "
                    "proposals, and a list of references.")
        return (f"Kirish, {count} ta savol, xulosa va takliflar hamda "
                "foydalanilgan adabiyotlar ro'yxatidan iborat.")

    if language == "ru":
        return (f"Введение, {count} главы, заключение и список "
                "использованной литературы.")
    if language == "en":
        return (f"An introduction, {count} chapters, a conclusion and a "
                "list of references.")
    return (f"Kirish, {count} ta bob, xulosa va foydalanilgan adabiyotlar "
            "ro'yxatidan iborat.")


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
