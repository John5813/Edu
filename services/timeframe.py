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

    Yil boshida joriy yil bo'yicha hali ma'lumot yo'q, shuning uchun
    mart oyigacha bir yil orqaga suriladi.
    """
    now = today()
    return now.year - 1 if now.month < 3 else now.year


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
    now = today()
    month = _MONTHS.get(language, _MONTHS["uz"])[now.month - 1]
    if language == "ru":
        return f"{now.day} {month} {now.year} года"
    if language == "en":
        return f"{month} {now.day}, {now.year}"
    return f"{now.year}-yil {month}"


def year_rule(language: str = "uz") -> str:
    """Promptga qo'shiladigan qoida: yillar bugungi kundan kelib chiqsin."""
    now = current_year()
    last = last_full_year()
    history = history_years()
    forecast = forecast_years()
    span = f"{history[0]}-{history[-1]}"
    ahead = f"{forecast[0]}-{forecast[-1]}"

    stale = f"{last - 4}-{last - 3}"

    if language == "ru":
        return (
            f"СЕГОДНЯ {today_text('ru')}. Текущий год — {now}.\n"
            f"- Ряд данных должен заканчиваться {last} годом (например {span}), "
            f"допустимо «по состоянию на {now} год».\n"
            f"- Прогноз — на {ahead} годы.\n"
            f"- Ряд не должен обрываться на {stale} годах, и старые цифры "
            f"нельзя подавать как «нынешнее состояние»."
        )
    if language == "en":
        return (
            f"TODAY IS {today_text('en')}. The current year is {now}.\n"
            f"- The data series must end at {last} (for example {span}); "
            f"\"as of {now}\" is fine.\n"
            f"- Forecast for {ahead}.\n"
            f"- The series must not stop at {stale}, and old figures must not "
            f"be presented as the \"current state\"."
        )
    return (
        f"BUGUN {today_text('uz')}. Joriy yil — {now}.\n"
        f"- Ma'lumot qatori {last}-yil bilan tugasin (masalan {span}); "
        f"\"{now}-yil holatiga\" deb yozish mumkin.\n"
        f"- Prognoz {ahead}-yillarga qilinadi.\n"
        f"- Qator {stale}-yillarda tugab qolmasin va eski raqamlar "
        f"\"hozirgi holat\" sifatida berilmasin."
    )


def year_headers(language: str = "uz") -> list:
    """Jadval ustunlari uchun zaxira sarlavhalar — yillari bugungidan."""
    previous, last = last_full_year() - 1, last_full_year()
    first = {"ru": "Показатель", "en": "Indicator"}.get(language, "Ko'rsatkich")
    change = {"ru": "Изменение", "en": "Change"}.get(language, "O'zgarish")
    return [first, str(previous), str(last), change]
