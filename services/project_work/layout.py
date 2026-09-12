"""Hujjat necha varoq chiqishini oldindan hisoblaydi va matn hajmini moslaydi.

Ilgari mijoz tanlagan hajm faqat bo'lim matnini ko'paytirar edi, bo'limlar
soniga esa ta'sir qilmasdi. Shu sababli "15-20 varoq" tanlagan mijoz 40 dan
ortiq varoq oladigan hol bo'lgan: har bir qo'shimcha blok o'zi bilan jadval,
diagramma va formulalarni olib kelardi, ular esa matndan ko'ra ko'proq joy
egallaydi.

Bu yerda hujjat elementlarining balandligi satr birligida o'lchanadi:

  • matn — belgilar soni satr kengligiga bo'linadi;
  • jadval — satrlar soni × satr balandligi;
  • diagramma — rasmning haqiqiy nisbati bo'yicha;
  • formula — nomi, rasmi, berilganlari va izohi.

Shundan keyin ikki savolga javob beriladi: tanlangan varoq soniga nechta
blok sig'adi (`blocks_for`), va qolgan joyni to'ldirish uchun har bo'limga
qancha so'z berish kerak (`word_scale`).

O'lchovlar `builder.py` dagi haqiqiy qiymatlardan olingan. Ular o'zgarsa
(masalan sahifa A4 ga o'tkazilsa) shu yerdagi doimiylar ham yangilanishi
kerak.
"""

from typing import List

# ─────────────────────────────────────────────────────── sahifa o'lchovlari
#
# python-docx sukut bo'yicha Letter beradi (8,5 × 11 dyuym) va `builder.py`
# sahifa o'lchamini o'zgartirmaydi.

PAGE_HEIGHT = 11.0
PAGE_WIDTH = 8.5
MARGIN_TOP = 0.79
MARGIN_BOTTOM = 0.79
MARGIN_LEFT = 1.18
MARGIN_RIGHT = 0.39

TEXT_HEIGHT = PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM      # 9,42"
TEXT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT        # 6,93"

BODY_SIZE = 14          # Times New Roman 14pt
LINE_SPACING = 1.5
SMALL_SIZE = 12         # jadval, izoh, berilganlar

# Bir satr balandligi dyuymda. Asosiy matn o'lchovi — qolgan hamma narsa
# shu "satr" birligida o'lchanadi.
LINE_HEIGHT = BODY_SIZE * LINE_SPACING / 72.0               # 0,2917"
LINES_PER_PAGE = TEXT_HEIGHT / LINE_HEIGHT                  # ≈ 32,3

# Times New Roman da belgining o'rtacha kengligi shrift o'lchamining yarmi.
# Mundarija hisobida ham shu koeffitsiyent ishlatiladi.
CHAR_EM = 0.5
CHARS_PER_LINE = TEXT_WIDTH / (BODY_SIZE * CHAR_EM / 72.0)  # ≈ 71

# O'zbekcha o'rtacha so'z: oltita harf va bitta probel.
CHARS_PER_WORD = 7.0
WORDS_PER_LINE = CHARS_PER_LINE / CHARS_PER_WORD            # ≈ 10,2
WORDS_PER_PAGE = WORDS_PER_LINE * LINES_PER_PAGE            # ≈ 329


def _lines(inches: float) -> float:
    return inches / LINE_HEIGHT


# ────────────────────────────────────────────── element balandliklari (satr)

# Bo'lim sarlavhasi: bitta satr va undan keyingi bo'shliq.
HEADING_LINES = 2.0

# Jadval: har satr 12pt matn va katak chekkalari bilan ≈ 0,25". Ustiga
# sarlavha satri (12pt kursiv) va ostiga bo'sh paragraf qo'shiladi.
TABLE_ROW_LINES = _lines(0.25)
TABLE_EXTRA_LINES = 2.5

# Diagramma 5,9" kenglikda qo'yiladi. matplotlib rasmlari `bbox_inches`
# bilan qirqilgani uchun nisbat 0,55-0,65 orasida bo'ladi; o'rtachasini
# olamiz. Ostida raqamli sarlavha, tushuntirish matni va bo'sh paragraf.
CHART_WIDTH = 5.9
CHART_RATIO = 0.60
CHART_LINES = _lines(CHART_WIDTH * CHART_RATIO) + 4.5

# Surat 5,0" kenglikda, nisbati 4:3.
PHOTO_LINES = _lines(5.0 * 0.75) + 2.5

# Formula bloki: nomi, formula rasmi, berilganlar ro'yxati va
# natija/ma'no/xulosa paragraflari.
#
# Formula rasmining balandligi e'lon qilingan figsize dan chiqmaydi:
# `bbox_inches="tight"` bo'sh joyni qirqadi va qisqa formulada kenglik
# balandlikdan ko'ra ko'proq qisqaradi. Tayyor hujjatlarda o'lchanganda
# 3,6" kenglikdagi rasm 1,23" balandlikda chiqadi.
FORMULA_IMAGE = 1.23
FORMULA_LINES = 1.0 + _lines(FORMULA_IMAGE) + 2.0 + 6.0 + 1.0

# Ko'rsatkich kartochkalari — beshta satrli jadval.
CARDS_LINES = 5 * _lines(0.33) + 1.0

# Muqova va mundarija alohida varoqlarda, adabiyotlar ro'yxati ham yangi
# varoqdan boshlanadi.
FRONT_MATTER_PAGES = 2.0
REFERENCES_PAGES = 1.0


def prose_lines(words: float) -> float:
    """Matn necha satr egallashi. Har paragraf oxirgi satrini to'ldirmaydi."""
    paragraphs = 2                       # `_split_into_paragraphs` ikkiga bo'ladi
    return words / WORDS_PER_LINE + paragraphs * 0.5


# ────────────────────────────────────────────────────────── bo'lim o'lchovi

# Har artefaktning jadvali taxminan nechta satrdan iborat. Aniq son modelning
# javobiga bog'liq, lekin tartib o'zgarmaydi.
_TABLE_ROWS = {
    "budget": 7,        # moddalar va yig'indi
    "costs": 7,
    "timeline": 6,
    "risks": 6,
    "marketing": 5,
    "cashflow": 5,
    "breakeven": 9,     # kirish qiymatlari va hisoblanganlari
    "forecast": 5,
    "calc": 7,
    "data": 7,
}


def _artifact_shape(artifact: str) -> tuple:
    """Artefakt qanday elementlar beradi: (jadval satrlari, diagramma, kartochka)."""
    from .specs import (CARD_ARTIFACTS, CHART_ARTIFACTS, DERIVED_TABLE_ARTIFACTS,
                        TABLE_ARTIFACTS)
    if not artifact:
        return 0, False, False
    rows = _TABLE_ROWS.get(artifact, 0) if (
        artifact in TABLE_ARTIFACTS or artifact in DERIVED_TABLE_ARTIFACTS) else 0
    chart = artifact in CHART_ARTIFACTS
    cards = artifact in CARD_ARTIFACTS
    return rows, chart, cards


def overhead_lines(spec) -> float:
    """Bo'limning matnga bog'liq bo'lmagan qismi: sarlavha va artefaktlar.

    Aynan shu qism hajmni boshqarishni qiyinlashtiradi — matnni qisqartirish
    bilan uni kamaytirib bo'lmaydi, faqat blok sonini kamaytirish yordam
    beradi.
    """
    from .specs import FORMULA_COUNTS

    rows, chart, cards = _artifact_shape(spec.artifact)
    total = HEADING_LINES
    if rows:
        total += rows * TABLE_ROW_LINES + TABLE_EXTRA_LINES
    if chart:
        total += CHART_LINES
    if cards:
        total += CARDS_LINES
    return total + FORMULA_LINES * FORMULA_COUNTS.get(spec.artifact or "", 0)


def section_lines(spec, words: float, has_photo: bool = False) -> float:
    """Bitta bo'lim necha satr egallashi — matni va hamma artefaktlari bilan."""
    return overhead_lines(spec) + prose_lines(words) + (PHOTO_LINES if has_photo else 0)


def _base_words(spec) -> float:
    """Spetsifikatsiyadagi "300-380" oralig'ining o'rtasi."""
    try:
        low, high = (float(part) for part in spec.words.split("-"))
        return (low + high) / 2
    except ValueError:
        return 320.0


# Bo'lim matni bundan qisqarmaydi: undan pasti akademik matn emas, qayd.
MIN_WORDS = 150
# Va bundan uzaymaydi: bitta bo'lim uchta varoqni egallab ketmasin.
MAX_WORDS = 900

# Hujjatda ikkita surat bor (`content.PHOTOGRAPHS_PER_WORK`).
PHOTOGRAPHS = 2


def fixed_pages() -> float:
    """Muqova, mundarija va adabiyotlar — matn hajmiga bog'liq emas."""
    return FRONT_MATTER_PAGES + REFERENCES_PAGES

def photographs_for(target_pages: float) -> int:
    """Nechta surat qo'yiladi.

    Ikkita surat 25 varoqli ishda o'rinli, 12 varoqlida esa hujjatning
    o'ndan birini egallaydi va matnga joy qoldirmaydi.
    """
    return PHOTOGRAPHS if target_pages >= 20 else 1


def free_lines(specs: List, target_pages: float) -> float:
    """Artefaktlardan keyin matnga qoladigan joy (satrda)."""
    lines = (target_pages - fixed_pages()) * LINES_PER_PAGE
    lines -= sum(overhead_lines(spec) for spec in specs)
    lines -= PHOTO_LINES * photographs_for(target_pages)
    lines -= len(specs)               # paragraf oxirlari to'lmaydi
    return lines


def _clamp(words: float) -> float:
    return min(MAX_WORDS, max(MIN_WORDS, words))


def estimate(specs: List, scale: float = 1.0, target_pages: float = 25.0) -> float:
    """Berilgan bo'limlar ro'yxati necha varoq chiqishini baholaydi."""
    lines = sum(section_lines(spec, _clamp(_base_words(spec) * scale))
                for spec in specs)
    lines += PHOTO_LINES * photographs_for(target_pages)
    return lines / LINES_PER_PAGE + fixed_pages()


def word_scale(specs: List, target_pages: float) -> float:
    """Bo'limlar shu varoq soniga tushishi uchun matnni qancha o'zgartirish kerak.

    Artefaktlar egallagan joy matn uzunligiga bog'liq emas, shuning uchun
    oddiy ko'paytirish yetarli emas: avval qo'zg'almas qism ayriladi,
    qolgani bo'limlar orasida taqsimlanadi.
    """
    if not specs:
        return 1.0
    wanted = sum(_base_words(spec) for spec in specs)
    if wanted <= 0:
        return 1.0
    available = free_lines(specs, target_pages) * WORDS_PER_LINE
    return max(0.45, min(2.5, available / wanted))


def _base_sections(field_key: str) -> List:
    """Bloklarsiz skelet: kirish, dolzarblik, tuzilma, soha bo'limlari, xulosa."""
    from .specs import FIELDS, sections_for

    # Ro'yxatda yo'q soha uchun o'rta bo'limlarni AI taklif qiladi va ular
    # hali ma'lum emas; biznes skeletida ham uchta o'rta bo'lim bor.
    return sections_for(field_key if field_key in FIELDS else "business", [])


def _block_specs(field_key: str) -> List:
    """Shu sohada haqiqatan hujjatga tushadigan bloklar."""
    from .specs import _BLOCK_SECTIONS, available_blocks
    return [_BLOCK_SECTIONS[key] for key in available_blocks(field_key)]


def min_blocks(field_key: str, target_pages: float) -> int:
    """Tanlangan varoq soniga yetish uchun eng kami nechta blok kerak.

    Matnni cheksiz cho'zib bo'lmaydi: bitta bo'lim ming so'zdan oshsa u
    akademik bo'lim emas, insho bo'lib qoladi. Shuning uchun katta hajm
    tanlangan bo'lsa, uni bo'limlar soni bilan to'ldirish kerak — aks holda
    mijoz "30-40 varoq" deb to'lab, 26 varoq oladi.
    """
    base = _base_sections(field_key)
    # Eng arzon bloklar bilan tekshiramiz: mijoz aynan shularni tanlasa ham
    # hujjat va'da qilingan varoq soniga yetishi kerak.
    blocks = sorted(_block_specs(field_key), key=overhead_lines)
    for count in range(0, len(blocks) + 1):
        if estimate([*base, *blocks[:count]], 2.5, target_pages) >= target_pages:
            return count
    return len(blocks)


def max_blocks(field_key: str, target_pages: float) -> int:
    """Tanlangan varoq soniga nechta mazmun bloki sig'adi.

    Har blok o'zi bilan jadval, diagramma va formulalarni olib keladi, ular
    esa matndan ko'ra ko'proq joy egallaydi. Shuning uchun varoq sonini
    faqat matnni qisqartirish bilan ushlab bo'lmaydi — bloklar sonini ham
    cheklash kerak.

    Bloklar bir xil qimmat emas (zararsizlikda uchta formula bor, ish
    jadvalida bittasi ham yo'q), shuning uchun o'rtacha qiymat olinadi:
    mijoz qaysilarini tanlashini oldindan bilib bo'lmaydi.
    """
    base = _base_sections(field_key)
    # Eng qimmat bloklar bilan tekshiramiz: mijoz qaysilarini tanlashini
    # bilmaymiz, shuning uchun cheklov eng og'ir holatga mo'ljallanadi.
    blocks = sorted(_block_specs(field_key), key=overhead_lines, reverse=True)
    for count in range(len(blocks), 0, -1):
        specs = [*base, *blocks[:count]]
        if estimate(specs, word_scale(specs, target_pages), target_pages) <= target_pages:
            return count
    return 1
