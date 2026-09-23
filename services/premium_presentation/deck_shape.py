"""Taqdimotning shakli MAVZUDAN kelib chiqsin.

Muammo shunda ediki, biz yozgan qoidalarning o'zi modelga prompt
bo'lib ketardi. Masalan "har uch slaydning birida diagramma bo'lsin"
degan qoida tufayli adabiyot mavzusida ham, matematikada ham model
statistika o'ylab topib chizardi — mavzuga umuman kerak bo'lmagan
raqamlar, prognozlar va yillar paydo bo'lardi. "Kamida oltita turli
kategoriya ishlatilsin" degan kvota esa mantiqan ketma-ket kelishi
kerak bo'lgan ikki ro'yxatni sun'iy ravishda ajratib yuborardi.

Ya'ni qoidalar mazmunni boshqarib qo'ygan edi. Aslida teskarisi
bo'lishi kerak: mavzu qanday shakl talab qilsa — shunday bo'lsin.

Shuning uchun kvotalar olib tashlandi, o'rniga mavzu OILASI aniqlanadi
va har oilaga o'ziga xos yo'riqnoma beriladi. Tarix taqdimoti vaqt
o'qi va sabab-oqibat bilan ochiladi; matematikada ta'rif, isbot va
misol bo'ladi; adabiyotda iqtibos va matn tahlili. Statistika esa
faqat mavzuning o'zida haqiqiy raqam bo'lganda paydo bo'ladi.
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
            "Raqam — bu yerda SANA va tarixiy miqdor (qo'shin soni, "
            "hudud maydoni). Foiz va o'sish diagrammasi tarixga deyarli "
            "kerak emas — prognoz esa umuman yozilmaydi."),
    },
    "aniq": {
        "name": "aniq fanlar (matematika, fizika, informatika, texnika)",
        "shape": (
            "- Mantiq zanjiri asosiy: ta'rif → xossa → isbot yoki\n"
            "  keltirib chiqarish → misol → qo'llanilishi.\n"
            "- FORMULA alohida `formula` blokida, yirik ko'rsatilsin;\n"
            "  ostida belgilar nimani bildirishi yozilsin.\n"
            "- KAMIDA BITTA ISHLANGAN MISOL bo'lsin: `misol` bloki —\n"
            "  masala sharti, qadamma-qadam yechim va javob.\n"
            "  Tushunchani faqat ta'rif bilan qoldirmang.\n"
            "- Tasnif va shartlar uchun jadval qulay."),
        "numbers": (
            "STATISTIKA BU YERDA KERAK EMAS. Diagramma faqat funksiya "
            "grafigi yoki o'lchov natijasi bo'lsa mazmunli. "
            "\"Foydalanish o'sishi\", \"bozor ulushi\" kabi o'ylab "
            "topilgan raqamlar mavzuni buzadi."),
    },
    "tabiiy": {
        "name": "tabiiy fanlar (biologiya, kimyo, geografiya, ekologiya)",
        "shape": (
            "- JARAYON va TUZILMA asosiy: bosqichlar, tarkibiy qismlar,\n"
            "  tasnif, aylanish (sikl).\n"
            "- Turlar va guruhlarni taqqoslash uchun jadval qulay.\n"
            "- Sabab va oqibat (masalan omil → natija) yaxshi ishlaydi.\n"
            "- Misol aniq bo'lsin: qaysi organizm, qaysi modda, qayerda."),
        "numbers": (
            "Raqam faqat haqiqiy o'lchov bo'lsa yoziladi (harorat, "
            "miqdor, tarkib foizi) — uni O'YLAB TOPMANG. Ishonchingiz "
            "komil bo'lmasa raqam o'rniga sifat tavsifini bering; "
            "prognoz diagrammasi bu yerda kerak emas."),
    },
    "ijtimoiy": {
        "name": "ijtimoiy fanlar (iqtisodiyot, huquq, sotsiologiya, siyosat)",
        "shape": (
            "- Tushuncha → maqsad → tarkib → vositalar → natija zanjiri\n"
            "  tabiiy ketma-ketlik.\n"
            "- Ko'rsatkich va qiyoslash shu yerda o'rinli.\n"
            "- Hisob formulasi bo'lsa (YIM, inflyatsiya,\n"
            "  rentabellik) uni `formula` blokida ko'rsating va\n"
            "  bitta raqamli misol bilan hisoblab bering.\n"
            "- Qonun, hujjat va institutlar nomi aniq ko'rsatilsin.\n"
            "- Muammo va yechim juftligi kuchli ishlaydi."),
        "numbers": (
            "Raqam o'rinli, lekin FAQAT siz ishonadigan haqiqiy "
            "ko'rsatkich bo'lsa. Kelajak prognozini o'ylab topmang — "
            "u taqdimotni ishonchsiz qiladi."),
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
            "DIAGRAMMA VA STATISTIKA YOZMANG. \"Asarning mashhurligi "
            "foizi\" kabi raqamlarni o'ylab topmang — ular soxta "
            "chiqadi. Prognoz ham yo'q. Sana faqat asar yozilgan yil "
            "yoki muallif umri kabi aniq faktda bo'ladi."),
    },
    "amaliy": {
        "name": "amaliy sohalar (pedagogika, psixologiya, tibbiyot, menejment)",
        "shape": (
            "- USUL va QADAM asosiy: nima qilinadi, qanday tartibda,\n"
            "  qanday natija kutiladi.\n"
            "- Real misol va vaziyat tahlili juda qimmatli.\n"
            "- Usullarni jadvalda taqqoslash qulay.\n"
            "- Muammo → sabab → tavsiya zanjiri tabiiy."),
        "numbers": (
            "Raqam faqat haqiqiy tadqiqot natijasi bo'lsa yoziladi va "
            "manbasi aytiladi. Aks holda usulni misol bilan "
            "tushuntiring — o'ylab topilgan foiz ishonchni yo'qotadi."),
    },
    "umumiy": {
        "name": "umumiy",
        "shape": (
            "- Mavzuni o'zi talab qilgan tartibda oching: tushuncha,\n"
            "  turlari, jarayoni, misoli, ahamiyati.\n"
            "- Har slaydda bitta fikr bo'lsin."),
        "numbers": (
            "Raqamni o'ylab topmang. Ishonchingiz komil bo'lmasa "
            "diagramma o'rniga matn bilan tushuntiring."),
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


def of(topic: str, hint: Optional[str] = None) -> str:
    """Mavzu qaysi oilaga tegishli.

    Avval modelning o'z taxmini (`hint`) qaraladi — u mavzuni to'liq
    o'qigan. Kelmasa yoki tanish bo'lmasa, do'kon tasnifidagi kalit
    so'zlardan foydalaniladi.
    """
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
