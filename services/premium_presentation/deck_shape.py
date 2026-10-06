"""Taqdimotning shakli MAVZUDAN kelib chiqsin.

Mavzu OILASI aniqlanadi va har oilaga o'ziga xos yo'riqnoma beriladi:
tarix vaqt o'qi va sabab-oqibat bilan ochiladi; matematikada ta'rif, isbot
va misol bo'ladi; adabiyotda iqtibos va matn tahlili.

Diagramma haqida: oldingi yo'riqnomalar "statistika bu yerda kerak emas,
diagramma yozmang" deb taqiqlar edi. Model taqiqni "diagrammani butunlay
chetlab o't" deb tushundi va taqdimotlarda halqa, chiziqli va ustunli
diagrammalar yo'qolib ketdi. Endi har oilada diagramma MUMKIN va mazmunga
mos turi ko'rsatiladi. Diagramma raqamlarini slayd yozuvchi model
to'qimaydi: ular alohida Claude chaqiruvidan haqiqiy ma'lumot sifatida
keladi (`chart_data`); ishonchli ma'lumot bo'lmasa diagramma qo'yilmaydi.
"""

import logging
from typing import Dict, Optional

log = logging.getLogger("deck_shape")

# Mavzu oilalari. Har biriga: qaysi bloklar tabiiy, nimadan qochish
# kerak va raqamga munosabat.
_FAMILIES: Dict[str, Dict[str, str]] = {
    "tarix": {
        "name": "tarix",
        "shape": (
            "- Voqealar KETMA-KETLIGI asosiy o'q: vaqt o'qi, bosqichlar,\n"
            "  sabab → voqea → oqibat zanjiri.\n"
            "- Shaxslar, sanalar, joylar va manbalar aniq ko'rsatilsin.\n"
            "- Davrni tushuntiruvchi iqtibos yoki hujjat parchasi yaxshi\n"
            "  ishlaydi.\n"
            "- Taqqoslash: davrdan davrga, yoki ikki hududning holati."),
        "numbers": (
            "Raqam — bu yerda SANA va tarixiy miqdor (aholi, qo'shin, "
            "hudud, ishlab chiqarish). DIAGRAMMA o'rinli: davrlar bo'yicha "
            "miqdor — ustunli yoki chiziqli (X o'qi yillar), tarkib "
            "(millatlar, hududlar, sohalar ulushi) — halqa. "
            "Diagramma ma'lumotini o'zingiz yozmaysiz: reja diagramma deb belgilagan slaydga tayyor, haqiqiy ma'lumot (manbasi bilan) beriladi — uni blokka ko'chirib, izohini yozasiz. Diagramma "
            "o'tmishdagi ma'lumotni ko'rsatadi (kelajak prognozi tarixga "
            "mos emas)."),
    },
    "aniq": {
        "name": "aniq fanlar (matematika, fizika, informatika, texnika)",
        "shape": (
            "- Mantiq zanjiri asosiy: ta'rif → xossa → isbot yoki\n"
            "  keltirib chiqarish → misol → qo'llanilishi.\n"
            "- Bu fanlarda tushuncha odatda formula bilan ta'riflanadi:\n"
            "  formulasi bor tushuncha formulasiz qolmasin — u\n"
            "  `formula` blokida yirik ko'rsatiladi, belgilari\n"
            "  izohlanadi.\n"
            "- Tushunchani misol bilan ko'rsatish mumkin bo'lsa,\n"
            "  `misol` bloki bor: masala sharti, qadamma-qadam\n"
            "  yechim va javob.\n"
            "- Tasnif va shartlar uchun kartochkalar yoki qiyoslash qulay."),
        "numbers": (
            "DIAGRAMMA bu yerda tabiiy: funksiya grafigi — chiziqli "
            "(X–Y o'qli, `calc` bilan formuladan), natijalarni solishtirish "
            "— ustunli, butunning qismlari — halqa. Formuladan hisoblangan "
            "raqam ruxsat etilgan. "
            "Diagramma ma'lumotini o'zingiz yozmaysiz: reja diagramma deb belgilagan slaydga tayyor, haqiqiy ma'lumot (manbasi bilan) beriladi — uni blokka ko'chirib, izohini yozasiz."),
    },
    "tabiiy": {
        "name": "tabiiy fanlar (biologiya, kimyo, geografiya, ekologiya)",
        "shape": (
            "- JARAYON va TUZILMA asosiy: bosqichlar, tarkibiy qismlar,\n"
            "  tasnif, aylanish (sikl).\n"
            "- Turlar va guruhlarni taqqoslash uchun qiyoslash, kartochkalar\n"
            "  yoki diagramma qulay.\n"
            "- Sabab va oqibat (masalan omil → natija) yaxshi ishlaydi.\n"
            "- Misol aniq bo'lsin: qaysi organizm, qaysi modda, qayerda."),
        "numbers": (
            "DIAGRAMMA o'rinli: tarkib foizi (modda, havo, hujayra, "
            "oziq tarkibi) — halqa; turlar yoki ko'rsatkichlarni "
            "solishtirish — ustunli; harorat, miqdor yoki o'sishning "
            "vaqt bo'yicha o'zgarishi — chiziqli. "
            "Diagramma ma'lumotini o'zingiz yozmaysiz: reja diagramma deb belgilagan slaydga tayyor, haqiqiy ma'lumot (manbasi bilan) beriladi — uni blokka ko'chirib, izohini yozasiz."),
    },
    "ijtimoiy": {
        "name": "ijtimoiy fanlar (iqtisodiyot, huquq, sotsiologiya, siyosat)",
        "shape": (
            "- Tushuncha → maqsad → tarkib → vositalar → natija zanjiri\n"
            "  tabiiy ketma-ketlik.\n"
            "- Ko'rsatkich va qiyoslash shu yerda o'rinli.\n"
            "- Hisob formulasi (YIM, inflyatsiya, rentabellik)\n"
            "  mavzuda uchrasa, uni `formula` blokida ko'rsatish\n"
            "  mumkin.\n"
            "- Qonun, hujjat va institutlar nomi aniq ko'rsatilsin.\n"
            "- Muammo va yechim juftligi kuchli ishlaydi."),
        "numbers": (
            "Raqam va DIAGRAMMA o'rinli: tarkib (ulushlar) — halqa, "
            "dinamika — chiziqli (X o'qi yillar), solishtirish — ustunli. "
            "Diagramma ma'lumotini o'zingiz yozmaysiz: reja diagramma deb belgilagan slaydga tayyor, haqiqiy ma'lumot (manbasi bilan) beriladi — uni blokka ko'chirib, izohini yozasiz. Kelajak "
            "prognozi faqat formuladan hisoblansa (`calc`) yoki rasmiy "
            "prognoz sifatida manbasi bilan beriladi."),
    },
    "gumanitar": {
        "name": "gumanitar fanlar (adabiyot, tilshunoslik, san'at, falsafa)",
        "shape": (
            "- MATN va MA'NO asosiy: iqtibos, uning tahlili, obraz,\n"
            "  g'oya, uslub.\n"
            "- Asar yoki ta'limotning tuzilishi, davr konteksti,\n"
            "  ta'siri — yaxshi ochiladigan yo'nalishlar.\n"
            "- Ikki asar, ikki qarash yoki ikki davrni qiyoslash kuchli.\n"
            "- Iqtibos bloki bu yerda eng ta'sirli vosita."),
        "numbers": (
            "Matn va ma'no asosiy, lekin bitta-ikkita DIAGRAMMA "
            "taqdimotni jonlantiradi: asar yoki ijod tarkibi (qismlar, "
            "janrlar ulushi) — halqa; yillar kesimida asarlar soni — "
            "ustunli (faqat aniq fakt bo'lsa); ikki muallif yoki davrni "
            "solishtirish — ustunli. "
            "Diagramma ma'lumotini o'zingiz yozmaysiz: reja diagramma deb belgilagan slaydga tayyor, haqiqiy ma'lumot (manbasi bilan) beriladi — uni blokka ko'chirib, izohini yozasiz. Sana asar yozilgan yil yoki "
            "muallif umri kabi aniq faktda bo'ladi."),
    },
    "amaliy": {
        "name": "amaliy sohalar (pedagogika, psixologiya, tibbiyot, menejment)",
        "shape": (
            "- USUL va QADAM asosiy: nima qilinadi, qanday tartibda,\n"
            "  qanday natija kutiladi.\n"
            "- Real misol va vaziyat tahlili juda qimmatli.\n"
            "- Usullarni qiyoslash yoki diagramma bilan taqqoslash qulay.\n"
            "- Muammo → sabab → tavsiya zanjiri tabiiy."),
        "numbers": (
            "DIAGRAMMA o'rinli: usullar samaradorligini solishtirish — "
            "ustunli, bosqich yoki omillar ulushi — halqa, natija "
            "dinamikasi — chiziqli. "
            "Diagramma ma'lumotini o'zingiz yozmaysiz: reja diagramma deb belgilagan slaydga tayyor, haqiqiy ma'lumot (manbasi bilan) beriladi — uni blokka ko'chirib, izohini yozasiz."),
    },
    "hisob": {
        "name": "hisob-kitob mavzulari (formula, prognoz, statistik hisob, moliyaviy hisob)",
        "shape": (
            "- Mavzu HISOB-KITOB talab qiladi: har tushuncha formula bilan\n"
            "  beriladi, formula esa ISHLANGAN MISOL bilan tasdiqlanadi.\n"
            "- Zanjir: tushuncha → formula (`formula` bloki, belgilari\n"
            "  izohi) → ishlangan misol (`misol` bloki: shart, qadamlar,\n"
            "  javob) → natija diagrammada → xulosa.\n"
            "- Hisob natijasi ko'rsatiladigan joyda DIAGRAMMA bo'lsin va\n"
            "  mazmunga mos turda: o'sish yoki prognoz — chiziqli (X o'qi\n"
            "  vaqt, Y o'qi qiymat), bir necha qiymatni solishtirish —\n"
            "  ustunli, butunning ulushlari — halqa. \"O'sdi\" deb faqat\n"
            "  matn bilan qo'ymang: raqamni ko'rsating.\n"
            "- Raqamlarni O'ZINGIZ hisoblamang: formulani `calc` (diagramma)\n"
            "  yoki `data-calc` (bitta raqam) bilan bering — kod hisoblaydi.\n"
            "- Ko'rsatkich (kpi) ham hisoblangan natijadan olinadi."),
        "numbers": (
            "Formuladan va boshlang'ich qiymatdan kelgan HISOBLANGAN raqam "
            "o'ylab topilgan emas — u ruxsat etilgan. Boshlang'ich qiymat "
            "haqiqiy statistika bo'lmasa, uni \"shartli misol\" deb belgilang. "
            "Haqiqiy statistik faktni (aholi soni, YIM) faqat ishonchli "
            "bilsangiz yozing va manbaga bugungi yoki kelgusi YIL qo'ymang."),
    },
    "umumiy": {
        "name": "umumiy",
        "shape": (
            "- Mavzuni o'zi talab qilgan tartibda oching: tushuncha,\n"
            "  turlari, jarayoni, misoli, ahamiyati.\n"
            "- Har slayd bitta savolga javob bersin va uni to'la\n"
            "  ochsin."),
        "numbers": (
            "DIAGRAMMA o'rinli: ulushlar — halqa, dinamika — chiziqli "
            "(X o'qi vaqt), solishtirish — ustunli. "
            "Diagramma ma'lumotini o'zingiz yozmaysiz: reja diagramma deb belgilagan slaydga tayyor, haqiqiy ma'lumot (manbasi bilan) beriladi — uni blokka ko'chirib, izohini yozasiz."),
    },
}

FAMILY_KEYS = tuple(_FAMILIES)

# Do'kon tasnifidagi fan nomlari qaysi oilaga tushadi.
_BY_SUBJECT = {
    "tarix": "tarix",
    "adabiyot": "gumanitar", "tilshunoslik": "gumanitar",
    "falsafa": "gumanitar", "san'at": "gumanitar", "din": "gumanitar",
    "matematika": "aniq", "fizika": "aniq", "informatika": "aniq",
    "texnika": "aniq",
    "kimyo": "tabiiy", "biologiya": "tabiiy", "geografiya": "tabiiy",
    "ekologiya": "tabiiy", "qishloq xo'jaligi": "tabiiy",
    "iqtisodiyot": "ijtimoiy", "moliya": "ijtimoiy", "huquq": "ijtimoiy",
    "sotsiologiya": "ijtimoiy", "menejment": "ijtimoiy",
    "marketing": "ijtimoiy",
    "pedagogika": "amaliy", "psixologiya": "amaliy", "tibbiyot": "amaliy",
    "sport": "amaliy",
}


# Mavzuning o'zi hisob-kitob so'rasa (formula, prognoz, hisoblash) — fan nomidan
# qat'i nazar "hisob" oilasi: "Demografik hisob-kitoblar" sotsiologiyaga
# tushsa-da, undan kutiladigani formula, ishlangan misol va diagramma.
_CALC_WORDS = (
    "hisob", "formula", "prognoz", "proagnoz", "bashorat", "koeffitsiyent",
    "hisoblash", "statistik tahlil", "regressiya", "korrelyatsiya",
    "расчёт", "расчет", "формул", "прогноз", "вычисл", "коэффициент",
    "calculat", "formula", "forecast", "projection", "computation",
)


def is_calculation(topic: str) -> bool:
    text = (topic or "").lower()
    return any(word in text for word in _CALC_WORDS)


def of(topic: str, hint: Optional[str] = None) -> str:
    """Mavzu qaysi oilaga tegishli.

    Avval modelning o'z taxmini (`hint`) qaraladi — u mavzuni to'liq
    o'qigan. Kelmasa yoki tanish bo'lmasa, do'kon tasnifidagi kalit
    so'zlardan foydalaniladi.
    """
    if is_calculation(topic):
        return "hisob"
    guess = str(hint or "").strip().lower()
    if guess in _FAMILIES:
        return guess
    if guess in _BY_SUBJECT:
        return _BY_SUBJECT[guess]

    try:
        from services import store_taxonomy

        subject = store_taxonomy.classify(topic)
    except Exception as exc:
        log.warning("Fan aniqlanmadi: %s", exc)
        subject = ""
    return _BY_SUBJECT.get(subject, "umumiy")


def guidance(family: str) -> str:
    """Shu oila uchun promptga qo'yiladigan yo'riqnoma."""
    item = _FAMILIES.get(family) or _FAMILIES["umumiy"]
    return (f"MAVZU OILASI: {item['name']}.\n"
            f"Shu oilada mazmun qanday ochiladi:\n{item['shape']}\n\n"
            f"RAQAMGA MUNOSABAT: {item['numbers']}")


def names() -> str:
    """Modeldan so'raladigan oila nomlari ro'yxati."""
    return ", ".join(FAMILY_KEYS)
