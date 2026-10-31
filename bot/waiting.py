"""Kutish paytidagi qiziqarli ma'lumotlar va "jarayon tirik" xabari.

Server band bo'lsa (bir vaqtda ko'p mijoz) og'ir ish navbatda kutadi (`services/heavy_gate.py`). Mijozga navbat
haqida hech narsa aytilmaydi — holat xabari belgilangan oraliqda yangi qiziqarli ma'lumot bilan yangilanib
turadi, shunda jarayon to'xtamagani bilinadi.
"""
import asyncio
import contextlib
import random
from typing import Callable, List, Optional

SPINNERS = ("◐", "◓", "◑", "◒")

FACTS = {
    "uz": [
        "Quyosh nuri Yerga taxminan 8 daqiqa 20 soniyada yetib keladi.",
        "Ahtapotning uchta yuragi bor, qoni esa ko‘kimtir rangda bo‘ladi.",
        "Asalarilar raqs orqali oziq manzilini bir-biriga bildiradi.",
        "Odam miyasi tanadagi energiyaning taxminan 20 foizini sarflaydi.",
        "Venerada bir kun bir yildan uzunroq davom etadi.",
        "«Algoritm» so‘zi buyuk olim Muhammad al-Xorazmiy nomidan kelib chiqqan.",
        "Mirzo Ulug‘bek rasadxonasida 1018 ta yulduzning o‘rni aniqlangan.",
        "Ibn Sinoning «Tib qonunlari» Yevropa universitetlarida bir necha asr darslik bo‘lgan.",
        "Samarqand 2700 yildan ortiq tarixga ega — u qadimiy Rim bilan tengdosh.",
        "Zarafshon daryosi nomi «oltin sochuvchi» degan ma’noni bildiradi.",
        "Yorug‘lik bir soniyada taxminan 300 000 km yo‘l bosadi.",
        "Ko‘k kit — Yer yuzida yashagan eng katta hayvon.",
        "Inson tanasidagi 206 ta suyakning qariyb yarmi qo‘l va oyoq panjalarida.",
        "Marsdagi Olimp tog‘i Everestdan qariyb 2,5 marta baland.",
        "Ba’zi bambuk turlari bir kunda 90 sm gacha o‘sadi.",
        "Okeandagi mikroskopik suv o‘tlari Yerdagi kislorodning qariyb yarmini beradi.",
        "Birinchi kompyuter dasturini 1843 yilda Ada Lavleys yozgan.",
    ],
    "ru": [
        "Солнечный свет достигает Земли примерно за 8 минут 20 секунд.",
        "У осьминога три сердца, а его кровь имеет голубоватый цвет.",
        "Пчёлы сообщают друг другу о местоположении пищи с помощью танца.",
        "Мозг человека расходует около 20 процентов энергии организма.",
        "На Венере один день длится дольше, чем один год.",
        "Слово «алгоритм» происходит от имени учёного Мухаммада аль-Хорезми.",
        "В обсерватории Улугбека определили положение 1018 звёзд.",
        "«Канон врачебной науки» Ибн Сины несколько веков был учебником в университетах Европы.",
        "Самарканду больше 2700 лет — он ровесник древнего Рима.",
        "Название реки Зеравшан означает «рассыпающая золото».",
        "Свет проходит около 300 000 км за одну секунду.",
        "Синий кит — самое большое животное, когда-либо жившее на Земле.",
        "Почти половина из 206 костей человека находится в кистях и стопах.",
        "Гора Олимп на Марсе почти в 2,5 раза выше Эвереста.",
        "Некоторые виды бамбука вырастают до 90 см за сутки.",
        "Микроскопические водоросли океана дают почти половину кислорода Земли.",
        "Первую компьютерную программу написала Ада Лавлейс в 1843 году.",
    ],
    "en": [
        "Sunlight takes about 8 minutes and 20 seconds to reach Earth.",
        "An octopus has three hearts, and its blood is bluish.",
        "Bees use a dance to tell each other where food can be found.",
        "The human brain uses about 20 percent of the body's energy.",
        "A day on Venus lasts longer than one Venusian year.",
        "The word “algorithm” comes from the name of the scholar Muhammad al-Khwarizmi.",
        "Ulugh Beg's observatory in Samarkand charted the positions of 1018 stars.",
        "Avicenna's “Canon of Medicine” was a university textbook in Europe for centuries.",
        "Samarkand is more than 2,700 years old — as old as ancient Rome.",
        "The name of the Zarafshan river means “gold-spreading”.",
        "Light travels about 300,000 km in one second.",
        "The blue whale is the largest animal that has ever lived on Earth.",
        "Almost half of the 206 bones in the human body are in the hands and feet.",
        "Olympus Mons on Mars is almost 2.5 times taller than Everest.",
        "Some kinds of bamboo grow up to 90 cm in a single day.",
        "Microscopic ocean algae produce about half of Earth's oxygen.",
        "Ada Lovelace wrote the first computer program in 1843.",
    ],
}


def facts(lang: str) -> List[str]:
    """Tilga mos ma'lumotlar, aralashtirilgan (har buyurtmada boshqa tartib)."""
    items = list(FACTS.get((lang or "uz").split("-")[0]) or FACTS["uz"])
    random.shuffle(items)
    return items


@contextlib.asynccontextmanager
async def keep_alive(message, text: Callable[[str, str], str], lang: str, every: float = 8.0):
    """Ichidagi ish davomida `message` ni har `every` soniyada `text(spinner, fakt)` bilan yangilaydi.
    Xabarni tahrirlab bo'lmasa — jim o'tadi (asosiy ish to'xtamaydi)."""
    pool = facts(lang)

    async def loop():
        n = 0
        while True:
            await asyncio.sleep(every)
            n += 1
            with contextlib.suppress(Exception):
                await message.edit_text(text(SPINNERS[n % len(SPINNERS)], pool[n % len(pool)]), parse_mode="HTML")

    task: Optional[asyncio.Task] = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
