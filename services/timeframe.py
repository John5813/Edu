"""Hozirgi yilni hujjat va taqdimot promptlariga uzatadi.

Model o'qitilgan ma'lumot ma'lum bir sanada tugaydi, shuning uchun u
"hozirgi yil" deb o'sha sanani oladi: 2026-yilda yaratilgan kurs ishida
diagramma 2022-2023 yillarda tugab qolardi, mijoz esa buni darhol
ko'rardi. Prompt ichida sana aytilsa, model uni ishlatadi.

Shu sababli yil hech qayerda kodga yozilmaydi — hammasi shu moduldan
olinadi. Kelasi yil kelganda hech narsani o'zgartirish shart emas.
"""

from datetime import date

# Tarixiy qatorning uzunligi: diagrammada odatda to'rtta nuqta ko'rsatiladi.
HISTORY_SPAN = 4
# Prognoz necha yilga qilinadi.
FORECAST_SPAN = 3


def today() -> date:
    return date.today()


def current_year() -> int:
    return today().year


def last_full_year() -> int:
    """Statistika to'liq bo'lgan oxirgi yil.

    Joriy yil hali tugamagan — uning yakuniy statistikasi yo'q. O'tgan yil natijalari esa odatda fevral–mart
    oylarida e'lon qilinadi: martgacha ikki yil orqaga suriladi. (Ilgari martdan keyin joriy yil olinardi va
    model 2026-yil noyabrida «2026-yil yakunlari» raqamlarini to'qirdi.)
    """
    now = today()
    return now.year - 2 if now.month < 3 else now.year - 1


def history_years(count: int = HISTORY_SPAN) -> list:
    """Tahlil uchun oxirgi yillar ketma-ketligi: [..., o'tgan, oxirgi]."""
    end = last_full_year()
    return list(range(end - max(count, 1) + 1, end + 1))


def forecast_years(count: int = FORECAST_SPAN) -> list:
    """Prognoz yillari — joriy yildan boshlanadi."""
    start = current_year()
    return list(range(start, start + max(count, 1)))


_MONTHS = {
    "uz": ("yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul",
           "avgust", "sentabr", "oktabr", "noyabr", "dekabr"),
    "ru": ("январь", "февраль", "март", "апрель", "май", "июнь", "июль",
           "август", "сентябрь", "октябрь", "ноябрь", "декабрь"),
    "en": ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"),
}


def today_text(language: str = "uz") -> str:
    """Bugungi sana — promptda aytiladigan ko'rinishda."""
    language = "ru" if language == "kk" else language      # qozoqcha hujjat: ruscha yo'l (kazakh_doc.py)
    now = today()
    month = _MONTHS.get(language, _MONTHS["uz"])[now.month - 1]
    if language == "ru":
        return f"{now.day} {month} {now.year} года"
    if language == "en":
        return f"{month} {now.day}, {now.year}"
    return f"{now.year}-yil {month}"


def year_rule(language: str = "uz") -> str:
    """Promptga qo'shiladigan qoida: yillar bugungi kundan kelib chiqsin."""
    language = "ru" if language == "kk" else language      # qozoqcha hujjat: ruscha yo'l (kazakh_doc.py)
    now = current_year()
    last = last_full_year()
    history = history_years()
    forecast = forecast_years()
    span = f"{history[0]}-{history[-1]}"
    ahead = f"{forecast[0]}-{forecast[-1]}"

    if language == "ru":
        return (
            f"СЕГОДНЯ {today_text('ru')}. Текущий год — {now}, он ещё не закончился: его итоговых цифр нет.\n"
            f"- Каждое число — только то, что ты точно знаешь или что дано в разделе ФАКТЫ; рядом всегда год "
            f"(«по данным за 2023 год»). Старые цифры не выдавай за «нынешнее состояние».\n"
            f"- Не выдумывай цифры за годы, данных о которых у тебя нет: ряд заканчивается последним годом, за "
            f"который данные есть (лучше всего {last}, например {span}, если он есть в ФАКТАХ).\n"
            f"- Прогноз — на {ahead} годы и всегда помечен словом «прогноз».\n"
            f"- Не выдумывай названия произведений, даты рождения и смерти, награды и цитаты: если не уверен — "
            f"не пиши. Никогда не давай «примерную цитату»."
        )
    if language == "en":
        return (
            f"TODAY IS {today_text('en')}. The current year is {now} and it is not over: it has no final figures.\n"
            f"- Every number is only what you know for sure or what the FACTS section gives; always write its year "
            f"(\"according to 2023 data\"). Never present old figures as the \"current state\".\n"
            f"- Do not invent figures for years you have no data for: a series ends at the latest year with real "
            f"data (ideally {last}, e.g. {span}, if FACTS give it).\n"
            f"- Forecast for {ahead}, always labelled \"forecast\".\n"
            f"- Never invent titles of works, birth and death dates, awards or quotes: if unsure, leave them out. "
            f"Never give an \"approximate quote\"."
        )
    return (
        f"BUGUN {today_text('uz')}. Joriy yil — {now}, u hali tugamagan: uning yakuniy raqamlari yo'q.\n"
        f"- Har raqam — faqat sen aniq bilgan yoki FAKTLAR bo'limida berilgan qiymat; yonida doim yili "
        f"tursin («2023-yil ma'lumotiga ko'ra»). Eski raqamni «hozirgi holat» deb berma.\n"
        f"- Ma'lumoti yo'q yillarga raqam to'qima: qator ma'lumot bor oxirgi yil bilan tugasin (eng yaxshisi "
        f"{last}-yil, masalan {span}, agar FAKTLARda bo'lsa).\n"
        f"- Prognoz {ahead}-yillarga qilinadi va doim «prognoz» deb belgilanadi.\n"
        f"- Asar nomlari, tug'ilgan va vafot sanalari, mukofotlar va iqtiboslarni to'qima: aniq bilmasang — "
        f"yozma. Hech qachon «taxminiy iqtibos» berma."
    )


def year_headers(language: str = "uz") -> list:
    """Jadval ustunlari uchun zaxira sarlavhalar — yillari bugungidan."""
    language = "ru" if language == "kk" else language      # qozoqcha hujjat: ruscha yo'l (kazakh_doc.py)
    previous, last = last_full_year() - 1, last_full_year()
    first = {"ru": "Показатель", "en": "Indicator"}.get(language, "Ko'rsatkich")
    change = {"ru": "Изменение", "en": "Change"}.get(language, "O'zgarish")
    return [first, str(previous), str(last), change]


def prose_year_rule(language: str = "uz") -> str:
    """Oddiy matn bo'limlari (kirish, asosiy qism, xulosa) uchun yil qoidasi.

    `year_rule` ma'lumot qatorlari uchun: u "ma'lumot oxirgi to'liq yilgacha,
    prognoz kelgusi yillarga" deydi. Matn bo'limlariga qo'yilganda model har
    bo'limga "2023-2026 yillarda tadqiqotlar..., kelgusi 2026-2028 yillarda..."
    deb yozib yuborardi — adabiyot yoki falsafa mavzusida ham, o'ylab topilgan.
    """
    language = "ru" if language == "kk" else language      # qozoqcha hujjat: ruscha yo'l (kazakh_doc.py)
    now = current_year()
    if language == "ru":
        return (f"Сегодня {today_text('ru')}. Годы указывайте только для точных исторических фактов. "
                f"Не выдумывайте общих утверждений вроде «в {now - 3}-{now} годах исследования показали…» "
                f"или «в ближайшие годы…» — если нет точного факта, пишите без дат.")
    if language == "en":
        return (f"Today is {today_text('en')}. Give years only for precise historical facts. "
                f"Do not invent generic claims such as \"studies in {now - 3}-{now} showed...\" or "
                f"\"in the coming years...\" — without an exact fact, write without dates.")
    return (f"Bugun {today_text('uz')}. Yilni faqat aniq tarixiy fakt uchun yozing. "
            f"\"{now - 3}-{now} yillarda tadqiqotlar ... ko'rsatdi\" yoki \"kelgusi yillarda ...\" kabi "
            f"umumiy, o'ylab topilgan gaplarni yozmang — aniq fakt bo'lmasa, sanasiz yozing.")
